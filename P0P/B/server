#!/usr/bin/python3
# pylint: disable=relative-beyond-top-level

# THREAD BASED SERVER

import sys
import threading
import socket as net

from socket import socket
from queue import Queue as queue
from typing import Iterable, Tuple, ContextManager

from lib import P0PCommand, P0PPacket


class P0PSession:
    """Metadata structure for P0 Protocol session"""

    _timer: threading.Timer
    _server: "P0PServer"
    _session_number: int
    _session_id: int
    _finished: bool
    _expected_commands: Iterable[P0PCommand]
    _client: Tuple[str, int]

    def __init__(self, server: "P0PServer", client: Tuple[str, int], session_id: int):
        self._server = server
        self._finished = False
        self._expected_commands = [P0PCommand.HELLO]
        self._session_id = session_id
        self._session_number = 0
        self._client = client
        self._timer = None

    def _log(self, message: str, *, session_number: int = None):
        """Send a formatted log to the server's logger containing the
        session ID, session number, and a message"""
        if session_number is None:
            session_number = self._session_number
        if not self._finished:
            self._server._logger.log(
                hex(self._session_id), f"[{session_number}]", message
            )
        else:
            self._server._logger.log(hex(self._session_id), message)

    def process_packet(self, packet: P0PPacket):
        """Process a packet sent from a client, performing correctness
        checks and providing logs for lost and duplicated packets. If
        the packet is correct, a response will be sent back to the
        client, and the transaction will be logged accordingly."""
        if self._timer is not None:
            self._timer.cancel()
        if packet.command not in self._expected_commands:
            self.close()
        else:
            for number in range(self._session_number + 1, packet.session_number):
                self._log("Lost packet!", session_number=number)
            if packet.session_number < self._session_number:
                self._log("Duplicated packet!", session_number=packet.session_number)
            else:
                if packet.command == P0PCommand.HELLO:
                    self._log("Session created")
                    self._expected_commands = [P0PCommand.DATA, P0PCommand.GOODBYE]
                elif packet.command == P0PCommand.DATA:
                    self._log(str(packet.data, encoding="utf-8").strip())
                elif packet.command == P0PCommand.GOODBYE:
                    self._log("GOODBYE from client.")
                    self.close()
                    return
                self._session_number += 1
                commands = {
                    P0PCommand.HELLO: P0PCommand.HELLO,
                    P0PCommand.DATA: P0PCommand.ALIVE,
                    P0PCommand.GOODBYE: P0PCommand.GOODBYE,
                }
                newpacket = P0PPacket(
                    1,
                    commands[packet.command],
                    self._session_number,
                    self._session_id,
                    b"",
                )
                self._server._bind.sendto(
                    bytes(newpacket), net.MSG_DONTWAIT, self._client
                )
                self._timer = threading.Timer(10.0, self.close)
                self._timer.start()

    def close(self):
        """Close the session and clean up any leftover resources"""
        self._finished = True
        self._server._sessions_lock.acquire(blocking=True)
        if self._session_id in self._server._sessions:
            del self._server._sessions[self._session_id]
        self._server._sessions_lock.release()
        packet = P0PPacket(
            1, P0PCommand.GOODBYE, self._session_number, self._session_id, b""
        )
        # Cancel the timer if it exists. This is a no-op if a timer
        # invokes this method.
        if self._timer is not None:
            self._timer.cancel()
        self._server._bind.sendto(bytes(packet), net.MSG_DONTWAIT, self._client)
        self._log("Session closed")


class P0PLogger(threading.Thread):
    """Thread specialized for logging server events"""

    Args = Tuple[object, ...]

    _logqueue: "queue[Args]"
    _sigclose: bool

    def __init__(self) -> None:
        super().__init__(target=self._consume_log)
        self._logqueue = queue()
        self._sigclose = False

    def _consume_log(self):
        """Log event loop"""
        while not self._sigclose or not self._logqueue.empty():
            log_args = self._logqueue.get()
            if self._sigclose:
                break
            print(*log_args)

    def log(self, *values: object):
        """Log an event"""
        self._logqueue.put_nowait(values)

    def close(self):
        """Close the log. Must be conducted from outside the logger
        thread."""
        self._sigclose = True
        self._logqueue.put_nowait(None)
        self.join()


class P0PServer(ContextManager):
    """Server for handling P0 Protocol packets. Implements the
    ContextManager interface so that it can be used in a `with
    ... as` block"""

    # A lock is required since there are multiple instances of
    # non-atomic data and control dependencies for _sessions.
    # Since close(), which contains lock acquisition code, can
    # be called within a synchronous block in the same thread,
    # a reentrant lock is used.
    _sessions_lock: threading.RLock
    _sessions: "dict[int, P0PSession]"
    _packet_queue: "queue[Tuple[bytes, Tuple[str, int]]]"
    _bind: socket
    _closed: bool
    _logger: P0PLogger
    _server_address: Tuple[str, int]

    def __init__(self, server_port: int):
        self._sessions_lock = threading.RLock()
        self._sessions = {}
        self._packet_queue = queue()
        self._bind = socket(net.AF_INET, net.SOCK_DGRAM)
        self._server_address = ("", server_port)
        self._closed = False
        self._logger = P0PLogger()

    def __enter__(self) -> "P0PServer":
        self._bind.bind(self._server_address)
        return self

    def __exit__(self, *_):
        self._bind.close()

    def _process_packets(self):
        """Packet processing loop. This should be run inside a
        thread to exploit concurrent I/O."""
        while not self._closed or not self._packet_queue.empty():
            item = self._packet_queue.get()
            self._packet_queue.task_done()
            # A None item will be enqueued if the server is closing
            if self._closed:
                break
            data, address = item
            packet = P0PPacket(data)
            if not packet._valid:
                continue
            self._sessions_lock.acquire(blocking=True)
            # Initialize a new session
            if packet.session_id not in self._sessions:
                self._sessions[packet.session_id] = P0PSession(
                    self, address, packet.session_id
                )
            session = self._sessions[packet.session_id]
            self._sessions_lock.release()
            session.process_packet(packet)
        self._sessions_lock.acquire(blocking=True)
        for session in list(self._sessions.values()):
            session.close()
        self._sessions_lock.release()

    def _read_from_bind(self):
        """Socket polling loop"""
        self._logger.log("Waiting on port", self._server_address[1])
        try:
            while not self._closed:
                data_address = self._bind.recvfrom(1 << 16)
                self._packet_queue.put_nowait(data_address)
        except:
            self._closed = True
        self._packet_queue.put_nowait(None)

    def serve(self):
        """Start the server. Initializes the packet, socket, and logger
        threads."""
        packet_thread = threading.Thread(target=self._process_packets)
        socket_thread = threading.Thread(target=self._read_from_bind)
        self._logger.start()
        socket_thread.start()
        packet_thread.start()
        try:
            while not self._closed:
                if input() == "q":
                    self._closed = True
        except:
            self._closed = True

        self._packet_queue.put_nowait(None)

        packet_thread.join()
        self._logger.close()
        # A strange caveat with sockets in Python 3.6 is that there's
        # no way to correctly wake up threads blocked on a socket you
        # want to close, so you need to call socket.shutdown(), even
        # though the socket is connectionless. Even though the desired
        # effect is still achieved, you need to anticipate an exception
        # for attempting to close the connection for a connectionless
        # socket
        try:
            self._bind.shutdown(net.SHUT_RDWR)
        except:
            pass
        socket_thread.join()


if __name__ == "__main__":
    port = int(sys.argv[1])
    with P0PServer(port) as server:
        server.serve()
