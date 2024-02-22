# Threading Model:
# Each Stream is managed in its own thread (process?), with a separate thread listening for connections.
# each connection to that stream is managed in its own separate thread
# The stream focuses on grabbing a frame and storing it in memory.
#   - This may involve some kind of Lock, but maybe not
# This data is accessed by (not (!) shared to) each connection (read-only, so should be fine)
# 
# Each connection owns a socket. In its thread, it constantly loops, checking if there is any incoming message 
# to process. If so, do so, otherwise, do nothing. Either way, continue to sending a frame (and accompanying data), if possible.
# Repeat

import numpy as np
from .camera import Camera, ProcessedCamera, FrameSource
from .protocol.message import *
from .protocol.socket_buffer import BufferedSocket

from threading import Thread, Lock, Event
from .socket_pool import SocketPool
from .frame_limiter import *

from typing import Callable

Layer = Callable[[np.ndarray], np.ndarray]

class Connection:
    stream: Stream
    sock: BufferedSocket
    frame_source: FrameSource
    worker: Thread
    transmitting: Event

    # options that are configurable on a per-connection basis
    compression: bool
    transmit_frame: Event
    transmit_data: Event

    worker: Thread

    def __init__(self, stream, socket):
        self.stream = stream
        self.frame_source = stream.source
        self.sock = BufferedSocket(socket)
        self.transmitting = Event()
        self.transmit_frames = Event()
        self.transmit_data = Event()

        self.compression = True

        def worker():
            while True:
                self.respond_if_necessary()
                
                if not self.transmitting.is_set():
                    continue
                
                m = FrameData(compressed = self.compression)
                frame = self.frame_source.get_frame()
                if self.transmit_frame.is_set():
                    m.frame_data = frame
                if self.transmit_data.is_set():
                    if self.stream.post_processor is not None:
                        data = self.stream.post_processing(frame)
                        m.addl_data = data

                self.sock.write(m.format, flush = True)
                        
        self.worker = Thread(worker)
        self.worker.start()

    def respond_if_necessary(self):
        if not self.sock.can_read():
            return
        m = Message.parse(self.sock)
        # server only responds to requests, some configures, starts, and stops
        # frame datas and configures for non-configurables are ignored
        t = type(m)
        if t == Request:
            data = {}
            # TODO figure out where I'm getting most of this data
            if Parameter.FRAME_SIZE in m:
                data[Parameter.FRAME_SIZE] = self.source.frame_size()
            if Parameter.COMPRESSED in m:
                data[Parameter.COMPRESSED] = self.compression
            if Parameter.FOV in m:
                pass # TODO
            if Parameter.TARGET_SIZE in m:
                pass # TODO
            bs = Configure(data).format()
            self.sock.write(bs, flush=True)

        elif t == Configure:
            if Parameter.COMPRESSED in m:
                self.compression = m.get(Parameter.COMPRESSED)
            # Do Nothing with these
            #  Parameter.FOV
            #  Parameter.TARGET_SIZE
            #  Parameter.FRAME_SIZE
        elif t == Start:
            self.transmitting.set()
            if m.frame_rate == 0:
                self.source = FrameSequencer(self.stream.source)
            else:
                self.source = FrameRateLimiter(self.stream.source, m.frame_rate)

            if StreamFlags.FRAME_DATA in m:
                self.transmit_frames.set()
            else:
                self.transmit_frames.clear()

            if StreamFlags.ADDL_DATA in m:
                self.transmit_data.set()
            else:
                self.transmit_data.clear()
            # start stream with proper settings
        elif t == Stop:
            self.transmitting.clear()
            # terminate stream


class Stream:
    source: FrameSource
  
    entry_point: socket
    listener: Thread
    connections: list[Connection]
    connection_lock: Thread

    post_processor: Optional[Callable[np.ndarray], bytes]

    @classmethod
    def initialize_socket_pool(cls, start: int, end: int):
        if not hasattr(cls, "socket_pool"):
            cls.socket_pool = SocketPool(start, end)

    def __init__(self, source: FrameSource):
        if not hasattr(type(self), "socket_pool"):
            raise ValueError("Socket pool hasn't been initialized")
        self.source = source
        entry_point = type(self).socket_pool.allocate()
        if entry_point is None:
            raise ValueError("no ports available")
        self.entry_point = entry_point
        
        self.pipeline = []
        self.result_layer = None

        def listener_job():
            self.entry_point.listen()
            while True:
                client, _address = self.entry_point.accept()
                client = Connection(self, client)
                with self.connection_lock:
                    self.connections.append(client)

        self.listener = Thread(listener_job)


    def add_post_processing(self, layer: Callable[[np.ndarray], bytes]):
        self.post_processer = layer

