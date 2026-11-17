# EA-31 — Real MQTT-to-Independent HTTP and SQLite Integration

**Authoring date:** 2026-11-17  
**Status:** software + 12 opt-in tests committed, **new tests NOT EXECUTED**.  
**Previous verified baseline:** 120/120 locally executed tests through EA-30; EA-30 evidence pushed by user in commit 877f835.  
**Boundary:** strictly localhost, disposable mTLS test certificates, synthetic telemetry and ephemeral test JWT. No industrial equipment, sensors, real OIDC, network HTTPS or production approvals.

## Integration

EA-29 previously connected a real broker to an in-process FastAPI TestClient. EA-30 separately verified a Uvicorn/FastAPI process with a SQLite store. EA-31 joins these two execution environments:

~~~mermaid
flowchart LR
  P[Python synthetic test publisher] -->|MQTT v5 QoS1 mTLS| B[Local Mosquitto with ACL]
  B -->|MQTT mTLS gateway-a| G[HTTP bridge]
  G -->|Real HTTP POST + synthetic JWT over 127.0.0.1| A[Separate Uvicorn FastAPI]
  A -->|EA-22 contract + EA-25 policy| D[(SQLite WAL transactions)]
~~~

Implemented:
- [EA-31 gateway bridge](security/live-sandbox/mqtt_http_bridge.py) validates incoming broker-delivered V2 JSON, restricts site/asset/device/topic/source to synthetic fixtures, requires nonempty verified session, and POSTs to localhost FastAPI with scoped ephemeral JWT.
- [EA-31 real-broker opt-in tests](security/live-sandbox/tests/test_mqtt_http_durable_optin.py) exercise real MQTT subscription, separate process HTTP, durable SQLite, replay, server restart and unavailability.
- [EA-30 durable HTTP service](security/live-sandbox/durable_service.py) returns HTTP 201 for an insert or 200 for a duplicate key after SQLite commit.
- [EA-28 disposable broker configuration](security/live-sandbox/compose.yaml) listens on 127.0.0.1:8883.

## Critical reliability and safety limitations

**MQTT PUBACK is NOT a database commit acknowledgement.** The broker can acknowledge a QoS1 publish before the separate HTTP API stores its data; if the API is unavailable, the bridge reports http_unavailable and that message can be lost unless an upstream party **explicitly republishes** it. EA-31 demonstrates such manual replay recovery, **not automatic retry, spool/queue, broker-session durable delivery, exactly-once processing or offline buffering**.

MQTT broker ACL, not the message body, establishes the limited publishing identity in this test. The bridge cannot cryptographically derive publisher certificate identity from payload. HTTP is plaintext on loopback only and JWT is issued by a synthetic shared test signer; production authentication and transport are still unresolved.

SQLite primary key (device_id, boot_id, sequence) survives API server restart. This is idempotence for stable verified boot IDs. Different payloads with an identical key are currently treated as duplicates, not surfaced as a conflict: this is another explicit open gap.

**Do not connect physical motors, ESP32 inputs, OT controllers or real customer data.** G4a independent cybersecurity review and G4b physical safety approval remain outstanding.

## Verification plan — Windows PowerShell

From the user's present directory:
C:\Users\Gaming PC i9 3080\edgeops-workspace\projects\industrial-edge-ai-predictive-maintenance\enterprise-architecture

~~~powershell
git pull --ff-only origin main
cd security/live-sandbox
python -m pip install -r requirements.txt
Test-Path generated/ca.crt
Test-Path generated/gateway-a.crt
Test-Path generated/device-a.crt
docker compose -f compose.yaml up -d
docker compose -f compose.yaml ps
$env:EDGEOPS_EA31_TEST = "1"
python -m unittest discover -s tests -p "test_mqtt_http_durable_optin.py" -v
$ea31Exit = $LASTEXITCODE
Remove-Item Env:EDGEOPS_EA31_TEST
~~~

The three certificate checks should be True. Broker should report Up. If generated files are missing, review EA-28 PKI bootstrap instructions and never commit keys. **Acceptance target, not a measured outcome:** 12 tests executed, 0 skipped, 0 failed, OK.

The test automatically starts/stops an independent temporary Uvicorn HTTP process with an isolated temporary SQLite DB. It does NOT stop or reconfigure any existing Finagent, NAWA or other container. Test 09 deliberately stops the HTTP service and records failed delivery; test 10 explicitly republishes following service recovery.

## Evidence capture — only after successful run

Keep broker running, then from security/live-sandbox:

~~~powershell
cd ../..
New-Item -ItemType Directory -Force -Path "evidence/EA-31" | Out-Null
$env:EDGEOPS_EA31_TEST = "1"
cmd /c "python -m unittest discover -s security/live-sandbox/tests -p test_mqtt_http_durable_optin.py -v > evidence\EA-31\integration-tests.txt 2>&1"
$ea31Exit = $LASTEXITCODE
Remove-Item Env:EDGEOPS_EA31_TEST
Get-Content "evidence/EA-31/integration-tests.txt" -Tail 20

$log = Get-Content "evidence/EA-31/integration-tests.txt" -Raw
if ($ea31Exit -ne 0 -or $log -notmatch 'Ran 12 tests' -or
    $log -notmatch '(?m)^OK\s*$' -or
    $log -match '(?m)^(FAILED|ERROR|OK \(skipped=)') {
    throw "EA-31 verification failed or skipped"
}
@(
  "EDGEOPS EA-31 - MQTT-to-independent-HTTP-to-SQLite integration"
  "Date: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz')"
  "Source commit: $(git rev-parse HEAD)"
  "Python: $(python --version)"
  "Result: 12/12 EA-31 tests passed"
  "Scope: real localhost MQTT mTLS + real HTTP loopback + SQLite"
  "Resilience: explicit replay after downtime; no automatic delivery guarantee"
  "Security and physical safety: not approved"
) | Set-Content "evidence/EA-31/README.txt"

git add evidence/EA-31/README.txt evidence/EA-31/integration-tests.txt
git commit -m "test(edgeops): record EA-31 localhost MQTT HTTP SQLite evidence"
git push origin main
git status
cd security/live-sandbox
docker compose -f compose.yaml down
~~~

If any tests fail, **do not commit a passing evidence summary**; provide the actual output first.

## EA-32 candidate

Durable outbox/spool, bounded retry with dead-letter evidence, crash consistency, duplicate payload-conflict detection, and metrics distinguishing broker acceptance from database commit. These are **not implemented in EA-31**.
