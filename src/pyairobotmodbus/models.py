"""Data models for Airobot ventilation unit state."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum, IntFlag


class OperatingMode(IntEnum):
    """Device working mode (register 2000)."""

    AUTOMATIC = 1
    MANUAL = 2


class ErrorFlag(IntFlag):
    """Error flags bitmask (register 1026, 32-bit)."""

    NONE = 0
    FIRE_ALARM = 1
    FAN1 = 2
    FAN2 = 4
    SENSOR_1 = 8
    SENSOR_2 = 16
    SENSOR_3 = 32
    SENSOR_4 = 64
    SENSOR_5 = 128
    SENSOR_CO2 = 256
    HEATER = 512
    LOW_SUPPLY = 1024
    FILTER = 2048


@dataclass(frozen=True)
class AirobotData:
    """Snapshot of all device data.

    Temperatures are in °C, humidity in RH%.
    """

    # Device info
    firmware_version: int

    # Temperatures (°C)
    extract_air_temp: float | None
    supply_air_temp: float | None
    outside_air_temp: float | None
    exhaust_air_temp: float | None
    extra_temp: float | None

    # Humidity (RH%)
    extract_air_humidity: float | None
    supply_air_humidity: float | None
    outside_air_humidity: float | None
    exhaust_air_humidity: float | None
    extra_humidity: float | None

    # Air quality
    co2_level: int | None  # ppm
    voc: int | None  # index 0-500
    pm25: int | None  # μg/m³

    # Fan status
    supply_fan_level: int
    extract_fan_level: int
    supply_fan_rpm: int
    extract_fan_rpm: int

    # Airflow (m³/h) — only with constant flow feature
    supply_airflow: int | None
    extract_airflow: int | None

    # Device status
    working_time_ms: int  # milliseconds since last reset
    error_flags: ErrorFlag
    server_connected: bool
    heat_recovery_efficiency: int  # 0-100%

    # Settings
    operating_mode: OperatingMode
    humidity_setpoint: float  # RH%
    co2_setpoint: int  # ppm
    voc_setpoint: int  # index
    pm25_setpoint: int  # μg/m³
    manual_fan_level: int
    overpressure_fan_level: int
    boost_timeout: int  # seconds
    overpressure_timeout: int  # seconds
    filter_reminder_interval: int  # hours
    filter_reminder_elapsed: int

    # Coil states
    power_on: bool
    bypass_on: bool
    boost_on: bool
    overpressure_on: bool
    filter_alert: bool
    humidity_control_enabled: bool
    voc_control_enabled: bool
    pm_control_enabled: bool
