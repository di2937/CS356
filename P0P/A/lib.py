import struct

from enum import IntEnum, auto
from typing import SupportsBytes, Optional, Union

class P0PCommand(IntEnum):
    HELLO = auto()
    DATA = auto()
    ALIVE = auto()
    GOODBYE = auto()

P0PCommand_VALUES = frozenset(value.value for value in P0PCommand)

class P0PPacket(SupportsBytes):
    MAGIC = 0xc356

    _version: int
    _command: P0PCommand
    _session_number: int
    _session_id: int
    _data: bytes
    _valid: bool

    def __init__(self, maybe_buffer: Union[bytes, int], *args) -> None:
        mb_type = type(maybe_buffer)
        if mb_type == bytes:
            magic, version, command, session_number, session_id = struct.unpack("> 1H 2B 2I", maybe_buffer[:12])
            data = maybe_buffer[12:]
            if magic != P0PPacket.MAGIC or version != 1 or command not in P0PCommand_VALUES:
                self._valid = False
            else:
                self._valid = True
                self._version = version
                self._command = command
                self._session_number = session_number
                self._session_id = session_id
                self._data = data
        elif mb_type == int and len(args) == 4:
            self._valid = True
            version, command, session_number, session_id, data = (maybe_buffer, *args)
            self._version = version
            self._command = command
            self._session_number = session_number
            self._session_id = session_id
            self._data = data

    def __bytes__(self) -> bytes:
        return struct.pack("> 1H 2B 2I", P0PPacket.MAGIC, self._version, self._command, 
                           self._session_number, self._session_id) + self.data

    @property
    def data(self) -> bytes:
        return self._data

    @property
    def command(self) -> P0PCommand:
        return self._command

    @property
    def session_number(self) -> int:
        return self._session_number

    @property
    def session_id(self) -> int:
        return self._session_id
