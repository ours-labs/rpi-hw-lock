# rpi-hw-lock

`rpi-hw-lock` is a lightweight Python library for safely obtaining exclusive access to Raspberry Pi hardware that is normally used by long-running systemd services.

It temporarily stops selected services before a block of code accesses GPIO, SPI, I2C, or UART devices, then restarts only the services that were active originally. Cleanup runs even when the protected block raises an exception.

> This library controls system services. Review the service list and sudoers rules carefully before using it on a production device.

## Installation

```bash
pip install rpi-hw-lock
```

The package has no runtime dependencies outside the Python standard library. It requires Python 3.9 or later and a Linux system using systemd.

## Usage

```python
from rpi_hw_lock import exclusive_hardware_access

with exclusive_hardware_access(["example-sensor.service"]):
    # Access GPIO, SPI, I2C, or UART hardware here.
    ...
# Services that were active before the block are running again here.
```

Multiple services can be controlled together:

```python
with exclusive_hardware_access(["service-a.service", "service-b.service"]):
    ...
```

## Configure sudoers

Stopping and starting a system service normally requires elevated privileges. Create a narrowly scoped sudoers rule that permits only the required actions for the required services:

```bash
sudo visudo -f /etc/sudoers.d/rpi-hw-lock
```

Example, adjusted for a dedicated service account and the exact service name:

```text
<service-user> ALL=(root) NOPASSWD: /usr/bin/systemctl stop example-sensor.service
<service-user> ALL=(root) NOPASSWD: /usr/bin/systemctl start example-sensor.service
```

Do not grant unrestricted passwordless access to `systemctl`.

You can check the configuration before attempting exclusive access:

```python
from rpi_hw_lock import check_permissions

check_permissions(["example-sensor.service"])
```

## API

| API | Purpose |
| --- | --- |
| `exclusive_hardware_access(services, timeout=10.0, verify_stopped=True)` | Temporarily stops one or more services and restores their original active state. |
| `check_permissions(services, timeout=5.0)` | Checks whether non-interactive sudo access is configured. |
| `is_active(service)` | Returns whether a service is currently active. |
| `ServiceControlError` | Raised when a stop, start, or verification operation fails. |

## Behavior and limitations

- Services that were already inactive are not started when the context exits.
- With `verify_stopped=True`, each stopped service is checked before the protected block runs.
- A normal `systemctl stop` is not treated as a failure by `Restart=on-failure`.
- If restarting a service fails while another exception is already propagating, the restart failure is logged so that the original exception is not hidden. Operators must monitor logs and recover the service manually.
- This library coordinates with systemd. It is not a cross-process lock for programs that access the same hardware outside those services.

## Development

```bash
python -m unittest discover -s tests -v
python -m build
python -m twine check dist/*
```

## License

MIT
