#!/usr/bin/python3
# pylint: disable=relative-beyond-top-level

# NON-BLOCKING CLIENT

import sys
import socket
import signal
import random
import asyncio

from lib import P0PCommand, P0PPacket
from typing import Dict, Tuple, Union


class P0PSession(asyncio.DatagramProtocol):
    """P0 Protocol client session"""

    _finished: bool
    _ip: Tuple[str, int]
    _transport: asyncio.DatagramTransport
    _stdin: asyncio.StreamReader
    _stdout: asyncio.StreamWriter
    _session_number_lock: asyncio.Lock
    _session_number: int
    _session_id: int
    _server_alive: asyncio.Semaphore
    _server_hello: asyncio.Semaphore
    _sent_command: P0PCommand

    def __init__(self, ip: Tuple[str, int]):
        super().__init__()
        self._ip = socket.gethostbyname(ip[0]), ip[1]
        self._session_id = random.randint(0, 1 << 32 - 1)
        self._session_number = 0
        self._session_number_lock = asyncio.Lock()
        self._server_alive = asyncio.Semaphore(0)
        self._server_hello = asyncio.Semaphore(0)
        self._finished = False
        self._condition = asyncio.Condition()

    async def _create_endpoint(self):
        """Open an endpoint for UDP communication"""
        loop = asyncio.get_event_loop()
        self._transport, _ = await loop.create_datagram_endpoint(
            lambda: self, family=socket.AF_INET
        )

    async def _connect_stdio(self):
        """Open asynchronous channels to stdin and stdout"""
        loop = asyncio.get_event_loop()
        stdin = asyncio.StreamReader()
        await loop.connect_read_pipe(
            lambda: asyncio.StreamReaderProtocol(stdin), sys.stdin
        )

        transport, protocol = await loop.connect_write_pipe(
            asyncio.streams.FlowControlMixin, sys.stdout
        )
        stdout = asyncio.StreamWriter(transport, protocol, stdin, loop)

        self._stdin, self._stdout = stdin, stdout

    async def _notify(self):
        """Notify all coroutines waiting on server failure/session completion
        of a change in state"""
        await self._condition.acquire()
        self._condition.notify_all()
        self._condition.release()

    async def sendto(self, data: Union[bytes, P0PCommand]):
        """Send a P0 Protocol-compliant packet to the session's endpoint"""
        await self._session_number_lock.acquire()
        try:
            # Marshal raw bytes into a data packet
            if type(data) is bytes:
                self._sent_command = P0PCommand.DATA
                self._transport.sendto(
                    bytes(
                        P0PPacket(
                            1,
                            P0PCommand.DATA,
                            self._session_number,
                            self._session_id,
                            data,
                        )
                    ),
                    addr=self.endpoint_ip,
                )
                await asyncio.wait_for(self._server_alive.acquire(), 10)
                self._session_number += 1
            # Marshal a command into a packet
            elif type(data) is P0PCommand:
                self._sent_command = data
                self._transport.sendto(
                    bytes(
                        P0PPacket(1, data, self._session_number, self._session_id, b"")
                    ),
                    addr=self.endpoint_ip,
                )
                # Don't wait for a response to GOODBYE
                if data.value != P0PCommand.GOODBYE:
                    await asyncio.wait_for(
                        self._semaphores[self._sent_command].acquire(), 10
                    )
                self._session_number += 1
            else:
                raise ValueError("Attempted to marshal invalid data")
        except:
            self._finished = True
            await self._notify()
        self._session_number_lock.release()

    def packet_received(self, packet: P0PPacket):
        """Process P0 Packet and mutate state according to sequence"""
        responses = {
            P0PCommand.HELLO: P0PCommand.HELLO,
            P0PCommand.DATA: P0PCommand.ALIVE,
        }
        if packet.command == responses[self._sent_command]:
            self._semaphores[packet.command].release()
        else:
            self._finished = True
            asyncio.get_event_loop().create_task(self._notify())

    def datagram_received(self, data: bytes, sender: Tuple[str, int]):
        """Process UDP payload and pass to packet_received() if it
        conforms to a P0 Protocol packet"""
        if self.endpoint_ip != sender:
            return 
        packet = P0PPacket(data)
        if packet._valid:
            self.packet_received(packet)

    def _isfinished(self):
        return self._finished

    async def loop(self):
        """Input loop for client session. Upon any input that isn't 'q',
        EOF, or a keyboard interrupt, a task is spawned to marshal the
        input into a P0 Protocol packet and transmit it to the server
        endpoint. For any of the aforementioned inputs or on a timeout
        error, the session will close."""
        await self._create_endpoint()
        await self._connect_stdio()
        loop = asyncio.get_event_loop()
        try:
            # Perform HELLO and GOODBYE synchronously since they only happen
            # once
            await self.sendto(P0PCommand.HELLO)
            while not self._finished:
                await self._condition.acquire()

                readline = loop.create_task(self._stdin.readline())
                wait_for_finish = loop.create_task(
                    self._condition.wait_for(self._isfinished)
                )
                # done and pending are singleton sets, as only two
                # tasks are being waited on and only one is guaranteed
                # to complete upon returning from asyncio.wait()
                done, pending = await asyncio.wait(
                    [readline, wait_for_finish],
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for pending_task in pending:
                    pending_task.cancel()
                    # Task cancellation is a bit wonky; we need to
                    # cancel the task then yield to it so we can catch
                    # the CancelledError being thrown inside of it
                    try:
                        await pending_task
                    except asyncio.CancelledError:
                        continue
                # Now that the condition variable coroutine has been
                # cleaned up and its resources have been released,
                # we own the lock again and can release it
                self._condition.release()
                if self._finished:
                    break 
                client_input = await done.pop()
                if client_input in {b"", b"q\n"}:
                    await self.sendto(P0PCommand.GOODBYE)
                    break
                # enqueue packet transmittion
                if client_input != b"\n":
                    loop.create_task(self.sendto(client_input))
        # These are acceptable exceptions
        except asyncio.TimeoutError:
            pass
        except KeyboardInterrupt:
            await self.sendto(P0PCommand.GOODBYE)
        except asyncio.CancelledError:
            await self.sendto(P0PCommand.GOODBYE)
            for pending_task in {readline, wait_for_finish}:
                pending_task.cancel()
                try:
                    await pending_task
                except:
                    continue

        self._server_alive.release()
        self._server_hello.release()
        self._transport.close()
        

    @property
    def _semaphores(self) -> Dict[P0PCommand, asyncio.Semaphore]:
        """Mappings from P0PCommands to semaphore objects used for
        tracking timeouts"""
        return {
            P0PCommand.ALIVE: self._server_alive,
            P0PCommand.HELLO: self._server_hello,
        }

    @property
    def endpoint_ip(self) -> Tuple[str, int]:
        """(IP, port) pair for P0 Protocol server"""
        return self._ip


if __name__ == "__main__":
    session = P0PSession((sys.argv[1], int(sys.argv[2])))
    loop = asyncio.get_event_loop()
    task = loop.create_task(session.loop())
    loop.add_signal_handler(signal.SIGINT, task.cancel)
    try:
        loop.run_until_complete(task)
    except asyncio.CancelledError:  # Except in the case of a cancelled error
        pass
    loop.close()
