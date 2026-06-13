"""Modbus register definitions for Airobot ventilation units.

Register addresses and metadata based on the Airobot VU Modbus specification.
"""

# ---------------------------------------------------------------------------
# Read-only holding registers (FC03) — sensor data and status
# ---------------------------------------------------------------------------

REG_FIRMWARE_VERSION = 1000
REG_EXTRACT_AIR_TEMP = 1001
REG_SUPPLY_AIR_TEMP = 1002
REG_OUTSIDE_AIR_TEMP = 1003
REG_EXHAUST_AIR_TEMP = 1004
REG_EXTRA_TEMP = 1005  # optional, for external humidifier
REG_EXTRACT_AIR_HUMIDITY = 1006
REG_SUPPLY_AIR_HUMIDITY = 1007
REG_OUTSIDE_AIR_HUMIDITY = 1008
REG_EXHAUST_AIR_HUMIDITY = 1009
REG_EXTRA_HUMIDITY = 1010  # optional, for external humidifier
REG_CO2_LEVEL = 1011
REG_SUPPLY_FAN_LEVEL = 1014
REG_EXTRACT_FAN_LEVEL = 1015
REG_SUPPLY_FAN_RPM = 1016
REG_EXTRACT_FAN_RPM = 1017
REG_WORKING_TIME = 1018  # 32-bit, spans 1018-1019, milliseconds
REG_ERROR_FLAGS = 1026  # 32-bit, spans 1026-1027
REG_SERVER_CONNECTED = 1028
REG_VOC = 1029
REG_PM25 = 1031  # 16-bit, μg/m³
REG_HEAT_RECOVERY_EFFICIENCY = 1034
REG_SUPPLY_AIRFLOW = 1051  # m3/h, only with constant flow feature
REG_EXTRACT_AIRFLOW = 1052  # m3/h, only with constant flow feature

# Contiguous read blocks for efficient batch reads
# (start_address, count)
SENSOR_BLOCK_1 = (1000, 12)  # 1000-1011: firmware, temps, humidity, CO2
SENSOR_BLOCK_2 = (1014, 6)  # 1014-1019: fan levels, RPMs, working time
SENSOR_BLOCK_3 = (1026, 4)  # 1026-1029: errors, server connected, VOC
SENSOR_BLOCK_4 = (1031, 4)  # 1031-1034: PM2.5, heat recovery
SENSOR_BLOCK_5 = (1051, 2)  # 1051-1052: airflow

# Sentinel raw values reported by optional sensors when not installed.
# These are the signed-16 register values; the scaled readings (value / 10)
# are 3276.7 °C and -0.1 % respectively, which the device emits when the
# corresponding extra sensor is absent.
EXTRA_TEMP_ABSENT_RAW = 32767  # 0x7FFF -> 3276.7 °C
EXTRA_HUMIDITY_ABSENT_RAW = -1  # 0xFFFF -> -0.1 %

# ---------------------------------------------------------------------------
# Read/write holding registers (FC03/FC06) — settings and setpoints
# ---------------------------------------------------------------------------

REG_WORKING_MODE = 2000
REG_HUMIDITY_SETPOINT = 2003
REG_CO2_SETPOINT = 2004
REG_MANUAL_FAN_LEVEL = 2005
REG_OVERPRESSURE_FAN_LEVEL = 2007
REG_SETTINGS_FLAGS = 2009
REG_BOOST_TIMEOUT = 2010  # 32-bit, spans 2010-2011, seconds
REG_OVERPRESSURE_TIMEOUT = 2012  # 32-bit, spans 2012-2013, seconds
REG_UI_FLAGS = 2014
REG_UI_FLAGS1 = 2015
REG_FILTER_REMINDER_INTERVAL = 2017  # hours
REG_FILTER_REMINDER_ELAPSED = 2018
REG_VOC_SETPOINT = 2034
REG_PM25_SETPOINT = 2064

# Settings read block
SETTINGS_BLOCK_1 = (2000, 1)  # 2000: working mode
SETTINGS_BLOCK_2 = (2003, 6)  # 2003-2008: setpoints, fan levels
SETTINGS_BLOCK_3 = (2009, 6)  # 2009-2014: flags, timeouts, UI flags
SETTINGS_BLOCK_4 = (2015, 4)  # 2015-2018: UI flags1, filter reminder
SETTINGS_BLOCK_5 = (2034, 1)  # 2034: VOC setpoint
SETTINGS_BLOCK_6 = (2064, 1)  # 2064: PM2.5 setpoint

# ---------------------------------------------------------------------------
# Coil registers (FC01/FC05) — boolean controls
# ---------------------------------------------------------------------------

COIL_POWER_ON = 4000
COIL_BYPASS_ON = 4003
COIL_BOOST_ON = 4004
COIL_OVERPRESSURE_ON = 4005
COIL_REBOOT = 4006
COIL_FILTER_ALERT = 4020  # read-only
COIL_HUMIDITY_CONTROL_ENABLE = 4027
COIL_VOC_CONTROL_ENABLE = 4030
COIL_PM_CONTROL_ENABLE = 4031
COIL_MODBUS_ON = 4036

# Coil read blocks
COIL_BLOCK_1 = (4000, 7)  # 4000-4006: power, bypass, boost, overpressure, reboot
COIL_BLOCK_2 = (4020, 1)  # 4020: filter alert
COIL_BLOCK_3 = (4027, 1)  # 4027: humidity control
COIL_BLOCK_4 = (4030, 7)  # 4030-4036: VOC, PM, modbus

# ---------------------------------------------------------------------------
# Settings flags bitmasks (register 2009)
# ---------------------------------------------------------------------------

FLAG_POWER_ON = 1
FLAG_BOOST_ON = 16
FLAG_OVERPRESSURE_ON = 32
FLAG_REBOOT = 64

# ---------------------------------------------------------------------------
# UI flags bitmasks (register 2014)
# ---------------------------------------------------------------------------

UI_FLAG_FILTER_ALERT = 16

# ---------------------------------------------------------------------------
# UI flags1 bitmasks (register 2015)
# ---------------------------------------------------------------------------

UI_FLAG1_MODBUS_ON = 16

# ---------------------------------------------------------------------------
# Error flags bitmasks (register 1026)
# ---------------------------------------------------------------------------

ERROR_FIRE_ALARM = 1
ERROR_FAN1 = 2
ERROR_FAN2 = 4
ERROR_SENSOR_1 = 8
ERROR_SENSOR_2 = 16
ERROR_SENSOR_3 = 32
ERROR_SENSOR_4 = 64
ERROR_SENSOR_5 = 128
ERROR_SENSOR_CO2 = 256
ERROR_HEATER = 512
ERROR_LOW_SUPPLY = 1024
ERROR_FILTER = 2048

# ---------------------------------------------------------------------------
# Write validation limits (min, max) from spec
# ---------------------------------------------------------------------------

LIMITS: dict[int, tuple[int, int]] = {
    REG_WORKING_MODE: (1, 8),
    REG_HUMIDITY_SETPOINT: (50, 950),
    REG_CO2_SETPOINT: (450, 2000),
    REG_MANUAL_FAN_LEVEL: (0, 10),
    REG_OVERPRESSURE_FAN_LEVEL: (0, 10),
    REG_BOOST_TIMEOUT: (180, 3600),
    REG_OVERPRESSURE_TIMEOUT: (180, 3600),
    REG_FILTER_REMINDER_INTERVAL: (720, 8760),
    REG_FILTER_REMINDER_ELAPSED: (0, 65535),
    REG_VOC_SETPOINT: (0, 500),
    REG_PM25_SETPOINT: (0, 999),
}
