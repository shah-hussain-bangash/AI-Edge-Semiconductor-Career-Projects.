#!/usr/bin/env python3
"""Capture ESP32 JSON Lines telemetry to CSV with basic schema checks."""
import argparse
import csv
import json
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

FIELDS = [
    "gateway_utc", "device_id", "seq", "uptime_ms", "ax_mps2",
    "ay_mps2", "az_mps2", "temp_c", "bus_v", "current_ma",
    "adxl345_valid", "ds18b20_valid", "ina219_valid", "valid",
]
NUMERIC = ("ax_mps2", "ay_mps2", "az_mps2", "temp_c", "bus_v", "current_ma")

def parse_record(line):
    obj = json.loads(line)
    if not isinstance(obj, dict) or obj.get("schema_version") != 1:
        raise ValueError("unsupported schema")
    if not isinstance(obj.get("device_id"), str) or not obj["device_id"]:
        raise ValueError("missing device_id")
    for key in ("seq", "uptime_ms"):
        if type(obj.get(key)) is not int or obj[key] < 0:
            raise ValueError(f"invalid {key}")
    for key in NUMERIC:
        value = obj.get(key)
        if type(value) not in (int, float) or not math.isfinite(value):
            raise ValueError(f"invalid {key}")
    for key in ("adxl345_valid", "ds18b20_valid", "ina219_valid", "valid"):
        if type(obj.get(key)) is not bool:
            raise ValueError(f"invalid {key}")
    if obj["valid"] != (obj["adxl345_valid"] and obj["ds18b20_valid"] and obj["ina219_valid"]):
        raise ValueError("inconsistent validity flags")
    return {k: obj[k] for k in FIELDS if k != "gateway_utc"}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True, help="e.g. /dev/cu.usbserial-XXXX or COM3")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--seconds", type=int, default=600)
    parser.add_argument("--output", default="data/baseline.csv")
    args = parser.parse_args()
    if args.seconds <= 0:
        parser.error("--seconds must be positive")
    try:
        import serial
    except ImportError:
        sys.exit("Install dependencies: python -m pip install -r scripts/requirements.txt")
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    valid = invalid = gaps = 0
    last_seq = {}
    start = time.monotonic()
    try:
        with serial.Serial(args.port, args.baud, timeout=1) as port, out.open("w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=FIELDS)
            writer.writeheader()
            while time.monotonic() - start < args.seconds:
                raw = port.readline()
                if not raw:
                    continue
                line = raw.decode("utf-8", errors="replace").strip()
                if not line or line.startswith("#"):
                    continue
                try:
                    record = parse_record(line)
                except (ValueError, json.JSONDecodeError) as exc:
                    invalid += 1
                    print(f"invalid line: {exc}", file=sys.stderr)
                    continue
                device = record["device_id"]
                prior = last_seq.get(device)
                if prior is not None and record["seq"] > prior + 1:
                    gaps += record["seq"] - prior - 1
                last_seq[device] = record["seq"]
                record["gateway_utc"] = datetime.now(timezone.utc).isoformat()
                writer.writerow(record)
                file.flush()
                valid += 1
    except (OSError, Exception) as exc:
        print(f"capture stopped: {exc}", file=sys.stderr)
        return 1
    finally:
        print(f"records={valid} invalid={invalid} sequence_gaps={gaps} output={out}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
