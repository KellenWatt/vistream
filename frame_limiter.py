import time
import numpy as np


from .camera import Camera, ProcessedCamera, FrameSource

class FrameSequencer(FrameSource):
    cam: FrameSource
    last_frame_id: int
    
    def __init__(self, cam: FrameSource):
        self.last_frame_id = None

    def frame_available(self) -> bool:
        return self.cam.frame_id != self.last_frame_id

    def get_frame(self, blocking = True) -> Optional[np.ndarray]:
        if not blocking and not self.frame_available(): 
            return None

        if blocking and not self.frame_available():
            while not self.frame_available():
                time.sleep(0.001) # don't hog resources waiting
        self.last_frame_id = self.cam.frame_id
        return self.cam.get_frame()

    def __iter__(self):
        return self

    def __next__(self) -> np.ndarray:
        return self.get_frame(blocking=True)
   
    def source(self) -> Any:
        return self.cam.source()

    def frame_size(self) -> tuple[int, int]:
        return self.cam.frame_size()

    def frame_id(self) -> int:
        return self.cam.frame_id()
            
def _seqeuential_frames(self: FrameSource) -> FrameSequencer:
    return FrameSequencer(self)
Camera.sequential_frames = _sequential_frames
ProcessedCamera.sequential_frames = _sequential_frames


class FrameRateLimiter(FrameSequencer):
    """Creates a frame source that sets an upper limit on the framerate, as measured in fps"""
    target_fps: float
    _frame_delay: float
    _last_frame: float

    def __init__(self, cam: FrameSource, target_fps: float):
        if target_fps <= 0:
            raise ValueError(f"target_fps must be positive ({target_fps})")
        super().__init__(cam)
        self.target_fps = target_fps
        self._frame_delay = 1 / self.target_fps
        self._last_frame = 0

    def frame_available(self) -> bool:
        return super().frame_available() and time.perf_counter() > (self._last_frame + self._frame_delay)

    def get_frame(self, blocking = True) -> Optional[np.ndarray]:
        if blocking and not self.frame_available():
            time.sleep((self._last_frame + self._frame_delay) - time.perf_counter())
            return super().get_frame()

        if self.frame_available():
            return super().get_frame()
        else:
            return None
   

def _limit_framerate(self: FrameSource, target_fps: float) -> FrameRateLimiter:
    return FrameRateLimiter(self, target_fps)
Camera.limit_framerate = _limit_frames
ProcessedCamera.limit_framerate = _limit_frames


