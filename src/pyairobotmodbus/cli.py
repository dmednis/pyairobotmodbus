"""Simple CLI for testing Airobot ventilation unit Modbus communication."""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Callable
from typing import Any

from .client import AirobotModbusClient
from .exceptions import AirobotError
from .models import AirobotData, ErrorFlag, OperatingMode
from .registers import (
    LIMITS,
    REG_BOOST_TIMEOUT,
    REG_CO2_SETPOINT,
    REG_FILTER_REMINDER_INTERVAL,
    REG_MANUAL_FAN_LEVEL,
    REG_OVERPRESSURE_FAN_LEVEL,
    REG_OVERPRESSURE_TIMEOUT,
    REG_PM25_SETPOINT,
    REG_VOC_SETPOINT,
)


def _range_hint(reg: int) -> str:
    """Build a CLI range hint (e.g. ``"450-2000"``) from the write LIMITS.

    Keeps the validated range and the displayed range as a single source of
    truth — the values come straight from :data:`LIMITS`.
    """
    low, high = LIMITS[reg]
    return f"{low}-{high}"


def _parse_bool(v: str) -> bool:
    """Parse a string to bool for CLI boolean arguments."""
    low = v.lower()
    if low in ("1", "true", "on"):
        return True
    if low in ("0", "false", "off"):
        return False
    raise ValueError(f"Invalid boolean value: {v!r} (expected on/off, true/false, 1/0)")


def _format_data(data: AirobotData) -> str:
    """Format device data for display."""
    errors: list[str] = []
    for flag in ErrorFlag:
        if flag != ErrorFlag.NONE and flag in data.error_flags:
            name = flag.name
            if name is not None:
                errors.append(name)

    extra_temp = f"{data.extra_temp}\u00b0C" if data.extra_temp is not None else "n/a"
    extra_hum = f"{data.extra_humidity}%" if data.extra_humidity is not None else "n/a"
    hum_ctrl = "ON" if data.humidity_control_enabled else "OFF"
    voc_ctrl = "ON" if data.voc_control_enabled else "OFF"
    pm_ctrl = "ON" if data.pm_control_enabled else "OFF"
    boost_status = "ON" if data.boost_on else "OFF"
    op_status = "ON" if data.overpressure_on else "OFF"
    op_fan = data.overpressure_fan_level
    op_timeout = data.overpressure_timeout
    filt_int = data.filter_reminder_interval
    filt_el = data.filter_reminder_elapsed

    lines = [
        "=== Device Info ===",
        f"  Firmware version:  {data.firmware_version}",
        f"  Operating mode:    {data.operating_mode.name}",
        f"  Power:             {'ON' if data.power_on else 'OFF'}",
        (f"  Server connected:  {'Yes' if data.server_connected else 'No'}"),
        (f"  Working time:      {data.working_time_ms / 1000 / 3600:.1f} hours"),
        "",
        "=== Temperatures ===",
        f"  Extract air:       {data.extract_air_temp}\u00b0C",
        f"  Supply air:        {data.supply_air_temp}\u00b0C",
        f"  Outside air:       {data.outside_air_temp}\u00b0C",
        f"  Exhaust air:       {data.exhaust_air_temp}\u00b0C",
        f"  Extra sensor:      {extra_temp}",
        "",
        "=== Humidity ===",
        f"  Extract air:       {data.extract_air_humidity}%",
        f"  Supply air:        {data.supply_air_humidity}%",
        f"  Outside air:       {data.outside_air_humidity}%",
        f"  Exhaust air:       {data.exhaust_air_humidity}%",
        f"  Extra sensor:      {extra_hum}",
        "",
        "=== Air Quality ===",
        f"  CO2:               {data.co2_level} ppm",
        f"  VOC:               {data.voc} index",
        f"  PM2.5:             {data.pm25} ug/m3",
        "",
        "=== Fans ===",
        f"  Supply level:      {data.supply_fan_level}/10",
        f"  Extract level:     {data.extract_fan_level}/10",
        f"  Supply RPM:        {data.supply_fan_rpm}",
        f"  Extract RPM:       {data.extract_fan_rpm}",
        f"  Supply airflow:    {data.supply_airflow} m3/h",
        f"  Extract airflow:   {data.extract_airflow} m3/h",
        "",
        "=== Heat Recovery ===",
        f"  Efficiency:        {data.heat_recovery_efficiency}%",
        "",
        "=== Setpoints ===",
        f"  Humidity:          {data.humidity_setpoint}% (control: {hum_ctrl})",
        f"  CO2:               {data.co2_setpoint} ppm",
        f"  VOC:               {data.voc_setpoint} index (control: {voc_ctrl})",
        f"  PM2.5:             {data.pm25_setpoint} ug/m3 (control: {pm_ctrl})",
        "",
        "=== Modes ===",
        f"  Manual fan level:  {data.manual_fan_level}",
        f"  Boost:             {boost_status} (timeout: {data.boost_timeout}s)",
        f"  Overpressure:      {op_status} (fan: {op_fan}, timeout: {op_timeout}s)",
        f"  Bypass:            {'ON' if data.bypass_on else 'OFF'}",
        "",
        "=== Alerts ===",
        f"  Filter alert:      {'YES' if data.filter_alert else 'No'}",
        f"  Filter reminder:   {filt_int}h interval, {filt_el}h elapsed",
        f"  Errors:            {', '.join(errors) if errors else 'None'}",
    ]
    return "\n".join(lines)


# Each entry: (method_name, converter | None, description)
# converter transforms a CLI string into the argument for the method.
_Converter = Callable[[str], Any]

_MODE_ALIASES: dict[str, str] = {
    "auto": "AUTOMATIC",
    "manual": "MANUAL",
}


def _parse_mode(v: str) -> OperatingMode:
    """Parse a mode string, accepting both full enum names and short aliases."""
    key = _MODE_ALIASES.get(v.lower(), v.upper())
    try:
        return OperatingMode[key]
    except KeyError:
        valid = ", ".join(
            sorted({*_MODE_ALIASES, *(m.name.lower() for m in OperatingMode)})
        )
        raise ValueError(f"Invalid mode: {v!r} (expected {valid})") from None


SETTERS: dict[str, tuple[str, _Converter | None, str]] = {
    "mode": (
        "async_set_mode",
        _parse_mode,
        "auto|manual",
    ),
    "fan_speed": ("async_set_fan_speed", int, _range_hint(REG_MANUAL_FAN_LEVEL)),
    "power": ("async_set_power", _parse_bool, "on|off"),
    "boost": ("async_set_boost", _parse_bool, "on|off"),
    "overpressure": (
        "async_set_overpressure",
        _parse_bool,
        "on|off",
    ),
    "bypass": ("async_set_bypass", _parse_bool, "on|off"),
    "co2_setpoint": ("async_set_co2_setpoint", int, _range_hint(REG_CO2_SETPOINT)),
    "humidity_setpoint": (
        "async_set_humidity_setpoint",
        float,
        "5.0-95.0",  # RH%, scaled x10 on the device — not a raw LIMITS range
    ),
    "voc_setpoint": ("async_set_voc_setpoint", int, _range_hint(REG_VOC_SETPOINT)),
    "pm25_setpoint": ("async_set_pm25_setpoint", int, _range_hint(REG_PM25_SETPOINT)),
    "boost_timeout": ("async_set_boost_timeout", int, _range_hint(REG_BOOST_TIMEOUT)),
    "overpressure_timeout": (
        "async_set_overpressure_timeout",
        int,
        _range_hint(REG_OVERPRESSURE_TIMEOUT),
    ),
    "overpressure_fan_level": (
        "async_set_overpressure_fan_level",
        int,
        _range_hint(REG_OVERPRESSURE_FAN_LEVEL),
    ),
    "filter_reminder_interval": (
        "async_set_filter_reminder_interval",
        int,
        _range_hint(REG_FILTER_REMINDER_INTERVAL),
    ),
    "humidity_control": (
        "async_set_humidity_control",
        _parse_bool,
        "on|off",
    ),
    "voc_control": (
        "async_set_voc_control",
        _parse_bool,
        "on|off",
    ),
    "pm_control": (
        "async_set_pm_control",
        _parse_bool,
        "on|off",
    ),
    "reset_filter": ("async_reset_filter_timer", None, ""),
    "reboot": ("async_reboot", None, ""),
}


async def _cmd_read(args: argparse.Namespace) -> None:
    client = AirobotModbusClient(args.host, port=args.port)
    await client.connect()
    try:
        data = await client.async_get_data()
        print(_format_data(data))
    finally:
        await client.disconnect()


async def _cmd_set(args: argparse.Namespace) -> None:
    param: str = args.param
    if param not in SETTERS:
        print(f"Unknown parameter: {param}")
        print("Available parameters:")
        for name in sorted(SETTERS):
            hint = SETTERS[name][2]
            print(f"  {name} {hint}".rstrip())
        sys.exit(1)

    method_name, converter, _ = SETTERS[param]
    client = AirobotModbusClient(args.host, port=args.port)
    await client.connect()
    try:
        method = getattr(client, method_name)
        if converter is None:
            await method()
        else:
            await method(converter(args.value))
        print(f"Set {param} successfully.")
    finally:
        await client.disconnect()


async def _cmd_monitor(args: argparse.Namespace) -> None:
    client = AirobotModbusClient(args.host, port=args.port)
    await client.connect()
    try:
        while True:
            data = await client.async_get_data()
            # Clear screen
            print("\033[2J\033[H", end="")
            print(_format_data(data))
            print(f"\nRefreshing every {args.interval}s... (Ctrl+C to stop)")
            await asyncio.sleep(args.interval)
    except (KeyboardInterrupt, asyncio.CancelledError):
        print("\nStopped.")
    finally:
        await client.disconnect()


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="pyairobotmodbus",
        description="CLI tool for Airobot ventilation unit Modbus communication",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=502,
        help="Modbus TCP port (default: 502)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # read
    p_read = sub.add_parser("read", help="Read and display all device data")
    p_read.add_argument("host", help="Device IP address")

    # set
    p_set = sub.add_parser("set", help="Set a device parameter")
    p_set.add_argument("host", help="Device IP address")
    p_set.add_argument("param", help="Parameter name")
    p_set.add_argument("value", nargs="?", default=None, help="Value to set")

    # monitor
    p_monitor = sub.add_parser("monitor", help="Continuously monitor device data")
    p_monitor.add_argument("host", help="Device IP address")
    p_monitor.add_argument(
        "--interval",
        type=int,
        default=5,
        help="Polling interval in seconds (default: 5)",
    )

    args = parser.parse_args()

    try:
        if args.command == "read":
            asyncio.run(_cmd_read(args))
        elif args.command == "set":
            asyncio.run(_cmd_set(args))
        elif args.command == "monitor":
            asyncio.run(_cmd_monitor(args))
    except KeyboardInterrupt:
        pass
    except AirobotError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
    except (ValueError, KeyError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
