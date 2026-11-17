"""EA-31 real MQTT mTLS -> separate HTTP FastAPI -> SQLite bridge.

Laboratory-only: loopback HTTP, shared test HS256 key, synthetic records,
broker ACL fixtures and disposable PKI. No production IAM/TLS, broker-to-DB
atomic acknowledgement, autonomous retry, offline queue or physical equipment.
"""
from __future__ import annotations

import json
import queue
import threading
from datetime import datetime, timedelta, timezone

import httpx
import jwt
from jsonschema import Draft202012Validator, FormatChecker

import durable_service
from gateway import TOPIC, tls_client

VALIDATOR = Draft202012Validator(durable_service.SCHEMA, format_checker=FormatChecker())


def verified_sample(sequence: int):
    """Make an explicitly simulated, verified-session fixture (not a claim of device attestation)."""
    from gateway import synthetic_sample
    record = synthetic_sample(sequence)
    record["boot_id"] = "ea31-synthetic-verified-boot"
    record["quality"]["session_quality"] = "verified"
    return record


class HttpMqttBridge:
    """One-test-topic MQTT subscriber, synchronous loopback HTTP forwarding.

    MQTT QoS1 broker ACK is independent from downstream DB commit. On HTTP
    failure the bridge records an error, but MQTT may already have ACKed and
    dropped the message. Tests use explicit upstream replay, NOT automatic
    reliable delivery; this must be redesigned before production.
    """

    def __init__(self, *, api_base: str, signing_key: str, subject="gateway-a"):
        if not api_base.startswith("http://127.0.0.1:"):
            raise ValueError("EA-31 supports loopback HTTP only")
        if len(signing_key) < 32:
            raise ValueError("EA-31 requires ephemeral test-only signing key")
        self.api_base = api_base.rstrip("/")
        self.signing_key = signing_key
        self.subject = subject
        self.client = tls_client("gateway-a")
        self.ready = threading.Event()
        self.error = None
        self.results: queue.Queue[tuple[str, int | None]] = queue.Queue()
        self.client.on_connect = self._on_connect
        self.client.on_subscribe = self._on_subscribe
        self.client.on_message = self._on_message

    def _on_connect(self, client, _userdata, _flags, reason, _properties):
        if reason.value:
            self.error = f"MQTT CONNACK failed: {reason}"
            self.ready.set()
        else:
            client.subscribe(TOPIC, qos=1)

    def _on_subscribe(self, client, _userdata, _mid, reasons, _properties):
        if not reasons or any(r.value >= 128 for r in reasons):
            self.error = "MQTT SUBACK rejected"
        self.ready.set()

    def _on_message(self, client, _userdata, message):
        try:
            outcome = self.forward(message.topic, message.payload)
        except Exception as exc:
            # Fail closed; never report delivery success for an unexpected error.
            outcome = ("bridge_error", None)
        self.results.put(outcome)

    def start(self):
        self.client.connect("localhost", 8883, keepalive=20)
        self.client.loop_start()
        if not self.ready.wait(8):
            self.stop()
            raise RuntimeError("gateway MQTT subscribe timeout")
        if self.error:
            self.stop()
            raise RuntimeError(self.error)
        return self

    def _fixture_token(self):
        now = datetime.now(timezone.utc)
        return jwt.encode({
            "sub": self.subject, "iss": durable_service.ISSUER,
            "aud": durable_service.AUDIENCE,
            "iat": now, "exp": now + timedelta(seconds=60),
        }, self.signing_key, algorithm="HS256")

    def forward(self, topic: str, raw: bytes):
        if topic != TOPIC or len(raw) > 65536:
            return ("topic_or_size_rejected", None)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return ("json_rejected", None)
        if not isinstance(payload, dict) or not VALIDATOR.is_valid(payload):
            return ("schema_rejected", None)
        if any(payload.get(field) != value for field, value in (
            ("source_type", "synthetic"), ("site_id", "site-a"),
            ("asset_id", "motor-a"), ("device_id", "device-a"),
        )):
            return ("registry_rejected", None)
        if not payload["boot_id"] or payload["quality"]["session_quality"] != "verified":
            return ("session_rejected", None)
        try:
            response = httpx.post(
                self.api_base + "/telemetry", json=payload,
                headers={"Authorization": "Bearer " + self._fixture_token()},
                timeout=3,
            )
        except httpx.RequestError:
            return ("http_unavailable", None)
        if response.status_code == 201 and response.json().get("stored") is True:
            return ("stored", 201)
        if response.status_code == 200 and response.json().get("duplicate") is True:
            return ("already_stored", 200)
        return ("api_rejected", response.status_code)

    def await_result(self, timeout=10):
        return self.results.get(timeout=timeout)

    def stop(self):
        self.client.disconnect()
        self.client.loop_stop()
