"""Tests for AirobotModbusClient with mocked pymodbus."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from conftest import (
    make_coil_result,
    make_error_result,
    make_register_result,
    make_write_result,
)

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
        # supply_fan=5, extract_fan=5, supply_rpm=1200,
        # extract_rpm=1100, working_time=0x00010000
        s2 = [5, 5, 1200, 1100, 1, 0]  # working_time = 65536 ms

        # Sensor block 3: 1026-1029 (4 registers)
        # errors=0 (2 regs), server_connected=1, voc=150
        s3 = [0, 0, 1, 150]

        # Sensor block 4: 1031-1034 (4 registers)
        # pm25=25 (2 regs), gap, heat_recovery=85
        s4 = [0, 25, 0, 85]

        # Sensor block 5: 1051-1052 (2 registers)
        s5 = [120, 115]

        # Settings block 1: 2000 (1 register)
        r1 = [1]  # automatic mode

        # Settings block 2: 2003-2008 (6 registers)
        # humidity=60.0, co2=800, fan=5, gap, overpressure_fan=5
        r2 = [600, 800, 5, 0, 5, 0]

        # Settings block 3: 2009-2014 (6 registers)
        # flags=1, boost_timeout=1800 (2 regs),
        # overpressure_timeout=1800 (2 regs), ui_flags=9
        r3 = [1, 0, 1800, 0, 1800, 9]

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
        assert data.working_time_ms == 65536
        assert data.error_flags == ErrorFlag.NONE
        assert data.server_connected is True
        assert data.voc == 150
        assert data.pm25 == 25
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
        assert AirobotModbusClient._combine_u32([0x0001, 0x0000], 0) == 65536
        assert AirobotModbusClient._combine_u32([0xFFFF, 0xFFFF], 0) == 4294967295
        assert AirobotModbusClient._combine_u32([0, 0], 0) == 0

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
