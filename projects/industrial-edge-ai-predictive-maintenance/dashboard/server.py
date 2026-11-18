"""EDGEOPS dashboard development backend.

Local-first prototype, not industrial production approval. Same-origin secure
session design, SQLite audit trail, read-only synthetic catalog, no actuation.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("EDGEOPS_DASHBOARD_DB", str(ROOT / ".local" / "dashboard.sqlite3"))).resolve()
SESSION_HOURS = 8
SESSION_SECONDS = SESSION_HOURS * 3600
COOKIE = "edgeops_session"
CSRF_COOKIE = "edgeops_csrf"
HTTPS_ONLY = os.environ.get("EDGEOPS_HTTPS_ONLY", "0") == "1"
BOOTSTRAP_EMAIL = os.environ.get("EDGEOPS_ADMIN_EMAIL", "").strip().lower()
BOOTSTRAP_PASSWORD = os.environ.get("EDGEOPS_ADMIN_PASSWORD", "")
MAX_BODY_BYTES = 8192

app = FastAPI(title="EDGEOPS Industrial Console", docs_url=None, redoc_url=None, openapi_url=None)
PUBLIC_ASSETS = {"styles.css", "app.js", "dashboard-auth.js", "architecture.js", "signin.css", "signin.js", "industrial-motor.svg", "industrial-plant.svg", "edgeops-motor-photo.jpg", "edgeops-factory-backdrop.jpg"}

@app.get("/static/{asset}")
def public_asset(asset: str):
    if asset not in PUBLIC_ASSETS:
        raise HTTPException(404, "Not found")
    candidate = ROOT / asset
    if not candidate.is_file():
        raise HTTPException(404, "Asset not installed")
    return FileResponse(candidate)

# Only hardware explicitly identified in prior user-provided inventory is named.
# Slots 15–30 are NOT confirmed purchases or engineering-approved parts.
HARDWARE = [
    ("HW-01", "Raspberry Pi 5 (4 GB)", "Edge compute", "edge"),
    ("HW-02", "ESP32-WROOM-32 development board", "Telemetry acquisition", "embedded"),
    ("HW-03", "ADXL345 accelerometer", "Vibration sensing", "sensor"),
    ("HW-04", "DS18B20 temperature sensor", "Temperature sensing", "sensor"),
    ("HW-05", "INA219 current/voltage sensor", "Electrical telemetry", "sensor"),
    ("HW-06", "12 V DC motor", "Guarded bench rig only", "equipment"),
    ("HW-07", "Raspberry Pi 5 power supply", "Regulated edge power", "power"),
    ("HW-08", "Raspberry Pi cooler and case", "Thermal and mechanical protection", "mechanical"),
    ("HW-09", "32/64 GB microSD card", "Development boot media", "storage"),
    ("HW-10", "Breadboard and jumper wires", "Low-voltage prototype interconnect", "prototype"),
    ("HW-11", "ESP32 USB data cable", "Provisioning and debugging", "cable"),
    ("HW-12", "Digital multimeter", "Electrical measurements", "instrument"),
    ("HW-13", "Resistors and connectors", "Low-voltage interconnect", "electrical"),
    ("HW-14", "Fuse, switch and protective motor guard", "Independent bench safeguards", "safety"),
]
HARDWARE += [(f"HW-{i:02d}", "Unconfirmed hardware slot", "Pending approved bill of materials", "unconfirmed")
             for i in range(15, 31)]


def now_epoch() -> int:
    return int(time.time())


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def password_hash(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 480_000)
    return "pbkdf2_sha256$480000$" + salt.hex() + "$" + digest.hex()


def password_matches(password: str, expected: str) -> bool:
    try:
        scheme, iterations, salt, digest = expected.split("$")
        if scheme != "pbkdf2_sha256" or int(iterations) < 300_000:
            return False
        calculated = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), int(iterations))
        return hmac.compare_digest(calculated, bytes.fromhex(digest))
    except (ValueError, TypeError):
        return False


@contextmanager
def database():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(DB_PATH), timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout=10000")
    connection.execute("PRAGMA foreign_keys=ON")
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


def init_db():
    with database() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY, email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL, role TEXT NOT NULL,
            disabled INTEGER NOT NULL DEFAULT 0)""")
        db.execute("""CREATE TABLE IF NOT EXISTS sessions(
            token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL,
            csrf_hash TEXT NOT NULL, expires_at INTEGER NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id))""")
        db.execute("""CREATE TABLE IF NOT EXISTS audit(
            id INTEGER PRIMARY KEY, time_utc TEXT NOT NULL,
            actor TEXT NOT NULL, action TEXT NOT NULL, detail TEXT NOT NULL)""")
        db.execute("DELETE FROM sessions WHERE expires_at <= ?", (now_epoch(),))
        number = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        if number == 0 and BOOTSTRAP_EMAIL and BOOTSTRAP_PASSWORD:
            if len(BOOTSTRAP_PASSWORD) < 14 or len(BOOTSTRAP_EMAIL) > 254 or "@" not in BOOTSTRAP_EMAIL:
                raise RuntimeError("Bootstrap admin needs a valid email and password of at least 14 characters")
            db.execute("INSERT INTO users(email,password_hash,role) VALUES(?,?,?)",
                       (BOOTSTRAP_EMAIL, password_hash(BOOTSTRAP_PASSWORD), "admin"))
            record_audit(db, BOOTSTRAP_EMAIL, "bootstrap", "local development admin created")


def record_audit(db: sqlite3.Connection, actor: str, action: str, detail: str):
    db.execute("INSERT INTO audit(time_utc,actor,action,detail) VALUES(?,?,?,?)",
               (datetime.now(timezone.utc).isoformat(), actor, action, detail[:240]))


@app.on_event("startup")
def startup():
    init_db()


def auth_context(request: Request) -> dict | None:
    token = request.cookies.get(COOKIE, "")
    if not token or len(token) != 64:
        return None
    with database() as db:
        row = db.execute("""SELECT u.id,u.email,u.role,u.disabled,s.csrf_hash,s.expires_at
            FROM sessions s JOIN users u ON u.id=s.user_id
            WHERE s.token_hash=?""", (token_hash(token),)).fetchone()
    if not row or row["disabled"] or row["expires_at"] <= now_epoch():
        return None
    return dict(row)


def require_user(request: Request):
    current = auth_context(request)
    if not current:
        raise HTTPException(401, "Authentication required")
    return current


def require_csrf(request: Request, current: dict):
    header = request.headers.get("x-edgeops-csrf", "")
    cookie = request.cookies.get(CSRF_COOKIE, "")
    if not header or not cookie or not hmac.compare_digest(header, cookie):
        raise HTTPException(403, "CSRF token missing or invalid")
    if not hmac.compare_digest(token_hash(header), current["csrf_hash"]):
        raise HTTPException(403, "CSRF token missing or invalid")


def set_session(response: Response, token: str, csrf: str):
    response.set_cookie(COOKIE, token, httponly=True, secure=HTTPS_ONLY,
                        samesite="strict", max_age=SESSION_SECONDS, path="/")
    # JS must read CSRF token for same-origin mutation requests.
    response.set_cookie(CSRF_COOKIE, csrf, httponly=False, secure=HTTPS_ONLY,
                        samesite="strict", max_age=SESSION_SECONDS, path="/")


def clear_session(response: Response):
    response.delete_cookie(COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")


class LoginInput(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=256)


class AlertAction(BaseModel):
    alert_id: str = Field(pattern=r"^AL-[0-9]{4}$", max_length=7)
    note: str = Field(default="", max_length=200)


# Small single-process throttle ONLY; needs distributed rate limiting at scale.
FAILED_LOGINS: dict[str, list[int]] = {}


@app.middleware("http")
async def secure_headers(request: Request, call_next):
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        if request.headers.get("content-length", "0").isdigit() and int(request.headers.get("content-length", "0")) > MAX_BODY_BYTES:
            return JSONResponse({"detail": "Request too large"}, status_code=413)
        origin = request.headers.get("origin")
        if origin and origin.rstrip("/") != str(request.base_url).rstrip("/"):
            return JSONResponse({"detail": "Origin mismatch"}, status_code=403)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Cache-Control"] = "no-store"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
    return response


@app.get("/")
def root(request: Request):
    return RedirectResponse("/app" if auth_context(request) else "/signin", status_code=303)


@app.get("/signin")
def signin(request: Request):
    if auth_context(request):
        return RedirectResponse("/app", status_code=303)
    return FileResponse(ROOT / "signin.html")


@app.get("/app")
def main_app(request: Request):
    if not auth_context(request):
        return RedirectResponse("/signin", status_code=303)
    return FileResponse(ROOT / "index.html")


@app.post("/api/auth/login")
def login(request: Request, body: LoginInput):
    email = body.email.strip().lower()
    # Hash email rather than store raw passwords or arbitrary client identifiers.
    client = request.client.host if request.client else "unknown"
    ipkey = token_hash(client + "|" + email)
    window = now_epoch() - 900
    attempts = [x for x in FAILED_LOGINS.get(ipkey, []) if x > window]
    if len(attempts) >= 5:
        raise HTTPException(429, "Too many attempts; retry later")
    with database() as db:
        user = db.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        # Do expensive KDF for nonexistent accounts to limit timing differences.
        dummy = "pbkdf2_sha256$480000$" + ("00" * 16) + "$" + ("00" * 32)
        ok = password_matches(body.password, user["password_hash"] if user else dummy)
        if not user or user["disabled"] or not ok:
            FAILED_LOGINS[ipkey] = attempts + [now_epoch()]
            record_audit(db, "unauthenticated", "login_failed", "invalid credentials")
            raise HTTPException(401, "Invalid email or password")
        FAILED_LOGINS.pop(ipkey, None)
        token = secrets.token_hex(32)
        csrf = secrets.token_urlsafe(32)
        db.execute("INSERT INTO sessions(token_hash,user_id,csrf_hash,expires_at) VALUES(?,?,?,?)",
                   (token_hash(token), user["id"], token_hash(csrf), now_epoch() + SESSION_SECONDS))
        record_audit(db, email, "login", "authenticated local browser session")
    response = JSONResponse({"ok": True, "role": user["role"], "redirect": "/app"})
    set_session(response, token, csrf)
    return response


@app.get("/api/me")
def me(request: Request):
    current = require_user(request)
    return {"email": current["email"], "role": current["role"],
            "mode": "synthetic", "session_expires_at": current["expires_at"]}


@app.post("/api/auth/logout")
def logout(request: Request):
    current = require_user(request)
    require_csrf(request, current)
    with database() as db:
        db.execute("DELETE FROM sessions WHERE token_hash=?", (token_hash(request.cookies[COOKIE]),))
        record_audit(db, current["email"], "logout", "local browser session ended")
    response = JSONResponse({"ok": True})
    clear_session(response)
    return response


@app.get("/api/hardware")
def hardware(request: Request):
    require_user(request)
    return {"mode": "proposed-inventory", "confirmed_hardware_count": 14,
            "slots_total": 30, "purchased_count": None,
            "devices": [{"id": i, "name": n, "purpose": p, "category": c,
                         "confirmed_inventory_name": c != "unconfirmed", "connected": False}
                        for i, n, p, c in HARDWARE]}


@app.get("/api/system/health")
def health(request: Request):
    require_user(request)
    return {"status": "local-demo", "hardware_connected": False,
            "telemetry_mode": "synthetic-browser-fixtures", "model_deployed": False,
            "actuators_enabled": False, "security_approval": "open",
            "physical_safety_gate": "blocking"}


@app.get("/api/audit")
def audit(request: Request, limit: int = 50):
    current = require_user(request)
    if current["role"] not in ("admin", "auditor"):
        raise HTTPException(403, "Role not authorized")
    limit = max(1, min(limit, 100))
    with database() as db:
        entries = db.execute("SELECT time_utc,actor,action,detail FROM audit ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return {"entries": [dict(e) for e in entries], "mode": "local-auth-audit-only"}


@app.post("/api/alerts/acknowledge")
def acknowledge(request: Request, body: AlertAction):
    current = require_user(request)
    require_csrf(request, current)
    if current["role"] not in ("admin", "operator"):
        raise HTTPException(403, "Role not authorized")
    # No real alarm mutation. Persist only audit record of a synthetic UI action.
    with database() as db:
        record_audit(db, current["email"], "demo_alert_ack", body.alert_id)
    return {"ok": True, "mode": "demo-audit-only", "persistent_alarm_state": False}
