# pyairobotmodbus

Python library for communicating with Airobot ventilation units via Modbus TCP.

## Installation

```bash
pip install pyairobotmodbus
```

The library itself only needs `modbus-connection`. The CLI and the example
below also need a Modbus backend, which the `cli` extra installs:

```bash
pip install 'pyairobotmodbus[cli]'
```

## Usage

The client talks through a [`modbus-connection`](https://home-assistant-libs.github.io/modbus-connection/)
`ModbusUnit`, so it can share one link with other devices on the same bus.
The unit opens the link on the first request and reconnects after a drop.

```python
import asyncio

from modbus_connection import ModbusTcpParams
from modbus_connection.tmodbus import ModbusConnection

from pyairobotmodbus import (
    DEFAULT_PORT,
    DEFAULT_UNIT_ID,
    AirobotModbusClient,
    OperatingMode,
)


async def main():
    connection = ModbusConnection(
        ModbusTcpParams(host="192.168.1.100", port=DEFAULT_PORT)
    )
    client = AirobotModbusClient(connection.for_unit(DEFAULT_UNIT_ID))
    try:
        data = await client.async_get_data()
        print(f"Supply air: {data.supply_air_temp}°C")
        print(f"CO2: {data.co2_level} ppm")

        await client.async_set_mode(OperatingMode.MANUAL)
        await client.async_set_fan_speed(7)
    finally:
        await connection.close()

asyncio.run(main())
```

### Error handling

All exceptions inherit from `AirobotError`:

```python
from pyairobotmodbus import AirobotError, AirobotConnectionError, AirobotTimeoutError

try:
    data = await client.async_get_data()
except AirobotTimeoutError:
    print("Device did not respond in time")
except AirobotConnectionError:
    print("Could not reach the device")
except AirobotError as e:
    print(f"Communication error: {e}")
```

### Sensor data

`async_get_data()` returns an `AirobotData` snapshot with:

- **Temperatures** — supply, extract, outside, exhaust, extra (°C)
- **Humidity** — supply, extract, outside, exhaust, extra (RH%)
- **Air quality** — CO2 (ppm), VOC (index), PM2.5 (μg/m³)
- **Fans** — supply/extract level, RPM, and airflow (m³/h)
- **Status** — error flags, heat recovery efficiency, working time

### Identity

```python
identity = await client.async_get_identity()
print(identity.serial_number)  # "01234567" for a label reading V01234567
print(identity.mac_address)    # "02:1a:2b:3c:4d:5e"
```

These come from registers the manufacturer does not document (see
[Undocumented registers](#undocumented-registers)). A unit whose firmware lacks
them raises `AirobotReadError`.

### Device control

```python
# Operating mode
await client.async_set_mode(OperatingMode.AUTOMATIC)

# Fan speed (1-10)
await client.async_set_fan_speed(7)

# Toggles
await client.async_set_boost(True)
await client.async_set_overpressure(True)
await client.async_set_bypass(True)
await client.async_set_power(True)

# Setpoints
await client.async_set_co2_setpoint(800)         # ppm
await client.async_set_humidity_setpoint(50.0)    # RH%
await client.async_set_voc_setpoint(200)          # index
await client.async_set_pm25_setpoint(25)          # μg/m³

# Timeouts
await client.async_set_boost_timeout(1200)        # seconds
await client.async_set_overpressure_timeout(600)  # seconds

# Filter reminder
await client.async_set_filter_reminder_interval(4380)  # hours

# Sensor control toggles
await client.async_set_humidity_control(True)
await client.async_set_voc_control(True)
await client.async_set_pm_control(True)
```

## Undocumented registers

Airobot's [Modbus specification](docs/airobot-vu-modbus-basic-en-2026-06-29.pdf)
does not cover the registers below. They were found by a read-only scan of a
unit running firmware 544 on 2026-10-02, so other firmware may move or drop
them. The examples use made-up values.

### Decoded

All are input registers, read with function code 0x04.

| Register | Value | Encoding |
|---|---|---|
| 3000–3001 | Serial number, digits only (a label reading `V01234567` gives `01234567`) | BCD, low word first: `0x4567 0x0123` |
| 3002–3004 | MAC address | Low byte first in each register: `0x1A02 0x3C2B 0x5E4D` is `02:1a:2b:3c:4d:5e` |

`async_get_identity()` reads these.

### Readable but not decoded

- **Input 3005–3011:** `0x1003`, `0x0402`, `0`, `0`, `1224`, `1680`, `1188` on
  the scanned unit.
- **Holding 2019–2020:** the unit's IPv4 address, low word first
  (`0x0132 0xC0A8` is `192.168.1.50`). The library doesn't read it.
- **Gaps in the documented ranges:** input 1012–1066 and holding 2001–2089
  answer at addresses the specification skips. Their meanings are unknown.

Every other address scanned returned exception 0x02 (illegal data address).
The scan covered input and holding 0–199 and the first 100 addresses of each
thousand block up to 9000. Input reads of the 2000s and holding reads of the
1000s are also rejected.

## CLI

Needs the `cli` extra (`pip install 'pyairobotmodbus[cli]'`).

```bash
# Read all data from the device
pyairobotmodbus read 192.168.1.100

# Set a parameter
pyairobotmodbus set 192.168.1.100 fan_speed 7

# Monitor continuously
pyairobotmodbus monitor 192.168.1.100
```

## Testing

`modbus-connection` ships a pytest plugin whose `mock_modbus_unit` fixture is
an in-memory unit, so tests can load registers and assert writes without a
device:

```python
async def test_power(mock_modbus_unit):
    client = AirobotModbusClient(mock_modbus_unit)
    await client.async_set_power(False)
    assert mock_modbus_unit.coil[4000] is False
```
