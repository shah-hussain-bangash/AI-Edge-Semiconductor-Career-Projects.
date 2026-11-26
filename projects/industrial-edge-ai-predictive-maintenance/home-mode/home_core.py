"""Small local acquisition controller. No training, network upload or equipment commands."""
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import secrets
import sqlite3
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
MODES = ('esp32-only', 'sensors', 'demo')
CHANNELS = (
    ('acceleration_x_mps2', 'Acceleration X', 'm/s²', 'ax_mps2', 'adxl345_valid'),
    ('acceleration_y_mps2', 'Acceleration Y', 'm/s²', 'ay_mps2', 'adxl345_valid'),
    ('acceleration_z_mps2', 'Acceleration Z', 'm/s²', 'az_mps2', 'adxl345_valid'),
    ('temperature_c', 'Temperature', '°C', 'temp_c', 'ds18b20_valid'),
    ('bus_voltage_v', 'Bus voltage', 'V', 'bus_v', 'ina219_valid'),
    ('current_a', 'Current', 'A', 'current_ma', 'ina219_valid'),
)
BOUNDARY = dict(scope='edgeops-lightweight-home', production_ready=False,
                hardware_verified=False, calibration_verified=False, equipment_authorized=False,
                wifi_implemented=False, automatic_remote_upload=False)
spec = importlib.util.spec_from_file_location('home_v1_contract', ROOT / 'phase-01-hardware/scripts/capture_serial.py')
contract = importlib.util.module_from_spec(spec)
spec.loader.exec_module(contract)


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec='microseconds')


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def strict_json(raw):
    return json.loads(raw, object_pairs_hook=contract.unique_object,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Nonfinite JSON')))


def validate_settings(value):
    if not isinstance(value, dict) or set(value) != {'mode', 'port', 'expected_device_id'}:
        raise ValueError('Use only mode, port and expected_device_id')
    if value['mode'] not in MODES or not isinstance(value['port'], str):
        raise ValueError('Unsupported mode or port')
    if value['port'] and not re.fullmatch(r'(?:/dev/cu\.[A-Za-z0-9._-]{1,100}|COM[1-9][0-9]{0,2}|/dev/tty[A-Za-z0-9._-]{1,100}|/dev/pts/[0-9]+)', value['port']):
        raise ValueError('Choose a serial device path, not a file or network address')
    if not isinstance(value['expected_device_id'], str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', value['expected_device_id']):
        raise ValueError('Use the declared firmware device ID')
    return dict(value)


def load_settings(directory):
    path = Path(directory) / 'config.json'
    if not path.exists():
        return dict(mode='esp32-only', port='/dev/cu.usbserial-0001' if os.name != 'nt' else '', expected_device_id='motor-001')
    if path.stat().st_size > 4096:
        raise ValueError('Home configuration exceeds 4 KiB')
    return validate_settings(strict_json(path.read_text(encoding='utf-8')))


def save_settings(directory, value):
    value = validate_settings(value)
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name != 'nt': directory.chmod(0o700)
    path = directory / ('config-' + secrets.token_hex(8) + '.tmp')
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
            stream.write(canonical(value) + '\n'); stream.flush(); os.fsync(stream.fileno())
        os.replace(path, directory / 'config.json')
    finally:
        if path.exists(): path.unlink()


def parse_line(line, mode, expected_device):
    if len(line) > 4096:
        raise ValueError('line-too-long')
    text = line.decode('utf-8').strip()
    if not text or text.startswith('#'):
        return None
    if text == 'ESP32 is working!':
        if mode != 'esp32-only': raise ValueError('text-test-is-not-sensor-firmware')
        return dict(mode=mode, source='simulated', kind='text-heartbeat', device_id=None,
                    device_sequence=None, device_uptime_ms=None, values={c[0]: None for c in CHANNELS},
                    sensor_quality={c[0]: 'unavailable-in-esp32-only-test' for c in CHANNELS})
    frame = strict_json(text)
    contract.parse_record(canonical(frame))
    if frame['device_id'] != expected_device: raise ValueError('device-id-mismatch')
    if mode == 'esp32-only' and any(frame[k] for k in ('adxl345_valid', 'ds18b20_valid', 'ina219_valid')):
        raise ValueError('sensor-flags-require-sensors-mode')
    values = {}
    quality = {}
    for key, _, _, wire, valid in CHANNELS:
        available = mode == 'sensors' and frame[valid]
        values[key] = frame[wire] / 1000 if available and key == 'current_a' else frame[wire] if available else None
        quality[key] = 'declared-valid-unverified' if available else 'unavailable'
    return dict(mode=mode, source='simulated' if mode == 'esp32-only' else 'serial-unverified',
                kind='json-v1', device_id=frame['device_id'], device_sequence=frame['seq'],
                device_uptime_ms=frame['uptime_ms'], values=values, sensor_quality=quality)


class Store:
    """Rolling local history; the explicit retention policy bounds a home installation."""
    def __init__(self, path, limit=10000):
        if type(limit) is not int or not 1 <= limit <= 100000: raise ValueError('Invalid history limit')
        self.path = Path(path); self.limit = limit
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if os.name != 'nt': self.path.parent.chmod(0o700)
        with closing(self.connect()) as db, db:
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('''CREATE TABLE IF NOT EXISTS home_samples(
                id INTEGER PRIMARY KEY AUTOINCREMENT,session_id TEXT NOT NULL,
                received_at TEXT NOT NULL,source TEXT NOT NULL,payload_json TEXT NOT NULL,content_hash TEXT NOT NULL)''')
        if os.name != 'nt': self.path.chmod(0o600)

    def connect(self):
        db = sqlite3.connect(self.path, timeout=5); db.row_factory = sqlite3.Row
        return db

    def append(self, sample):
        payload = canonical(sample)
        with closing(self.connect()) as db, db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('INSERT INTO home_samples(session_id,received_at,source,payload_json,content_hash) VALUES(?,?,?,?,?)',
                       (sample['session_id'], sample['received_at'], sample['source'], payload, hashlib.sha256(payload.encode()).hexdigest()))
            db.execute('''DELETE FROM home_samples WHERE id <= COALESCE((
                SELECT id FROM home_samples ORDER BY id DESC LIMIT 1 OFFSET ?),-1)''', (self.limit,))

    def history(self, limit=60):
        if type(limit) is not int or not 1 <= limit <= 200: raise ValueError('Limit must be between 1 and 200')
        with closing(self.connect()) as db:
            rows = db.execute('SELECT * FROM home_samples ORDER BY id DESC LIMIT ?', (limit,)).fetchall()
            total = db.execute('SELECT count(*) FROM home_samples').fetchone()[0]
        result = []
        for row in rows:
            if hashlib.sha256(row['payload_json'].encode()).hexdigest() != row['content_hash']:
                raise ValueError('Retained reading integrity check failed')
            result.append({'id': row['id'], **strict_json(row['payload_json'])})
        return dict(items=result, total=total, retention_limit=self.limit, rolling_retention=True, **BOUNDARY)


class ProcessLock:
    def __init__(self, path): self.path = Path(path); self.stream = None
    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.stream = open(self.path, 'a+b')
        try:
            if self.path.stat().st_size == 0: self.stream.write(b'0'); self.stream.flush()
            self.stream.seek(0)
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self.stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.stream.close(); self.stream = None
            raise ValueError('Home mode is already running from this folder. Stop that session first.') from None
        return self
    def __exit__(self, *_):
        if self.stream: self.stream.close(); self.stream = None


class Controller:
    def __init__(self, store, settings, directory, serial_factory=None, monotonic=time.monotonic):
        self.store = store; self.settings = validate_settings(settings); self.directory = Path(directory)
        self.serial_factory = serial_factory; self.monotonic = monotonic
        self.lock = threading.RLock(); self.operation = threading.Lock()
        self.stop_event = threading.Event(); self.thread = None; self.generation = 0
        self.latest = None; self.last_tick = None; self.state = 'disconnected'; self.error = None
        self.accepted = self.rejected = 0; self.session_id = None

    def stop(self):
        with self.operation: self._stop()

    def _stop(self):
        self.stop_event.set()
        if self.thread: self.thread.join(timeout=3)
        with self.lock:
            self.latest = None; self.last_tick = None
            if self.thread and self.thread.is_alive():
                self.state = 'stopping'; raise ValueError('Serial reader is still stopping; retry after it stops')
            self.state = 'disconnected'; self.thread = None

    def start(self, settings):
        settings = validate_settings(settings)
        if settings['mode'] != 'demo' and not settings['port']: raise ValueError('Select a serial port first')
        with self.operation:
            self._stop()
            save_settings(self.directory, settings)
            with self.lock:
                self.settings = settings; self.stop_event = threading.Event(); self.generation += 1
                generation = self.generation; self.session_id = secrets.token_hex(16)
                self.accepted = self.rejected = 0; self.error = None; self.state = 'connecting'
                self.thread = threading.Thread(target=self._run, args=(generation, self.stop_event, dict(settings), self.session_id), daemon=True, name='edgeops-home-reader')
                self.thread.start()

    def _accept(self, sample, generation, stop, session_id):
        with self.lock:
            if generation != self.generation or stop.is_set(): return
            sample = {**sample, 'received_at': utc_now(), 'session_id': session_id, **BOUNDARY}
            self.store.append(sample)
            self.latest = sample; self.last_tick = self.monotonic(); self.accepted += 1; self.state = 'receiving'; self.error = None

    def _run(self, generation, stop, settings, session_id):
        stream = None
        try:
            if settings['mode'] == 'demo':
                index = 0
                while not stop.is_set():
                    values = [math.sin(index / 4), 0.0, 9.81, 23 + math.sin(index / 10), 3.3, 0.02]
                    self._accept(dict(mode='demo', source='simulated', kind='software-demo', device_id=None,
                        device_sequence=None, device_uptime_ms=None,
                        values={c[0]: v for c, v in zip(CHANNELS, values)},
                        sensor_quality={c[0]: 'simulated-example-not-a-physical-sensor' for c in CHANNELS}), generation, stop, session_id)
                    index += 1; stop.wait(1)
                return
            factory = self.serial_factory
            if factory is None:
                import serial
                factory = serial.Serial
            stream = factory(settings['port'], 115200, timeout=0.5, **({'exclusive': True} if os.name != 'nt' else {}))
            with self.lock:
                if generation == self.generation and not stop.is_set(): self.state = 'port-open'
            pending = b''; discarding = False
            while not stop.is_set():
                raw = stream.readline(4097)
                if not raw: continue
                pending += raw
                if len(pending) > 4096: pending = b''; discarding = True
                if not raw.endswith(b'\n'): continue
                line = pending; pending = b''
                try:
                    if discarding: discarding = False; raise ValueError('line-too-long')
                    sample = parse_line(line, settings['mode'], settings['expected_device_id'])
                except (ValueError, UnicodeError, RecursionError):
                    with self.lock:
                        self.rejected += 1; self.error = 'unusable-frame-check-firmware-mode-or-device-id'
                    continue
                if sample: self._accept(sample, generation, stop, session_id)
        except Exception:
            with self.lock:
                if generation == self.generation and not stop.is_set():
                    self.state = 'error'; self.error = 'serial-or-local-storage-unavailable'; self.latest = None; self.last_tick = None
        finally:
            if stream:
                try: stream.close()
                except Exception: pass

    def status(self):
        with self.lock:
            age = None if self.last_tick is None else max(0.0, self.monotonic() - self.last_tick)
            fresh = self.state == 'receiving' and age is not None and age <= 5 and self.latest is not None
            return dict(settings=dict(self.settings), state=self.state, error=self.error,
                session_id=self.session_id, accepted=self.accepted, rejected=self.rejected,
                age_seconds=age, fresh=fresh, last_sample=self.latest,
                live_values=self.latest['values'] if fresh else {c[0]: None for c in CHANNELS},
                channels=[dict(key=c[0],label=c[1],unit=c[2]) for c in CHANNELS],
                device_utc=None, device_boot_id=None, **BOUNDARY)


def serial_ports():
    from serial.tools.list_ports import comports
    return [dict(port=port.device, description=port.description) for port in comports()]
