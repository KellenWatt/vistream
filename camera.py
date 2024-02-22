import os
os.environ["LIBCAMERA_LOG_LEVELS"] = "*:WARN"

import picamera2
import cv2 as cv
import time
import numpy as np
from collections import deque
from threading import Thread, Lock, Event


from typing import Any, Optional, Callable

class FrameSource:
    def get_frame(self) -> Optional[np.ndarray]:
        """Returns the current frame of the device, in the form of a `numpy.ndarray`.
        This method does not inherently guarantee unique frames per call, though some
        subclasses may provide this guarantee.

        The `Optional` annotation is intended to allow for non-blocking operations.
        However, blocking is assumed to be the default, and blocking operations should
        never return `None`.
        """
        raise "Not implemented"

    def source(self) -> Any:
        """Returns the raw, root frame source. This will most often be a class representing 
        some kind of camera, and does not guarantee any API.
        """
        raise "Not implemented"

    def frame_size(self) -> tuple[int, int]:
        """The size of the default frame returned, in pixels. Required for reconstructing 
        frame data on the client side
        """
        raise "Not implemented"

    def frame_id(self) -> int:
        """The id of the current frame. Generally assumed to increment for sequenctial frames, 
        but it's really only important that frames have unique ids over a reasonable period of time.
        """
        raise "Not implemented"

    def field_of_view(self) -> tuple[float, float]:
        """The horizontal and vertical field-of-views of the root frame source, respectively."""
        raise "Not implemented"

class Camera(FrameSource):
    frame_grabber: Thread
    frame_lock: Thread
    stop_capture: Event
    current_frame: np.ndarray
    _frameid: int

    def __init__(self):
        self.frame_lock = Lock()
        self.stop_capture = Event()
        # Only one thread should ever modify this, so no need for a mutex
        self._frameid = 0

        def _grab_frame():
            while not self.stop_capture.is_set():
                frame = self._next_frame_()
                if frame is None:
                    continue
                with self.frame_lock:
                    self.current_frame = frame
                self._frameid += 1
        self._frame_grabber_f = _grab_frame
        self.frame_grabber = None
       
    def start(self):
        self.frame_grabber = Thread(self._frame_grabber_f)
        self.frame_grabber.start()

    def stop(self):
        self.stop_capture.set()
        self.frame_grabber.join()
        self.frame_grabber = None

    def is_capturing(self) -> bool:
        return self.frame_grabber is not None and self.frame_grabber.is_alive()

    def get_frame(self) -> np.array:
        """Returns the most recent frame captured by the camera. This is non-blocking 
        (technically. There is a mutex involved), and can result in the same image 
        between calls. For semi-guaranteed sequential frames, prefer any of the 
        frame limiter/sequencer classes.

        Frame data is returned as a `numpy.ndarray` with depth 3 in BGR format
        """
        with self.frame_lock:
            # shouldn't take very long to copy, but better safe than sorry
            res = self.current_frame
        return res

    def _next_frame_(self) -> Optional[np.ndarray]:
        raise "Not implemented"

    def source(self) -> Any:
        raise "Not implemented"

    def frame_size(self) -> tuple[int, int]:
        raise "Not implemented"



class PiCamera(Camera):
    cam: picamera2.Picamera2
    _frame_size: tuple[int, int] 

    def __init__(self, size: tuple[int, int], mode: int = 0):
        """Creates a new instance of the Raspberry Pi camera connect to the CSI port
        By default the camera is launched into mode 0, which is usually, if not always, 
        the highest framerate. To determine the modes, you can run the following program.
        ```python
            from picamera2 import Picamera2
            from pprint import pprint
            cam = Picamera2()
            pprint(cam.sensormodes)
        ```

        Note that, since you can only have one Pi camera without external modules, attempting
        to instantiate this class more than once is undefined behaviour. It may work fine, 
        but don't count on it in general use.
        """
        cam = picamera2.Picamera2()
        mode = cam.sensor_modes[mode]
        config = picam2.create_preview_configuration({"size": size, "format": "RGB888"},
                                             controls={"FrameDurationLimits": (100, 8333)},
                                             sensor={"output_size": mode["output_size"], "bit_depth": mode["bit_depth"]})

        cam.align_configuration(config)
        cam.configure(config)
        cam.start()
        self.cam = cam
        self._frame_size = config["main"]["size"]

    def source(self) -> picamera2.Picamera2:
        return self.cam

    def frame_size(self) -> tuple[int, int]:
        return self._frame_size

    def _next_frame_(self) -> Optional[np.ndarray]:
        return self.cam.capture_array()


def _detect_cameras(skip: int = 0) -> list[int]:
    cam_id = skip
    ids = []
    while cam_id < 20:
        cam = cv.VideoCapture(cam_id)
        if cam.read()[0]:
            ids.append(cam_id)
        cam.release()
        cam_id += 1
    return ids


class USBCamera(Camera):
    cam: cv.VideoCapture

    possible_cameras = _detect_cameras()

    def __init__(self, source = None):
        """Create a new instance of a USB camera.

        `source` must be the valid video device number that can be accessed by OpenCV's
        `VideoCapture`. A limited, but significant number of devices are checked on startup
        and valid devices are listed in `USBCamera.possible_cameras`.

        If `source` is `None`, the first device from `USBCamera.possible_cameras` is used.
        """
        if source is not None and type(source) is not int:
            raise ValueError(f"device id must be an integer")
        
        if source is None:
            if len(USBCamera.possible_cameras) == 0:
                source = USBCamera.possible_cameras[0]
            else:
                raise ValueError("no known devices available. Cannot initialize camera")

        USBCamera.possible_cameras.remove(source)

        cam = cv.VideoCapture(source)
        cam.set(cv.CAP_PROP_FOURCC,cv.VideoWriter_fourcc(*"MJPG"))
        if not cam.isOpened():
            raise f"VideoCapture could not open source at '{source}'"
        self.cam = cam

    def source(self) -> cv.VideoCapture:
        return self.cam
    
    def frame_size(self) -> tuple[int, int]:
        return (int(self.cam.get(cv.CAP_PROP_FRAME_WIDTH)), int(self.cam.get(cv.CAP_PROP_FRAME_HEIGHT)))
    
    def _next_frame(self) -> Optional[np.ndarray]:
        ok, frame = self.cam.read()
        if not ok:
            return None
        return frame


Layer = Callable[[np.ndarray], np.ndarray]

class ProcessedCamera(FrameSource):
    source: FrameSource

    frame_grabber: Thread
    frame_lock: Thread
    current_frame: np.ndarray
    _frame_id: int

    layers: list[Layer]

    def __init__(self):
        self.frame_lock = Lock()
        self.stop_capture = Event()
        # Only one thread should ever modify this, so no need for a mutex
        self._frame_id = 0

        self.layers = []

        def _grab_frame():
            while not self.stop_capture.is_set():
                if self._frame_id == self.source.frame_id():
                    continue
                frame = self.source.get_frame()
                if frame is None:
                    continue
                for layer in self.layers:
                    frame = layer(frame)
                with self.frame_lock:
                    self.current_frame = frame
                self._frame_id += 1
        self._frame_grabber_f = _grab_frame
        self.frame_grabber = None
       
    def start(self):
        self.frame_grabber = Thread(self._frame_grabber_f)
        self.frame_grabber.start()

    def stop(self):
        self.stop_capture.set()
        self.frame_grabber.join()
        self.frame_grabber = None

    def is_capturing(self) -> bool:
        return self.frame_grabber is not None and self.frame_grabber.is_alive()

    def get_frame(self) -> np.array:
        """Returns the most recent frame captured by the camera. This is non-blocking 
        (technically. There is a mutex involved), and can result in the same image 
        between calls. For semi-guaranteed sequential frames, prefer any of the 
        frame limiter/sequencer classes.

        Frame data is returned as a `numpy.ndarray` with depth 3 in BGR format
        """
        with self.frame_lock:
            # shouldn't take very long to copy, but better safe than sorry
            res = self.current_frame
        return res

    def add_layer(self, layer: Layer):
        self.layers.append(layer)

    def source(self) -> Any:
        return self.source.source()

    def frame_size(self) -> tuple[int, int]:
        return self.source.frame_size()
    
    def frame_id(self) -> int:
        return self._frame_id
