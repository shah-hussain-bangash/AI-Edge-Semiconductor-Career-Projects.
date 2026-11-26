# Continuous synthetic delivery runner

This working runner repeatedly invokes the scoped one-pass HTTP worker. It is explicitly started, uses a device-specific private spool and accepts only loopback HTTP. It is not an installed operating-system service, an automatic process restarter, a broker integration or physical commissioning evidence.

Supply `EDGEOPS_SERVICE_TOKEN` through a private environment. From the dashboard directory, choose an explicit finite rehearsal or continuous run:

```powershell
.\.venv\Scripts\python.exe service_delivery_runner.py --spool .local\private-device-spool.sqlite3 --server http://127.0.0.1:8877 --interval 5 --max-passes 10
```

Use `--forever` instead of `--max-passes` only when deliberately running continuously. The interval is 1–300 seconds. No process starts from opening the dashboard. Default failure budgets stop after five consecutive unavailable heartbeat checks or local pass exceptions. A denied credential or conflicting report lease stops immediately. Unexpected process exit requires an explicit restart or separately qualified OS supervision. The pass count is not a throughput guarantee.

Each pass first publishes an authenticated heartbeat before claiming work. The existing queue controls central receipt matching, leases, retry backoff, capacity and permanent denials. The last queue outcome is read back from the saved spool record; attempt counters do not mean successful delivery. A transport error handled by the spool can leave an entry pending or blocked without becoming a Python runner exception. Mixed-device spools can be rejected by the scoped credential; use a dedicated spool.

A nonblocking OS file lock excludes a second runner for the same resolved spool pathname. Lock release on process exit permits restart; different hard-link/path aliases are not a universal identity guarantee. A hard kill does not send a final stop report. Existing queue claims remain subject to their normal lease expiry and cannot be reassigned early by the runner.

The server also leases each credential's report stream to one run ID. A competing run must wait until the current report lease expires or a stopped report is accepted. The lease lasts `max(30, interval_seconds × 3 + 15)` seconds according to the service wall clock. Restart immediately after a hard kill can therefore be denied temporarily. Do not delete queue leases, rewrite source identities or bypass revocation to force recovery.

`POST /api/edge/heartbeat` accepts the same scoped credential, with strict counters/run/sequence fields and no hardware authority. Exact duplicate reports reconcile a lost response without extending the old report lease; altered/replayed sequences are refused. New reports and observation commits share current credential/binding checks. The runner flushes a pending exact report before publishing fresh counters. Metadata is bounded to one current report per retained credential, at most 100. Reports carry no token, local path or raw exception text.

**Device → Continuous delivery runner activity** reads `GET /api/service-runners` using the current authenticated dashboard account. It displays recent heartbeat, stale heartbeat, reported stopped or inactive credential, with service receipt/observation times. These are saved authenticated reports, not independent process, device, broker or equipment liveness. Counters are runner-declared. Refresh clears old results/export authority; exporting retains the exact loaded report without a live requery. A stopped or stale report never changes hardware readiness or production acceptance.

Restore retains historical reports but revokes service credentials. Their effective state is inactive until a deliberately issued replacement is used. No restored report authorizes new work. Server clock qualification, production TLS/broker connectivity, OS-service installation/restart policy, resource/soak measurement and operational acceptance remain separate work.
