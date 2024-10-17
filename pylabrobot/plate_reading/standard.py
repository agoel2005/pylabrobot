import enum
from typing import Union, Literal


class ImagingMode(enum.Enum):
  BRIGHTFIELD = enum.auto()
  GFP = enum.auto()
  TEXAS_RED = enum.auto()
  PHASE_CONTRAST = enum.auto()
  COLOR_BRIGHTFIELD = enum.auto()


Exposure = Union[float, Literal["auto"]]
FocalPosition = Union[float, Literal["auto"]]
Gain = Union[float, Literal["auto"]]