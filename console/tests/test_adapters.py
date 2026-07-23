import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))

from adapters import openmotor, openrocket  # noqa: E402


class AdapterErrorTests(unittest.TestCase):
    def test_openrocket_timeout_becomes_domain_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            python = Path(tmp) / "python"
            python.touch()
            motor = Path(tmp) / "motor.eng"
            motor.touch()
            timeout = subprocess.TimeoutExpired(cmd=["openrocket"], timeout=1)
            with (
                mock.patch.object(openrocket, "OPENROCKET_VENV_PYTHON", python),
                mock.patch.object(openrocket.subprocess, "run", side_effect=timeout),
            ):
                with self.assertRaisesRegex(openrocket.OpenRocketError, "did not finish"):
                    openrocket.fly(str(motor), timeout_s=1)

    def test_openrocket_rejects_missing_motor_curve(self):
        with tempfile.TemporaryDirectory() as tmp:
            python = Path(tmp) / "python"
            python.touch()
            with mock.patch.object(openrocket, "OPENROCKET_VENV_PYTHON", python):
                with self.assertRaisesRegex(openrocket.OpenRocketError, "not found"):
                    openrocket.fly(str(Path(tmp) / "missing.eng"))

    def test_openmotor_timeout_becomes_domain_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            python = Path(tmp) / "python"
            python.touch()
            timeout = subprocess.TimeoutExpired(cmd=["openmotor"], timeout=1)
            with (
                mock.patch.object(openmotor, "OPENMOTOR_VENV_PYTHON", python),
                mock.patch.object(openmotor.subprocess, "run", side_effect=timeout),
            ):
                with self.assertRaisesRegex(openmotor.OpenMotorError, "did not finish"):
                    openmotor.run_sweep({}, timeout_s=1)


if __name__ == "__main__":
    unittest.main()
