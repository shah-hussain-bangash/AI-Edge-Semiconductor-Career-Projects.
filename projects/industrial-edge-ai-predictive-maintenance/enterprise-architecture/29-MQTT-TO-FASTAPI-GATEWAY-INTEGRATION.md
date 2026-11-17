# EA-29 — Local MQTT-to-FastAPI Gateway Integration Slice

> **Date:** 2026-11-17 | **Status:** Source and 12 tests committed; **new tests NOT EXECUTED**  
> **Baseline evidence:** EA-23 18/18 + EA-25 34/34 + EA-27 24/24 + EA-28 API 14/14 + EA-28 real broker 3/3 = **93 locally verified tests** as reported by the user.

## Architecture

This phase connects the **real localhost Mosquitto MQTT broker** (mutual TLS identities and broker topic ACL from EA-28) to a gateway subscriber using a real MQTT v5 subscription. The gateway enforces V2 JSON Schema, fixed site/device/asset binding and process-local duplicate checks, then calls the FastAPI application through an **in-process FastAPI TestClient** with an ephemeral, synthetic, signed JWT.

**This is NOT an independently deployed HTTP service, real OIDC, durable database, reboot-proof dedupe, real sensor/ESP32 telemetry, production IAM, or OT equipment interface.**

~~~mermaid
flowchart LR
  P[Python synthetic V2 publisher] -->|Real MQTT mTLS QoS1| B[Local Mosquitto]
  B -->|Real MQTT mTLS subscription| G[Python gateway]
  G --> V[V2 validation + device/site binding + volatile dedupe]
  V -->|Synthetic JWT / in-process TestClient| A[FastAPI telemetry route]
  A --> M[EA-25 authorization / in-memory records]
~~~

## Files

- [Gateway implementation](security/live-sandbox/gateway.py)
- [12 real-broker opt-in tests](security/live-sandbox/tests/test_gateway_integration_optin.py)
- [EA-28 broker Compose](security/live-sandbox/compose.yaml)
- [EA-28 broker ACL](security/live-sandbox/acl)
- [EA-28 FastAPI](security/live-sandbox/api.py)
- [EA-22 Telemetry V2 Schema](contracts/telemetry-v2.schema.json)

## 12 new cases (authoring targets, not results)

| Test | Expected behavior |
|---|---|
| 01 | Real broker delivers synthetic V2 telemetry, gateway and in-process API accept, HTTP 202 |
| 02 | Replayed same sequence rejected by process-local dedupe |
| 03–04 | Malformed JSON or V2 schema violation rejected |
| 05–06 | Spoofed site or asset in broker-delivered payload rejected |
| 07 | Invalid sensor quality with non-null numeric measurement rejected |
| 08 | Wrong synthetic JWT principal/role cannot ingest (403) |
| 09 | Two different sequences accepted |
| 10 | Measured rather than synthetic source rejected (strict laboratory provenance) |
| 11–12 | Unexpected topic and oversized payload rejected locally |

**Threat-model limitations:** A broker-delivered message does not carry trusted publishing-certificate identity in the JSON body. The broker ACL is the test trust anchor. An in-process TestClient and signer are not genuine network API service-to-service security. API acceptance uses in-memory lists, not durable transactions. Dedupe key [device, boot, sequence] is volatile and cannot ensure cross-reboot correctness if boot ID is null. Serial V1 firmware is not integrated. No message retries, replay-window security, credential revocation, workload identity or production hardening is verified.

## Run the real local gateway tests on Windows

From the directory security/live-sandbox in your existing EDGEOPS checkout:

~~~powershell
git pull --ff-only origin main
Test-Path generated/ca.crt
Test-Path generated/device-a.crt
Test-Path generated/gateway-a.crt
docker compose -f compose.yaml up -d
docker compose -f compose.yaml ps
$env:EDGEOPS_GATEWAY_TEST = "1"
python -m unittest discover -s tests -p "test_gateway_integration_optin.py" -v
$gatewayExit = $LASTEXITCODE
Remove-Item Env:EDGEOPS_GATEWAY_TEST
~~~

The certificate checks should print True. If missing, generate credentials using the existing EA-28 bootstrap script only when its generated directory is empty. **Do not commit or share private keys.** Confirm Docker broker shows Up before running. The goal is **Ran 12 tests ... OK**, no skips; do not count skipped suites as passes.

### Evidence capture only after successful local execution

Keep the broker running. From security/live-sandbox:

~~~powershell
cd ../..
New-Item -ItemType Directory -Force -Path "evidence/EA-29" | Out-Null
$env:EDGEOPS_GATEWAY_TEST = "1"
cmd /c "python -m unittest discover -s security/live-sandbox/tests -p test_gateway_integration_optin.py -v > evidence\EA-29\gateway-tests.txt 2>&1"
$gatewayExit = $LASTEXITCODE
Remove-Item Env:EDGEOPS_GATEWAY_TEST
Get-Content "evidence/EA-29/gateway-tests.txt" -Tail 18
$log = Get-Content "evidence/EA-29/gateway-tests.txt" -Raw
if ($gatewayExit -ne 0 -or $log -notmatch 'Ran 12 tests' -or
    $log -notmatch '(?m)^OK\s*$' -or
    $log -match '(?m)^(FAILED|ERROR|OK \(skipped=)') {
    throw "EA-29 gateway tests failed or skipped"
}
@(
  "EA-29 - local MQTT to in-process FastAPI integration evidence"
  "Date: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz')"
  "Commit: $(git rev-parse HEAD)"
  "Python: $(python --version)"
  "Result: 12/12 real MQTT broker -> in-process API tests passed"
  "Scope: localhost, synthetic fixture PKI and JWT, volatile storage"
  "No hardware, external OIDC, network HTTP/TLS, durable DB or production approval"
) | Set-Content "evidence/EA-29/README.txt"
~~~

Review evidence for secrets. Then commit:

~~~powershell
git add evidence/EA-29/README.txt evidence/EA-29/gateway-tests.txt
git commit -m "test(edgeops): record EA-29 gateway integration verification"
git push origin main
git status
cd security/live-sandbox
docker compose -f compose.yaml down
~~~

## Gates / proposed next phase

- G4a security: OPEN; software-only local tests are not independent cybersecurity signoff.
- G4b electrical and physical: BLOCKING; do not energize the motor.
- EA-29: **12 tests authored, not yet locally run.**
- EA-30 candidate: independent HTTP API process, controlled issuer trust, durable ingestion with idempotency and restart/replay tests.
