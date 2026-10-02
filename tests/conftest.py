"""Shared test fixtures for pyairobotmodbus."""

from __future__ import annotations

import pytest
from modbus_connection.mock import MockModbusUnit, WriteEvent

from pyairobotmodbus.client import AirobotModbusClient

# A snapshot of a unit's registers, keyed by each read block's start address.
SAMPLE_INPUT: dict[int, list[int]] = {
    # firmware=300, temps=21.5, 22.0, 5.0, -1.0 (65526 is -10 signed), 0.0,
    # humidity=65.0, 60.0, 80.0, 40.0, 0.0, co2=450
    1000: [300, 215, 220, 50, 65526, 0, 650, 600, 800, 400, 0, 450],
    # fan levels 5/5, rpm 1200/1100, working time low word first:
    # 0x79FC7860 = 2046589024 ms. Both words are non-zero so a word-order
    # regression changes the result.
    1014: [5, 5, 1200, 1100, 0x7860, 0x79FC],
    # error flags (2 regs), server connected, voc
    1026: [0, 0, 1, 150],
    # pm25=2 is a single register; 1032 also reads 2 and must not be folded
    # into pm25 (that regression would yield 0x00020002 = 131074)
    1031: [2, 2, 0, 85],
    1051: [120, 115],
}
SAMPLE_HOLDING: dict[int, list[int]] = {
    2000: [1],  # automatic mode
    # humidity=60.0, co2=800, fan=5, gap, overpressure fan=5
    2003: [600, 800, 5, 0, 5, 0],
    # flags, boost timeout and overpressure timeout (low word first), ui flags
    2009: [1, 1800, 0, 1800, 0, 9],
    2015: [8, 0, 4320, 100],
    2034: [200],
    2064: [50],
}
SAMPLE_COIL: dict[int, list[bool]] = {
    4000: [True, False, False, False, False, False, False],
    4020: [False],
    4027: [False],
    4030: [False] * 7,
}


def load_sample(unit: MockModbusUnit) -> None:
    """Fill a mock unit with the sample register snapshot."""
    unit.input.update(SAMPLE_INPUT)
    unit.holding.update(SAMPLE_HOLDING)
    unit.coil.update(SAMPLE_COIL)


@pytest.fixture
def client(mock_modbus_unit: MockModbusUnit) -> AirobotModbusClient:
    """A client over an in-memory unit holding the sample snapshot."""
    load_sample(mock_modbus_unit)
    return AirobotModbusClient(mock_modbus_unit)


@pytest.fixture
def writes(mock_modbus_unit: MockModbusUnit) -> list[WriteEvent]:
    """Every write the client sends to the mock unit."""
    events: list[WriteEvent] = []
    mock_modbus_unit.on_write(events.append)
    return events
