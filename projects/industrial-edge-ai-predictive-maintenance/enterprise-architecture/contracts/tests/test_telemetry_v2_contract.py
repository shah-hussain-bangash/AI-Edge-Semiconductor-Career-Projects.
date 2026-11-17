"""EA-23 candidate telemetry V2 contract checks.

Run from enterprise-architecture/:
    python -m pip install -r contracts/tests/requirements.txt
    python -m unittest discover -s contracts/tests -v

These checks validate the documented proposed contract, not real hardware,
the serial-to-V2 adapter, MQTT security, deployed ingestion, or an approved release.
"""
from __future__ import annotations

import copy
import json
import math
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / "telemetry-v2.schema.json").read_text(encoding="utf-8"))
VALID = json.loads(
    (ROOT / "examples/telemetry-v2.synthetic-valid.json").read_text(encoding="utf-8")
)
PARTIAL = json.loads(
    (ROOT / "examples/telemetry-v2.synthetic-partial.json").read_text(encoding="utf-8")
)
Draft202012Validator.check_schema(SCHEMA)
VALIDATOR = Draft202012Validator(SCHEMA, format_checker=FormatChecker())

CHANNELS = {
    "adxl345": ("acceleration_x_mps2", "acceleration_y_mps2", "acceleration_z_mps2"),
    "ds18b20": ("motor_case_temperature_c",),
    "ina219": ("bus_voltage_v", "current_a"),
}


def semantic_errors(record: dict) -> list[str]:
    """Additional local invariants beyond Draft 2020-12 JSON Schema."""
    errors: list[str] = []
    for channel, field_names in CHANNELS.items():
        if record["quality"][channel] == "valid":
            if any(record["measurements"][name] is None for name in field_names):
                errors.append(f"valid {channel} has missing measurement")
    for key, value in record["measurements"].items():
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if not math.isfinite(value):
                errors.append(f"nonfinite {key}")
    if record["quality"]["session_quality"] == "unavailable" and record["boot_id"] is not None:
        errors.append("unavailable session must not assert boot ID")
    if record["timestamp"]["clock_quality"] == "gateway_receipt_only":
        if record["timestamp"]["device_time_utc"] is not None:
            errors.append("gateway-only clock cannot assert device UTC")
    return errors


def failures(record: dict) -> list[str]:
    """Return schema and semantic failure messages for one in-memory fixture."""
    schema_errors = [e.message for e in VALIDATOR.iter_errors(record)]
    if schema_errors:
        return schema_errors
    return semantic_errors(record)


class TelemetryV2ContractTests(unittest.TestCase):
    def assert_rejected(self, record: dict) -> None:
        self.assertTrue(failures(record), "Expected contract rejection")

    def test_t01_valid_synthetic_fixture(self) -> None:
        self.assertEqual(failures(VALID), [])

    def test_t02_partial_sensor_fixture(self) -> None:
        self.assertEqual(failures(PARTIAL), [])

    def test_t03_invalid_ina219_cannot_emit_zero(self) -> None:
        item = copy.deepcopy(PARTIAL)
        item["measurements"]["current_a"] = 0.0
        self.assert_rejected(item)

    def test_t04_invalid_adxl345_requires_null_axes(self) -> None:
        item = copy.deepcopy(VALID)
        item["quality"]["adxl345"] = "invalid"
        self.assert_rejected(item)

    def test_t05_invalid_temperature_requires_null(self) -> None:
        item = copy.deepcopy(VALID)
        item["quality"]["ds18b20"] = "stale"
        self.assert_rejected(item)

    def test_t09_reject_wrong_schema(self) -> None:
        item = copy.deepcopy(VALID)
        item["schema_version"] = "3.0"
        self.assert_rejected(item)

    def test_t09_reject_missing_site(self) -> None:
        item = copy.deepcopy(VALID)
        del item["site_id"]
        self.assert_rejected(item)

    def test_t09_reject_extra_top_level_field(self) -> None:
        item = copy.deepcopy(VALID)
        item["unapproved"] = 42
        self.assert_rejected(item)

    def test_t09_reject_boolean_as_sequence(self) -> None:
        item = copy.deepcopy(VALID)
        item["sequence"] = True
        self.assert_rejected(item)

    def test_t09_reject_out_of_range_sequence(self) -> None:
        item = copy.deepcopy(VALID)
        item["sequence"] = 4294967296
        self.assert_rejected(item)

    def test_t10_verified_device_clock_requires_timestamp(self) -> None:
        item = copy.deepcopy(VALID)
        item["timestamp"]["clock_quality"] = "device_clock_verified"
        self.assert_rejected(item)

    def test_t11_verified_session_requires_boot_id(self) -> None:
        item = copy.deepcopy(VALID)
        item["quality"]["session_quality"] = "verified"
        self.assert_rejected(item)

    def test_valid_channel_cannot_be_null(self) -> None:
        item = copy.deepcopy(VALID)
        item["measurements"]["motor_case_temperature_c"] = None
        self.assert_rejected(item)

    def test_reject_nonfinite_measurement(self) -> None:
        item = copy.deepcopy(VALID)
        item["measurements"]["current_a"] = float("nan")
        self.assert_rejected(item)

    def test_reject_invalid_timestamp_format(self) -> None:
        item = copy.deepcopy(VALID)
        item["timestamp"]["gateway_received_utc"] = "yesterday"
        self.assert_rejected(item)

    def test_gateway_only_cannot_claim_device_utc(self) -> None:
        item = copy.deepcopy(VALID)
        item["timestamp"]["device_time_utc"] = "2026-11-17T07:00:00Z"
        self.assert_rejected(item)

    def test_unavailable_session_cannot_claim_boot_identity(self) -> None:
        item = copy.deepcopy(VALID)
        item["quality"]["session_quality"] = "unavailable"
        item["boot_id"] = "invented-boot"
        self.assert_rejected(item)

    def test_valid_sensor_may_read_actual_zero(self) -> None:
        item = copy.deepcopy(VALID)
        item["measurements"]["current_a"] = 0.0
        self.assertEqual(failures(item), [])


if __name__ == "__main__":
    unittest.main()
