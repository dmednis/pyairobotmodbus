"""Tests for AirobotModbusClient with mocked pymodbus."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from conftest import (
    make_coil_result,
    make_error_result,
    make_register_result,
    make_write_result,
)
from pymodbus import ModbusException

from pyairobotmodbus.client import AirobotModbusClient
from pyairobotmodbus.exceptions import (
    AirobotConnectionError,
    AirobotInvalidDataError,
    AirobotReadError,
    AirobotTimeoutError,
    AirobotWriteError,
)
from pyairobotmodbus.models import ErrorFlag, OperatingMode


class TestConnection:
    @pytest.mark.asyncio
    async def test_connect_success(self, mock_modbus_client: Any) -> None:
        c, mock = mock_modbus_client
        await c.connect()
        mock.connect.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_connect_failure(self, mock_modbus_client: Any) -> None:
        c, mock = mock_modbus_client
        mock.connect.return_value = False
        with pytest.raises(AirobotConnectionError):
            await c.connect()

    @pytest.mark.asyncio
    async def test_disconnect(self, mock_modbus_client: Any) -> None:
        c, mock = mock_modbus_client
        await c.disconnect()
        mock.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_read_when_not_connected(self, mock_modbus_client: Any) -> None:
        c, mock = mock_modbus_client
        mock.connected = False
        with pytest.raises(AirobotConnectionError, match="Not connected"):
            await c.async_get_data()

    @pytest.mark.asyncio
    async def test_write_register_when_not_connected(
        self, mock_modbus_client: Any
    ) -> None:
        c, mock = mock_modbus_client
        mock.connected = False
        with pytest.raises(AirobotConnectionError, match="Not connected"):
            await c.async_set_mode(OperatingMode.MANUAL)

    @pytest.mark.asyncio
    async def test_write_coil_when_not_connected(self, mock_modbus_client: Any) -> None:
        c, mock = mock_modbus_client
        mock.connected = False
        with pytest.raises(AirobotConnectionError, match="Not connected"):
            await c.async_set_power(True)


class TestReadData:
    @pytest.mark.asyncio
    async def test_async_get_data(self, mock_modbus_client: Any) -> None:
        c, mock = mock_modbus_client

        # Sensor block 1: 1000-1011 (12 registers)
        # firmware=300, temps=215,220,50,-10,0, humidity=650,600,800,400,0, co2=450
        s1 = [300, 215, 220, 50, 65526, 0, 650, 600, 800, 400, 0, 450]
        # 65526 unsigned = -10 signed (0x10000 - 10 = 65526)

        # Sensor block 2: 1014-1019 (6 registers)
        # supply_fan=5, extract_fan=5, supply_rpm=1200, extract_rpm=1100,
        # working_time: low word first (little-endian). reg1018=0x7860 (low),
        # reg1019=0x79FC (high) -> 0x79FC7860 = 2046589024 ms. Both words are
        # non-zero so a word-order regression changes the result.
        s2 = [5, 5, 1200, 1100, 0x7860, 0x79FC]  # working_time = 2046589024 ms

        # Sensor block 3: 1026-1029 (4 registers)
        # errors=0 (2 regs), server_connected=1, voc=150
        s3 = [0, 0, 1, 150]

        # Sensor block 4: 1031-1034 (4 registers)
        # pm25=2 (single 16-bit reg at 1031); 1032 is a separate
        # register that also reads 2 — must NOT be folded into pm25
        # (regression: would yield 0x00020002 = 131074)
        s4 = [2, 2, 0, 85]

        # Sensor block 5: 1051-1052 (2 registers)
        s5 = [120, 115]

        # Settings block 1: 2000 (1 register)
        r1 = [1]  # automatic mode

        # Settings block 2: 2003-2008 (6 registers)
        # humidity=60.0, co2=800, fan=5, gap, overpressure_fan=5
        r2 = [600, 800, 5, 0, 5, 0]

        # Settings block 3: 2009-2014 (6 registers)
        # flags=1, boost_timeout=1800 (2 regs, low word first),
        # overpressure_timeout=1800 (2 regs, low word first), ui_flags=9.
        # The value lands in the low word (base register) — exactly what
        # write_register targets, so read and write stay consistent.
        r3 = [1, 1800, 0, 1800, 0, 9]

        # Settings block 4: 2015-2018 (4 registers)
        r4 = [8, 0, 4320, 100]

        # Settings block 5: 2034 (1 register)
        r5 = [200]

        # Settings block 6: 2064 (1 register)
        r6 = [50]

        # Sensor blocks use input registers (FC04)
        mock.read_input_registers = AsyncMock(
            side_effect=[
                make_register_result(s1),
                make_register_result(s2),
                make_register_result(s3),
                make_register_result(s4),
                make_register_result(s5),
            ]
        )

        # Settings blocks use holding registers (FC03)
        mock.read_holding_registers = AsyncMock(
            side_effect=[
                make_register_result(r1),
                make_register_result(r2),
                make_register_result(r3),
                make_register_result(r4),
                make_register_result(r5),
                make_register_result(r6),
            ]
        )

        # Coil blocks
        c1 = [True, False, False, False, False, False, False]  # power on
        c2 = [False]  # no filter alert
        c3 = [False]  # humidity control off
        c4 = [False, False, False, False, False, False, False]  # all off

        mock.read_coils = AsyncMock(
            side_effect=[
                make_coil_result(c1),
                make_coil_result(c2),
                make_coil_result(c3),
                make_coil_result(c4),
            ]
        )

        data = await c.async_get_data()

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

    @pytest.mark.asyncio
    async def test_extra_sensors_absent_decode_to_none(
        self, mock_modbus_client: Any
    ) -> None:
        c, mock = mock_modbus_client

        # extra temp raw 32767 (0x7FFF -> 3276.7 °C) and extra humidity raw
        # 0xFFFF (-1 -> -0.1 %) are the sentinels the device reports when the
        # optional sensors are not installed.
        s1 = [300, 215, 220, 50, 65526, 32767, 650, 600, 800, 400, 0xFFFF, 450]
        s2 = [5, 5, 1200, 1100, 0x7860, 0x79FC]
        s3 = [0, 0, 1, 150]
        s4 = [2, 2, 0, 85]
        s5 = [120, 115]
        r1 = [1]
        r2 = [600, 800, 5, 0, 5, 0]
        r3 = [1, 1800, 0, 1800, 0, 9]
        r4 = [8, 0, 4320, 100]
        r5 = [200]
        r6 = [50]

        mock.read_input_registers = AsyncMock(
            side_effect=[make_register_result(b) for b in (s1, s2, s3, s4, s5)]
        )
        mock.read_holding_registers = AsyncMock(
            side_effect=[make_register_result(b) for b in (r1, r2, r3, r4, r5, r6)]
        )
        mock.read_coils = AsyncMock(
            side_effect=[
                make_coil_result([True, False, False, False, False, False, False]),
                make_coil_result([False]),
                make_coil_result([False]),
                make_coil_result([False] * 7),
            ]
        )

        data = await c.async_get_data()

        assert data.extra_temp is None
        assert data.extra_humidity is None
        # A real (non-sentinel) extra reading is still decoded normally.
        assert data.extract_air_temp == pytest.approx(21.5)

    @pytest.mark.asyncio
    async def test_read_error(self, mock_modbus_client: Any) -> None:
        c, mock = mock_modbus_client
        mock.read_input_registers = AsyncMock(return_value=make_error_result())
        with pytest.raises(AirobotReadError):
            await c.async_get_data()


class TestWriteData:
    @pytest.mark.asyncio
    async def test_set_mode(self, mock_modbus_client: Any) -> None:
        c, mock = mock_modbus_client
        mock.write_register = AsyncMock(return_value=make_write_result())
        await c.async_set_mode(OperatingMode.MANUAL)
        mock.write_register.assert_awaited_once_with(address=2000, value=2, device_id=1)

    @pytest.mark.asyncio
    async def test_set_fan_speed(self, mock_modbus_client: Any) -> None:
        c, mock = mock_modbus_client
        mock.write_register = AsyncMock(return_value=make_write_result())
        await c.async_set_fan_speed(7)
        mock.write_register.assert_awaited_once_with(address=2005, value=7, device_id=1)

    @pytest.mark.asyncio
    async def test_set_fan_speed_out_of_range(self, mock_modbus_client: Any) -> None:
        c, mock = mock_modbus_client
        with pytest.raises(AirobotWriteError, match="out of range"):
            await c.async_set_fan_speed(15)

    @pytest.mark.asyncio
    async def test_set_humidity_setpoint(self, mock_modbus_client: Any) -> None:
        c, mock = mock_modbus_client
        mock.write_register = AsyncMock(return_value=make_write_result())
        await c.async_set_humidity_setpoint(65.0)
        mock.write_register.assert_awaited_once_with(
            address=2003, value=650, device_id=1
        )

    @pytest.mark.asyncio
    async def test_set_humidity_setpoint_out_of_range(
        self, mock_modbus_client: Any
    ) -> None:
        c, mock = mock_modbus_client
        with pytest.raises(AirobotWriteError, match="out of range"):
            await c.async_set_humidity_setpoint(99.0)  # 990 > 950

    @pytest.mark.asyncio
    async def test_set_co2_setpoint(self, mock_modbus_client: Any) -> None:
        c, mock = mock_modbus_client
        mock.write_register = AsyncMock(return_value=make_write_result())
        await c.async_set_co2_setpoint(1000)
        mock.write_register.assert_awaited_once_with(
            address=2004, value=1000, device_id=1
        )

    @pytest.mark.asyncio
    async def test_set_power(self, mock_modbus_client: Any) -> None:
        c, mock = mock_modbus_client
        mock.write_coil = AsyncMock(return_value=make_write_result())
        await c.async_set_power(False)
        mock.write_coil.assert_awaited_once_with(address=4000, value=False, device_id=1)

    @pytest.mark.asyncio
    async def test_set_boost(self, mock_modbus_client: Any) -> None:
        c, mock = mock_modbus_client
        mock.write_coil = AsyncMock(return_value=make_write_result())
        await c.async_set_boost(True)
        mock.write_coil.assert_awaited_once_with(address=4004, value=True, device_id=1)

    @pytest.mark.asyncio
    async def test_reboot(self, mock_modbus_client: Any) -> None:
        c, mock = mock_modbus_client
        mock.write_coil = AsyncMock(return_value=make_write_result())
        await c.async_reboot()
        mock.write_coil.assert_awaited_once_with(address=4006, value=True, device_id=1)

    @pytest.mark.asyncio
    async def test_write_error(self, mock_modbus_client: Any) -> None:
        c, mock = mock_modbus_client
        mock.write_register = AsyncMock(return_value=make_error_result())
        with pytest.raises(AirobotWriteError):
            await c.async_set_mode(OperatingMode.AUTOMATIC)


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


class TestRegisterValidation:
    @pytest.mark.asyncio
    async def test_input_register_count_mismatch(self, mock_modbus_client: Any) -> None:
        c, mock = mock_modbus_client
        # Return 5 registers when 12 expected (SENSOR_BLOCK_1)
        mock.read_input_registers = AsyncMock(
            return_value=make_register_result([0, 0, 0, 0, 0])
        )
        with pytest.raises(AirobotInvalidDataError, match="Expected 12.*got 5"):
            await c.async_get_data()

    @pytest.mark.asyncio
    async def test_holding_register_count_mismatch(
        self, mock_modbus_client: Any
    ) -> None:
        c, mock = mock_modbus_client
        # Input registers return correct data
        mock.read_input_registers = AsyncMock(
            side_effect=[
                make_register_result([0] * 12),
                make_register_result([0] * 6),
                make_register_result([0] * 4),
                make_register_result([0] * 4),
                make_register_result([0] * 2),
            ]
        )
        # First holding register read returns wrong count
        mock.read_holding_registers = AsyncMock(
            return_value=make_register_result([0, 0, 0])  # expected 1
        )
        with pytest.raises(AirobotInvalidDataError, match="Expected 1.*got 3"):
            await c.async_get_data()

    @pytest.mark.asyncio
    async def test_coil_count_mismatch(self, mock_modbus_client: Any) -> None:
        """Short coil responses must raise AirobotInvalidDataError, not IndexError."""
        c, mock = mock_modbus_client
        # Input and holding registers return correct data
        mock.read_input_registers = AsyncMock(
            side_effect=[
                make_register_result([0] * 12),
                make_register_result([0] * 6),
                make_register_result([0] * 4),
                make_register_result([0] * 4),
                make_register_result([0] * 2),
            ]
        )
        mock.read_holding_registers = AsyncMock(
            side_effect=[
                make_register_result([1]),  # SETTINGS_BLOCK_1 (1 reg)
                make_register_result([0] * 6),  # SETTINGS_BLOCK_2
                make_register_result([0] * 6),  # SETTINGS_BLOCK_3
                make_register_result([0] * 4),  # SETTINGS_BLOCK_4
                make_register_result([0]),  # SETTINGS_BLOCK_5
                make_register_result([0]),  # SETTINGS_BLOCK_6
            ]
        )
        # First coil read returns too few bits (expected 7 for COIL_BLOCK_1)
        # Use raw mock (not make_coil_result) to avoid padding to 16 bits
        short_coil = MagicMock()
        short_coil.isError.return_value = False
        short_coil.bits = [True, False]  # only 2 bits, no padding
        mock.read_coils = AsyncMock(return_value=short_coil)
        with pytest.raises(AirobotInvalidDataError, match="Expected 7.*got 2"):
            await c.async_get_data()


class TestContextManager:
    @pytest.mark.asyncio
    async def test_context_manager_happy_path(self, mock_modbus_client: Any) -> None:
        c, mock = mock_modbus_client
        async with c:
            mock.connect.assert_awaited_once()
            assert c.connected

        mock.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_context_manager_connect_failure(
        self, mock_modbus_client: Any
    ) -> None:
        c, mock = mock_modbus_client
        mock.connect.return_value = False
        with pytest.raises(AirobotConnectionError):
            async with c:
                pass


class TestFactoryMethod:
    @pytest.mark.asyncio
    async def test_create_success(self, mock_modbus_client: Any) -> None:
        _, mock = mock_modbus_client
        with patch("pyairobotmodbus.client.AsyncModbusTcpClient") as mock_cls:
            mock_modbus = AsyncMock()
            mock_modbus.connected = True
            mock_modbus.connect = AsyncMock(return_value=True)
            mock_cls.return_value = mock_modbus

            c = await AirobotModbusClient.create("192.168.1.100")
            mock_modbus.connect.assert_awaited_once()
            assert c.host == "192.168.1.100"

    @pytest.mark.asyncio
    async def test_create_failure(self, mock_modbus_client: Any) -> None:
        _, mock = mock_modbus_client
        with patch("pyairobotmodbus.client.AsyncModbusTcpClient") as mock_cls:
            mock_modbus = AsyncMock()
            mock_modbus.connect = AsyncMock(return_value=False)
            mock_cls.return_value = mock_modbus

            with pytest.raises(AirobotConnectionError):
                await AirobotModbusClient.create("192.168.1.100")

    @pytest.mark.asyncio
    async def test_create_custom_params(self, mock_modbus_client: Any) -> None:
        _, mock = mock_modbus_client
        with patch("pyairobotmodbus.client.AsyncModbusTcpClient") as mock_cls:
            mock_modbus = AsyncMock()
            mock_modbus.connected = True
            mock_modbus.connect = AsyncMock(return_value=True)
            mock_cls.return_value = mock_modbus

            c = await AirobotModbusClient.create(
                "10.0.0.1", port=5020, device_id=2, timeout=30
            )
            assert c.host == "10.0.0.1"
            assert c.port == 5020


class TestEnhancedErrorHandling:
    @pytest.mark.asyncio
    async def test_connect_timeout(self, mock_modbus_client: Any) -> None:
        c, mock = mock_modbus_client
        mock.connect = AsyncMock(side_effect=TimeoutError("timed out"))
        with pytest.raises(AirobotTimeoutError):
            await c.connect()

    @pytest.mark.asyncio
    async def test_connect_os_error(self, mock_modbus_client: Any) -> None:
        c, mock = mock_modbus_client
        mock.connect = AsyncMock(side_effect=OSError("network unreachable"))
        with pytest.raises(AirobotConnectionError):
            await c.connect()

    @pytest.mark.asyncio
    async def test_read_timeout(self, mock_modbus_client: Any) -> None:
        c, mock = mock_modbus_client
        mock.read_input_registers = AsyncMock(side_effect=TimeoutError("read timeout"))
        with pytest.raises(AirobotTimeoutError):
            await c.async_get_data()

    @pytest.mark.asyncio
    async def test_write_timeout(self, mock_modbus_client: Any) -> None:
        c, mock = mock_modbus_client
        mock.write_register = AsyncMock(side_effect=TimeoutError("write timeout"))
        with pytest.raises(AirobotTimeoutError):
            await c.async_set_mode(OperatingMode.MANUAL)

    @pytest.mark.asyncio
    async def test_write_coil_timeout(self, mock_modbus_client: Any) -> None:
        c, mock = mock_modbus_client
        mock.write_coil = AsyncMock(side_effect=TimeoutError("write timeout"))
        with pytest.raises(AirobotTimeoutError):
            await c.async_set_power(True)

    @pytest.mark.asyncio
    async def test_connect_modbus_exception(self, mock_modbus_client: Any) -> None:
        c, mock = mock_modbus_client
        exc = ModbusException("modbus failure")  # type: ignore[no-untyped-call]
        mock.connect = AsyncMock(side_effect=exc)
        with pytest.raises(AirobotConnectionError, match="Failed to connect"):
            await c.connect()

    @pytest.mark.asyncio
    async def test_read_input_modbus_exception(self, mock_modbus_client: Any) -> None:
        c, mock = mock_modbus_client
        mock.read_input_registers = AsyncMock(
            side_effect=ModbusException("comm error")  # type: ignore[no-untyped-call]
        )
        with pytest.raises(AirobotConnectionError, match="Communication error"):
            await c.async_get_data()

    @pytest.mark.asyncio
    async def test_read_holding_timeout(self, mock_modbus_client: Any) -> None:
        c, mock = mock_modbus_client
        # Input registers succeed, holding registers timeout
        mock.read_input_registers = AsyncMock(
            side_effect=[
                make_register_result([0] * 12),
                make_register_result([0] * 6),
                make_register_result([0] * 4),
                make_register_result([0] * 4),
                make_register_result([0] * 2),
            ]
        )
        mock.read_holding_registers = AsyncMock(
            side_effect=TimeoutError("holding timeout")
        )
        with pytest.raises(AirobotTimeoutError, match="Timeout reading register"):
            await c.async_get_data()

    @pytest.mark.asyncio
    async def test_read_holding_modbus_exception(self, mock_modbus_client: Any) -> None:
        c, mock = mock_modbus_client
        mock.read_input_registers = AsyncMock(
            side_effect=[
                make_register_result([0] * 12),
                make_register_result([0] * 6),
                make_register_result([0] * 4),
                make_register_result([0] * 4),
                make_register_result([0] * 2),
            ]
        )
        mock.read_holding_registers = AsyncMock(
            side_effect=ModbusException("comm error")  # type: ignore[no-untyped-call]
        )
        with pytest.raises(AirobotConnectionError, match="Communication error"):
            await c.async_get_data()

    @pytest.mark.asyncio
    async def test_read_holding_error_result(self, mock_modbus_client: Any) -> None:
        c, mock = mock_modbus_client
        mock.read_input_registers = AsyncMock(
            side_effect=[
                make_register_result([0] * 12),
                make_register_result([0] * 6),
                make_register_result([0] * 4),
                make_register_result([0] * 4),
                make_register_result([0] * 2),
            ]
        )
        mock.read_holding_registers = AsyncMock(return_value=make_error_result())
        with pytest.raises(AirobotReadError, match="Modbus error reading register"):
            await c.async_get_data()

    @pytest.mark.asyncio
    async def test_read_coils_timeout(self, mock_modbus_client: Any) -> None:
        c, mock = mock_modbus_client
        mock.read_input_registers = AsyncMock(
            side_effect=[
                make_register_result([0] * 12),
                make_register_result([0] * 6),
                make_register_result([0] * 4),
                make_register_result([0] * 4),
                make_register_result([0] * 2),
            ]
        )
        mock.read_holding_registers = AsyncMock(
            side_effect=[
                make_register_result([1]),
                make_register_result([0] * 6),
                make_register_result([0] * 6),
                make_register_result([0] * 4),
                make_register_result([0]),
                make_register_result([0]),
            ]
        )
        mock.read_coils = AsyncMock(side_effect=TimeoutError("coil timeout"))
        with pytest.raises(AirobotTimeoutError, match="Timeout reading register"):
            await c.async_get_data()

    @pytest.mark.asyncio
    async def test_read_coils_modbus_exception(self, mock_modbus_client: Any) -> None:
        c, mock = mock_modbus_client
        mock.read_input_registers = AsyncMock(
            side_effect=[
                make_register_result([0] * 12),
                make_register_result([0] * 6),
                make_register_result([0] * 4),
                make_register_result([0] * 4),
                make_register_result([0] * 2),
            ]
        )
        mock.read_holding_registers = AsyncMock(
            side_effect=[
                make_register_result([1]),
                make_register_result([0] * 6),
                make_register_result([0] * 6),
                make_register_result([0] * 4),
                make_register_result([0]),
                make_register_result([0]),
            ]
        )
        exc = ModbusException("comm error")  # type: ignore[no-untyped-call]
        mock.read_coils = AsyncMock(side_effect=exc)
        with pytest.raises(AirobotConnectionError, match="Communication error"):
            await c.async_get_data()

    @pytest.mark.asyncio
    async def test_read_coils_error_result(self, mock_modbus_client: Any) -> None:
        c, mock = mock_modbus_client
        mock.read_input_registers = AsyncMock(
            side_effect=[
                make_register_result([0] * 12),
                make_register_result([0] * 6),
                make_register_result([0] * 4),
                make_register_result([0] * 4),
                make_register_result([0] * 2),
            ]
        )
        mock.read_holding_registers = AsyncMock(
            side_effect=[
                make_register_result([1]),
                make_register_result([0] * 6),
                make_register_result([0] * 6),
                make_register_result([0] * 4),
                make_register_result([0]),
                make_register_result([0]),
            ]
        )
        mock.read_coils = AsyncMock(return_value=make_error_result())
        with pytest.raises(AirobotReadError, match="Modbus error reading coil"):
            await c.async_get_data()

    @pytest.mark.asyncio
    async def test_write_register_modbus_exception(
        self, mock_modbus_client: Any
    ) -> None:
        c, mock = mock_modbus_client
        mock.write_register = AsyncMock(
            side_effect=ModbusException("comm error")  # type: ignore[no-untyped-call]
        )
        with pytest.raises(AirobotConnectionError, match="Communication error"):
            await c.async_set_mode(OperatingMode.MANUAL)

    @pytest.mark.asyncio
    async def test_write_coil_modbus_exception(self, mock_modbus_client: Any) -> None:
        c, mock = mock_modbus_client
        mock.write_coil = AsyncMock(
            side_effect=ModbusException("comm error")  # type: ignore[no-untyped-call]
        )
        with pytest.raises(AirobotConnectionError, match="Communication error"):
            await c.async_set_power(True)

    @pytest.mark.asyncio
    async def test_write_coil_error_result(self, mock_modbus_client: Any) -> None:
        c, mock = mock_modbus_client
        mock.write_coil = AsyncMock(return_value=make_error_result())
        with pytest.raises(AirobotWriteError, match="Modbus error writing coil"):
            await c.async_set_power(True)

    @pytest.mark.asyncio
    async def test_read_input_os_error(self, mock_modbus_client: Any) -> None:
        c, mock = mock_modbus_client
        mock.read_input_registers = AsyncMock(
            side_effect=ConnectionResetError("connection reset")
        )
        with pytest.raises(AirobotConnectionError, match="Communication error"):
            await c.async_get_data()

    @pytest.mark.asyncio
    async def test_read_holding_os_error(self, mock_modbus_client: Any) -> None:
        c, mock = mock_modbus_client
        mock.read_input_registers = AsyncMock(
            side_effect=[
                make_register_result([0] * 12),
                make_register_result([0] * 6),
                make_register_result([0] * 4),
                make_register_result([0] * 4),
                make_register_result([0] * 2),
            ]
        )
        mock.read_holding_registers = AsyncMock(
            side_effect=ConnectionResetError("connection reset")
        )
        with pytest.raises(AirobotConnectionError, match="Communication error"):
            await c.async_get_data()

    @pytest.mark.asyncio
    async def test_read_coils_os_error(self, mock_modbus_client: Any) -> None:
        c, mock = mock_modbus_client
        mock.read_input_registers = AsyncMock(
            side_effect=[
                make_register_result([0] * 12),
                make_register_result([0] * 6),
                make_register_result([0] * 4),
                make_register_result([0] * 4),
                make_register_result([0] * 2),
            ]
        )
        mock.read_holding_registers = AsyncMock(
            side_effect=[
                make_register_result([1]),
                make_register_result([0] * 6),
                make_register_result([0] * 6),
                make_register_result([0] * 4),
                make_register_result([0]),
                make_register_result([0]),
            ]
        )
        mock.read_coils = AsyncMock(
            side_effect=ConnectionResetError("connection reset")
        )
        with pytest.raises(AirobotConnectionError, match="Communication error"):
            await c.async_get_data()

    @pytest.mark.asyncio
    async def test_write_register_os_error(self, mock_modbus_client: Any) -> None:
        c, mock = mock_modbus_client
        mock.write_register = AsyncMock(
            side_effect=ConnectionResetError("connection reset")
        )
        with pytest.raises(AirobotConnectionError, match="Communication error"):
            await c.async_set_mode(OperatingMode.MANUAL)

    @pytest.mark.asyncio
    async def test_write_coil_os_error(self, mock_modbus_client: Any) -> None:
        c, mock = mock_modbus_client
        mock.write_coil = AsyncMock(
            side_effect=ConnectionResetError("connection reset")
        )
        with pytest.raises(AirobotConnectionError, match="Communication error"):
            await c.async_set_power(True)


class TestAllSetters:
    """Test each setter method to ensure full coverage."""

    @pytest.mark.asyncio
    async def test_set_overpressure_fan_level(self, mock_modbus_client: Any) -> None:
        c, mock = mock_modbus_client
        mock.write_register = AsyncMock(return_value=make_write_result())
        await c.async_set_overpressure_fan_level(8)
        mock.write_register.assert_awaited_once_with(address=2007, value=8, device_id=1)

    @pytest.mark.asyncio
    async def test_set_voc_setpoint(self, mock_modbus_client: Any) -> None:
        c, mock = mock_modbus_client
        mock.write_register = AsyncMock(return_value=make_write_result())
        await c.async_set_voc_setpoint(300)
        mock.write_register.assert_awaited_once_with(
            address=2034, value=300, device_id=1
        )

    @pytest.mark.asyncio
    async def test_set_pm25_setpoint(self, mock_modbus_client: Any) -> None:
        c, mock = mock_modbus_client
        mock.write_register = AsyncMock(return_value=make_write_result())
        await c.async_set_pm25_setpoint(100)
        mock.write_register.assert_awaited_once_with(
            address=2064, value=100, device_id=1
        )

    @pytest.mark.asyncio
    async def test_set_boost_timeout(self, mock_modbus_client: Any) -> None:
        c, mock = mock_modbus_client
        mock.write_register = AsyncMock(return_value=make_write_result())
        await c.async_set_boost_timeout(600)
        mock.write_register.assert_awaited_once_with(
            address=2010, value=600, device_id=1
        )

    @pytest.mark.asyncio
    async def test_set_overpressure_timeout(self, mock_modbus_client: Any) -> None:
        c, mock = mock_modbus_client
        mock.write_register = AsyncMock(return_value=make_write_result())
        await c.async_set_overpressure_timeout(900)
        mock.write_register.assert_awaited_once_with(
            address=2012, value=900, device_id=1
        )

    @pytest.mark.asyncio
    async def test_set_filter_reminder_interval(self, mock_modbus_client: Any) -> None:
        c, mock = mock_modbus_client
        mock.write_register = AsyncMock(return_value=make_write_result())
        await c.async_set_filter_reminder_interval(2000)
        mock.write_register.assert_awaited_once_with(
            address=2017, value=2000, device_id=1
        )

    @pytest.mark.asyncio
    async def test_reset_filter_timer(self, mock_modbus_client: Any) -> None:
        c, mock = mock_modbus_client
        mock.write_register = AsyncMock(return_value=make_write_result())
        await c.async_reset_filter_timer()
        mock.write_register.assert_awaited_once_with(address=2018, value=0, device_id=1)

    @pytest.mark.asyncio
    async def test_set_overpressure(self, mock_modbus_client: Any) -> None:
        c, mock = mock_modbus_client
        mock.write_coil = AsyncMock(return_value=make_write_result())
        await c.async_set_overpressure(True)
        mock.write_coil.assert_awaited_once_with(address=4005, value=True, device_id=1)

    @pytest.mark.asyncio
    async def test_set_bypass(self, mock_modbus_client: Any) -> None:
        c, mock = mock_modbus_client
        mock.write_coil = AsyncMock(return_value=make_write_result())
        await c.async_set_bypass(True)
        mock.write_coil.assert_awaited_once_with(address=4003, value=True, device_id=1)

    @pytest.mark.asyncio
    async def test_set_humidity_control(self, mock_modbus_client: Any) -> None:
        c, mock = mock_modbus_client
        mock.write_coil = AsyncMock(return_value=make_write_result())
        await c.async_set_humidity_control(True)
        mock.write_coil.assert_awaited_once_with(address=4027, value=True, device_id=1)

    @pytest.mark.asyncio
    async def test_set_voc_control(self, mock_modbus_client: Any) -> None:
        c, mock = mock_modbus_client
        mock.write_coil = AsyncMock(return_value=make_write_result())
        await c.async_set_voc_control(True)
        mock.write_coil.assert_awaited_once_with(address=4030, value=True, device_id=1)

    @pytest.mark.asyncio
    async def test_set_pm_control(self, mock_modbus_client: Any) -> None:
        c, mock = mock_modbus_client
        mock.write_coil = AsyncMock(return_value=make_write_result())
        await c.async_set_pm_control(True)
        mock.write_coil.assert_awaited_once_with(address=4031, value=True, device_id=1)
