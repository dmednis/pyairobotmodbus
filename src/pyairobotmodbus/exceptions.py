"""Exceptions for the Airobot Modbus library."""


class AirobotError(Exception):
    """Base exception for Airobot Modbus communication."""


class AirobotConnectionError(AirobotError):
    """Connection or transport-level failure."""


class AirobotTimeoutError(AirobotError, TimeoutError):
    """Timeout during Modbus communication."""


class AirobotReadError(AirobotError):
    """Modbus protocol error when reading registers."""


class AirobotWriteError(AirobotError):
    """Modbus protocol error when writing registers."""


class AirobotInvalidDataError(AirobotError):
    """Unexpected or malformed data from the device."""
