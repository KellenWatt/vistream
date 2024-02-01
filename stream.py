from typing import Optional

class StreamContext:
    dimensions: tuple[int, int]
    fov: float | tuple[float, float] # diagonal or (hor, vert)
    target_size: Optional[tuple[int, int]] # detected objects width at 1 meter and vertical

    def __init__(self, dims: tuple[int, int], fov: float | tuple[float, float], target_size: Optional[int | tuple[int, int]] = None):
        self.dimensions = dims
        self.fov = fov
        
        if type(object_size) != tuple:
            size = int(object_size)
            self.target_size = (size, size)
        else:
            self.target_size = target_size


class Stream:
    pass
