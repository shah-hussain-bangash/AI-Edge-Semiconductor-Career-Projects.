"""Optional single-process USB heartbeat observation; no sensor or actuator claims."""
import re
import threading
import time
from datetime import datetime, timezone

HEARTBEAT = b"ESP32 is working!"
MAX_LINE = 256
FRESH_SECONDS = 5


def valid_port(port):
    # Reject pyserial URL handlers and unrelated device/file paths.
    return bool(re.fullmatch(r"/dev/cu\.(?:usbserial|usbmodem|SLAB_USBtoUART|wchusbserial)[A-Za-z0-9_.-]*|COM[1-9][0-9]*|/dev/tty(?:USB|ACM)[0-9]+", port))


class UsbHeartbeat:
    def __init__(self, port="", clock=time.monotonic, factory=None):
        if port and not valid_port(port):
            raise ValueError("Choose a local USB serial device, not a URL or file")
        self.port = port
        self.clock = clock
        self.factory = factory
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.thread = None
        self.state = "disabled" if not port else "waiting"
        self.last_seen = None
        self.last_utc = None
        self.count = 0
        self.ignored = 0

    def observe(self, raw):
        # Display only the fixed known heartbeat, never arbitrary serial content.
        with self.lock:
            if len(raw) <= MAX_LINE and raw.strip() == HEARTBEAT:
                self.last_seen = self.clock()
                self.last_utc = datetime.now(timezone.utc).isoformat()
                self.count = min(self.count + 1, 1_000_000_000)
                return True
            self.ignored = min(self.ignored + 1, 1_000_000_000)
            return False

    def snapshot(self):
        with self.lock:
            age = None if self.last_seen is None else max(0, self.clock() - self.last_seen)
            state = self.state
            if state == "open":
                state = "waiting" if age is None else "receiving" if age < FRESH_SECONDS else "stale"
            fresh = state == "receiving"
            return {"mode": "usb-heartbeat-only", "state": state,
                    "port": self.port or None, "baud": 115200,
                    "heartbeat_fresh": fresh, "last_received_utc": self.last_utc,
                    "age_seconds": None if age is None else round(age, 2),
                    "heartbeat_count": self.count, "ignored_line_count": self.ignored,
                    "message": HEARTBEAT.decode() if fresh else None,
                    "sensor_telemetry_verified": False, "actuators_enabled": False}

    def start(self):
        if not self.port or self.thread is not None:
            return
        self.thread = threading.Thread(target=self._run, name="edgeops-usb", daemon=True)
        self.thread.start()

    def _run(self):
        if self.factory is None:
            try:
                import serial
            except ImportError:
                with self.lock:
                    self.state = "dependency_missing"
                return
            self.factory = serial.Serial
        while not self.stop_event.is_set():
            device = None
            try:
                device = self.factory(port=None, baudrate=115200, timeout=1,
                                      **({"exclusive": True} if self.port.startswith("/dev/") else {}))
                device.dtr = False
                device.rts = False
                device.port = self.port
                device.open()
                with self.lock:
                    self.state = "open"
                    self.last_seen = None
                    self.last_utc = None
                discard = False
                pending = bytearray()
                while not self.stop_event.is_set():
                    # Keep partial lines until a newline; never display a truncated match.
                    chunk = device.read_until(b"\n", MAX_LINE + 1)
                    if not chunk:
                        continue
                    if len(pending) + len(chunk) > MAX_LINE:
                        discard = True
                    if not discard:
                        pending.extend(chunk)
                    if chunk.endswith(b"\n"):
                        self.observe(b"" if discard else bytes(pending))
                        pending.clear()
                        discard = False
            except (OSError, ValueError):
                with self.lock:
                    self.state = "disconnected"
                    self.last_seen = None
                    self.last_utc = None
            finally:
                if device is not None:
                    try:
                        device.close()
                    except OSError:
                        pass
            self.stop_event.wait(3)
        with self.lock:
            self.state = "stopped"
            self.last_seen = None
            self.last_utc = None

    def stop(self):
        self.stop_event.set()
        if self.thread is not None:
            self.thread.join(timeout=3)
