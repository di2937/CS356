#!/usr/bin/python3

# NON-BLOCKING SERVER

import sys
import asyncio

from lib import P0PCommand, P0PPacket
from typing import Dict, Tuple, Union


class P0PSession():
    """P0 Protocol server session with each client"""
    TIMEOUT = 10

    _client_addr: Tuple[str, int]
    _transport: asyncio.DatagramTransport
    _recv_seq_num: int
    _sent_seq_num: int
    _session_id: int
    _session_closed: bool
    _server: "P0PServer"
    _timer: "Timer"
    _set_timer: bool

    def __init__(
        self, addr: Tuple[str, int], session_id, transport, server: "P0PServer"):
        self._client_addr = addr
        self._transport = transport
        self._recv_seq_num = 0
        self._sent_seq_num = 0
        self._session_id = session_id
        self._session_closed = False
        self._server = server
        self._set_timer = False

    # send method for server. Server never sends data to a client.
    def _send(self, command: P0PCommand):
        """Send a P0 Protocol-compliant packet to the session's endpoint"""
        self._transport.sendto(
            bytes(P0PPacket(1, command, self._sent_seq_num, self._session_id, b"")), 
            self._client_addr
        )
        if command != P0PCommand.GOODBYE and not self._set_timer:
            self._timer = Timer(P0PSession.TIMEOUT, self)
            self._set_timer = True
        self._sent_seq_num += 1

    async def _packet_received(self, packet: P0PPacket, stdout):
        """Send back a corresponding message to the client 
        and print out the state"""
        if packet.command == P0PCommand.HELLO and packet.session_number == 0:
            self._session_id = packet.session_id
            print("{0} [{1}] Session created".format(
                hex(self._session_id), self._recv_seq_num)
            )
            self._send(P0PCommand.HELLO)
            self._recv_seq_num += 1
        elif packet.session_number == self._recv_seq_num - 1:
            # duplicate packet
            print(
                "{0} [{1}] Duplicate packet!".format(
                    self._session_id, self._recv_seq_num
                )
            )
        elif packet.command == P0PCommand.DATA and packet.session_number > 0:
            # cancel timer
            if self._set_timer:
                self._timer._cancel()
                self._set_timer = False
            if packet.session_number == self._recv_seq_num:
                s = packet.data.decode(encoding='utf-8').strip()
                # print it out and send back with ALIVE message
                print(
                    "{0} [{1}] {2}".format(
                        hex(self._session_id), 
                        self._recv_seq_num, 
                        str(packet.data, encoding='utf-8').strip()
                    )
                )
                self._send(P0PCommand.ALIVE)
                self._recv_seq_num += 1
            elif packet.session_number > self._recv_seq_num:
                # lost packet
                await self._lost_packet_print(
                    packet.session_number - self._recv_seq_num, 
                    stdout
                )
                self._sent_seq_num = self._recv_seq_num
                self._send(P0PCommand.ALIVE)
            else:
                self._goodbye()
        elif packet.command == P0PCommand.GOODBYE:
            # cancel timer
            if self._set_timer:
                self._timer._cancel()
                self._set_timer = False
            # print out goodbye message
            print(
                "{0} [{1}] GOODBYE from client".format(
                    hex(self._session_id), self._recv_seq_num
                )
            )
            if packet.session_number > self._recv_seq_num:
                await self._lost_packet_print(
                    packet.session_number - self._recv_seq_num, 
                    stdout
                )
            self._goodbye()
        else:
            self._goodbye()

    async def _lost_packet_print(self, num, stdout):
        """Print out lost packet message for the number 
        of packets lost times"""
        # lost packet
        for i in range(num):
            print(
                "{0} [{1}] Lost packet!".format(
                    self._session_id, 
                    self._recv_seq_num
                )
            )
            await stdout.drain()
            self._recv_seq_num += 1

    def _goodbye(self):
        """Send GOODBYE message to the client and close the session"""
        self._send(P0PCommand.GOODBYE)
        self._session_closed = True
        self._server._sessions.pop(self._session_id)
        if not self._server._closing:
            print("{0} Session closed".format(hex(self._session_id)))
        

class Timer:
    _timeout: int
    _session: P0PSession
    _task: asyncio.Task

    def __init__(self, timeout, session):
        self._timeout = timeout
        self._session = session
        self._task = asyncio.ensure_future(
            self._timeout_start(), 
            loop=asyncio.get_event_loop()
        )

    async def _timeout_start(self):
        """Timeout event. Close the session with the client 
        if the task is not cancelled within TIMEOUT"""
        await asyncio.sleep(self._timeout)
        self._session._goodbye()

    def _cancel(self):
        """Cancel the task"""
        self._task.cancel()


class P0PServer(asyncio.DatagramProtocol):
    """Server for handling P0 Protocol packets."""
    _transport: asyncio.DatagramTransport
    _sessions: Dict[int, P0PSession]
    _stdin: asyncio.StreamReader
    _stdout: asyncio.StreamWriter
    _closing: bool

    def __init__(self):
        super().__init__()
        self._sessions = {}
        self._closing = False
        asyncio.ensure_future(self.stdin_loop(), loop=asyncio.get_event_loop())

    def connection_made(self, transport):
        """Called when a connection is made"""
        self._transport = transport

    def datagram_received(self, data, addr):
        """Process UDP payload and pass to packet_received() if it
        conforms to a P0 Protocol packet"""
        packet = P0PPacket(data)
        if packet._valid:
            if packet.session_id in self._sessions.keys():
                session = self._sessions.get(packet.session_id)
                if not session._session_closed:
                    asyncio.ensure_future(
                        session._packet_received(packet, self._stdout), 
                        loop=asyncio.get_event_loop()
                    )
            elif packet.session_number == 0 and packet.command == P0PCommand.HELLO:
                # create a new session and add it in the dictionary
                session = P0PSession(addr, packet.session_id, self._transport, self)
                self._sessions[packet.session_id] = session
                asyncio.ensure_future(
                    session._packet_received(packet, self._stdout), 
                    loop=asyncio.get_event_loop()
                )

    async def _connect_stdio(self):
        """Open asynchronous channels to stdin and stdout"""
        loop = asyncio.get_event_loop()
        stdin = asyncio.StreamReader()
        await loop.connect_read_pipe(
            lambda: asyncio.StreamReaderProtocol(stdin), 
            sys.stdin
        )
        transport, protocol = await loop.connect_write_pipe(
            asyncio.streams.FlowControlMixin, 
            sys.stdout
        )
        stdout = asyncio.StreamWriter(transport, protocol, stdin, loop)
        self._stdin, self._stdout = stdin, stdout

    async def stdin_loop(self):
        """Accept the keyboard input and close only when eof 
        or q is inputted"""
        await self._connect_stdio()
        while True:
            keyboard_input = await self._stdin.readline()
            if keyboard_input == b"" or keyboard_input == b"q\n":
                self._close()

    def _close(self):
        """Close the server and clean up the resources"""
        self._closing = True
        # send GOODBYE to all the clients and close the server
        for client in list(self._sessions.values()):
            client._goodbye()
        ask_exit(self._transport)

async def exit():
    """Stop the loop"""
    loop = asyncio.get_event_loop()                                
    loop.stop()   

def ask_exit(transport):
    """Avoid the problem which comes from closing the loop 
    immediately after cancelling the tasks"""
    for task in asyncio.Task.all_tasks():
        task.cancel()                   
    transport.close() 
    asyncio.ensure_future(exit())

if __name__ == '__main__':
    print("Waiting on port {0}...".format(int(sys.argv[1])))
    loop = asyncio.get_event_loop()
    server = P0PServer()
    listen = loop.create_datagram_endpoint(
        lambda: server,
        local_addr=('0.0.0.0', int(sys.argv[1])))
    transport, protocol = loop.run_until_complete(listen)
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        server._close()