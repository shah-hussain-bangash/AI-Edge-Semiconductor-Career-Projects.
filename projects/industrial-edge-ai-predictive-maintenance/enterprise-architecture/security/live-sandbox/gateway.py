"""EA-29 localhost MQTT -> authenticated gateway -> in-process FastAPI slice.

Experimental only: real local broker mTLS and MQTT topic ACL; FastAPI TestClient
is in the SAME Python process, not an independently deployed HTTP server.
Synthetic records only. No hardware, real device identity or durable storage.
"""
from __future__ import annotations

import copy
import json
import queue
import threading
from pathlib import Path

import paho.mqtt.client as mqtt
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator, FormatChecker

import api

HERE = Path(__file__).resolve().parent
CERTS = HERE / "generated"
TOPIC = "edgeops/v1/site-a/device-a/telemetry"
SAMPLE_PATH = api.ARCH / "contracts" / "examples" / "telemetry-v2.synthetic-valid.json"
VALIDATOR = Draft202012Validator(api.SCHEMA, format_checker=FormatChecker())


def synthetic_sample(sequence: int = 1) -> dict:
    data = json.loads(SAMPLE_PATH.read_text(encoding="utf-8"))
    data.update(site_id="site-a", asset_id="motor-a", device_id="device-a", sequence=sequence)
    return data


def tls_client(identity: str) -> mqtt.Client:
    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        protocol=mqtt.MQTTv5,
    )
    client.tls_set(
        ca_certs=str(CERTS / "ca.crt"),
        certfile=str(CERTS / f"{identity}.crt"),
        keyfile=str(CERTS / f"{identity}.key"),
    )
    return client


class Gateway:
    """Mqtt subscriber, identity bound fixture, and TestClient forwarding."""

    def __init__(self, *, jwt_subject: str = "gateway-a"):
        self.client = tls_client("gateway-a")
        self.http = TestClient(api.app)
        self.jwt_subject = jwt_subject
        self.ready = threading.Event()
        self.results: queue.Queue[tuple[str, int | None]] = queue.Queue()
        self.seen: set[tuple[str, object, int]] = set()
        self._lock = threading.Lock()
        self._error: str | None = None
        self.client.on_connect = self._on_connect
        self.client.on_subscribe = self._on_subscribe
        self.client.on_message = self._on_message

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code.value:
            self._error = f"gateway MQTT CONNACK refused: {reason_code}"
            self.ready.set()
        else:
            client.subscribe(TOPIC, qos=1)

    def _on_subscribe(self, client, userdata, mid, reason_code_list, properties):
        if not reason_code_list or any(c.value >= 128 for c in reason_code_list):
            self._error = "gateway MQTT SUBACK rejected"
        self.ready.set()

    def start(self):
        self.client.connect("localhost", 8883, keepalive=20)
        self.client.loop_start()
        if not self.ready.wait(8):
            self.stop()
            raise RuntimeError("gateway subscribe timeout")
        if self._error:
            self.stop()
            raise RuntimeError(self._error)
        return self

    def _on_message(self, client, userdata, message):
        # Publish origin is NOT derivable from MQTT message.topic or payload.
        # Broker test ACL is the only origin restriction at this boundary.
        status = self.forward(message.topic, message.payload)
        self.results.put(status)

    def forward(self, topic: str, payload: bytes) -> tuple[str, int | None]:
        """Validate the broker-delivered V2 JSON and call in-process API."""
        if topic != TOPIC or len(payload) > 65536:
            return ("topic_or_size_rejected", None)
        try:
            record = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return ("json_rejected", None)
        if not isinstance(record, dict) or not VALIDATOR.is_valid(record):
            return ("schema_rejected", None)
        # Bind to the known single-device test registry. Do not trust arbitrary
        # site/asset/device values from message body.
        if any(record.get(k) != v for k, v in (
            ("site_id", "site-a"), ("asset_id", "motor-a"),
            ("device_id", "device-a"), ("source_type", "synthetic")
        )):
            return ("registry_rejected", None)
        key = (record["device_id"], record["boot_id"], record["sequence"])
        with self._lock:
            if key in self.seen:
                return ("duplicate_rejected", None)
            # TestClient is in-process and reuses ephemeral JWT signer.
            # No live HTTP transport or independent identity provider exists.
            token = api.fixture_token(self.jwt_subject)
            response = self.http.post("/telemetry", json=record,
                                      headers={"Authorization": f"Bearer {token}"})
            if response.status_code != 202:
                return ("api_rejected", response.status_code)
            self.seen.add(key)  # process-local; NOT persistent across restart
            return ("accepted", response.status_code)

    def await_result(self, timeout=8):
        return self.results.get(timeout=timeout)

    def stop(self):
        self.client.disconnect()
        self.client.loop_stop()
        self.http.close()


def publish_synthetic(record: dict | bytes) -> int:
    """Send real mTLS MQTT v5 QoS1 publish and return broker PUBACK code."""
    connected = threading.Event()
    published = threading.Event()
    state = {}
    publisher = tls_client("device-a")

    def on_connect(client, userdata, flags, rc, properties):
        state["connack"] = int(rc.value)
        connected.set()

    def on_publish(client, userdata, mid, rc, properties):
        state["puback"] = int(rc.value)
        published.set()

    publisher.on_connect = on_connect
    publisher.on_publish = on_publish
    try:
        publisher.connect("localhost", 8883, keepalive=20)
        publisher.loop_start()
        if not connected.wait(8) or state.get("connack") != 0:
            raise RuntimeError("device MQTT CONNECT failed/timeout")
        body = record if isinstance(record, bytes) else json.dumps(record).encode("utf-8")
        info = publisher.publish(TOPIC, body, qos=1)
        if info.rc != mqtt.MQTT_ERR_SUCCESS:
            raise RuntimeError(f"publisher local error: {info.rc}")
        if not published.wait(8):
            raise RuntimeError("PUBACK timeout")
        return state["puback"]
    finally:
        publisher.disconnect()
        publisher.loop_stop()
