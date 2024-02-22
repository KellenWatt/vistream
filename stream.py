from typing import Optional, Callable, Any
import socket
import functools
import cv2 as cv
import math

from vistream.camera import Camera


class StreamContext:
    fov: float | tuple[float, float] # diagonal or (hor, vert)
    target_size: Optional[tuple[int, int]] # detected objects width at 1 meter and vertical

    def __init__(self, fov: float | tuple[float, float], target_size: Optional[int | tuple[int, int]] = None, target_framerate: Optional[float] = None):
        self.dimensions = dims
        self.fov = fov
        self.target_framerate = target_framerate
        
        if type(target_size) != tuple:
            size = int(target_size)
            self.target_size = (size, size)
        else:
            self.target_size = target_size

    def cardinal_fov(self, frame_size: tuple[int, int]) -> (float, float):
        if type(fov) is not float:
            return self.fov
            
        w = frame_size[0]
        h = frame_size[1]
        hyp = math.sqrt(w * w + h * h)
        scale = hyp / fov
        return (w / scale, h / scale)



    #  FPS = auto() # float64
    #  FRAME_SIZE = auto() # pair of uint16
    #  COMPRESSED = auto() # uint8
    #  FOV = auto() # pair of float32
    #  TARGET_SIZE = auto() # pair of uint16
class StreamConnection:
    sock: socket.socket
    pipeline: list[Callable[[np.ndarray], np.ndarray]]
    result_step: Callable[[np.ndarray], Any]
   
    context: StreamContext
    duration: int # frame duration -1 for forever, otherwise positive - set on start - default to -1
    fps: float # - configurable
    frame_size: Optional[(int, int)] # pixel size of transmitted frame - configurable - default to None (input frame size)
    # other parameters gotten from stream context

    def __init__(self, client: socket, context: Optional[StreamContext] = None, dimensions: Optional[tuple[int, int]] = None):
        self.sock = client
        self.dimensions = dimensions
        self.context = context
        self.pipeline = []

    def add_processing_step(self, step): 
        self.pipeline.append(step)

    def set_result_step(self, step: Callable[[np.ndarray], Any]):
        self.result_step = step

    def reset_pipeline(self):
        self.pipeline.clear()

    def send(self, frame: np.ndarray):
        """Run a frame through the pipeline"""
        if self.dimensions is not None:
            frame = cv.resize(frame, self.dimensions)
        frame_data = functools.reduce(lambda fr, step: step(fr), self.pipeline, frame)
        addl_data = self.final_step(frame_data)


        
        pass

class Stream:
    connections: list[StreamConnection]
    cam: Camera
    pass

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

