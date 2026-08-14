"""Unit tests that mock subprocess calls and never control real services."""
import subprocess
import unittest
from unittest.mock import patch, MagicMock

from rpi_hw_lock.exclusive_access import (
    exclusive_hardware_access,
    check_permissions,
    is_active,
    ServiceControlError,
)


def _completed(stdout="", stderr="", returncode=0):
    return subprocess.CompletedProcess(
        args=[], returncode=returncode, stdout=stdout, stderr=stderr)


class TestIsActive(unittest.TestCase):
    @patch("rpi_hw_lock.exclusive_access.subprocess.run")
    def test_active_service(self, mock_run):
        mock_run.return_value = _completed(stdout="active\n")
        self.assertTrue(is_active("foo.service"))

    @patch("rpi_hw_lock.exclusive_access.subprocess.run")
    def test_inactive_service(self, mock_run):
        mock_run.return_value = _completed(stdout="inactive\n")
        self.assertFalse(is_active("foo.service"))

    @patch("rpi_hw_lock.exclusive_access.subprocess.run")
    def test_unknown_service_is_not_active(self, mock_run):
        # Unknown services are not considered active.
        mock_run.return_value = _completed(stdout="unknown\n")
        self.assertFalse(is_active("does-not-exist.service"))


class TestExclusiveHardwareAccess(unittest.TestCase):
    def _mock_run_sequence(self, mock_run, is_active_value):
        """Simulate state transitions for is-active, stop, and start."""
        state = {"active": is_active_value}

        def side_effect(cmd, **kwargs):
            if "is-active" in cmd:
                return _completed(stdout="active\n" if state["active"] else "inactive\n")
            if "stop" in cmd:
                state["active"] = False
                return _completed()
            if "start" in cmd:
                state["active"] = True
                return _completed()
            return _completed()
        mock_run.side_effect = side_effect

    @patch("rpi_hw_lock.exclusive_access.subprocess.run")
    def test_stops_and_restarts_active_service(self, mock_run):
        self._mock_run_sequence(mock_run, is_active_value=True)

        with exclusive_hardware_access(["sensor.service"]):
            pass

        called_cmds = [call.args[0] for call in mock_run.call_args_list]
        self.assertIn(["sudo", "systemctl", "stop", "sensor.service"], called_cmds)
        self.assertIn(["sudo", "systemctl", "start", "sensor.service"], called_cmds)

    @patch("rpi_hw_lock.exclusive_access.subprocess.run")
    def test_does_not_touch_already_inactive_service(self, mock_run):
        # A service that starts inactive must not be stopped or started.
        self._mock_run_sequence(mock_run, is_active_value=False)

        with exclusive_hardware_access(["sensor.service"]):
            pass

        called_cmds = [call.args[0] for call in mock_run.call_args_list]
        self.assertNotIn(["sudo", "systemctl", "stop", "sensor.service"], called_cmds)
        self.assertNotIn(["sudo", "systemctl", "start", "sensor.service"], called_cmds)

    @patch("rpi_hw_lock.exclusive_access.subprocess.run")
    def test_restarts_even_when_exception_raised_inside_block(self, mock_run):
        self._mock_run_sequence(mock_run, is_active_value=True)

        with self.assertRaises(ValueError):
            with exclusive_hardware_access(["sensor.service"]):
                raise ValueError("simulated protected-block failure")

        called_cmds = [call.args[0] for call in mock_run.call_args_list]
        self.assertIn(["sudo", "systemctl", "start", "sensor.service"], called_cmds)

    @patch("rpi_hw_lock.exclusive_access.subprocess.run")
    def test_multiple_services_mixed_active_state(self, mock_run):
        # Verify a mixed set of active and inactive services.
        state = {"service-a": True, "service-b": False}

        def side_effect(cmd, **kwargs):
            service = cmd[-1]
            if "is-active" in cmd:
                return _completed(stdout="active\n" if state[service] else "inactive\n")
            if "stop" in cmd:
                state[service] = False
            elif "start" in cmd:
                state[service] = True
            return _completed()
        mock_run.side_effect = side_effect

        with exclusive_hardware_access(["service-a", "service-b"]):
            pass

        called_cmds = [call.args[0] for call in mock_run.call_args_list]
        self.assertIn(["sudo", "systemctl", "stop", "service-a"], called_cmds)
        self.assertIn(["sudo", "systemctl", "start", "service-a"], called_cmds)
        self.assertNotIn(["sudo", "systemctl", "stop", "service-b"], called_cmds)
        self.assertNotIn(["sudo", "systemctl", "start", "service-b"], called_cmds)

    @patch("rpi_hw_lock.exclusive_access.subprocess.run")
    def test_single_string_service_is_accepted(self, mock_run):
        # A single service string is accepted.
        self._mock_run_sequence(mock_run, is_active_value=True)

        with exclusive_hardware_access("sensor.service"):
            pass

        called_cmds = [call.args[0] for call in mock_run.call_args_list]
        self.assertIn(["sudo", "systemctl", "stop", "sensor.service"], called_cmds)

    @patch("rpi_hw_lock.exclusive_access.subprocess.run")
    def test_verify_stopped_raises_if_still_active(self, mock_run):
        # The service remains active even though the stop command returned.
        def side_effect(cmd, **kwargs):
            if "is-active" in cmd:
                return _completed(stdout="active\n")
            return _completed()
        mock_run.side_effect = side_effect

        with self.assertRaises(ServiceControlError):
            with exclusive_hardware_access(["sensor.service"]):
                pass

    @patch("rpi_hw_lock.exclusive_access.subprocess.run")
    def test_stop_command_failure_raises_service_control_error(self, mock_run):
        def side_effect(cmd, **kwargs):
            if "is-active" in cmd:
                return _completed(stdout="active\n")
            if "stop" in cmd:
                raise subprocess.CalledProcessError(
                    returncode=1, cmd=cmd, stderr="Unit not found.")
            return _completed()
        mock_run.side_effect = side_effect

        with self.assertRaises(ServiceControlError):
            with exclusive_hardware_access(["sensor.service"]):
                pass

    @patch("rpi_hw_lock.exclusive_access.subprocess.run")
    def test_stop_command_timeout_raises_service_control_error(self, mock_run):
        def side_effect(cmd, **kwargs):
            if "is-active" in cmd:
                return _completed(stdout="active\n")
            if "stop" in cmd:
                raise subprocess.TimeoutExpired(cmd=cmd, timeout=10)
            return _completed()
        mock_run.side_effect = side_effect

        with self.assertRaises(ServiceControlError):
            with exclusive_hardware_access(["sensor.service"], timeout=10):
                pass

    @patch("rpi_hw_lock.exclusive_access.subprocess.run")
    def test_restart_failure_does_not_mask_original_exception(self, mock_run):
        # A restart failure must not mask the protected block's exception.
        state = {"active": True}

        def side_effect(cmd, **kwargs):
            if "is-active" in cmd:
                return _completed(stdout="active\n" if state["active"] else "inactive\n")
            if "stop" in cmd:
                state["active"] = False
                return _completed()
            if "start" in cmd:
                raise subprocess.CalledProcessError(
                    returncode=1, cmd=cmd, stderr="restart failed")
            return _completed()
        mock_run.side_effect = side_effect

        with self.assertRaises(ValueError) as ctx:
            with exclusive_hardware_access(["sensor.service"]):
                raise ValueError("original error")

        self.assertEqual(str(ctx.exception), "original error")


class TestCheckPermissions(unittest.TestCase):
    @patch("rpi_hw_lock.exclusive_access.subprocess.run")
    def test_raises_when_password_required(self, mock_run):
        mock_run.return_value = _completed(
            stderr="sudo: a password is required")
        with self.assertRaises(PermissionError):
            check_permissions(["sensor.service"])

    @patch("rpi_hw_lock.exclusive_access.subprocess.run")
    def test_passes_when_no_password_required(self, mock_run):
        mock_run.return_value = _completed(stdout="active\n")
        check_permissions(["sensor.service"])


if __name__ == "__main__":
    unittest.main()
