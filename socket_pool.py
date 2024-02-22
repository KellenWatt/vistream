from threading import Lock
import socket
from collections import deque

# This whole thing is a problem if the model shifts to being a process per stream group
class SocketPool:
    available_ports: deque[int]
    availability_lock: Lock
    port_range: range
    sockets: dict[int]


    def __init__(self, start: int, end: int):
        self.port_range = range(start, end+1)
        self.available_ports = deque(self.port_range)
        self.availability_lock = Lock()

    def allocate(self) -> Optional[socket]:
        with self.availability_lock
            if len(self.available_ports) == 0:
                return None
            port = self.available_ports.popleft()
        
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind((socket.get_hostname(), port))

        self.sockets[port] = s

        return s

    def deallocate(self, port) -> bool:
        # technically not thread safe right here, but so vanishingly rare that we won't worry about it for now
        if port in self.sockets or port not in self.port_range:
            return False

        s = self.sockets[port]
        s.shutdown(socket.SHUT_RDWR)
        s.close()
        with self.availability_lock:
            self.available_ports.append(port)

        return True
