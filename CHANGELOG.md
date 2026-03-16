# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

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
