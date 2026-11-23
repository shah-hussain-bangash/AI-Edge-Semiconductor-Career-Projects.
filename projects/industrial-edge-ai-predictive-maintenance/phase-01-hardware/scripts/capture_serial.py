#!/usr/bin/env python3
"""Capture ESP32 JSON Lines telemetry to CSV with basic schema checks."""
import argparse
import csv
import io
import json
import math
import re
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

MAX_LINE_BYTES = 4096
MAX_RECORDS = 10000
MAX_OUTPUT_BYTES = 16 * 1024 * 1024


def csv_text(record=None):
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=FIELDS)
    if record is None: writer.writeheader()
    else: writer.writerow(record)
    return stream.getvalue()


def validate_limits(max_records, max_output_bytes):
    if type(max_records) is not int or not 1 <= max_records <= MAX_RECORDS:
        raise ValueError('max records must be between 1 and 10000')
    if type(max_output_bytes) is not int or not len(csv_text().encode('utf-8')) <= max_output_bytes <= MAX_OUTPUT_BYTES:
        raise ValueError('max output bytes must fit the CSV header and stay within 16 MiB')


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON field")
        result[key] = value
    return result


def parse_record(line):
    obj = json.loads(line, object_pairs_hook=unique_object)
    expected = (set(FIELDS) - {"gateway_utc"}) | {"schema_version"}
    if not isinstance(obj, dict) or set(obj) != expected:
        raise ValueError("unexpected record fields")
    if type(obj.get("schema_version")) is not int or obj["schema_version"] != 1:
        raise ValueError("unsupported schema")
    if not isinstance(obj.get("device_id"), str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", obj["device_id"]):
        raise ValueError("missing device_id")
    for key in ("seq", "uptime_ms"):
        if type(obj.get(key)) is not int or not 0 <= obj[key] <= 4294967295:
            raise ValueError(f"invalid {key}")
    for key in NUMERIC:
        value = obj.get(key)
        if type(value) not in (int, float) or abs(value) > sys.float_info.max or not math.isfinite(value):
            raise ValueError(f"invalid {key}")
    for key in ("adxl345_valid", "ds18b20_valid", "ina219_valid", "valid"):
        if type(obj.get(key)) is not bool:
            raise ValueError(f"invalid {key}")
    if obj["valid"] != (obj["adxl345_valid"] and obj["ds18b20_valid"] and obj["ina219_valid"]):
        raise ValueError("inconsistent validity flags")
    return {k: obj[k] for k in FIELDS if k != "gateway_utc"}

def capture_stream(port, file, seconds, monotonic=time.monotonic,
                   receipt=lambda: datetime.now(timezone.utc).isoformat(), *,
                   max_records=MAX_RECORDS, max_output_bytes=MAX_OUTPUT_BYTES):
    """Read bounded chunks; preserve only complete, validated V1 records.

    Injected ports/clocks allow offline tests. Counts describe captured records,
    not physical measurement validity, authenticated sessions or packet loss.
    The output must use UTF-8 with newline='' as in the CLI. Byte counts cover
    successful writes and flushes; they are not power-loss durability evidence.
    """
    validate_limits(max_records, max_output_bytes)
    counts = dict(records=0, invalid=0, sensor_invalid=0, sequence_gaps=0, discontinuities=0,
                  output_bytes=0, withheld_records=0, stop_reason='duration_elapsed')
    previous = {}
    pending = bytearray()
    discarding = False
    start = monotonic()
    try:
        header = csv_text()
        if file.write(header) != len(header): raise OSError('incomplete CSV header write')
        file.flush()
        counts['output_bytes'] = len(header.encode('utf-8'))
        if counts['output_bytes'] == max_output_bytes:
            counts['stop_reason'] = 'byte_limit'
            return counts
        while monotonic() - start < seconds:
            raw = port.readline(MAX_LINE_BYTES + 1)
            if not raw:
                continue  # A timeout is not a record boundary.
            if discarding:
                if raw.endswith(b"\n"):
                    discarding = False
                continue
            pending.extend(raw)
            if len(pending) > MAX_LINE_BYTES:
                counts["invalid"] += 1
                pending.clear()
                discarding = not raw.endswith(b"\n")
                continue
            if not pending.endswith(b"\n"):
                continue
            try:
                line = pending.decode("utf-8").strip()
                pending.clear()
                if not line or line.startswith("#"):
                    continue
                record = parse_record(line)
            except (ValueError, UnicodeError, RecursionError):
                pending.clear()
                counts["invalid"] += 1
                continue
            record["gateway_utc"] = receipt()
            row = csv_text(record)
            row_bytes = len(row.encode('utf-8'))
            if counts['output_bytes'] + row_bytes > max_output_bytes:
                counts['withheld_records'] += 1
                counts['stop_reason'] = 'byte_limit'
                break
            if file.write(row) != len(row): raise OSError('incomplete CSV row write')
            file.flush()
            counts['output_bytes'] += row_bytes
            prior = previous.get(record["device_id"])
            if prior is not None:
                if record["seq"] <= prior[0] or record["uptime_ms"] < prior[1]:
                    counts["discontinuities"] += 1
                else:
                    counts["sequence_gaps"] += max(0, record["seq"] - prior[0] - 1)
            previous[record["device_id"]] = (record["seq"], record["uptime_ms"])
            counts["records"] += 1
            if not record["valid"]:
                counts["sensor_invalid"] += 1
            if counts['records'] >= max_records:
                counts['stop_reason'] = 'record_limit'
                break
            if counts['output_bytes'] == max_output_bytes:
                counts['stop_reason'] = 'byte_limit'
                break
    except KeyboardInterrupt:
        counts['stop_reason'] = 'interrupted'
        raise
    except Exception:
        counts['stop_reason'] = 'capture_failed'
        raise
    finally:
        if pending:
            counts["invalid"] += 1
        print(json.dumps(counts, sort_keys=True))
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True, help="e.g. /dev/cu.usbserial-XXXX or COM3")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--seconds", type=int, default=600)
    parser.add_argument("--output", default="data/baseline.csv")
    parser.add_argument('--max-records', type=int, default=MAX_RECORDS, help='1–10000 saved records; default 10000')
    parser.add_argument('--max-output-bytes', type=int, default=MAX_OUTPUT_BYTES, help='CSV byte cap including header; maximum/default 16 MiB')
    parser.add_argument('--dry-run', action='store_true', help='Preview validated settings without importing serial, creating output or opening a port')
    args = parser.parse_args()
    if not args.port.strip() or len(args.port)>200 or any(ord(char)<32 or ord(char)==127 for char in args.port):
        parser.error('--port must be bounded nonblank text without control characters')
    if not 0 < args.seconds <= 86400:
        parser.error("--seconds must be between 1 and 86400")
    if args.baud <= 0:
        parser.error("--baud must be positive")
    try: validate_limits(args.max_records, args.max_output_bytes)
    except ValueError as error: parser.error(str(error))
    out = Path(args.output)
    try: occupied=out.exists() or out.is_symlink()
    except OSError:
        parser.exit(1, 'Capture refused: output path inspection failed. No capture started.\n')
    if occupied:
        parser.exit(1, "Capture refused: choose a new output filename; existing evidence is never overwritten.\n")
    if args.dry_run:
        try:
            # Read-only path inspection. Missing directories are not created or reserved.
            for parent in out.absolute().parents:
                if parent.exists() or parent.is_symlink():
                    if not parent.is_dir():
                        parser.exit(1, 'Settings preview refused: an output ancestor is not a directory. No capture started.\n')
                    break
            preview={'format':'edgeops-serial-capture-settings-preview-v1','dry_run':True,
                     'requested_port':args.port,'baud':args.baud,'seconds':args.seconds,
                     'output_file':str(out.absolute()),'output_parent_exists':out.parent.is_dir(),
                     'max_records':args.max_records,'max_output_bytes':args.max_output_bytes,
                     'capture_started':False,'serial_module_imported':False,'port_opened':False,
                     'port_availability_verified':False,'output_created':False,'output_reserved':False,
                     'output_writability_verified':False,'hardware_connected':False,
                     'equipment_authorized':False,'production_ready':False,
                     'note':'Settings and current output-path shape only. The port, driver, baud compatibility, sensors, writable space and hardware are not tested. No file or directory is created and no filename is reserved. A real invocation must recheck the target and create it exclusively.'}
        except OSError:
            parser.exit(1, 'Settings preview unavailable: output path inspection failed. No capture started.\n')
        print(json.dumps(preview, sort_keys=True))
        return 0
    try:
        import serial
    except ImportError:
        parser.exit(1, "Install dependencies: python -m pip install -r scripts/requirements.txt\n")
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        # Exclusive creation occurs before opening the port, including race cases.
        with out.open("x", newline="", encoding="utf-8") as file:
            with serial.Serial(args.port, args.baud, timeout=1) as port:
                counts = capture_stream(port, file, args.seconds, max_records=args.max_records, max_output_bytes=args.max_output_bytes)
        if counts['stop_reason'] in ('record_limit', 'byte_limit'):
            print('Capture stopped at a configured capacity limit; retain the complete-row prefix for review and choose a new filename for another capture.', file=sys.stderr)
            return 2
        if counts["records"] == 0:
            print("No complete valid-format records were captured; retain the file for review.", file=sys.stderr)
            return 2
    except KeyboardInterrupt:
        print("Capture interrupted; any saved CSV is partial and requires review.", file=sys.stderr)
        return 130
    except (OSError, serial.SerialException):
        print("Capture stopped: output unavailable or serial connection failed. Any saved CSV is partial and requires review.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
