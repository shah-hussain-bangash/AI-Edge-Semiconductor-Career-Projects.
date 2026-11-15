import importlib.util
import json
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "capture_serial.py"
spec = importlib.util.spec_from_file_location("capture_serial", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

GOOD = {
    "schema_version": 1, "device_id": "motor-001", "seq": 1, "uptime_ms": 1000,
    "ax_mps2": 0.1, "ay_mps2": 0.2, "az_mps2": 9.8,
    "temp_c": 25.0, "bus_v": 12.0, "current_ma": 100.0,
    "adxl345_valid": True, "ds18b20_valid": True, "ina219_valid": True, "valid": True,
}

class CaptureTests(unittest.TestCase):
    def test_valid_record(self):
        self.assertEqual(module.parse_record(json.dumps(GOOD))["seq"], 1)

    def test_reject_wrong_schema(self):
        value = dict(GOOD, schema_version=2)
        with self.assertRaises(ValueError):
            module.parse_record(json.dumps(value))

    def test_reject_nonfinite(self):
        value = dict(GOOD, current_ma=float("nan"))
        with self.assertRaises(ValueError):
            module.parse_record(json.dumps(value))

    def test_reject_invalid_flags(self):
        value = dict(GOOD, valid=False)
        with self.assertRaises(ValueError):
            module.parse_record(json.dumps(value))

if __name__ == "__main__":
    unittest.main()
