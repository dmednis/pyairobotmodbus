"""Simple CLI for testing Airobot ventilation unit Modbus communication."""

from __future__ import annotations

import argparse
import asyncio
import sys

from .client import AirobotModbusClient
from .exceptions import AirobotError
from .models import AirobotData, ErrorFlag, OperatingMode


def _format_data(data: AirobotData) -> str:
    """Format device data for display."""
    errors = []
    for flag in ErrorFlag:
        if flag != ErrorFlag.NONE and flag in data.error_flags:
            errors.append(flag.name)

    lines = [
        "=== Device Info ===",
        f"  Firmware version:  {data.firmware_version}",
        f"  Operating mode:    {data.operating_mode.name}",
        f"  Power:             {'ON' if data.power_on else 'OFF'}",
        f"  Server connected:  {'Yes' if data.server_connected else 'No'}",
        f"  Working time:      {data.working_time_ms / 1000 / 3600:.1f} hours",
        "",
        "=== Temperatures ===",
        f"  Extract air:       {data.extract_air_temp}°C",
        f"  Supply air:        {data.supply_air_temp}°C",
        f"  Outside air:       {data.outside_air_temp}°C",
        f"  Exhaust air:       {data.exhaust_air_temp}°C",
        f"  Extra sensor:      {data.extra_temp}°C",
        "",
        "=== Humidity ===",
        f"  Extract air:       {data.extract_air_humidity}%",
        f"  Supply air:        {data.supply_air_humidity}%",
        f"  Outside air:       {data.outside_air_humidity}%",
        f"  Exhaust air:       {data.exhaust_air_humidity}%",
        f"  Extra sensor:      {data.extra_humidity}%",
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
        f"  Humidity:          {data.humidity_setpoint}% (control: {'ON' if data.humidity_control_enabled else 'OFF'})",
        f"  CO2:               {data.co2_setpoint} ppm",
        f"  VOC:               {data.voc_setpoint} index (control: {'ON' if data.voc_control_enabled else 'OFF'})",
        f"  PM2.5:             {data.pm25_setpoint} ug/m3 (control: {'ON' if data.pm_control_enabled else 'OFF'})",
        "",
        "=== Modes ===",
        f"  Manual fan level:  {data.manual_fan_level}",
        f"  Boost:             {'ON' if data.boost_on else 'OFF'} (timeout: {data.boost_timeout}s)",
        f"  Overpressure:      {'ON' if data.overpressure_on else 'OFF'} (fan: {data.overpressure_fan_level}, timeout: {data.overpressure_timeout}s)",
        f"  Bypass:            {'ON' if data.bypass_on else 'OFF'}",
        "",
        "=== Alerts ===",
        f"  Filter alert:      {'YES' if data.filter_alert else 'No'}",
        f"  Filter reminder:   {data.filter_reminder_interval}h interval, {data.filter_reminder_elapsed}h elapsed",
        f"  Errors:            {', '.join(errors) if errors else 'None'}",
    ]
    return "\n".join(lines)


SETTERS = {
    "mode": ("async_set_mode", lambda v: OperatingMode[v.upper()], "auto|manual"),
    "fan_speed": ("async_set_fan_speed", int, "0-10"),
    "power": ("async_set_power", lambda v: v.lower() in ("1", "true", "on"), "on|off"),
    "boost": ("async_set_boost", lambda v: v.lower() in ("1", "true", "on"), "on|off"),
    "overpressure": ("async_set_overpressure", lambda v: v.lower() in ("1", "true", "on"), "on|off"),
    "bypass": ("async_set_bypass", lambda v: v.lower() in ("1", "true", "on"), "on|off"),
    "co2_setpoint": ("async_set_co2_setpoint", int, "450-2000"),
    "humidity_setpoint": ("async_set_humidity_setpoint", float, "5.0-95.0"),
    "voc_setpoint": ("async_set_voc_setpoint", int, "0-500"),
    "pm25_setpoint": ("async_set_pm25_setpoint", int, "0-999"),
    "boost_timeout": ("async_set_boost_timeout", int, "180-3600"),
    "overpressure_timeout": ("async_set_overpressure_timeout", int, "180-3600"),
    "overpressure_fan_level": ("async_set_overpressure_fan_level", int, "0-10"),
    "filter_reminder_interval": ("async_set_filter_reminder_interval", int, "720-8760"),
    "humidity_control": ("async_set_humidity_control", lambda v: v.lower() in ("1", "true", "on"), "on|off"),
    "voc_control": ("async_set_voc_control", lambda v: v.lower() in ("1", "true", "on"), "on|off"),
    "pm_control": ("async_set_pm_control", lambda v: v.lower() in ("1", "true", "on"), "on|off"),
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
    param = args.param
    if param not in SETTERS:
        print(f"Unknown parameter: {param}")
        print(f"Available parameters: {', '.join(sorted(SETTERS))}")
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
    parser.add_argument("--port", type=int, default=502, help="Modbus TCP port (default: 502)")
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
    p_monitor.add_argument("--interval", type=int, default=5, help="Polling interval in seconds (default: 5)")

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


if __name__ == "__main__":
    main()
