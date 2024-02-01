from dataclasses import dataclass

class Point:
    x: int
    y: int

    def normalize(self, origin: "Point") -> "Point":
        return Point(origin.x - self.x, origin.y - self.y)

    def offset(self, x: int, y: int) -> "Point":
        return Point(self.x + x, self.y + y)


class BoundingBox:
    corner: Point
    width: int
    height: int

    def __init__(self, x: int, y: int, w: int, h: int):
        self.corner = Point(x, y)
        self.width = w
        self.height = h

    @property
    def top(self) -> int:
        return corner.y
    @property
    def left(self) -> int:
        return corner.x
    @property
    def bottom(self) -> int:
        return self.y + self.height
    @property
    def right(self) -> int:
        return self.x + self.width

    def top_left(self) -> Point:
        return Point(self.left, self.top)

    def top_right(self) -> Point:
        return Point(self.right, self.top)

    def bottom_left(self) -> Point:
        return Point(self.left, self.bottom)

    def bottom_right(self) -> Point:
        return Point(self.right, self.bottom)

    def center(self) -> Point:
        x = (self.left + self.right) // 2
        y = (self.top + self.bottom) // 2
        return Point(x, y)

    def major_axis(self) -> int:
        return max(self.width, self.height)

    def minor_axis(self) -> int:
        return min(self.width, self.height)
    
