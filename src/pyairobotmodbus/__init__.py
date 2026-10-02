"""pyairobotmodbus — Python library for Airobot ventilation units."""

import logging
from importlib.metadata import version

from .client import DEFAULT_PORT, DEFAULT_UNIT_ID, AirobotModbusClient
from .exceptions import (
    AirobotConnectionError,
    AirobotError,
    AirobotInvalidDataError,
    AirobotReadError,
    AirobotTimeoutError,
    AirobotWriteError,
)
from .models import AirobotData, ErrorFlag, OperatingMode

__version__ = version("pyairobotmodbus")

logging.getLogger(__name__).addHandler(logging.NullHandler())

__all__ = [
    "AirobotModbusClient",
    "AirobotData",
    "AirobotConnectionError",
    "AirobotError",
    "AirobotInvalidDataError",
    "AirobotReadError",
    "AirobotTimeoutError",
    "AirobotWriteError",
    "DEFAULT_PORT",
    "DEFAULT_UNIT_ID",
    "ErrorFlag",
    "OperatingMode",
    "__version__",
]
