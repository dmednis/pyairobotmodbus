"""Async Modbus TCP client for Airobot ventilation units."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any, Self

from pymodbus import ModbusException
from pymodbus.client import AsyncModbusTcpClient

from .exceptions import (
    AirobotConnectionError,
    AirobotError,
    AirobotInvalidDataError,
    AirobotReadError,
    AirobotTimeoutError,
    AirobotWriteError,
)
from .models import AirobotData, ErrorFlag, OperatingMode
from .registers import (
    COIL_BLOCK_1,
    COIL_BLOCK_2,
    COIL_BLOCK_3,
    COIL_BLOCK_4,
    COIL_BOOST_ON,
    COIL_BYPASS_ON,
    COIL_FILTER_ALERT,
    COIL_HUMIDITY_CONTROL_ENABLE,
    COIL_OVERPRESSURE_ON,
    COIL_PM_CONTROL_ENABLE,
    COIL_POWER_ON,
    COIL_REBOOT,
    COIL_VOC_CONTROL_ENABLE,
    EXTRA_HUMIDITY_ABSENT_RAW,
    EXTRA_TEMP_ABSENT_RAW,
    LIMITS,
    REG_BOOST_TIMEOUT,
    REG_CO2_LEVEL,
    REG_CO2_SETPOINT,
    REG_ERROR_FLAGS,
    REG_EXHAUST_AIR_HUMIDITY,
    REG_EXHAUST_AIR_TEMP,
    REG_EXTRA_HUMIDITY,
    REG_EXTRA_TEMP,
    REG_EXTRACT_AIR_HUMIDITY,
    REG_EXTRACT_AIR_TEMP,
    REG_EXTRACT_AIRFLOW,
    REG_EXTRACT_FAN_LEVEL,
    REG_EXTRACT_FAN_RPM,
    REG_FILTER_REMINDER_ELAPSED,
    REG_FILTER_REMINDER_INTERVAL,
    REG_FIRMWARE_VERSION,
    REG_HEAT_RECOVERY_EFFICIENCY,
    REG_HUMIDITY_SETPOINT,
    REG_MANUAL_FAN_LEVEL,
    REG_OUTSIDE_AIR_HUMIDITY,
    REG_OUTSIDE_AIR_TEMP,
    REG_OVERPRESSURE_FAN_LEVEL,
    REG_OVERPRESSURE_TIMEOUT,
    REG_PM25,
    REG_PM25_SETPOINT,
    REG_SERVER_CONNECTED,
    REG_SUPPLY_AIR_HUMIDITY,
    REG_SUPPLY_AIR_TEMP,
    REG_SUPPLY_AIRFLOW,
    REG_SUPPLY_FAN_LEVEL,
    REG_SUPPLY_FAN_RPM,
    REG_VOC,
    REG_VOC_SETPOINT,
    REG_WORKING_MODE,
    REG_WORKING_TIME,
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


def _validate_register_count(name: str, registers: list[int], expected: int) -> None:
    """Raise AirobotInvalidDataError if register count doesn't match."""
    if len(registers) != expected:
        raise AirobotInvalidDataError(
            f"Expected {expected} registers for {name}, got {len(registers)}"
        )


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

    @classmethod
    async def create(
        cls,
        host: str,
        port: int = DEFAULT_PORT,
        device_id: int = DEFAULT_DEVICE_ID,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> Self:
        """Create and connect a client instance."""
        client = cls(host, port=port, device_id=device_id, timeout=timeout)
        await client.connect()
        return client

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
        except TimeoutError as exc:
            raise AirobotTimeoutError(
                f"Timeout connecting to {self._host}:{self._port}: {exc}"
            ) from exc
        except (OSError, ModbusException) as exc:
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

    async def __aenter__(self) -> Self:
        """Connect and return client for use as async context manager."""
        await self.connect()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        """Disconnect on context manager exit."""
        await self.disconnect()

    def _ensure_connected(self) -> None:
        """Raise if the client is not connected."""
        if not self.connected:
            raise AirobotConnectionError(f"Not connected to {self._host}:{self._port}")

    # ------------------------------------------------------------------
    # Reading data
    # ------------------------------------------------------------------

    async def _execute(
        self,
        operation: Callable[[], Awaitable[Any]],
        *,
        action: str,
        error_cls: type[AirobotError],
    ) -> Any:
        """Run a Modbus operation, translating failures to Airobot errors.

        ``action`` is a present-tense phrase (e.g. ``"reading coil 4000"``) woven
        into the error messages. ``error_cls`` is raised when the device returns
        a protocol-level error response.
        """
        self._ensure_connected()
        try:
            result = await operation()
        except TimeoutError as exc:
            raise AirobotTimeoutError(f"Timeout {action}: {exc}") from exc
        except (OSError, ModbusException) as exc:
            raise AirobotConnectionError(
                f"Communication error {action}: {exc}"
            ) from exc
        if result.isError():
            raise error_cls(f"Modbus error {action}: {result}")
        return result

    async def _read_input(self, address: int, count: int) -> list[int]:
        """Read input registers (FC04) and return raw values."""
        result = await self._execute(
            lambda: self._client.read_input_registers(
                address=address, count=count, device_id=self._device_id
            ),
            action=f"reading input register {address}",
            error_cls=AirobotReadError,
        )
        registers = list(result.registers)
        _validate_register_count(f"input@{address}", registers, count)
        return registers

    async def _read_holding(self, address: int, count: int) -> list[int]:
        """Read holding registers (FC03) and return raw values."""
        result = await self._execute(
            lambda: self._client.read_holding_registers(
                address=address, count=count, device_id=self._device_id
            ),
            action=f"reading register {address}",
            error_cls=AirobotReadError,
        )
        registers = list(result.registers)
        _validate_register_count(f"holding@{address}", registers, count)
        return registers

    async def _read_coils(self, address: int, count: int) -> list[bool]:
        """Read coils and return boolean values."""
        result = await self._execute(
            lambda: self._client.read_coils(
                address=address, count=count, device_id=self._device_id
            ),
            action=f"reading coil {address}",
            error_cls=AirobotReadError,
        )
        bits = list(result.bits[:count])
        if len(bits) != count:
            raise AirobotInvalidDataError(
                f"Expected {count} coils for coil@{address}, got {len(bits)}"
            )
        return bits

    @staticmethod
    def _combine_u32(regs: list[int], offset: int) -> int:
        """Combine two consecutive 16-bit registers into a 32-bit unsigned value.

        The device transmits the low word first (little-endian word order): the
        lower register address holds the least-significant 16 bits. This matches
        the write path, which writes a value to its base (low) register.
        """
        return (regs[offset + 1] << 16) | regs[offset]

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

    @staticmethod
    def _at(block: list[Any], block_def: tuple[int, int], reg: int) -> Any:
        """Return the block element holding the value for register ``reg``.

        ``block_def`` is the ``(start_address, count)`` tuple the block was read
        with, so an absolute register address maps to its position in the block.
        Parsing by register name (rather than a bare index) keeps the offsets
        from drifting away from the register map.
        """
        return block[reg - block_def[0]]

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

        # Parse sensor block 1 (1000-1011). The extra temp/humidity sensors are
        # optional, so their device sentinels decode to None.
        def s1_temp(reg: int) -> float:
            return self._scale_temp(
                self._to_signed16(self._at(s1, SENSOR_BLOCK_1, reg))
            )

        def s1_humidity(reg: int) -> float:
            return self._scale_humidity(
                self._to_signed16(self._at(s1, SENSOR_BLOCK_1, reg))
            )

        firmware_version = self._at(s1, SENSOR_BLOCK_1, REG_FIRMWARE_VERSION)
        extract_air_temp = s1_temp(REG_EXTRACT_AIR_TEMP)
        supply_air_temp = s1_temp(REG_SUPPLY_AIR_TEMP)
        outside_air_temp = s1_temp(REG_OUTSIDE_AIR_TEMP)
        exhaust_air_temp = s1_temp(REG_EXHAUST_AIR_TEMP)
        extra_temp_raw = self._to_signed16(self._at(s1, SENSOR_BLOCK_1, REG_EXTRA_TEMP))
        extra_temp = (
            None
            if extra_temp_raw == EXTRA_TEMP_ABSENT_RAW
            else self._scale_temp(extra_temp_raw)
        )
        extract_air_humidity = s1_humidity(REG_EXTRACT_AIR_HUMIDITY)
        supply_air_humidity = s1_humidity(REG_SUPPLY_AIR_HUMIDITY)
        outside_air_humidity = s1_humidity(REG_OUTSIDE_AIR_HUMIDITY)
        exhaust_air_humidity = s1_humidity(REG_EXHAUST_AIR_HUMIDITY)
        extra_humidity_raw = self._to_signed16(
            self._at(s1, SENSOR_BLOCK_1, REG_EXTRA_HUMIDITY)
        )
        extra_humidity = (
            None
            if extra_humidity_raw == EXTRA_HUMIDITY_ABSENT_RAW
            else self._scale_humidity(extra_humidity_raw)
        )
        co2_level = self._at(s1, SENSOR_BLOCK_1, REG_CO2_LEVEL)

        # Parse sensor block 2 (1014-1019)
        supply_fan_level = self._at(s2, SENSOR_BLOCK_2, REG_SUPPLY_FAN_LEVEL)
        extract_fan_level = self._at(s2, SENSOR_BLOCK_2, REG_EXTRACT_FAN_LEVEL)
        supply_fan_rpm = self._at(s2, SENSOR_BLOCK_2, REG_SUPPLY_FAN_RPM)
        extract_fan_rpm = self._at(s2, SENSOR_BLOCK_2, REG_EXTRACT_FAN_RPM)
        working_time_ms = self._combine_u32(s2, REG_WORKING_TIME - SENSOR_BLOCK_2[0])

        # Parse sensor block 3 (1026-1029)
        error_flags = ErrorFlag(
            self._combine_u32(s3, REG_ERROR_FLAGS - SENSOR_BLOCK_3[0])
        )
        server_connected = bool(self._at(s3, SENSOR_BLOCK_3, REG_SERVER_CONNECTED))
        voc = self._at(s3, SENSOR_BLOCK_3, REG_VOC)

        # Parse sensor block 4 (1031-1034)
        pm25 = self._at(s4, SENSOR_BLOCK_4, REG_PM25)  # single 16-bit reg, μg/m³
        heat_recovery_efficiency = self._at(
            s4, SENSOR_BLOCK_4, REG_HEAT_RECOVERY_EFFICIENCY
        )

        # Parse sensor block 5 (1051-1052)
        supply_airflow = self._at(s5, SENSOR_BLOCK_5, REG_SUPPLY_AIRFLOW)
        extract_airflow = self._at(s5, SENSOR_BLOCK_5, REG_EXTRACT_AIRFLOW)

        # Parse settings
        operating_mode = OperatingMode(self._at(r1, SETTINGS_BLOCK_1, REG_WORKING_MODE))
        humidity_setpoint = self._at(r2, SETTINGS_BLOCK_2, REG_HUMIDITY_SETPOINT) / 10.0
        co2_setpoint = self._at(r2, SETTINGS_BLOCK_2, REG_CO2_SETPOINT)
        manual_fan_level = self._at(r2, SETTINGS_BLOCK_2, REG_MANUAL_FAN_LEVEL)
        overpressure_fan_level = self._at(
            r2, SETTINGS_BLOCK_2, REG_OVERPRESSURE_FAN_LEVEL
        )
        boost_timeout = self._combine_u32(r3, REG_BOOST_TIMEOUT - SETTINGS_BLOCK_3[0])
        overpressure_timeout = self._combine_u32(
            r3, REG_OVERPRESSURE_TIMEOUT - SETTINGS_BLOCK_3[0]
        )
        filter_reminder_interval = self._at(
            r4, SETTINGS_BLOCK_4, REG_FILTER_REMINDER_INTERVAL
        )
        filter_reminder_elapsed = self._at(
            r4, SETTINGS_BLOCK_4, REG_FILTER_REMINDER_ELAPSED
        )
        voc_setpoint = self._at(r5, SETTINGS_BLOCK_5, REG_VOC_SETPOINT)
        pm25_setpoint = self._at(r6, SETTINGS_BLOCK_6, REG_PM25_SETPOINT)

        # Parse coils
        power_on = self._at(c1, COIL_BLOCK_1, COIL_POWER_ON)
        bypass_on = self._at(c1, COIL_BLOCK_1, COIL_BYPASS_ON)
        boost_on = self._at(c1, COIL_BLOCK_1, COIL_BOOST_ON)
        overpressure_on = self._at(c1, COIL_BLOCK_1, COIL_OVERPRESSURE_ON)
        filter_alert = self._at(c2, COIL_BLOCK_2, COIL_FILTER_ALERT)
        humidity_control_enabled = self._at(
            c3, COIL_BLOCK_3, COIL_HUMIDITY_CONTROL_ENABLE
        )
        voc_control_enabled = self._at(c4, COIL_BLOCK_4, COIL_VOC_CONTROL_ENABLE)
        pm_control_enabled = self._at(c4, COIL_BLOCK_4, COIL_PM_CONTROL_ENABLE)

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
        self._ensure_connected()
        if address in LIMITS:
            min_val, max_val = LIMITS[address]
            if not min_val <= value <= max_val:
                raise AirobotWriteError(
                    f"Value {value} out of range [{min_val}, {max_val}] "
                    f"for register {address}"
                )
        await self._execute(
            lambda: self._client.write_register(
                address=address, value=value, device_id=self._device_id
            ),
            action=f"writing register {address}",
            error_cls=AirobotWriteError,
        )

    async def _write_coil(self, address: int, value: bool) -> None:
        """Write a single coil."""
        await self._execute(
            lambda: self._client.write_coil(
                address=address, value=value, device_id=self._device_id
            ),
            action=f"writing coil {address}",
            error_cls=AirobotWriteError,
        )

    async def async_set_mode(self, mode: OperatingMode) -> None:
        """Set the device working mode."""
        await self._write_register(REG_WORKING_MODE, int(mode))

    async def async_set_fan_speed(self, speed: int) -> None:
        """Set the manual mode fan working level. Range enforced from LIMITS."""
        await self._write_register(REG_MANUAL_FAN_LEVEL, speed)

    async def async_set_overpressure_fan_level(self, level: int) -> None:
        """Set the overpressure/fireplace mode fan level. Range from LIMITS."""
        await self._write_register(REG_OVERPRESSURE_FAN_LEVEL, level)

    async def async_set_co2_setpoint(self, ppm: int) -> None:
        """Set the CO2 setpoint, in ppm. Range enforced from LIMITS."""
        await self._write_register(REG_CO2_SETPOINT, ppm)

    async def async_set_humidity_setpoint(self, rh: float) -> None:
        """Set the humidity setpoint, in RH%. Range enforced from LIMITS.

        The value is stored as integer * 10 on the device.
        """
        raw = int(round(rh * 10))
        await self._write_register(REG_HUMIDITY_SETPOINT, raw)

    async def async_set_voc_setpoint(self, index: int) -> None:
        """Set the VOC setpoint, as an index. Range enforced from LIMITS."""
        await self._write_register(REG_VOC_SETPOINT, index)

    async def async_set_pm25_setpoint(self, ugm3: int) -> None:
        """Set the PM2.5 setpoint, in μg/m³. Range enforced from LIMITS."""
        await self._write_register(REG_PM25_SETPOINT, ugm3)

    async def async_set_boost_timeout(self, seconds: int) -> None:
        """Set the boost mode timeout, in seconds. Range enforced from LIMITS."""
        await self._write_register(REG_BOOST_TIMEOUT, seconds)

    async def async_set_overpressure_timeout(self, seconds: int) -> None:
        """Set the overpressure/fireplace timeout (s). Range from LIMITS."""
        await self._write_register(REG_OVERPRESSURE_TIMEOUT, seconds)

    async def async_set_filter_reminder_interval(self, hours: int) -> None:
        """Set the filter reminder interval, in hours. Range from LIMITS."""
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
