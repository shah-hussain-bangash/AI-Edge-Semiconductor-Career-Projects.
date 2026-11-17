# EA-30 - Independent localhost HTTP API and SQLite durable ingestion

**Date:** 2026-11-17  
**Status:** Files committed, 15 tests authored but NOT EXECUTED.  
**Baseline:** 105/105 previous local tests reported passed with user-committed EA-23, 25, 27, 28, 29 evidence.  
**Safety:** No sensor, physical motor, PLC, real identity credentials, or operational controls.

## Architecture and trust boundaries

EA-29 used real local MQTT mTLS but an in-process FastAPI TestClient and volatile event list. EA-30 adds an independent Uvicorn/FastAPI server subprocess bound to 127.0.0.1 with a local SQLite database. Tests use actual localhost HTTP to validate synthetic JWT issuer, audience, signature, expiry; EA-22 V2 schema; fixed device/site/asset registry; EA-25 ingestion authorization; and SQLite persistent primary-key deduplication.

**Not yet integrated:** The EA-29 MQTT subscriber does NOT yet forward over real HTTP to this new service. Thus EA-30 is a distinct standalone vertical slice, not complete MQTT-to-durable-API end-to-end integration.

~~~mermaid
flowchart LR
  T[Separate test process] -->|HTTP localhost| U[Independent Uvicorn FastAPI process]
  T -->|Ephemeral signed test JWT| U
  U --> V[V2 schema and EA-25 policy]
  V --> S[SQLite transaction]
  S --> R[Restart and duplicate replay checks]
  M[Existing local MQTT gateway] -.not yet connected.-> U
~~~

## Implementation links

- [Durable API service](security/live-sandbox/durable_service.py)
- [15 independent-process HTTP and SQLite tests](security/live-sandbox/tests/test_durable_http.py)
- [Dependencies](security/live-sandbox/requirements.txt)
- [Local data ignore rules](security/live-sandbox/.gitignore)

## Idempotency acceptance contract

A new record with a nonempty verified boot session, synthetic source and registry-bound identity is inserted inside a SQLite transaction. First acceptance is HTTP 201 and duplicate replay is HTTP 200. Primary key fields are device_id, boot_id, sequence. The tests restart the API server subprocess and verify the same database and deduplication key survive restart.

**Limitations:** A duplicate with the same key but a different payload currently counts as duplicate without conflict detection; this is an open gap. SQLite persistence is not an exactly-once MQTT end-to-end guarantee. Test-issued HS256 tokens share a secret between test harness and server and are not real OIDC. HTTP is unencrypted, intentionally bound only to localhost. Never expose the service to public interfaces or reuse the test signing key.

## Execute EA-30 on Windows PowerShell

From the existing enterprise-architecture/security/live-sandbox directory:

~~~powershell
git pull --ff-only origin main
python -m pip install -r requirements.txt
cd ../..
python -m unittest discover -s security/live-sandbox/tests -p "test_durable_http.py" -v
~~~

Target is exactly 15 tests and OK with zero failures and skips. These test cases create a disposable temp SQLite file and start/stop a real localhost Uvicorn subprocess. No broker, Docker or other project container needs to start.

## Evidence capture only after actual local success

From enterprise-architecture directory:

~~~powershell
New-Item -ItemType Directory -Force -Path "evidence/EA-30" | Out-Null
cmd /c "python -m unittest discover -s security/live-sandbox/tests -p test_durable_http.py -v > evidence\EA-30\http-tests.txt 2>&1"
$httpExit = $LASTEXITCODE
Get-Content "evidence/EA-30/http-tests.txt" -Tail 18
$log = Get-Content "evidence/EA-30/http-tests.txt" -Raw
if ($httpExit -ne 0 -or $log -notmatch "Ran 15 tests" -or
    $log -notmatch "(?m)^OK\s*$" -or
    $log -match "(?m)^(FAILED|ERROR|OK \(skipped=)") {
    throw "EA-30 HTTP tests failed or skipped"
}
@(
  "EA-30 independent localhost Uvicorn/FastAPI and SQLite evidence"
  "Date: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz')"
  "Commit: $(git rev-parse HEAD)"
  "Python: $(python --version)"
  "Results: 15/15 local HTTP and SQLite tests passed"
  "API: separate Uvicorn server process, HTTP loopback only"
  "Persistence: SQLite temporary test DB, restart and idempotency checks"
  "Credentials: synthetic ephemeral JWT signer shared by test harness"
  "Limitations: no live MQTT-to-HTTP link, real OIDC, TLS or physical hardware"
) | Set-Content "evidence/EA-30/README.txt"
~~~

If the result is genuinely 15/15 and evidence contains no secrets:

~~~powershell
git add evidence/EA-30/README.txt evidence/EA-30/http-tests.txt
git commit -m "test(edgeops): record EA-30 durable HTTP verification"
git push origin main
git status
~~~

## Gates and proposed EA-31

Cybersecurity gate G4a remains OPEN. Physical/electrical safety gate G4b remains BLOCKING. No hardware motor operation is authorized.

EA-31 candidate: connect the real MQTT mTLS gateway to the independently deployed localhost HTTP server; add durable replay recovery, conflicting payload detection, failure injection, credential separation and test evidence. Do not claim these are already implemented.
