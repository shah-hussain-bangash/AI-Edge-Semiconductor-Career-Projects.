# Scoped local service ingestion

This is a working software integration using synthetic observations. It does not enroll physical hardware, connect a broker, install a supervisor, provide enterprise identity or establish production acceptance.

Administrators open **Device → Scoped edge service credentials**, select an active synthetic test binding, then issue a credential with an exact binding revision and lifetime of 1–1440 minutes. Issuance and revocation require a current session, CSRF and administrator password reauthentication. A token is returned once; only its SHA-256 digest is stored. Keep it in a private environment, never in source, logs or screenshots.

The credential authorizes `POST /api/edge/observations` for its exact synthetic site/asset/device/binding revision and `POST /api/edge/heartbeat` for its own bounded runner report. Browser cookies cannot substitute for the bearer credential, and the bearer cannot access browser administration. Measured/replayed observations remain rejected by the existing strict contract. The central commit path shares key/hash deduplication, conflict preservation, capacity checks and receipts with the existing local delivery path. It records a service principal rather than impersonating a browser user.

The endpoint refuses plaintext non-loopback clients. The worker intentionally accepts only an explicit loopback HTTP origin; production TLS/broker integration remains separate. Existing gateway/proxy trust must be reviewed before any network deployment.

```powershell
.\.venv\Scripts\python.exe service_delivery_worker.py --spool <private-spool-path> --server http://127.0.0.1:8877
```

Supply `EDGEOPS_SERVICE_TOKEN` through the worker's private environment. This is one explicit pass with bounded request timeout, no redirects and no environmental proxy use. It does not log in with an administrator password or install an unattended process. The queue retains its existing backoff, lease, capacity and failure behavior. A scoped credential does not select which due queue item is claimed; use an isolated device-specific test spool, since a different binding is denied and blocked rather than silently rewritten.

Expiry, explicit revocation, binding retirement/change and issuer role/access/account revision changes deny subsequent ingestion, including duplicate retries. Authorization and central commitment share a database write transaction. Logout ends the browser session, not its independently issued service credentials. Revoke those explicitly or allow expiry. No refresh token or automatic rotation is installed.

Credential metadata is bounded to 100 retained entries, including revoked/expired entries; there is no automatic deletion or capacity reset. Issuing a credential is not idempotent: after a lost issuance response, inspect metadata and revoke unused entries before issuing another. The token cannot be retrieved again. Restore tooling revokes all unrevoked service credentials while preserving observation/credential records; reissue deliberately after restoration.

The credential UI clears token/password fields on close, navigation and hidden-page events, and stores no secrets in browser storage. A browser/OS compromise or a screenshot while the token is displayed remains outside those protections. Credential APIs use no-store responses; list responses never contain tokens or digests.

Backend changes require a server restart. The new schema is additive. Existing accounts, sessions, reports, observations and hardware readiness flags are preserved during ordinary startup. Test using disposable databases before activation; back up the configured live database using the existing recovery procedure before restarting with new source.

The same scoped credential can report its own synthetic MQTT ingress through /api/edge/mqtt-heartbeat. See [MQTT ingress](MQTT_INGRESS.md) for topic scope, mutual TLS, durable-before-ACK handling and the separate central delivery boundary.
