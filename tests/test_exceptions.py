"""Tests for exception hierarchy."""

from pyairobotmodbus.exceptions import (
    AirobotConnectionError,
    AirobotError,
    AirobotInvalidDataError,
    AirobotReadError,
    AirobotTimeoutError,
    AirobotWriteError,
)


class TestExceptionHierarchy:
    def test_base_exception(self) -> None:
        assert issubclass(AirobotError, Exception)

    def test_connection_error(self) -> None:
        assert issubclass(AirobotConnectionError, AirobotError)

    def test_read_error(self) -> None:
        assert issubclass(AirobotReadError, AirobotError)

    def test_write_error(self) -> None:
        assert issubclass(AirobotWriteError, AirobotError)

    def test_timeout_error_dual_inheritance(self) -> None:
        assert issubclass(AirobotTimeoutError, AirobotError)
        assert issubclass(AirobotTimeoutError, TimeoutError)

    def test_invalid_data_error(self) -> None:
        assert issubclass(AirobotInvalidDataError, AirobotError)


class TestExceptionChaining:
    def test_cause_chaining(self) -> None:
        original = OSError("network down")
        exc = AirobotConnectionError("failed")
        exc.__cause__ = original
        assert exc.__cause__ is original

    def test_timeout_catchable_as_timeout_error(self) -> None:
        exc = AirobotTimeoutError("timed out")
        try:
            raise exc
        except TimeoutError as caught:
            assert caught is exc
        except AirobotError:
            raise AssertionError("Should have been caught as TimeoutError") from None

    def test_timeout_catchable_as_airobot_error(self) -> None:
        exc = AirobotTimeoutError("timed out")
        try:
            raise exc
        except AirobotError as caught:
            assert caught is exc
