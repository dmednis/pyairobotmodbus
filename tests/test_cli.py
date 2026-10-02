"""Tests for the CLI module."""

from __future__ import annotations

import argparse
import asyncio
import subprocess
import sys
from collections.abc import Iterator
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from conftest import load_sample
from modbus_connection import ModbusConnectionError, ModbusTcpParams
from modbus_connection.mock import MockModbusConnection, WriteEvent

from pyairobotmodbus.cli import (
    SETTERS,
    _cmd_monitor,
    _cmd_read,
    _cmd_set,
    _format_data,
    _parse_bool,
    main,
)
from pyairobotmodbus.client import DEFAULT_UNIT_ID
from pyairobotmodbus.exceptions import AirobotConnectionError, AirobotError
from pyairobotmodbus.models import AirobotData, ErrorFlag, OperatingMode


def _close_coro(coro: Any) -> None:
    """Close coroutine to avoid 'coroutine was never awaited' warnings."""
    coro.close()


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
        for v in ("0", "false", "off", "False", "OFF", "FALSE"):
            assert _parse_bool(v) is False

    def test_invalid_value_raises(self) -> None:
        """Invalid boolean strings must raise ValueError, not silently return False."""
        for v in ("wat", "yes", "no", "maybe", "2", ""):
            with pytest.raises(ValueError, match="Invalid boolean"):
                _parse_bool(v)


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


@pytest.fixture
def connection_cls(
    mock_modbus_connection: MockModbusConnection,
) -> Iterator[MagicMock]:
    """Route the CLI's connection to an in-memory unit holding the sample."""
    load_sample(mock_modbus_connection.for_unit(DEFAULT_UNIT_ID))
    with patch(
        "modbus_connection.tmodbus.ModbusConnection",
        return_value=mock_modbus_connection,
    ) as cls:
        yield cls


class TestCmdRead:
    async def test_cmd_read_success(
        self,
        connection_cls: MagicMock,
        mock_modbus_connection: MockModbusConnection,
    ) -> None:
        args = argparse.Namespace(host="192.168.1.100", port=5020)
        with patch("builtins.print") as mock_print:
            await _cmd_read(args)

        connection_cls.assert_called_once_with(
            ModbusTcpParams(host="192.168.1.100", port=5020)
        )
        mock_print.assert_called_once()
        assert "Firmware" in mock_print.call_args.args[0]
        assert mock_modbus_connection.connected is False

    async def test_cmd_read_failure_closes_connection(
        self,
        connection_cls: MagicMock,
        mock_modbus_connection: MockModbusConnection,
    ) -> None:
        unit = mock_modbus_connection.for_unit(DEFAULT_UNIT_ID)
        unit.fail_requests(ModbusConnectionError("connection reset"))
        args = argparse.Namespace(host="192.168.1.100", port=502)

        with pytest.raises(AirobotConnectionError):
            await _cmd_read(args)

        assert mock_modbus_connection.connected is False


class TestCmdSet:
    @pytest.mark.parametrize(
        ("param", "value", "event"),
        [
            pytest.param(
                "fan_speed",
                "7",
                WriteEvent("holding", 2005, [7], 0x06),
                id="with_converter",
            ),
            pytest.param(
                "reset_filter",
                None,
                WriteEvent("holding", 2018, [0], 0x06),
                id="without_converter",
            ),
        ],
    )
    async def test_set_param(
        self,
        connection_cls: MagicMock,
        mock_modbus_connection: MockModbusConnection,
        param: str,
        value: str | None,
        event: WriteEvent,
    ) -> None:
        writes: list[WriteEvent] = []
        mock_modbus_connection.for_unit(DEFAULT_UNIT_ID).on_write(writes.append)
        args = argparse.Namespace(
            host="192.168.1.100", port=502, param=param, value=value
        )
        with patch("builtins.print"):
            await _cmd_set(args)

        assert writes == [event]
        assert mock_modbus_connection.connected is False

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
    @pytest.mark.parametrize(
        "stop",
        [
            pytest.param(KeyboardInterrupt, id="keyboard_interrupt"),
            pytest.param(asyncio.CancelledError, id="cancelled"),
        ],
    )
    async def test_monitor_stops(
        self,
        connection_cls: MagicMock,
        mock_modbus_connection: MockModbusConnection,
        stop: type[BaseException],
    ) -> None:
        args = argparse.Namespace(host="192.168.1.100", port=502, interval=1)

        with (
            patch("builtins.print") as mock_print,
            patch("pyairobotmodbus.cli.asyncio.sleep", side_effect=stop),
        ):
            await _cmd_monitor(args)

        assert any("Firmware" in str(c) for c in mock_print.call_args_list)
        assert mock_modbus_connection.connected is False


class TestMain:
    def test_main_read_command(self) -> None:
        with (
            patch("sys.argv", ["pyairobotmodbus", "read", "192.168.1.100"]),
            patch(
                "pyairobotmodbus.cli.asyncio.run", side_effect=_close_coro
            ) as mock_run,
        ):
            main()
            mock_run.assert_called_once()

    def test_main_set_command(self) -> None:
        with (
            patch(
                "sys.argv",
                ["pyairobotmodbus", "set", "192.168.1.100", "fan_speed", "7"],
            ),
            patch(
                "pyairobotmodbus.cli.asyncio.run", side_effect=_close_coro
            ) as mock_run,
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
            patch(
                "pyairobotmodbus.cli.asyncio.run", side_effect=_close_coro
            ) as mock_run,
        ):
            main()
            mock_run.assert_called_once()

    def test_main_custom_port(self) -> None:
        with (
            patch(
                "sys.argv",
                ["pyairobotmodbus", "--port", "5020", "read", "10.0.0.1"],
            ),
            patch(
                "pyairobotmodbus.cli.asyncio.run", side_effect=_close_coro
            ) as mock_run,
        ):
            main()
            mock_run.assert_called_once()

    def test_main_keyboard_interrupt(self) -> None:
        def _close_and_raise(coro: Any) -> None:
            coro.close()
            raise KeyboardInterrupt

        with (
            patch("sys.argv", ["pyairobotmodbus", "read", "192.168.1.100"]),
            patch(
                "pyairobotmodbus.cli.asyncio.run",
                side_effect=_close_and_raise,
            ),
        ):
            # Should not raise, just pass silently
            main()

    def test_main_airobot_error(self) -> None:
        def _close_and_raise(coro: Any) -> None:
            coro.close()
            raise AirobotError("test error")

        with (
            patch("sys.argv", ["pyairobotmodbus", "read", "192.168.1.100"]),
            patch(
                "pyairobotmodbus.cli.asyncio.run",
                side_effect=_close_and_raise,
            ),
            patch("builtins.print"),
            pytest.raises(SystemExit, match="1"),
        ):
            main()

    def test_main_set_bad_value_exits_cleanly(self) -> None:
        """Bad converter values must produce clean exit, not traceback."""

        def _run_and_raise(coro: Any) -> None:
            coro.close()
            raise ValueError("invalid literal for int()")

        with (
            patch(
                "sys.argv",
                ["pyairobotmodbus", "set", "192.168.1.100", "fan_speed", "abc"],
            ),
            patch(
                "pyairobotmodbus.cli.asyncio.run",
                side_effect=_run_and_raise,
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

    def test_mode_converter_accepts_short_names(self) -> None:
        """Help text says auto|manual, so those must work."""
        _, converter, _ = SETTERS["mode"]
        assert converter is not None
        assert converter("auto") == OperatingMode.AUTOMATIC
        assert converter("manual") == OperatingMode.MANUAL

    def test_mode_converter_invalid_raises_airobot_error(self) -> None:
        """Invalid mode values must raise a clean error, not raw KeyError."""
        _, converter, _ = SETTERS["mode"]
        assert converter is not None
        with pytest.raises((ValueError, AirobotError)):
            converter("turbo")


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
    @pytest.mark.filterwarnings("ignore:.*found in sys.modules.*:RuntimeWarning")
    def test_cli_module_name_main(self) -> None:
        """Cover the `if __name__ == '__main__': main()` guard in cli.py."""
        import runpy

        with (
            patch("sys.argv", ["pyairobotmodbus", "read", "192.168.1.100"]),
            patch(
                "pyairobotmodbus.cli.asyncio.run", side_effect=_close_coro
            ) as mock_run,
        ):
            runpy.run_module(
                "pyairobotmodbus.cli", run_name="__main__", alter_sys=False
            )
            mock_run.assert_called_once()


class TestMissingBackend:
    """The core install has no Modbus backend; only the cli extra brings one."""

    def test_command_prints_install_hint(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with (
            patch("sys.argv", ["pyairobotmodbus", "read", "192.168.1.100"]),
            patch.dict(sys.modules, {"modbus_connection.tmodbus": None}),
            patch("pyairobotmodbus.cli.asyncio.run") as mock_run,
            pytest.raises(SystemExit, match="1"),
        ):
            main()

        mock_run.assert_not_called()
        assert "pip install 'pyairobotmodbus[cli]'" in capsys.readouterr().err

    def test_cli_imports_without_backend(self) -> None:
        # A fresh interpreter, so a top-level backend import in the CLI module
        # would crash the console script with a traceback instead.
        script = (
            "import sys\n"
            "sys.modules['tmodbus'] = None\n"
            "sys.argv = ['pyairobotmodbus', 'read', '192.168.1.100']\n"
            "from pyairobotmodbus.cli import main\n"
            "main()\n"
        )
        result = subprocess.run(
            [sys.executable, "-c", script], capture_output=True, text=True, check=False
        )

        assert result.returncode == 1
        assert "Traceback" not in result.stderr
        assert "pip install 'pyairobotmodbus[cli]'" in result.stderr
