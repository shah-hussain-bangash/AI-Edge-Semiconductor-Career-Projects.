# Synthetic mTLS MQTT → durable edge → central delivery

This is a working software integration for synthetic fixture envelopes. It does not enroll physical sensors, commission hardware, validate a production broker deployment or change production readiness. Source bindings retain `source_type=synthetic` and `transport=simulator`; MQTT is the carrier for those fixtures, not a rewrite into measured origin.

Install the optional runtime with the dashboard Python environment:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-mqtt.txt
```

Configure an independently reviewed broker with mutual TLS, certificate identity/topic ACLs, a bounded packet size, stable persistent client sessions and accepted persistence/retention settings. The adapter uses a trusted CA, hostname verification and a client certificate/key; there is no insecure TLS fallback or plaintext MQTT mode. Private keys stay outside source and reports. The native Mosquitto integration tests generate disposable certificates and use a temporary loopback broker process; they do not install a Windows service or change Docker.

Use a private device-specific spool and an exact active synthetic binding. Supply `EDGEOPS_SERVICE_TOKEN` privately. For example, substitute actual reviewed paths and identifiers:

```powershell
.\.venv\Scripts\python.exe mqtt_ingress.py --spool .local\private-device-spool.sqlite3 --server http://127.0.0.1:8877 --host localhost --port 8883 --ca private\ca.crt --cert private\bridge.crt --key private\bridge.key --site TEST_SITE --asset MTR-001 --device TEST_DEVICE --revision 1 --seconds 60
```

`--forever` is an explicit alternative to the finite 1–3600 second rehearsal. An active bounded network call may finish after the requested duration. No bridge, publisher or broker starts from opening the dashboard. Unexpected exits require an explicit restart or separately qualified process supervision.

The exact topic is `edgeops/synthetic/{site_id}/{asset_id}/{device_id}/telemetry`. Payload is the existing strict `DeliveryInput` envelope: `binding_revision` plus the synthetic V2 `observation`. Duplicate JSON members, invalid UTF-8/schema, modified source identities, wrong scope, retained messages, unsupported delivery QoS and payloads over 8192 bytes are refused. A broker packet cap is also required because the MQTT client receives the packet before application validation. The adapter subscribes at QoS1 and requires a QoS1 SUBACK. It uses a stable persistent-session client ID and manual acknowledgements.

**Commit boundaries:** a publisher's broker receipt does not mean edge or central commitment. The adapter requests MQTT acknowledgement only after the durable spool transaction returns. Identical replay reuses the stored source identity; changed content is refused without overwriting the original. If the spool is full/unavailable or the message is invalid, the bridge stops without acknowledging that received QoS1 message. Recovery depends on the broker retaining that persistent session and message. QoS0 has no such recovery guarantee and is refused. An ACK request queued by the client is not independent proof that the broker received it.

The HTTP one-pass/continuous service worker separately delivers the same spool to `/api/edge/observations`, retaining existing leases, backoff, capacity and central key/hash receipts. MQTT intake and HTTP delivery can operate together; their local process locks use different suffixes. Only one MQTT bridge for a resolved spool and one credential report stream are permitted at a time. A lost ACK followed by broker redelivery is safe for identical content; finite tests do not establish every crash, power-loss or network interleaving.

The bridge authenticates its exact topic with `/api/edge/mqtt-heartbeat` before broker connection and periodically afterward. Reports have a server lease of `max(30, interval × 3 + 15)` seconds. A competing bridge, revoked credential or altered/replayed report is refused. Exact pending report retries reconcile lost responses. After abrupt exit, wait for normal report/queue lease expiry; do not rewrite identities or force-clear leases. Collection between periodic reports is not per-message central authorization; every eventual central ingest still checks current credential and binding scope. Prolonged reporting failure stops the bridge after five failed periodic reports.

**Device → MQTT → durable edge intake** shows authenticated, bridge-declared counts and service receipt times. Accepted-message counts include identical retries; ACK counts are client requests, not central delivery counts. Inspect central history performs an authorized read of the saved observations. Export retains the loaded report without querying the broker/device again. No report changes hardware or production acceptance. Restore retains reports but revokes their service credentials.

Tests cover durable-before-ACK ordering, scope/schema refusal, full/unavailable spool, conflict preservation, lost ACK and native broker redelivery, mutual TLS/hostname rejection and certificate ACL denial. The complete browser rehearsal uses native Mosquitto, mTLS MQTT, a separate durable spool, real loopback HTTP delivery and persisted dashboard history. Cryptography is a test-fixture dependency, not a core dashboard requirement.

Install `requirements-mqtt-test.txt` and set `EDGEOPS_MOSQUITTO_EXE` to a reviewed native broker executable to run all MQTT tests. The four real-broker tests are explicitly skipped when that executable or optional dependencies are unavailable; the four core queue/report tests remain runnable with the base dashboard environment. `tests/browser_mqtt_ingress.cjs` requires the same extras plus the existing browser-test setup. The reviewed local execution used Paho 2.1.0, cryptography 47.0.0 and native Mosquitto 2.1.4. No test execution is implied by merely installing the files.

Protocol references: [Paho manual acknowledgements](https://eclipse.dev/paho/files/paho.mqtt.python/html/client.html), [official Mosquitto downloads](https://mosquitto.org/download/). Production certificate enrollment/rotation/revocation, broker operations, network TLS deployment, resource/soak testing and qualified physical acceptance remain pending.
