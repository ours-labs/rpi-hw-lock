"""Temporarily stop systemd services for exclusive hardware access.

The context manager records which services are active, stops those services,
and restores them after the protected block exits. This lets an existing
service release GPIO, SPI, I2C, or UART devices without requiring cooperation
from that service's application code.
"""
import contextlib
import logging
import subprocess

logger = logging.getLogger("rpi_hw_lock")

# Default timeout for each systemctl stop or start operation.
DEFAULT_TIMEOUT_SEC = 10.0


class ServiceControlError(RuntimeError):
    """Raised when a systemctl operation or state check fails."""


def is_active(service: str) -> bool:
    """Return whether the named systemd service reports an active state."""
    result = subprocess.run(
        ["systemctl", "is-active", service],
        capture_output=True, text=True,
    )
    return result.stdout.strip() == "active"


def _run_systemctl(action: str, service: str, timeout: float) -> None:
    """Run a narrowly scoped sudo systemctl action for one service."""
    try:
        subprocess.run(
            ["sudo", "systemctl", action, service],
            check=True, timeout=timeout,
            capture_output=True, text=True,
        )
    except subprocess.CalledProcessError as e:
        raise ServiceControlError(
            f"systemctl {action} {service} failed: {e.stderr.strip()}"
        ) from e
    except subprocess.TimeoutExpired as e:
        raise ServiceControlError(
            f"systemctl {action} {service} did not complete within {timeout} seconds"
        ) from e


def check_permissions(services, timeout: float = 5.0) -> None:
    """Check whether non-interactive sudo is available for each service."""
    if isinstance(services, str):
        services = [services]
    for service in services:
        result = subprocess.run(
            ["sudo", "-n", "systemctl", "status", service],
            capture_output=True, text=True, timeout=timeout,
        )
        # sudo -n returns immediately when a password would be required.
        if "password is required" in (result.stderr or "").lower():
            raise PermissionError(
                f"Passwordless sudo access is not configured for {service}. "
                "Review the sudoers setup in README.md."
            )


@contextlib.contextmanager
def exclusive_hardware_access(services, timeout: float = DEFAULT_TIMEOUT_SEC,
                               verify_stopped: bool = True):
    """Temporarily stop services and restore their original active state.

    Args:
        services: One service name or an iterable of service names.
        timeout: Timeout in seconds for each stop or start command.
        verify_stopped: Verify that each stopped service becomes inactive.

    Usage:
        from rpi_hw_lock import exclusive_hardware_access

        with exclusive_hardware_access(["example-sensor.service"]):
            # Access GPIO, SPI, I2C, or UART hardware here.
            ...
    """
    if isinstance(services, str):
        services = [services]

    was_active = {}
    stopped = []

    for service in services:
        was_active[service] = is_active(service)

    for service in services:
        if was_active[service]:
            logger.info("stopping %s for exclusive hardware access", service)
            _run_systemctl("stop", service, timeout)
            stopped.append(service)
            if verify_stopped and is_active(service):
                raise ServiceControlError(
                    f"{service} is still active after the stop command"
                )

    try:
        yield
    finally:
        for service in stopped:
            logger.info("restarting %s", service)
            try:
                _run_systemctl("start", service, timeout)
            except ServiceControlError:
                # Preserve any exception raised by the protected block. The
                # restart failure remains visible in the service logs.
                logger.exception(
                    "failed to restart %s; manual recovery is required", service
                )
