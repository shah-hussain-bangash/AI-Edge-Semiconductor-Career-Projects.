# EA-25 — Executable Zero-Trust Policy Contract and Offline Tests

> **Status:** Candidate policy and executable **offline unit tests**, committed but **not executed** at document authoring time.  
> **Date:** 2026-11-17  
> **Scope:** EDGEOPS proposed IAM authorization and role/asset scope controls; **not** authentication, broker ACL, deployed security or electrical safety authorization.  
> **Dependency:** [EA-24 Security Architecture](24-ENTERPRISE-SECURITY-AND-ZERO-TRUST-VERIFICATION.md)

## 1. Enterprise security design objective

Translate a subset of proposed EA-24 authorization rules into a **deny-by-default machine-readable policy** and a deterministic standard-library Python test suite. Use mock identities and mock resources so no physical device, network broker, credential, cloud tenant or motor is required.

This exercise is **policy-contract unit testing**, not actual end-to-end Zero Trust security. The function accepts *trusted* principal data supplied by the caller; a production service would first need to authenticate the principal via properly implemented OIDC/mTLS/device registry, perform trusted resource lookup, and log decisions. Never expose the offline policy checker as an unrestricted external decision endpoint.

## 2. Artifacts

| Artifact | Description | Evidence status |
|---|---|---|
| [Proposed JSON policy](security/policy/edgeops-zero-trust.v1.json) | Default deny, action allowlist, role/type/scope conditions and synthetic principal fixtures | Authored |
| [Policy evaluator](security/policy/edgeops_policy.py) | Pure Python predicate with default-deny and action-specific checks | Authored, not executed at publication |
| [Unit tests](security/tests/test_zero_trust_policy.py) | **34** positive and negative synthetic policy test methods | Authored, not executed at publication |
| [EA-24](24-ENTERPRISE-SECURITY-AND-ZERO-TRUST-VERIFICATION.md) | 25 broader security scenarios including real transport, credentials and runtime checks | All 25 not yet executed |
| [EA-23 evidence](evidence/EA-23/test-results.txt) | Earlier local telemetry contract tests | 18 passed locally; *different verification scope* |

## 3. Candidate policy rules

| Action | Allowed principals | Resource checks | Special denial |
|---|---|---|---|
| `telemetry.publish` | device with publisher role | assigned site, asset and own device ID | cross-device/site publication |
| `telemetry.ingest` | service with ingestor role | assigned site and asset | unassigned asset |
| `asset.read` | operator, reviewer or admin human | assigned site and asset | cross-site and cross-asset |
| `sop.read` | operator/reviewer human or rag_reader service | assigned site and asset | SOP cross-site exposure |
| `workorder.draft` | operator human or advisory agent | assigned site and asset | draft outside scope |
| `workorder.approve` | reviewer human | assigned site and asset | self-approval; stale/missing version |
| `motor.start/stop`, `plc.write`, `scada.command`, `shell.execute`, `admin.grant_role`, `credential.read`, `model.deploy_unreviewed` | nobody | n/a | prohibited for entire prototype |

**Never interpret test fixture roles or principal IDs as actual authenticated user accounts.** The policy is intentionally not linked to an identity provider.

## 4. Repeatable local run (Windows PowerShell)

Run from:
`C:\Users\Gaming PC i9 3080\edgeops-workspace\projects\industrial-edge-ai-predictive-maintenance\enterprise-architecture`

```powershell
git pull --ff-only origin main
python --version
git rev-parse HEAD
python -m unittest discover -s security/tests -v
```

This suite uses Python's **standard library only**, so no extra package installation is required for EA-25. Tests should be run before recording a status of `passed`.

To preserve exact test output and environment *after a successful run*, execute:

```powershell
New-Item -ItemType Directory -Force -Path "evidence/EA-25" | Out-Null
python -m unittest discover -s security/tests -v *> "evidence/EA-25/test-results.txt"
$testExit = $LASTEXITCODE
@(
  "EDGEOPS EA-25 offline Zero-Trust policy test evidence"
  "Execution date: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz')"
  "Git commit: $(git rev-parse HEAD)"
  "Python: $(python --version)"
  "Command: python -m unittest discover -s security/tests -v"
  "Exit code: $testExit"
  "Mock-only authorization tests; no live broker, IAM, API, or OT safety evidence"
) | Set-Content "evidence/EA-25/README.txt"
Get-Content "evidence/EA-25/test-results.txt" -Tail 8
if ($testExit -ne 0) { throw "EA-25 tests failed: review before committing evidence." }
```

Then **only after reviewing the output**:

```powershell
git add evidence/EA-25/README.txt evidence/EA-25/test-results.txt
git commit -m "test(edgeops): record EA-25 offline zero-trust policy evidence"
git push origin main
```

Avoid committing `__pycache__` folders. A separate repo-wide `.gitignore` change may be proposed in a later code hygiene phase.

## 5. Verification map: offline versus true security

| EA-24 scenario | EA-25 support | What still requires runtime evidence |
|---|---|---|
| ZT-03/04 topic isolation | checks mock device/site scope | actual broker ACL, certificate binding and publish denial |
| ZT-06 identity mismatch | checks mock own-device and scope | cryptographic authenticated identity and registry lookup |
| ZT-11 cross-site asset request | tests `asset.read` deny | FastAPI token validation and database row policy |
| ZT-12/13 reviewer / self approval | tests role and creator inequality | real OIDC identity, workflow state machine, audit and separation |
| ZT-14 stale approval | tests exact version match | concurrency-safe transactional update |
| ZT-16 SOP isolation | tests site/asset policy | retrieval-time ACL and vector database filtering |
| ZT-18/19/21 agent/OT denies | tests hard-denied tool/action strings | deployed tool registry and absence of motor command endpoints |
| ZT-01/02/05/07/08/09/10/15/17/20/22/23/24/25 | **not covered by offline policy tests** | separate live or sandbox integration/security exercises |

## 6. Acceptance and readiness gate

- The 34 unit tests should pass on a clean checkout with commit SHA and Python version retained.
- Document each test failure and remediation rather than editing assertions merely to achieve green status.
- Extend future tests for malformed principal claims, token signatures/expiries, resource lookup races, partial updates and multi-tenant system boundaries.
- Formal **G4a security gate remains OPEN**, even if all 34 mock tests pass.
- **G4b physical safety gate remains BLOCKING**. No agent/API/motor actuation feature is authorized.
- No third-party security review or enterprise audit certification is implied.

## 7. Career/architecture impact

Demonstrates converting architecture requirements into *executable authorization specifications*, role and scope permission matrices, negative access tests, and evidence-based decision gates. This is relevant to Security & AI Governance, Enterprise AI Architect, Agentic AI Architect, AI Solutions Architect and AI Technical Lead roles — without overstating production security.

**Next phase after local run:** EA-26 security integration strategy and identity/broker/API configuration design with safe mock/sandbox scenarios, not hardware deployment.
