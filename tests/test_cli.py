"""Tests for the CLI module."""

from __future__ import annotations

import argparse
import asyncio
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from pyairobotmodbus.cli import (
    SETTERS,
    _cmd_monitor,
    _cmd_read,
    _cmd_set,
    _format_data,
    _parse_bool,
    main,
)
from pyairobotmodbus.exceptions import AirobotError
from pyairobotmodbus.models import AirobotData, ErrorFlag, OperatingMode


def _make_data(**overrides: Any) -> AirobotData:
    """Build an AirobotData with sensible defaults, allowing overrides."""
    defaults: dict[str, Any] = dict(
        firmware_version=300,
        extract_air_temp=21.5,
        supply_air_temp=22.0,
        outside_air_temp=5.0,
        exhaust_air_temp=-1.0,
        extra_temp=0.0,
        extract_air_humidity=65.0,
        supply_air_humidity=60.0,
        outside_air_humidity=80.0,
        exhaust_air_humidity=40.0,
        extra_humidity=0.0,
        co2_level=450,
        voc=150,
        pm25=25,
        supply_fan_level=5,
        extract_fan_level=5,
        supply_fan_rpm=1200,
        extract_fan_rpm=1100,
        supply_airflow=120,
        extract_airflow=115,
        working_time_ms=3600000,
        error_flags=ErrorFlag.NONE,
        server_connected=True,
        heat_recovery_efficiency=85,
        operating_mode=OperatingMode.AUTOMATIC,
        humidity_setpoint=60.0,
        co2_setpoint=800,
        voc_setpoint=200,
        pm25_setpoint=50,
        manual_fan_level=5,
        overpressure_fan_level=5,
        boost_timeout=1800,
        overpressure_timeout=1800,
        filter_reminder_interval=4320,
        filter_reminder_elapsed=100,
        power_on=True,
        bypass_on=False,
        boost_on=False,
        overpressure_on=False,
        filter_alert=False,
        humidity_control_enabled=True,
        voc_control_enabled=False,
        pm_control_enabled=False,
    )
    defaults.update(overrides)
    return AirobotData(**defaults)


class TestParseBool:
    def test_true_values(self) -> None:
        for v in ("1", "true", "on", "True", "ON", "TRUE"):
            assert _parse_bool(v) is True

    def test_false_values(self) -> None:
        for v in ("0", "false", "off", "no", "whatever"):
            assert _parse_bool(v) is False


class TestFormatData:
    def test_basic_output(self) -> None:
        data = _make_data()
        output = _format_data(data)
        assert "=== Device Info ===" in output
        assert "Firmware version:  300" in output
        assert "AUTOMATIC" in output
        assert "ON" in output  # power_on=True
        assert "21.5" in output  # extract_air_temp
        assert "450 ppm" in output  # co2
        assert "120 m3/h" in output  # airflow
        assert "85%" in output  # heat recovery
        assert "Errors:            None" in output

    def test_error_flags_displayed(self) -> None:
        data = _make_data(error_flags=ErrorFlag.FAN1 | ErrorFlag.HEATER)
        output = _format_data(data)
        assert "FAN1" in output
        assert "HEATER" in output

    def test_controls_on_off(self) -> None:
        data = _make_data(
            humidity_control_enabled=True,
            voc_control_enabled=True,
            pm_control_enabled=True,
            boost_on=True,
            overpressure_on=True,
            bypass_on=True,
        )
        output = _format_data(data)
        # humidity/voc/pm control should show ON
        assert "control: ON" in output

    def test_power_off(self) -> None:
        data = _make_data(power_on=False)
        output = _format_data(data)
        assert "Power:             OFF" in output

    def test_filter_alert_yes(self) -> None:
        data = _make_data(filter_alert=True)
        output = _format_data(data)
        assert "Filter alert:      YES" in output


class TestCmdRead:
    @pytest.mark.asyncio
    async def test_cmd_read_success(self) -> None:
        mock_client = AsyncMock()
        mock_client.async_get_data = AsyncMock(return_value=_make_data())
        mock_client.connect = AsyncMock()
        mock_client.disconnect = AsyncMock()

        args = argparse.Namespace(host="192.168.1.100", port=502)
        with (
            patch(
                "pyairobotmodbus.cli.AirobotModbusClient",
                return_value=mock_client,
            ),
            patch("builtins.print") as mock_print,
        ):
            await _cmd_read(args)

        mock_client.connect.assert_awaited_once()
        mock_client.async_get_data.assert_awaited_once()
        mock_client.disconnect.assert_awaited_once()
        mock_print.assert_called_once()


class TestCmdSet:
    @pytest.mark.asyncio
    async def test_set_known_param_with_converter(self) -> None:
        mock_client = AsyncMock()
        mock_client.connect = AsyncMock()
        mock_client.disconnect = AsyncMock()
        mock_client.async_set_fan_speed = AsyncMock()

        args = argparse.Namespace(
            host="192.168.1.100", port=502, param="fan_speed", value="7"
        )
        with (
            patch(
                "pyairobotmodbus.cli.AirobotModbusClient",
                return_value=mock_client,
            ),
            patch("builtins.print"),
        ):
            await _cmd_set(args)

        mock_client.async_set_fan_speed.assert_awaited_once_with(7)
        mock_client.disconnect.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_set_param_without_converter(self) -> None:
        """Test a setter that has no converter (e.g. reset_filter)."""
        mock_client = AsyncMock()
        mock_client.connect = AsyncMock()
        mock_client.disconnect = AsyncMock()
        mock_client.async_reset_filter_timer = AsyncMock()

        args = argparse.Namespace(
            host="192.168.1.100", port=502, param="reset_filter", value=None
        )
        with (
            patch(
                "pyairobotmodbus.cli.AirobotModbusClient",
                return_value=mock_client,
            ),
            patch("builtins.print"),
        ):
            await _cmd_set(args)

        mock_client.async_reset_filter_timer.assert_awaited_once_with()
        mock_client.disconnect.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_set_unknown_param(self) -> None:
        args = argparse.Namespace(
            host="192.168.1.100", port=502, param="nonexistent", value="1"
        )
        with (
            patch("builtins.print") as mock_print,
            pytest.raises(SystemExit, match="1"),
        ):
            await _cmd_set(args)

        # Should have printed the unknown parameter message
        calls = [str(c) for c in mock_print.call_args_list]
        assert any("Unknown parameter" in c for c in calls)
        assert any("Available parameters" in c for c in calls)


class TestCmdMonitor:
    @pytest.mark.asyncio
    async def test_monitor_keyboard_interrupt(self) -> None:
        mock_client = AsyncMock()
        mock_client.connect = AsyncMock()
        mock_client.disconnect = AsyncMock()
        mock_client.async_get_data = AsyncMock(return_value=_make_data())

        args = argparse.Namespace(host="192.168.1.100", port=502, interval=1)

        # Make asyncio.sleep raise KeyboardInterrupt to stop the loop
        with (
            patch(
                "pyairobotmodbus.cli.AirobotModbusClient",
                return_value=mock_client,
            ),
            patch("builtins.print"),
            patch(
                "pyairobotmodbus.cli.asyncio.sleep",
                side_effect=KeyboardInterrupt,
            ),
        ):
            await _cmd_monitor(args)

        mock_client.disconnect.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_monitor_cancelled_error(self) -> None:
        mock_client = AsyncMock()
        mock_client.connect = AsyncMock()
        mock_client.disconnect = AsyncMock()
        mock_client.async_get_data = AsyncMock(return_value=_make_data())

        args = argparse.Namespace(host="192.168.1.100", port=502, interval=1)

        with (
            patch(
                "pyairobotmodbus.cli.AirobotModbusClient",
                return_value=mock_client,
            ),
            patch("builtins.print"),
            patch(
                "pyairobotmodbus.cli.asyncio.sleep",
                side_effect=asyncio.CancelledError,
            ),
        ):
            await _cmd_monitor(args)

        mock_client.disconnect.assert_awaited_once()


class TestMain:
    def test_main_read_command(self) -> None:
        with (
            patch("sys.argv", ["pyairobotmodbus", "read", "192.168.1.100"]),
            patch("pyairobotmodbus.cli.asyncio.run") as mock_run,
        ):
            main()
            mock_run.assert_called_once()

    def test_main_set_command(self) -> None:
        with (
            patch(
                "sys.argv",
                ["pyairobotmodbus", "set", "192.168.1.100", "fan_speed", "7"],
            ),
            patch("pyairobotmodbus.cli.asyncio.run") as mock_run,
        ):
            main()
            mock_run.assert_called_once()

    def test_main_monitor_command(self) -> None:
        with (
            patch(
                "sys.argv",
                [
                    "pyairobotmodbus",
                    "monitor",
                    "192.168.1.100",
                    "--interval",
                    "2",
                ],
            ),
            patch("pyairobotmodbus.cli.asyncio.run") as mock_run,
        ):
            main()
            mock_run.assert_called_once()

    def test_main_custom_port(self) -> None:
        with (
            patch(
                "sys.argv",
                ["pyairobotmodbus", "--port", "5020", "read", "10.0.0.1"],
            ),
            patch("pyairobotmodbus.cli.asyncio.run") as mock_run,
        ):
            main()
            mock_run.assert_called_once()

    def test_main_keyboard_interrupt(self) -> None:
        with (
            patch("sys.argv", ["pyairobotmodbus", "read", "192.168.1.100"]),
            patch(
                "pyairobotmodbus.cli.asyncio.run",
                side_effect=KeyboardInterrupt,
            ),
        ):
            # Should not raise, just pass silently
            main()

    def test_main_airobot_error(self) -> None:
        with (
            patch("sys.argv", ["pyairobotmodbus", "read", "192.168.1.100"]),
            patch(
                "pyairobotmodbus.cli.asyncio.run",
                side_effect=AirobotError("test error"),
            ),
            patch("builtins.print"),
            pytest.raises(SystemExit, match="1"),
        ):
            main()

    def test_main_no_command(self) -> None:
        with (
            patch("sys.argv", ["pyairobotmodbus"]),
            pytest.raises(SystemExit, match="2"),
        ):
            main()


class TestSettersDict:
    def test_all_setters_have_valid_structure(self) -> None:
        for _name, (method_name, converter, desc) in SETTERS.items():
            assert isinstance(method_name, str)
            assert converter is None or callable(converter)
            assert isinstance(desc, str)

    def test_mode_converter(self) -> None:
        _, converter, _ = SETTERS["mode"]
        assert converter is not None
        assert converter("automatic") == OperatingMode.AUTOMATIC
        assert converter("MANUAL") == OperatingMode.MANUAL


class TestMainModule:
    def test_main_module(self) -> None:
        called = False

        def fake_main() -> None:
            nonlocal called
            called = True

        with patch("pyairobotmodbus.cli.main", fake_main):
            import importlib

            import pyairobotmodbus.__main__

            importlib.reload(pyairobotmodbus.__main__)

        assert called


class TestCliIfNameMain:
    def test_cli_module_name_main(self) -> None:
        """Cover the `if __name__ == '__main__': main()` guard in cli.py."""
        import runpy

        with (
            patch("sys.argv", ["pyairobotmodbus", "read", "192.168.1.100"]),
            patch("pyairobotmodbus.cli.asyncio.run") as mock_run,
        ):
            runpy.run_module(
                "pyairobotmodbus.cli", run_name="__main__", alter_sys=False
            )
            mock_run.assert_called_once()
