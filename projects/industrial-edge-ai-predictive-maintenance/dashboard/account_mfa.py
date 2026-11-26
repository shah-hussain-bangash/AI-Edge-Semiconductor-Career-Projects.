"""Optional local TOTP with encrypted seeds, durable replay guard and one-use recovery codes."""
import hashlib
import hmac
import json
import re
import secrets
import time
from datetime import datetime,timezone
from fastapi import HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from maintenance_requests import fresh_actor,require_role,READ_ROLES
import private_crypto


class Password(BaseModel):
    model_config=ConfigDict(extra='forbid')
    current_password:str=Field(strict=True,min_length=1,max_length=256)


class Confirm(BaseModel):
    model_config=ConfigDict(extra='forbid')
    nonce:str=Field(strict=True,pattern=r'^[a-f0-9]{32}$')
    code:str=Field(strict=True,pattern=r'^[0-9]{6}$')


class Disable(Password):
    code:str=Field(strict=True,min_length=6,max_length=32)


def init_schema(db):
    db.execute('''CREATE TABLE IF NOT EXISTS account_mfa(
        user_id INTEGER PRIMARY KEY REFERENCES users(id),secret_cipher TEXT,enabled INTEGER NOT NULL,last_counter INTEGER NOT NULL,
        pending_cipher TEXT,pending_nonce TEXT,pending_expires REAL,revision INTEGER NOT NULL)''')
    db.execute('''CREATE TABLE IF NOT EXISTS account_mfa_recovery(
        user_id INTEGER NOT NULL REFERENCES users(id),code_hash TEXT NOT NULL,used_at REAL,PRIMARY KEY(user_id,code_hash))''')
    db.execute('CREATE TABLE IF NOT EXISTS account_mfa_denials(user_id INTEGER NOT NULL REFERENCES users(id),time_epoch REAL NOT NULL)')
    db.execute('CREATE INDEX IF NOT EXISTS account_mfa_denial_time ON account_mfa_denials(user_id,time_epoch)')


def _secret(encrypted,user_id):
    try:
        data=json.loads(private_crypto.cipher().decrypt(encrypted.encode()).decode('utf-8'))
        if data['user_id']!=user_id or data['purpose']!='edgeops-totp-v1':raise ValueError()
        return data['secret']
    except Exception:raise HTTPException(503,'Account protection key or encrypted seed unavailable; use a retained recovery code or administrator recovery procedure') from None


def _counter(secret,code,last=-1):
    import pyotp
    if not re.fullmatch('[0-9]{6}',code):return None
    step=int(time.time()//30)
    for counter in (step,step-1,step+1):
        if counter>last and hmac.compare_digest(pyotp.TOTP(secret).at(datetime.fromtimestamp(counter*30,timezone.utc)),code):return counter
    return None


def _denied(db,user_id):
    db.execute('DELETE FROM account_mfa_denials WHERE time_epoch<?',(time.time()-900,))
    return db.execute('SELECT count(*) FROM account_mfa_denials WHERE user_id=?',(user_id,)).fetchone()[0]>=5


def verify_login(db,user_id,code):
    row=db.execute('SELECT * FROM account_mfa WHERE user_id=?',(user_id,)).fetchone()
    if not row or not row['enabled']:return True
    if _denied(db,user_id):return False
    if re.fullmatch('[a-f0-9]{32}',code or ''):
        hashed=hashlib.sha256(code.encode()).hexdigest()
        changed=db.execute('UPDATE account_mfa_recovery SET used_at=? WHERE user_id=? AND code_hash=? AND used_at IS NULL',(time.time(),user_id,hashed)).rowcount
        if changed:return True
    elif re.fullmatch('[0-9]{6}',code or ''):
        counter=_counter(_secret(row['secret_cipher'],user_id),code,row['last_counter'])
        if counter is not None:
            db.execute('UPDATE account_mfa SET last_counter=? WHERE user_id=?',(counter,user_id));return True
    db.execute('INSERT INTO account_mfa_denials VALUES(?,?)',(user_id,time.time()));return False


def install_routes(app,database,require_user,require_csrf,matches,audit):
    def authorize(db,request):
        if request.url.scheme!='https' and (not request.client or request.client.host not in ('127.0.0.1','::1')):raise HTTPException(403,'Account-protection changes require HTTPS or actual loopback')
        current=require_user(request);require_csrf(request,current)
        actor=fresh_actor(db,current);require_role(actor,READ_ROLES);return current,actor

    def password(db,actor,value):
        if _denied(db,actor['id']):raise HTTPException(429,'Too many account-protection attempts; retry after the 15-minute window')
        expected=db.execute('SELECT password_hash FROM users WHERE id=?',(actor['id'],)).fetchone()[0]
        if not matches(value,expected):
            db.execute('INSERT INTO account_mfa_denials VALUES(?,?)',(actor['id'],time.time()));audit(db,actor['email'],'mfa_change_denied','Password check failed');db.commit()
            raise HTTPException(403,'Account-protection change refused')

    @app.get('/api/account/mfa')
    def status(request:Request,response:Response):
        current=require_user(request);response.headers['Cache-Control']='no-store'
        with database() as db:
            db.execute('BEGIN');actor=fresh_actor(db,current);require_role(actor,READ_ROLES)
            row=db.execute('SELECT * FROM account_mfa WHERE user_id=?',(actor['id'],)).fetchone()
            return dict(enabled=bool(row and row['enabled']),pending=bool(row and row['pending_expires'] and row['pending_expires']>time.time()),
                        private_key_ready=private_crypto.configured(),recovery_codes_remaining=db.execute('SELECT count(*) FROM account_mfa_recovery WHERE user_id=? AND used_at IS NULL',(actor['id'],)).fetchone()[0],
                        method='TOTP plus one-use recovery codes',scope='local-account-protection',sso_connected=False)

    @app.post('/api/account/mfa/begin')
    def begin(body:Password,request:Request,response:Response):
        with database() as db:
            db.execute('BEGIN IMMEDIATE');current,actor=authorize(db,request);password(db,actor,body.current_password)
            row=db.execute('SELECT * FROM account_mfa WHERE user_id=?',(actor['id'],)).fetchone()
            if row and row['enabled']:raise HTTPException(409,'Account protection is already enabled; disable with a current code before replacing it')
            if not private_crypto.configured():raise HTTPException(503,'Configure a protected server key file before enrolling an authenticator')
            import pyotp
            seed=pyotp.random_base32();nonce=secrets.token_hex(16);expires=time.time()+600
            encrypted=private_crypto.cipher().encrypt(json.dumps(dict(purpose='edgeops-totp-v1',user_id=actor['id'],secret=seed)).encode()).decode()
            db.execute('INSERT INTO account_mfa VALUES(?,NULL,0,-1,?,?,?,1) ON CONFLICT(user_id) DO UPDATE SET pending_cipher=excluded.pending_cipher,pending_nonce=excluded.pending_nonce,pending_expires=excluded.pending_expires,revision=account_mfa.revision+1',
                       (actor['id'],encrypted,nonce,expires))
            audit(db,actor['email'],'mfa_enrollment_started','Pending authenticator enrollment, 10-minute expiry')
            response.headers['Cache-Control']='no-store'
            return dict(secret=seed,provisioning_uri=pyotp.TOTP(seed).provisioning_uri(name=actor['email'],issuer_name='EDGEOPS'),nonce=nonce,expires_at=expires,
                        enabled=False,instruction='Add this private seed to an authenticator, then confirm a code. Do not share the seed or URI.')

    @app.post('/api/account/mfa/confirm')
    def confirm(body:Confirm,request:Request,response:Response):
        with database() as db:
            db.execute('BEGIN IMMEDIATE');current,actor=authorize(db,request)
            if _denied(db,actor['id']):raise HTTPException(429,'Too many account-protection attempts; retry later')
            row=db.execute('SELECT * FROM account_mfa WHERE user_id=?',(actor['id'],)).fetchone()
            if not row or row['enabled'] or not row['pending_nonce'] or not hmac.compare_digest(row['pending_nonce'],body.nonce) or row['pending_expires']<time.time():raise HTTPException(409,'Pending enrollment expired or changed; begin again')
            counter=_counter(_secret(row['pending_cipher'],actor['id']),body.code)
            if counter is None:
                db.execute('INSERT INTO account_mfa_denials VALUES(?,?)',(actor['id'],time.time()));db.commit();raise HTTPException(403,'Authenticator code refused')
            db.execute('UPDATE account_mfa SET secret_cipher=pending_cipher,enabled=1,last_counter=?,pending_cipher=NULL,pending_nonce=NULL,pending_expires=NULL,revision=revision+1 WHERE user_id=?',(counter,actor['id']))
            db.execute('DELETE FROM account_mfa_recovery WHERE user_id=?',(actor['id'],))
            codes=[secrets.token_hex(16) for _ in range(10)]
            db.executemany('INSERT INTO account_mfa_recovery VALUES(?,?,NULL)',[(actor['id'],hashlib.sha256(code.encode()).hexdigest()) for code in codes])
            db.execute('DELETE FROM sessions WHERE user_id=? AND csrf_hash<>?',(actor['id'],current['csrf_hash']))
            audit(db,actor['email'],'mfa_enabled','Authenticator confirmed; other browser sessions revoked')
            response.headers['Cache-Control']='no-store';return dict(enabled=True,recovery_codes=codes,recovery_codes_shown_once=True)

    @app.post('/api/account/mfa/disable')
    def disable(body:Disable,request:Request):
        with database() as db:
            db.execute('BEGIN IMMEDIATE');current,actor=authorize(db,request);password(db,actor,body.current_password)
            row=db.execute('SELECT * FROM account_mfa WHERE user_id=?',(actor['id'],)).fetchone()
            if not row or not row['enabled']:raise HTTPException(409,'Account protection is not enabled')
            if not verify_login(db,actor['id'],body.code):db.commit();raise HTTPException(403,'Current authenticator or unused recovery code required')
            db.execute('UPDATE account_mfa SET secret_cipher=NULL,enabled=0,last_counter=-1,pending_cipher=NULL,pending_nonce=NULL,pending_expires=NULL,revision=revision+1 WHERE user_id=?',(actor['id'],))
            db.execute('DELETE FROM account_mfa_recovery WHERE user_id=?',(actor['id'],));db.execute('DELETE FROM sessions WHERE user_id=? AND csrf_hash<>?',(actor['id'],current['csrf_hash']))
            audit(db,actor['email'],'mfa_disabled','Explicit password and factor verification; other sessions revoked')
            return dict(enabled=False)
