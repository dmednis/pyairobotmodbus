# pyairobotmodbus

Python library for communicating with Airobot ventilation units via Modbus TCP.

## Installation

```bash
pip install pyairobotmodbus
```

## Usage

```python
import asyncio
from pyairobotmodbus import AirobotModbusClient, OperatingMode

async def main():
    client = AirobotModbusClient("192.168.1.100")
    await client.connect()

    # Read all data
    data = await client.async_get_data()
    print(f"Supply air: {data.supply_air_temp}°C")
    print(f"Extract air: {data.extract_air_temp}°C")
    print(f"CO2: {data.co2_level} ppm")
    print(f"Fan level: {data.supply_fan_level}")

    # Control the device
    await client.async_set_mode(OperatingMode.MANUAL)
    await client.async_set_fan_speed(7)
    await client.async_set_boost(True)

    await client.disconnect()

asyncio.run(main())
```

## CLI

```bash
# Read all data from the device
pyairobotmodbus read 192.168.1.100

# Set a parameter
pyairobotmodbus set 192.168.1.100 fan_speed 7

# Monitor continuously
pyairobotmodbus monitor 192.168.1.100
```
