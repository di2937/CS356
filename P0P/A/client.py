#!/usr/bin/python3

# THREAD BASED CLIENT

import sys
import threading
import random

from socket import *
from lib import P0PCommand, P0PPacket
from typing import Tuple, Union


class P0PSession():
    TIMEOUT = 10.0

    _client_socket: socket
    _ip: Tuple[str, int]
    _sequence_number: int
    _session_id: int
    _session_created: bool
    _session_terminated: bool
    _timer: threading.Timer
    _set_timer: bool

    def __init__(self, ip: Tuple[str, int]):
        self._client_socket = socket(AF_INET, SOCK_DGRAM)
        self._ip = ip
        self._session_id = random.randint(0, 1 << 32 - 1)
        self._sequence_number = 0
        self._session_created = False
        self._session_terminated = False
        self._set_timer = False

    # function to send messages to server
    def _send(self, data: Union[bytes, P0PCommand]):
        """Send messages to server and set the timer 
        if it is in Ready state"""
        if type(data) is bytes:
            self._client_socket.sendto(
                bytes(
                    P0PPacket(
                        1, 
                        P0PCommand.DATA, 
                        self._sequence_number, 
                        self._session_id, 
                        data
                    )
                ), 
                self._ip
            )
            self._sequence_number += 1
        elif type(data) is P0PCommand:
            self._client_socket.sendto(
                bytes(P0PPacket(1, data, self._sequence_number, self._session_id, b"")),
                self._ip
            )
            self._sequence_number += 1
        if not self._set_timer:
            self._timer = threading.Timer(self.TIMEOUT, self._close)
            self._timer.start()
            self._set_timer = True

    def _client_send(self):
        """Get inputted data to send to server or close the session. 
        Main thread takes care of this."""
        self._send(P0PCommand.HELLO)
        while not self._session_terminated:
            # get a line of input from the user's keyboard
            try:
                sentence = input()
            except EOFError:
                sentence = "eof"
            if sentence == "q" or sentence == "eof":
                self._close()
                break
            # pack the header and data, and send it to the server
            self._send(bytes(sentence, 'utf-8'))

    def _client_receive(self):
        """Receive responses from server. Thread 2 takes care of this."""
        thread2 = threading.Thread(target=session._client_send, daemon=True)
        thread2.start()
        try:
            while not self._session_terminated:
                # receive message from the server
                receivedData, serverAddress = self._client_socket.recvfrom(4096)
                packet = P0PPacket(receivedData)
                if packet._valid and packet.session_id == self._session_id:
                    if packet.command == P0PCommand.HELLO and not self._session_created:
                        # cancel timer
                        if self._set_timer:
                            self._timer.cancel()
                            self._set_timer = False
                        self._session_created = True
                    elif packet.command == P0PCommand.ALIVE and self._session_created:
                        # cancel timer
                        if self._set_timer:
                            self._timer.cancel()
                            self._set_timer = False
                    elif packet.command == P0PCommand.GOODBYE and self._session_created:
                        # cancel timer
                        if self._set_timer:
                            self._timer.cancel()
                            self._set_timer = False
                        # close the session
                        self._client_socket.close()
                        self._session_terminated = True
                        break
                    else:
                        # invalid: send goodbye to server
                        self._close()
                else:
                    # invalid: send goodbye to server
                    self._close()
        except KeyboardInterrupt:
            self._send(P0PCommand.GOODBYE)
            self._timer.cancel()
            self._set_timer = False
        except TimeoutError:
            pass

    def _close(self):
        """Close the session and set the timer to wait 
        for the server sending goodbye"""
        # cancel timer (and reset timer in _send method)
        if self._set_timer:
            self._timer.cancel()
            self._set_timer = False
        if self._session_created:
            self._send(P0PCommand.GOODBYE)
        else:
            # if timeout event occurs before creating a session
            raise TimeoutError


# Main function
if __name__ == '__main__':
    session = P0PSession((sys.argv[1], int(sys.argv[2])))
    session._client_receive()
