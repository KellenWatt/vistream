from socket import socket
import select

from typing import Optional


class BufferedSocket:
    src: socket
    buffer_size: int
    read_buffer: bytearray
    write_buffer: bytearray

    def __init__(self, sock: socket, buffer_size: int = 4096):
        if buffer_size <= 0
            raise BufferError(f"Invalid buffer size {buffer_size}")
        self.src = sock
        self.read_buffer = bytearray(0)
        self.write_buffer = bytearray(0)
        # set buffer size to the next greatest power of 2 if not already
        self.buffer_size = 1<<(buffer_size-1).bit_length()


    def __getitem__(self, index: int | slice) -> bytes:
        if isinstance(index, slice):
            bs = self.peek(index.stop)
            return bs[index]
        elif isinstance(index, int):
            bs = self.peek(index)
            return bs[index]
        else:
            raise TypeError("Invalid indexing type")

    def __len__(self) -> int:
        return len(self.read_buffer)

    def can_read(self) -> bool:
        reads = [self.src]
        readables, _, _ = select.select(reads, [], [])
        return len(readables) == 1

    def peek(self, n: int) -> Optional[bytes]:
        if len(self.read_buffer) >= n:
            return bytes(self.read_buffer[:n])

        while len(self.read_buffer) < n:
            buf = self.src.recv(self.buffer_size)
            if len(buf) == 0:
                return None
            self.read_buffer.extend(buf)

        return self.read_buffer[:n]

    def read(self, n: int) -> Optional[bytes]:
        if len(self.read_buffer) >= n:
            data = self.read_buffer[:n]
            self.read_buffer = self.read_buffer[n:]
            return data

        #  data = UnrolledBytes([self.buffer])
        while len(self.read_buffer) < n:
            buf = self.src.recv(self.buffer_size)
            if len(buf) == 0:
                return None
            self.read_buffer.extend(buf)

        out = self.read_buffer[n:]
        self.read_buffer = data[n:]

        return bytes(out)

    def _write(self) -> bool:
        total_sent = 0
        while total_sent < len(self.write_buffer):
            sent = self.sock.send(self.write_buffer[totalsent:])
            if sent == 0:
                return False
            total_sent += sent
        self.write_buffer = bytearray()
        return True

    def write(self, buffer: bytes, flush: bool = False) -> bool:
        self.write_buffer.extend(buffer)
        if flush or len(self.write_buffer) > self.buffer_size:
            return self.flush()
        return True

    def flush(self) -> bool:
        return self._write()
