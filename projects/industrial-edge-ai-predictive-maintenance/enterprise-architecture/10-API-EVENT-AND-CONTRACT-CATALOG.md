# EA-10 — API, MQTT and Event Contract Catalog

**Status:** Proposed contract baseline. Not verified against deployed firmware or endpoints.

## 1. Interface catalog

| ID | Producer -> consumer | Transport | Authentication | Schema | Failure behavior |
|---|---|---|---|---|---|
| INT-01 | ESP32 -> edge broker | MQTT v5 or 3.1.1 to confirm | per-device TLS identity | Telemetry v1 | bounded reconnect and visible drop count |
| INT-02 | Broker -> Pi gateway | MQTT subscription | private broker ACL | Telemetry v1 | dedupe and quarantine malformed |
| INT-03 | Pi -> FastAPI | HTTPS POST | scoped edge-service credential | IngestWindow v1 | retry with idempotency key |
| INT-04 | FastAPI -> DB | PostgreSQL protocol | least-privilege app role | versioned relational migrations | transactional rollback |
| INT-05 | Web -> FastAPI | HTTPS JSON | OIDC-backed session + RBAC | OpenAPI v1 | reject unauthorized |
| INT-06 | RAG -> approved SOP store | read-only document query | scoped service identity | RetrievalHit v1 | abstain if no eligible citations |
| INT-07 | Workflow -> audit/outbox | transactional events | service principal | WorkOrderEvent v1 | durable event with retry |

## 2. Telemetry envelope

```json
{
  "schema_version": "1.0",
  "source_type": "measured",
  "device_id": "lab-esp32-001",
  "site_id": "lab",
  "asset_id": "motor-001",
  "boot_id": "example-boot-001",
  "sequence": 1,
  "device_timestamp_utc": null,
  "gateway_received_utc": "ILLUSTRATIVE_ONLY",
  "firmware_version": "UNVERIFIED",
  "measurements": {
    "accel_x_g": null,
    "accel_y_g": null,
    "accel_z_g": null,
    "temperature_c": null,
    "bus_voltage_v": null,
    "current_a": null
  },
  "quality": {
    "clock_sync": "unknown",
    "vibration": "not_connected",
    "temperature": "not_connected",
    "current": "not_connected"
  }
}
```

Values are placeholders, **not real telemetry**. `source_type` must be one of `measured`, `synthetic`, `replayed`; raw data are never silently relabeled. For unsynchronized controllers, gateway receipt timestamp and boot/sequence form the ordering reference; no false device timestamp precision.

## 3. MQTT contract

Proposed topic: `edgeops/v1/{site_id}/{device_id}/telemetry`. No wildcard publish rights. Proposed QoS1 requires idempotent consumers; it does not guarantee exactly-once business processing. Ensure max packet size and accepted schema versions are defined. MQTT control/actuation topics are **not in scope**.

## 4. HTTP endpoint sketch

| Method/path | Rights | Preconditions | Success | Errors |
|---|---|---|---|---|
| POST /v1/ingest/windows | edge:write | valid schema, device identity, idempotency | 202 or documented idempotent equivalent | 400, 401, 403, 409, 429 |
| GET /v1/assets/{asset_id}/telemetry | asset:read | tenant/site grants, pagination | 200 paged | 401, 403, 404 |
| GET /v1/incidents | incident:read | site/asset filter | 200 paged | 401, 403 |
| POST /v1/incidents/{id}/acknowledge | incident:write | current version | 200 | 403, 409 |
| POST /v1/work-orders/{id}/approve | workorder:approve | different authorized approver, current version | 200 | 403, 409 |
| POST /v1/knowledge/query | knowledge:read | allowed SOP index | 200 answer+citation or explicit abstention | 403, 422 |

The above is an **API design proposal**, not a claim about existing routes.

## 5. Versioning and compatibility

Schema major version changes require explicit migration plan, dual-read/write transition where relevant, old-firmware compatibility window and negative tests. Use an idempotency key scoped to authenticated sender and event identity. Persist event receipt and model version to enable deterministic replay. Keep OpenAPI and JSON Schema documents canonical during implementation.

## 6. Approval invariants

A work order approved at version N becomes unapproved after a material change. Creator and approver cannot be the same identity where separation of duties is mandated. An LLM cannot supply an approver identity or override this invariant.
