"""Tests for AirobotModbusClient over an in-memory Modbus unit."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import pytest
from modbus_connection import (
    IllegalDataAddressError,
    ModbusConnectionError,
    ModbusError,
    ModbusProtocolError,
    ModbusTimeoutError,
)
from modbus_connection.mock import MockModbusUnit, WriteEvent

import pyairobotmodbus
from pyairobotmodbus.client import AirobotModbusClient
from pyairobotmodbus.exceptions import (
    AirobotConnectionError,
    AirobotError,
    AirobotInvalidDataError,
    AirobotReadError,
    AirobotTimeoutError,
    AirobotWriteError,
)
from pyairobotmodbus.models import ErrorFlag, OperatingMode

Call = Callable[[AirobotModbusClient], Awaitable[None]]


class TestConnection:
    def test_default_link_settings_exported(self) -> None:
        assert pyairobotmodbus.DEFAULT_PORT == 502
        assert pyairobotmodbus.DEFAULT_UNIT_ID == 1

    async def test_connected_follows_unit(self, client: AirobotModbusClient) -> None:
        # The unit opens its link on the first request, not on construction.
        assert client.connected is False
        await client.async_get_data()
        assert client.connected is True


class TestReadData:
    async def test_async_get_data(self, client: AirobotModbusClient) -> None:
        data = await client.async_get_data()

        assert data.firmware_version == 300
        assert data.extract_air_temp == pytest.approx(21.5)
        assert data.supply_air_temp == pytest.approx(22.0)
        assert data.outside_air_temp == pytest.approx(5.0)
        assert data.exhaust_air_temp == pytest.approx(-1.0)
        assert data.extra_temp == pytest.approx(0.0)
        assert data.extract_air_humidity == pytest.approx(65.0)
        assert data.supply_air_humidity == pytest.approx(60.0)
        assert data.co2_level == 450
        assert data.supply_fan_level == 5
        assert data.extract_fan_level == 5
        assert data.supply_fan_rpm == 1200
        assert data.extract_fan_rpm == 1100
        assert data.working_time_ms == 2046589024
        assert data.error_flags == ErrorFlag.NONE
        assert data.server_connected is True
        assert data.voc == 150
        assert data.pm25 == 2
        assert data.heat_recovery_efficiency == 85
        assert data.supply_airflow == 120
        assert data.extract_airflow == 115
        assert data.operating_mode == OperatingMode.AUTOMATIC
        assert data.humidity_setpoint == pytest.approx(60.0)
        assert data.co2_setpoint == 800
        assert data.manual_fan_level == 5
        assert data.boost_timeout == 1800
        assert data.overpressure_timeout == 1800
        assert data.filter_reminder_interval == 4320
        assert data.voc_setpoint == 200
        assert data.pm25_setpoint == 50
        assert data.power_on is True
        assert data.bypass_on is False
        assert data.boost_on is False
        assert data.filter_alert is False

    async def test_extra_sensors_absent_decode_to_none(
        self, client: AirobotModbusClient, mock_modbus_unit: MockModbusUnit
    ) -> None:
        # 32767 (3276.7 °C) and 0xFFFF (-0.1 %) are the sentinels the device
        # reports when the optional extra sensors are not installed.
        mock_modbus_unit.input[1005] = 32767
        mock_modbus_unit.input[1010] = 0xFFFF

        data = await client.async_get_data()

        assert data.extra_temp is None
        assert data.extra_humidity is None
        # A real (non-sentinel) reading is still decoded normally.
        assert data.extract_air_temp == pytest.approx(21.5)

    @pytest.mark.parametrize(
        ("space", "address", "action"),
        [
            pytest.param("input", 1000, "reading input register 1000", id="input"),
            pytest.param("holding", 2000, "reading register 2000", id="holding"),
            pytest.param("coil", 4000, "reading coil 4000", id="coil"),
        ],
    )
    @pytest.mark.parametrize(
        ("error", "expected", "prefix"),
        [
            pytest.param(
                IllegalDataAddressError(),
                AirobotReadError,
                "Modbus error",
                id="exception_response",
            ),
            pytest.param(
                ModbusTimeoutError("timed out"),
                AirobotTimeoutError,
                "Timeout",
                id="timeout",
            ),
            pytest.param(
                ModbusConnectionError("connection reset"),
                AirobotConnectionError,
                "Communication error",
                id="connection",
            ),
            pytest.param(
                ModbusProtocolError("bad frame"),
                AirobotConnectionError,
                "Communication error",
                id="protocol",
            ),
        ],
    )
    async def test_read_failure(
        self,
        client: AirobotModbusClient,
        mock_modbus_unit: MockModbusUnit,
        space: Any,
        address: int,
        action: str,
        error: ModbusError,
        expected: type[AirobotError],
        prefix: str,
    ) -> None:
        mock_modbus_unit.fail_read(address, error, register_type=space)
        with pytest.raises(expected, match=f"^{prefix} {action}") as exc_info:
            await client.async_get_data()
        assert exc_info.value.__cause__ is error

    @pytest.mark.parametrize(
        ("method", "match"),
        [
            pytest.param("read_input_registers", "Expected 12.*got 11", id="input"),
            pytest.param("read_holding_registers", "Expected 1.*got 0", id="holding"),
            pytest.param("read_coils", "Expected 7.*got 6", id="coil"),
        ],
    )
    async def test_short_response(
        self,
        client: AirobotModbusClient,
        mock_modbus_unit: MockModbusUnit,
        monkeypatch: pytest.MonkeyPatch,
        method: str,
        match: str,
    ) -> None:
        read = getattr(mock_modbus_unit, method)

        async def short_read(address: int, count: int) -> list[Any]:
            return list(await read(address, count))[:-1]

        monkeypatch.setattr(mock_modbus_unit, method, short_read)
        with pytest.raises(AirobotInvalidDataError, match=match):
            await client.async_get_data()


class TestWriteData:
    @pytest.mark.parametrize(
        ("call", "event"),
        [
            pytest.param(
                lambda c: c.async_set_mode(OperatingMode.MANUAL),
                WriteEvent("holding", 2000, [2], 0x06),
                id="mode",
            ),
            pytest.param(
                lambda c: c.async_set_fan_speed(7),
                WriteEvent("holding", 2005, [7], 0x06),
                id="fan_speed",
            ),
            pytest.param(
                lambda c: c.async_set_overpressure_fan_level(8),
                WriteEvent("holding", 2007, [8], 0x06),
                id="overpressure_fan_level",
            ),
            pytest.param(
                lambda c: c.async_set_co2_setpoint(1000),
                WriteEvent("holding", 2004, [1000], 0x06),
                id="co2_setpoint",
            ),
            pytest.param(
                lambda c: c.async_set_humidity_setpoint(65.0),
                WriteEvent("holding", 2003, [650], 0x06),
                id="humidity_setpoint",
            ),
            pytest.param(
                lambda c: c.async_set_voc_setpoint(300),
                WriteEvent("holding", 2034, [300], 0x06),
                id="voc_setpoint",
            ),
            pytest.param(
                lambda c: c.async_set_pm25_setpoint(100),
                WriteEvent("holding", 2064, [100], 0x06),
                id="pm25_setpoint",
            ),
            pytest.param(
                lambda c: c.async_set_boost_timeout(600),
                WriteEvent("holding", 2010, [600], 0x06),
                id="boost_timeout",
            ),
            pytest.param(
                lambda c: c.async_set_overpressure_timeout(900),
                WriteEvent("holding", 2012, [900], 0x06),
                id="overpressure_timeout",
            ),
            pytest.param(
                lambda c: c.async_set_filter_reminder_interval(2000),
                WriteEvent("holding", 2017, [2000], 0x06),
                id="filter_reminder_interval",
            ),
            pytest.param(
                lambda c: c.async_reset_filter_timer(),
                WriteEvent("holding", 2018, [0], 0x06),
                id="reset_filter_timer",
            ),
            pytest.param(
                lambda c: c.async_set_power(False),
                WriteEvent("coil", 4000, [False], 0x05),
                id="power",
            ),
            pytest.param(
                lambda c: c.async_set_bypass(True),
                WriteEvent("coil", 4003, [True], 0x05),
                id="bypass",
            ),
            pytest.param(
                lambda c: c.async_set_boost(True),
                WriteEvent("coil", 4004, [True], 0x05),
                id="boost",
            ),
            pytest.param(
                lambda c: c.async_set_overpressure(True),
                WriteEvent("coil", 4005, [True], 0x05),
                id="overpressure",
            ),
            pytest.param(
                lambda c: c.async_reboot(),
                WriteEvent("coil", 4006, [True], 0x05),
                id="reboot",
            ),
            pytest.param(
                lambda c: c.async_set_humidity_control(True),
                WriteEvent("coil", 4027, [True], 0x05),
                id="humidity_control",
            ),
            pytest.param(
                lambda c: c.async_set_voc_control(True),
                WriteEvent("coil", 4030, [True], 0x05),
                id="voc_control",
            ),
            pytest.param(
                lambda c: c.async_set_pm_control(True),
                WriteEvent("coil", 4031, [True], 0x05),
                id="pm_control",
            ),
        ],
    )
    async def test_setter(
        self,
        client: AirobotModbusClient,
        writes: list[WriteEvent],
        call: Call,
        event: WriteEvent,
    ) -> None:
        await call(client)
        assert writes == [event]

    @pytest.mark.parametrize(
        "call",
        [
            pytest.param(lambda c: c.async_set_fan_speed(15), id="fan_speed"),
            # 990 raw > 950
            pytest.param(lambda c: c.async_set_humidity_setpoint(99.0), id="humidity"),
        ],
    )
    async def test_setter_out_of_range(
        self, client: AirobotModbusClient, writes: list[WriteEvent], call: Call
    ) -> None:
        with pytest.raises(AirobotWriteError, match="out of range"):
            await call(client)
        assert writes == []

    @pytest.mark.parametrize(
        ("call", "space", "address", "action"),
        [
            pytest.param(
                lambda c: c.async_set_mode(OperatingMode.AUTOMATIC),
                "holding",
                2000,
                "writing register 2000",
                id="register",
            ),
            pytest.param(
                lambda c: c.async_set_power(True),
                "coil",
                4000,
                "writing coil 4000",
                id="coil",
            ),
        ],
    )
    @pytest.mark.parametrize(
        ("error", "expected", "prefix"),
        [
            pytest.param(
                IllegalDataAddressError(),
                AirobotWriteError,
                "Modbus error",
                id="exception_response",
            ),
            pytest.param(
                ModbusTimeoutError("timed out"),
                AirobotTimeoutError,
                "Timeout",
                id="timeout",
            ),
            pytest.param(
                ModbusConnectionError("connection reset"),
                AirobotConnectionError,
                "Communication error",
                id="connection",
            ),
        ],
    )
    async def test_write_failure(
        self,
        client: AirobotModbusClient,
        mock_modbus_unit: MockModbusUnit,
        call: Call,
        space: Any,
        address: int,
        action: str,
        error: ModbusError,
        expected: type[AirobotError],
        prefix: str,
    ) -> None:
        mock_modbus_unit.fail_write(address, error, register_type=space)
        with pytest.raises(expected, match=f"^{prefix} {action}") as exc_info:
            await call(client)
        assert exc_info.value.__cause__ is error


class TestHelpers:
    def test_combine_u32(self) -> None:
        # Device transmits the low word first (little-endian word order):
        # the lower register address holds the least-significant 16 bits.
        assert AirobotModbusClient._combine_u32([0x0000, 0x0001], 0) == 65536
        assert AirobotModbusClient._combine_u32([0xFFFF, 0xFFFF], 0) == 4294967295
        assert AirobotModbusClient._combine_u32([0, 0], 0) == 0
        # Regression guard with distinct words, captured from a real unit:
        # reg=0x7860 (low), reg+1=0x79FC (high) -> 0x79FC7860 = 2046589024
        assert AirobotModbusClient._combine_u32([0x7860, 0x79FC], 0) == 2046589024

    def test_to_signed16(self) -> None:
        assert AirobotModbusClient._to_signed16(0) == 0
        assert AirobotModbusClient._to_signed16(100) == 100
        assert AirobotModbusClient._to_signed16(65526) == -10
        assert AirobotModbusClient._to_signed16(0x8000) == -32768
        assert AirobotModbusClient._to_signed16(0x7FFF) == 32767

    def test_scale_temp(self) -> None:
        assert AirobotModbusClient._scale_temp(215) == pytest.approx(21.5)
        assert AirobotModbusClient._scale_temp(-10) == pytest.approx(-1.0)
        assert AirobotModbusClient._scale_temp(0) == pytest.approx(0.0)
