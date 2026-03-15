"""Async Modbus TCP client for Airobot ventilation units."""

from __future__ import annotations

import logging

from pymodbus import ModbusException
from pymodbus.client import AsyncModbusTcpClient

from .exceptions import AirobotConnectionError, AirobotReadError, AirobotWriteError
from .models import AirobotData, ErrorFlag, OperatingMode
from .registers import (
    COIL_BLOCK_1,
    COIL_BLOCK_2,
    COIL_BLOCK_3,
    COIL_BLOCK_4,
    COIL_BOOST_ON,
    COIL_BYPASS_ON,
    COIL_HUMIDITY_CONTROL_ENABLE,
    COIL_OVERPRESSURE_ON,
    COIL_PM_CONTROL_ENABLE,
    COIL_POWER_ON,
    COIL_REBOOT,
    COIL_VOC_CONTROL_ENABLE,
    LIMITS,
    REG_BOOST_TIMEOUT,
    REG_CO2_SETPOINT,
    REG_FILTER_REMINDER_ELAPSED,
    REG_FILTER_REMINDER_INTERVAL,
    REG_HUMIDITY_SETPOINT,
    REG_MANUAL_FAN_LEVEL,
    REG_OVERPRESSURE_FAN_LEVEL,
    REG_OVERPRESSURE_TIMEOUT,
    REG_PM25_SETPOINT,
    REG_VOC_SETPOINT,
    REG_WORKING_MODE,
    SENSOR_BLOCK_1,
    SENSOR_BLOCK_2,
    SENSOR_BLOCK_3,
    SENSOR_BLOCK_4,
    SENSOR_BLOCK_5,
    SETTINGS_BLOCK_1,
    SETTINGS_BLOCK_2,
    SETTINGS_BLOCK_3,
    SETTINGS_BLOCK_4,
    SETTINGS_BLOCK_5,
    SETTINGS_BLOCK_6,
)

_LOGGER = logging.getLogger(__name__)

DEFAULT_PORT = 502
DEFAULT_DEVICE_ID = 1
DEFAULT_TIMEOUT = 10


class AirobotModbusClient:
    """High-level async interface to an Airobot ventilation unit via Modbus TCP."""

    def __init__(
        self,
        host: str,
        port: int = DEFAULT_PORT,
        device_id: int = DEFAULT_DEVICE_ID,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> None:
        self._host = host
        self._port = port
        self._device_id = device_id
        self._client = AsyncModbusTcpClient(
            host=host,
            port=port,
            timeout=timeout,
        )

    @property
    def host(self) -> str:
        return self._host

    @property
    def port(self) -> int:
        return self._port

    @property
    def connected(self) -> bool:
        return self._client.connected

    async def connect(self) -> None:
        """Connect to the device."""
        try:
            ok = await self._client.connect()
        except Exception as exc:
            raise AirobotConnectionError(
                f"Failed to connect to {self._host}:{self._port}: {exc}"
            ) from exc
        if not ok:
            raise AirobotConnectionError(
                f"Failed to connect to {self._host}:{self._port}"
            )

    async def disconnect(self) -> None:
        """Disconnect from the device."""
        self._client.close()

    # ------------------------------------------------------------------
    # Reading data
    # ------------------------------------------------------------------

    async def _read_input(self, address: int, count: int) -> list[int]:
        """Read input registers (FC04) and return raw values."""
        try:
            result = await self._client.read_input_registers(
                address=address, count=count, device_id=self._device_id
            )
        except ModbusException as exc:
            raise AirobotConnectionError(
                f"Communication error reading input register {address}: {exc}"
            ) from exc
        if result.isError():
            raise AirobotReadError(
                f"Modbus error reading input register {address}: {result}"
            )
        return list(result.registers)

    async def _read_holding(self, address: int, count: int) -> list[int]:
        """Read holding registers (FC03) and return raw values."""
        try:
            result = await self._client.read_holding_registers(
                address=address, count=count, device_id=self._device_id
            )
        except ModbusException as exc:
            raise AirobotConnectionError(
                f"Communication error reading register {address}: {exc}"
            ) from exc
        if result.isError():
            raise AirobotReadError(f"Modbus error reading register {address}: {result}")
        return list(result.registers)

    async def _read_coils(self, address: int, count: int) -> list[bool]:
        """Read coils and return boolean values."""
        try:
            result = await self._client.read_coils(
                address=address, count=count, device_id=self._device_id
            )
        except ModbusException as exc:
            raise AirobotConnectionError(
                f"Communication error reading coil {address}: {exc}"
            ) from exc
        if result.isError():
            raise AirobotReadError(f"Modbus error reading coil {address}: {result}")
        return list(result.bits[:count])

    @staticmethod
    def _combine_u32(regs: list[int], offset: int) -> int:
        """Combine two consecutive 16-bit registers into a 32-bit unsigned value."""
        return (regs[offset] << 16) | regs[offset + 1]

    @staticmethod
    def _to_signed16(value: int) -> int:
        """Convert unsigned 16-bit value to signed."""
        if value >= 0x8000:
            return value - 0x10000
        return value

    @staticmethod
    def _scale_temp(raw: int) -> float:
        """Convert raw register value to temperature in °C (value / 10)."""
        return raw / 10.0

    @staticmethod
    def _scale_humidity(raw: int) -> float:
        """Convert raw register value to humidity in RH% (value / 10)."""
        return raw / 10.0

    async def async_get_data(self) -> AirobotData:
        """Read all sensor data and settings from the device."""
        # Batch-read all register blocks
        # 1000-series are read-only input registers (FC04)
        s1 = await self._read_input(*SENSOR_BLOCK_1)  # 1000-1011
        s2 = await self._read_input(*SENSOR_BLOCK_2)  # 1014-1019
        s3 = await self._read_input(*SENSOR_BLOCK_3)  # 1026-1029
        s4 = await self._read_input(*SENSOR_BLOCK_4)  # 1031-1034
        s5 = await self._read_input(*SENSOR_BLOCK_5)  # 1051-1052

        r1 = await self._read_holding(*SETTINGS_BLOCK_1)  # 2000
        r2 = await self._read_holding(*SETTINGS_BLOCK_2)  # 2003-2008
        r3 = await self._read_holding(*SETTINGS_BLOCK_3)  # 2009-2014
        r4 = await self._read_holding(*SETTINGS_BLOCK_4)  # 2015-2018
        r5 = await self._read_holding(*SETTINGS_BLOCK_5)  # 2034
        r6 = await self._read_holding(*SETTINGS_BLOCK_6)  # 2064

        c1 = await self._read_coils(*COIL_BLOCK_1)  # 4000-4006
        c2 = await self._read_coils(*COIL_BLOCK_2)  # 4020
        c3 = await self._read_coils(*COIL_BLOCK_3)  # 4027
        c4 = await self._read_coils(*COIL_BLOCK_4)  # 4030-4036

        # Parse sensor block 1 (1000-1011)
        firmware_version = s1[0]
        extract_air_temp = self._scale_temp(self._to_signed16(s1[1]))
        supply_air_temp = self._scale_temp(self._to_signed16(s1[2]))
        outside_air_temp = self._scale_temp(self._to_signed16(s1[3]))
        exhaust_air_temp = self._scale_temp(self._to_signed16(s1[4]))
        extra_temp = self._scale_temp(self._to_signed16(s1[5]))
        extract_air_humidity = self._scale_humidity(self._to_signed16(s1[6]))
        supply_air_humidity = self._scale_humidity(self._to_signed16(s1[7]))
        outside_air_humidity = self._scale_humidity(self._to_signed16(s1[8]))
        exhaust_air_humidity = self._scale_humidity(self._to_signed16(s1[9]))
        extra_humidity = self._scale_humidity(self._to_signed16(s1[10]))
        co2_level = s1[11]

        # Parse sensor block 2 (1014-1019, offset from 1014)
        supply_fan_level = s2[0]
        extract_fan_level = s2[1]
        supply_fan_rpm = s2[2]
        extract_fan_rpm = s2[3]
        working_time_ms = self._combine_u32(s2, 4)

        # Parse sensor block 3 (1026-1029, offset from 1026)
        error_flags = ErrorFlag(self._combine_u32(s3, 0))
        server_connected = bool(s3[2])
        voc = s3[3]

        # Parse sensor block 4 (1031-1034, offset from 1031)
        pm25 = self._combine_u32(s4, 0)
        heat_recovery_efficiency = s4[3]

        # Parse sensor block 5 (1051-1052)
        supply_airflow = s5[0]
        extract_airflow = s5[1]

        # Parse settings
        operating_mode = OperatingMode(r1[0])
        # r2 is registers 2003-2008 (count=6)
        humidity_setpoint = r2[0] / 10.0  # 50-950 -> 5.0-95.0
        co2_setpoint = r2[1]  # 450-2000 ppm
        manual_fan_level = r2[2]  # 0-10
        # r2[3] is register 2006 (gap)
        overpressure_fan_level = r2[4]  # register 2007
        # r3 is registers 2009-2014 (count=6)
        # settings_flags = r3[0]  # register 2009 (informational, coils are more direct)
        boost_timeout = self._combine_u32(r3, 1)  # register 2010-2011
        overpressure_timeout = self._combine_u32(r3, 3)  # register 2012-2013
        # r3[5] = register 2014 (UI flags)

        # r4 is registers 2015-2018 (count=4)
        filter_reminder_interval = r4[2]  # register 2017
        filter_reminder_elapsed = r4[3]  # register 2018

        voc_setpoint = r5[0]
        pm25_setpoint = r6[0]

        # Parse coils
        # c1: 4000-4006 (7 coils)
        power_on = c1[0]
        # c1[1], c1[2] are gaps (4001, 4002)
        bypass_on = c1[3]  # 4003
        boost_on = c1[4]  # 4004
        overpressure_on = c1[5]  # 4005
        # c1[6] = 4006 (reboot, transient)

        filter_alert = c2[0]  # 4020

        humidity_control_enabled = c3[0]  # 4027

        # c4: 4030-4036 (7 coils)
        voc_control_enabled = c4[0]  # 4030
        pm_control_enabled = c4[1]  # 4031

        return AirobotData(
            firmware_version=firmware_version,
            extract_air_temp=extract_air_temp,
            supply_air_temp=supply_air_temp,
            outside_air_temp=outside_air_temp,
            exhaust_air_temp=exhaust_air_temp,
            extra_temp=extra_temp,
            extract_air_humidity=extract_air_humidity,
            supply_air_humidity=supply_air_humidity,
            outside_air_humidity=outside_air_humidity,
            exhaust_air_humidity=exhaust_air_humidity,
            extra_humidity=extra_humidity,
            co2_level=co2_level,
            voc=voc,
            pm25=pm25,
            supply_fan_level=supply_fan_level,
            extract_fan_level=extract_fan_level,
            supply_fan_rpm=supply_fan_rpm,
            extract_fan_rpm=extract_fan_rpm,
            supply_airflow=supply_airflow,
            extract_airflow=extract_airflow,
            working_time_ms=working_time_ms,
            error_flags=error_flags,
            server_connected=server_connected,
            heat_recovery_efficiency=heat_recovery_efficiency,
            operating_mode=operating_mode,
            humidity_setpoint=humidity_setpoint,
            co2_setpoint=co2_setpoint,
            voc_setpoint=voc_setpoint,
            pm25_setpoint=pm25_setpoint,
            manual_fan_level=manual_fan_level,
            overpressure_fan_level=overpressure_fan_level,
            boost_timeout=boost_timeout,
            overpressure_timeout=overpressure_timeout,
            filter_reminder_interval=filter_reminder_interval,
            filter_reminder_elapsed=filter_reminder_elapsed,
            power_on=power_on,
            bypass_on=bypass_on,
            boost_on=boost_on,
            overpressure_on=overpressure_on,
            filter_alert=filter_alert,
            humidity_control_enabled=humidity_control_enabled,
            voc_control_enabled=voc_control_enabled,
            pm_control_enabled=pm_control_enabled,
        )

    # ------------------------------------------------------------------
    # Writing data — holding registers
    # ------------------------------------------------------------------

    async def _write_register(self, address: int, value: int) -> None:
        """Write a single holding register with validation."""
        if address in LIMITS:
            min_val, max_val = LIMITS[address]
            if not min_val <= value <= max_val:
                raise AirobotWriteError(
                    f"Value {value} out of range [{min_val}, {max_val}] "
                    f"for register {address}"
                )
        try:
            result = await self._client.write_register(
                address=address, value=value, device_id=self._device_id
            )
        except ModbusException as exc:
            raise AirobotConnectionError(
                f"Communication error writing register {address}: {exc}"
            ) from exc
        if result.isError():
            raise AirobotWriteError(
                f"Modbus error writing register {address}: {result}"
            )

    async def _write_coil(self, address: int, value: bool) -> None:
        """Write a single coil."""
        try:
            result = await self._client.write_coil(
                address=address, value=value, device_id=self._device_id
            )
        except ModbusException as exc:
            raise AirobotConnectionError(
                f"Communication error writing coil {address}: {exc}"
            ) from exc
        if result.isError():
            raise AirobotWriteError(f"Modbus error writing coil {address}: {result}")

    async def async_set_mode(self, mode: OperatingMode) -> None:
        """Set the device working mode."""
        await self._write_register(REG_WORKING_MODE, int(mode))

    async def async_set_fan_speed(self, speed: int) -> None:
        """Set the manual mode fan working level (0-10)."""
        await self._write_register(REG_MANUAL_FAN_LEVEL, speed)

    async def async_set_overpressure_fan_level(self, level: int) -> None:
        """Set the overpressure/fireplace mode fan level (0-10)."""
        await self._write_register(REG_OVERPRESSURE_FAN_LEVEL, level)

    async def async_set_co2_setpoint(self, ppm: int) -> None:
        """Set the CO2 setpoint (450-2000 ppm)."""
        await self._write_register(REG_CO2_SETPOINT, ppm)

    async def async_set_humidity_setpoint(self, rh: float) -> None:
        """Set the humidity setpoint (5.0-95.0 RH%).

        The value is stored as integer * 10 on the device.
        """
        raw = int(round(rh * 10))
        await self._write_register(REG_HUMIDITY_SETPOINT, raw)

    async def async_set_voc_setpoint(self, index: int) -> None:
        """Set the VOC setpoint (0-500 index)."""
        await self._write_register(REG_VOC_SETPOINT, index)

    async def async_set_pm25_setpoint(self, ugm3: int) -> None:
        """Set the PM2.5 setpoint (0-999 μg/m³)."""
        await self._write_register(REG_PM25_SETPOINT, ugm3)

    async def async_set_boost_timeout(self, seconds: int) -> None:
        """Set the boost mode timeout (180-3600 seconds)."""
        await self._write_register(REG_BOOST_TIMEOUT, seconds)

    async def async_set_overpressure_timeout(self, seconds: int) -> None:
        """Set the overpressure/fireplace mode timeout (180-3600 seconds)."""
        await self._write_register(REG_OVERPRESSURE_TIMEOUT, seconds)

    async def async_set_filter_reminder_interval(self, hours: int) -> None:
        """Set the filter reminder interval (720-8760 hours)."""
        await self._write_register(REG_FILTER_REMINDER_INTERVAL, hours)

    async def async_reset_filter_timer(self) -> None:
        """Reset the filter reminder timer."""
        await self._write_register(REG_FILTER_REMINDER_ELAPSED, 0)

    # ------------------------------------------------------------------
    # Writing data — coils
    # ------------------------------------------------------------------

    async def async_set_power(self, on: bool) -> None:
        """Turn ventilation on or off."""
        await self._write_coil(COIL_POWER_ON, on)

    async def async_set_boost(self, on: bool) -> None:
        """Activate or deactivate boost mode."""
        await self._write_coil(COIL_BOOST_ON, on)

    async def async_set_overpressure(self, on: bool) -> None:
        """Activate or deactivate overpressure/fireplace mode."""
        await self._write_coil(COIL_OVERPRESSURE_ON, on)

    async def async_set_bypass(self, on: bool) -> None:
        """Enable or disable bypass automatic mode."""
        await self._write_coil(COIL_BYPASS_ON, on)

    async def async_set_humidity_control(self, enable: bool) -> None:
        """Enable or disable humidity setpoint control."""
        await self._write_coil(COIL_HUMIDITY_CONTROL_ENABLE, enable)

    async def async_set_voc_control(self, enable: bool) -> None:
        """Enable or disable VOC setpoint control."""
        await self._write_coil(COIL_VOC_CONTROL_ENABLE, enable)

    async def async_set_pm_control(self, enable: bool) -> None:
        """Enable or disable PM2.5 setpoint control."""
        await self._write_coil(COIL_PM_CONTROL_ENABLE, enable)

    async def async_reboot(self) -> None:
        """Reboot the device."""
        await self._write_coil(COIL_REBOOT, True)
