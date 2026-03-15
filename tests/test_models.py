"""Tests for data models."""

from pyairobotmodbus.models import ErrorFlag, OperatingMode


class TestOperatingMode:
    def test_values(self):
        assert OperatingMode.AUTOMATIC == 1
        assert OperatingMode.MANUAL == 2

    def test_from_int(self):
        assert OperatingMode(1) is OperatingMode.AUTOMATIC
        assert OperatingMode(2) is OperatingMode.MANUAL


class TestErrorFlag:
    def test_no_errors(self):
        flags = ErrorFlag(0)
        assert flags == ErrorFlag.NONE

    def test_single_flag(self):
        flags = ErrorFlag(1)
        assert ErrorFlag.FIRE_ALARM in flags

    def test_multiple_flags(self):
        flags = ErrorFlag(2 | 2048)
        assert ErrorFlag.FAN1 in flags
        assert ErrorFlag.FILTER in flags
        assert ErrorFlag.FIRE_ALARM not in flags

    def test_all_flags(self):
        all_val = 1 | 2 | 4 | 8 | 16 | 32 | 64 | 128 | 256 | 512 | 1024 | 2048
        flags = ErrorFlag(all_val)
        assert ErrorFlag.FIRE_ALARM in flags
        assert ErrorFlag.FAN1 in flags
        assert ErrorFlag.FAN2 in flags
        assert ErrorFlag.HEATER in flags
        assert ErrorFlag.FILTER in flags
