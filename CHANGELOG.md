# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [0.3.0] - 2026-08-09

### Added
- Python 3.14 support (added to the CI test matrix)
- Automated PyPI publishing on GitHub release, with PEP 740 attestations

### Changed
- `AirobotData` sensor fields that are always present (core temperatures,
  humidity, CO2, VOC, PM2.5, airflow) are no longer typed as `Optional` — they
  always carry a value. `extra_temp` and `extra_humidity` remain `Optional`.

### Fixed
- Extra temperature/humidity sensors now decode to `None` when the optional
  sensor is not installed, instead of leaking the device sentinel readings
  (3276.7 °C / -0.1 %). The CLI shows `n/a` for these cases.
- Decode 32-bit registers (working time, boost/overpressure timeouts) using
  little-endian word order, matching the device and the write path
- Read PM2.5 as a single 16-bit register (1031) rather than folding the
  following register into a 32-bit value

## [0.2.0] - 2026-03-15

### Added
- Async context manager support (`async with AirobotModbusClient(...)`)
- Factory method `AirobotModbusClient.create()` for connected client instances
- Connection guards on all read/write operations
- Register count validation on read operations
- `AirobotTimeoutError` exception with dual `TimeoutError` inheritance
- `AirobotInvalidDataError` exception for malformed device data
- `__version__` attribute from package metadata
- PEP 561 `py.typed` marker for type checker support
- `NullHandler` logging setup
- Pre-commit hooks (ruff, mypy, codespell)
- GitHub Actions CI (lint, test, build)
- 100% test coverage enforcement

### Changed
- Enhanced error handling: `TimeoutError` and `OSError` now raise specific exceptions
- Dev dependencies expanded: ruff, mypy, pytest-cov, pytest-timeout

## [0.1.0] - 2026-03-15

### Added
- Initial release
- Async Modbus TCP client for Airobot ventilation units
- Full sensor data reading (temperatures, humidity, CO2, VOC, PM2.5, fans)
- Device control (mode, fan speed, setpoints, boost, overpressure, bypass)
- CLI with `read`, `set`, and `monitor` commands
- Register definitions based on Airobot VU Modbus specification
