"""Shared test fixtures for pyairobotmodbus."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pyairobotmodbus.client import AirobotModbusClient


def make_register_result(registers: list[int]) -> MagicMock:
    """Create a mock Modbus register response."""
    result = MagicMock()
    result.isError.return_value = False
    result.registers = registers
    return result


def make_coil_result(bits: list[bool]) -> MagicMock:
    """Create a mock Modbus coil response."""
    result = MagicMock()
    result.isError.return_value = False
    result.bits = bits + [False] * (16 - len(bits))
    return result


def make_error_result() -> MagicMock:
    """Create a mock Modbus error response."""
    result = MagicMock()
    result.isError.return_value = True
    result.configure_mock(__str__=lambda self: "Modbus Error")
    return result


def make_write_result() -> MagicMock:
    """Create a mock successful write response."""
    result = MagicMock()
    result.isError.return_value = False
    return result


@pytest.fixture
def mock_modbus_client() -> Any:
    """Create a client with a mocked underlying pymodbus client."""
    with patch("pyairobotmodbus.client.AsyncModbusTcpClient") as mock_cls:
        mock_modbus = AsyncMock()
        mock_modbus.connected = True
        mock_modbus.connect = AsyncMock(return_value=True)
        mock_cls.return_value = mock_modbus
        c = AirobotModbusClient("192.168.1.100")
        yield c, mock_modbus
