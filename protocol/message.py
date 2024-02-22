import bitstring
from enum import IntFlag, IntEnum, auto
import numpy as np
import zlib


from typing import Optional, Any

from .socket_buffer import BufferedSocket

class MessageKind(IntEnum):
    FRAME_DATA = auto()
    REQUEST = auto()
    CONFIGURE = auto()
    START = auto()
    STOP = auto()
    INVALID = -1

    @classmethod
    def of(cls, b: bytes) -> "MessageKind":
        byte = b[0]
        if byte == cls.FRAME_DATA:
            return cls.FRAME_DATA
        elif byte == cls.REQUEST:
            return cls.REQUEST
        elif byte == cls.CONFIGURE:
            return cls.CONFIGURE
        elif byte == cls.START:
            return cls.START
        elif byte == cls.STOP:
            return cls.STOP
        else:
            return cls.INVALID

class Parameter(IntFlag):
    FRAME_SIZE = auto() # pair of uint16
    COMPRESSED = auto() # uint8
    FOV = auto() # pair of float32
    TARGET_SIZE = auto() # pair of uint16

    def parse_bytes(self, b: bytes) -> dict["Parameter", Any]:
        data = {}
        if Parameter.FRAME_SIZE in self:
            data[Parameter.FRAME_SIZE] = tuple(bitstring.Bits(bytes=b).unpack(["uintbe16", "uintbe16"]))
            b = b[4:]
        if Parameter.COMPRESSED in self:
            data[Parameter.COMPRESSED] = bool(bitstring.Bits(bytes=b).unpack(["uint8"])[0])
            b = b[1:]
        if Parameter.FOV in self:
            data[Parameter.FOV] = bitstring.Bits(bytes=b).unpack(["floatbe32", "floatbe32"])
            b = b[8:]
        if Parameter.TARGET_SIZE in self:
            data[Parameter.TARGET_SIZE] = bitstring.Bits(bytes=b).unpack(["uintbe16", "uintbe16"])
            b = b[4:]

        return data

    @staticmethod
    def format_data(data: dict["Parameter", Any]) -> bytes:
        bs = []
        if Parameter.FRAME_SIZE in data:
            bs.append(bitstring.pack(["uintbe16", "uintbe16"], *data[Parameter.FRAME_SIZE]))
        if Parameter.COMPRESSED in data:
            bs.append(bitstring.Bits(uint=data[Parameter.COMPRESSED], length=8))
        if Parameter.FOV in data:
            bs.append(bitstring.pack(["floatbe32", "floatbe32"], *data[Parameter.FOV]))
        if Parameter.TARGET_SIZE in data:
            bs.append(bitstring.pack(["uintbe16", "uintbe16"], *data[Parameter.TARGET_SIZE]))

        return (b'').join(b.tobytes() for b in bs)

    def byte_length(self) -> int:
        return (Parameter.FRAME_SIZE in self) * 4 +\
            (Parameter.COMPRESSED in self) * 1 +\
            (Parameter.FOV_HORIZONTAL in self) * 8 +\
            (Parameter.TARGET_SIZE in self) * 4
        

class StreamFlags(IntFlag):
    COMPRESSED = auto()
    FRAME_DATA = auto()
    ADDL_DATA = auto()

class Message:
    @classmethod
    def parse(self, buffer: BufferedSocket) -> Optional[Message]:
        message_kind = buffer.peek(1)
		if message_kind == MessageKind.FRAME_DATA:
			return FrameData(buffer)
		elif message_kind == MessageKind.REQUEST:
			return Request(buffer)
		elif message_kind == MessageKind.CONFIGURE:
			return Configure(buffer)
		elif message_kind == MessageKind.START:
			return Start(buffer)
		elif message_kind == MessageKind.STOP:
			return Stop(buffer)
        else:
            return None

    def format(self) -> bytes:
        raise TypeError("base messages cannot be formatted")

class FrameData(Message):
    frame_data: Optional[np.ndarray | bytes]
    addl_data: Optional[bytes]
    compressed: bool

    _currently_compressed: bool

    def __init__(self, frame_data = Optional[np.ndarray] = None, addl_data: Optional[bytes] = None, compressed = False, _currently_compressed = False):
        if frame_data is None and addl_data is None:
            raise ValueError("No data provided")
        self._frame_data = frame_data
        self._addl_data = addl_data
        self.compressed = compressed
        self._currently_compressed = _currently_compressed

    def _compress(self):
        if self._currently_compressed:
            return

        if self._frame_data is not None:
            comp_frame = zlib.compress(self._frame_data.data)
            self._frame_data = comp_frame
        
        if self._addl_data is not None:
            comp_addl = zlib.compress(self._addl_data)
            self._addl_data = comp_addl

        self._currently_compressed = True

    def _decompress(self):
        if not self._currently_compressed:
            return

        if self._frame_data is not None:
            decomp_frame = zlib.decompress(self._frame_data)
            self._frame_data = decomp_frame
       
        if self._addl_data is not None:
            decomp_addl = zlib.compress(self._addl_data)
            self._addl_data = decompl_addl

        self._currently_compressed = False

    @property
    def frame(self) -> Optional[np.ndarray]:
        if self._frame_data is None:
            return None

        self._decompress()
        return self._frame_data

    @property
    def addl_data(self) -> Optional[np.ndarray]:
        if self.addl_data is None:
            return None
        self._decompress()
        return self._addl_data

    @classmethod
    def parse(cls, buffer: BufferedSocket) -> Optional["FrameData"]:
        header = buffer.read(1)
        if header != MessageKind.FRAME_DATA:
            return None

        flags = buffer.read(1)
        if flags is None: # length check should be implied by the None check
            return None
   
        compressed = flags & StreamFlags.COMPRESSED

        frame_len = buffer.read(3)
        if frame_len is None or len(frame_len) != 3:
            return None
        frame_len = bitstring.Bits(bytes=frame_len).unpack(["uintbe24"])[0]

        if frame_len > 0:
            frame_data = buffer.read(frame_len)
            if frame_data is None or len(frame_data) != frame_len:
                return None
        else:
            frame_data = None

        addl_len = buffer.read(2)
        if addl_len is None or len(addl_len) != 2:
            return None
        
        if addl_len > 0:
            addl_data = buffer.read(addl_len)
            if addl_data is None or len(addl_data) != addl_len:
                return None
        else:
            addl_data = None

        return cls(frame_data, addl_data, compressed, compressed)

    def format(self) -> bytes:
        if self.compressed:
            self._compress()

        frame_len = len(self._frame_data)
        addl_len = len(self._addl_data)

        data = bytearray()
        data.append(MessageKind.FRAME_DATA)
        
        flags = self.compressed * StreamFlags.COMPRESSED
        data.append(flags)

        data.extend(bitstring.Bits(uintbe=frame_len, length=24))
        data.extend(self._frame_data)
        data.extend(bitstring.Bits(uintbe=addl_len, length=16))
        data.extend(self._addl_data)

        return bytes(data)
        


class Request(Message):
    parameters: Parameter

    def __init__(self, params: Parameter = 0):
        self.parameters = params

    def set(self, params: Parameter):
        self.parameters |= params

    def __contains__(self, params: Parameter) -> bool:
        return params in self.parameters

    def clear(self, params: Parameter):
        self.parameters &= ~params

    def clear_all(self):
        self.parameters = 0

    @classmethod
    def parse(cls, buffer: BufferedSocket) -> Optional["Request"]:
        header = buffer.read(1)
        if header is None or header != MessageKind.REQUEST:
            return None
        flags = buffer.read(2)
        if flags is None or len(flags) != 2:
            return None
        flags = bitstream.Bits(bytes=flags).unpack(["uintbe16"])[0]
        flags = Parameter(flags)
        return cls(flags)

    def format(self) -> bytes:
        b = bitstring.pack(["uintbe8", "uintbe16"], MessageKind.Request, self.parameters)
        return b.tobytes()

class Configure(Message):
    parameters: dict[Parameter, Any]

    def __init__(self, params: dict[Parameter, Any] = {}):
        self.parameters = params

    def set(self, key: Parameter, value: Any):
        self.parameters[key] = value

    def get(self, key: Parameter) -> Optional[Any]:
        if key not in self.parameters:
            return None
        return self.parameters[key]

    def __contains__(self, param: Parameter) -> bool:
        return param in self.parameters

    def clear(self, key: Parameter):
        del self.parameters[key]

    def clear_all(self):
        self.parameters = {}

   
    @classmethod
    def parse(cls, buffer: BufferedSocket) -> Optional["Configure"]:
        header = buffer.read(1)
        if header is None or header != MessageKind.CONFIGURE:
            return None
        flags = buffer.read(2)
        if flags is None or len(flags) != 2:
            return None
        flags = bitstream.Bits(bytes=flags).unpack(["uintbe16"])[0]
        flags = Parameter(flags)
        
        byte_count = flags.byte_length()
        param_data = buffer.read(byte_count)
        if param_data is None or len(param_data) != byte_count):
            return None
        
        params = flags.parse_bytes(param_data)
        return cls(params)


    def format(self) -> bytes:
        flags = 0
        for flag in self.parameters:
            flags |= flag
        param_data = Parameter.format_data(self.parameters)
        return bitstring.pack(["uintbe8", "uintbe16", "bytes"], MessageKind.CONFIGURE, flags, param_data)


class Start(Message):
    flags: StreamFlags
    frame_rate: float


    def __init__(self, flags: StreamFlags = 0, frame_rate: int = 0):
        self.flags = flags
        self.set_frame_rate(frame_rate)

    def set(self, flags: StreamFlags):
        self.flags |= flags

    def __contains__(self, flags: StreamFlags):
        return flags in self.flags

    def clear(self, flags: StreamFlags):
        self.flags &= !flags

    def clear_all_flags(self):
        self.flags = 0

    def set_frame_rate(self, frame_rate: int):
        if frame_rate < 0:
            frame_rate = 0
        self.frame_rate = frame_rate

    bitstring_format = ['uintbe8', 'uintbe8', 'floatbe32']
    
    @classmethod
    def parse(cls, buffer: BufferedSocket) -> Optional["Start"]:
        header = buffer.read(1)
        if header is None or header != MessageKind.START:
            return None
        bs = buffer.read(4)
        if bs is None or len(bs) != 4:
            return None
        bits = bitstring.Bits(bytes=bs).
        flags, frames = bits.unpack(Start.bitstring_format[1:])
        return (cls(flags, frames), 5)

    def format(self) -> bytes:
        bits = bitstring.pack(Start.bitstring_format, MessageKind.START, self.flags, self.frame_rate)
        return bits.tobytes()


class Stop(Message):
    def __init__(self): 
        # Do nothing, since this is an empty message under all circumstances
        pass

    @classmethod
    def parse(cls, buffer: BufferedSocket) -> Optional["Stop"]:
        byte = buffer.read(1)
        if byte is None or byte != MessageKind.STOP:
            return None
        return cls()

    def format(self) -> bytes:
        return bytes([MessageKind.STOP])
        
