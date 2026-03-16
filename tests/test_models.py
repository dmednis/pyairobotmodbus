"""Tests for data models."""

from pyairobotmodbus.models import ErrorFlag, OperatingMode


class TestOperatingMode:
    def test_values(self) -> None:
        assert OperatingMode.AUTOMATIC.value == 1
        assert OperatingMode.MANUAL.value == 2

    def test_from_int(self) -> None:
        assert OperatingMode(1) is OperatingMode.AUTOMATIC
        assert OperatingMode(2) is OperatingMode.MANUAL


class TestErrorFlag:
    def test_no_errors(self) -> None:
        flags = ErrorFlag(0)
        assert flags == ErrorFlag.NONE

    def test_single_flag(self) -> None:
        flags = ErrorFlag(1)
        assert ErrorFlag.FIRE_ALARM in flags

    def test_multiple_flags(self) -> None:
        flags = ErrorFlag(2 | 2048)
        assert ErrorFlag.FAN1 in flags
        assert ErrorFlag.FILTER in flags
        assert ErrorFlag.FIRE_ALARM not in flags

    def test_all_flags(self) -> None:
        all_val = 1 | 2 | 4 | 8 | 16 | 32 | 64 | 128 | 256 | 512 | 1024 | 2048
        flags = ErrorFlag(all_val)
        assert ErrorFlag.FIRE_ALARM in flags
        assert ErrorFlag.FAN1 in flags
        assert ErrorFlag.FAN2 in flags
        assert ErrorFlag.HEATER in flags
        assert ErrorFlag.FILTER in flags
