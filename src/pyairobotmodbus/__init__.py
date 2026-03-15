"""pyairobotmodbus — Python library for Airobot ventilation units."""

from .client import AirobotModbusClient
from .exceptions import (
    AirobotConnectionError,
    AirobotError,
    AirobotReadError,
    AirobotWriteError,
)
from .models import AirobotData, ErrorFlag, OperatingMode

__all__ = [
    "AirobotModbusClient",
    "AirobotData",
    "AirobotConnectionError",
    "AirobotError",
    "AirobotReadError",
    "AirobotWriteError",
    "ErrorFlag",
    "OperatingMode",
]
