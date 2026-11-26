"""Bounded USB-to-HTTPS bench gateway. No motor actuation, Wi-Fi or cloud provisioning."""
import argparse
from datetime import datetime,timezone
import hashlib
import importlib.util
import ipaddress
import json
import os
from pathlib import Path
import secrets
import sqlite3
import sys
import time
from urllib.parse import urlsplit

ROOT=Path(__file__).resolve().parents[1]
PRIVATE=ROOT/'.local'
spec=importlib.util.spec_from_file_location('capture_contract',ROOT/'phase-01-hardware/scripts/capture_serial.py')
capture=importlib.util.module_from_spec(spec);spec.loader.exec_module(capture)
MAX_PENDING=10000


def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)
def digest(value):return hashlib.sha256(canonical(value).encode()).hexdigest()


def validate_config(value):
    if not isinstance(value,dict) or set(value)!={'portal_url','token','expected_device_id'}:raise ValueError('Unsupported gateway configuration')
    url=urlsplit(value['portal_url'])
    loopback=False
    try:loopback=ipaddress.ip_address(url.hostname or '').is_loopback
    except ValueError:pass
    if (url.scheme!='https' and not (url.scheme=='http' and loopback)) or not url.hostname or url.username or url.password or url.query or url.fragment or url.path not in ('','/'):
        raise ValueError('Use an HTTPS portal root URL; HTTP is allowed only for literal loopback testing')
    if not isinstance(value['token'],str) or not value['token'].startswith('edgeops_bench_') or len(value['token'])!=len('edgeops_bench_')+64:raise ValueError('Use a scoped bench credential from Devices → USB bench readings')
    import re
    if not isinstance(value['expected_device_id'],str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',value['expected_device_id']):raise ValueError('Use the exact firmware device ID')
    return {**value,'portal_url':value['portal_url'].rstrip('/')}


def private_directory():
    PRIVATE.mkdir(exist_ok=True,mode=0o700)
    if os.name!='nt':os.chmod(PRIVATE,0o700)


def configure():
    from getpass import getpass
    private_directory()
    path=PRIVATE/'gateway.json'
    if path.exists() and input('Replace existing private gateway configuration? Type REPLACE: ')!='REPLACE':return
    data=validate_config(dict(portal_url=input('Portal root URL (HTTPS, or http://127.0.0.1:8877 for local testing): ').strip(),
        token=getpass('Scoped bench token (hidden): ').strip(),expected_device_id=input('Firmware device ID [motor-001]: ').strip() or 'motor-001'))
    if (PRIVATE/'gateway-spool.sqlite3').exists():
        spool=Spool(PRIVATE/'gateway-spool.sqlite3')
        try:spool.bind(data)
        finally:spool.close()
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
    with os.fdopen(fd,'w',encoding='utf-8') as stream:json.dump(data,stream,indent=2)
    if os.name!='nt':os.chmod(path,0o600)
    print('Private gateway configuration saved. It is excluded from Git.')


class Spool:
    def __init__(self,path):
        self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True)
        lock_path=Path(str(self.path)+'.lock');self.lock=open(lock_path,'a+b')
        try:
            if lock_path.stat().st_size==0:self.lock.write(b'0');self.lock.flush()
            self.lock.seek(0)
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(self.lock.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(self.lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError:
            self.lock.close();raise ValueError('Another gateway is using this spool; stop that gateway first')
        self.db=sqlite3.connect(self.path,timeout=10)
        self.db.execute('PRAGMA journal_mode=WAL');self.db.execute('PRAGMA synchronous=FULL')
        self.db.execute('''CREATE TABLE IF NOT EXISTS pending(id INTEGER PRIMARY KEY,
            run_id TEXT NOT NULL,frame_index INTEGER NOT NULL,payload TEXT NOT NULL,hash TEXT NOT NULL,
            UNIQUE(run_id,frame_index))''');self.db.commit()
        self.db.execute('''CREATE TABLE IF NOT EXISTS destination(singleton INTEGER PRIMARY KEY CHECK(singleton=1),
            portal_url TEXT NOT NULL,token_fingerprint TEXT NOT NULL,device_id TEXT NOT NULL)''');self.db.commit()
        if os.name!='nt':os.chmod(self.path,0o600)

    def bind(self,config):
        context=(config['portal_url'],hashlib.sha256(config['token'].encode()).hexdigest(),config['expected_device_id'])
        with self.db:
            previous=self.db.execute('SELECT portal_url,token_fingerprint,device_id FROM destination WHERE singleton=1').fetchone()
            if previous!=context and self.db.execute('SELECT count(*) FROM pending').fetchone()[0]:
                raise ValueError('Pending readings belong to another portal, credential or device. Retry the original configuration or reconcile the retained spool before changing it.')
            self.db.execute('''INSERT INTO destination VALUES(1,?,?,?) ON CONFLICT(singleton) DO UPDATE SET
                portal_url=excluded.portal_url,token_fingerprint=excluded.token_fingerprint,device_id=excluded.device_id''',context)

    def add(self,body):
        previous=self.db.execute('SELECT hash FROM pending WHERE run_id=? AND frame_index=?',(body['run_id'],body['frame_index'])).fetchone()
        if previous:
            if previous[0]!=digest(body):raise ValueError('Pending frame identity conflict')
            return
        with self.db:
            if self.db.execute('SELECT count(*) FROM pending').fetchone()[0]>=MAX_PENDING:raise ValueError('Pending spool capacity reached; capture stopped without discarding retained readings')
            self.db.execute('INSERT INTO pending(run_id,frame_index,payload,hash) VALUES(?,?,?,?)',(body['run_id'],body['frame_index'],canonical(body),digest(body)))

    def drain(self,client,limit=100):
        count=0
        for row in self.db.execute('SELECT id,payload,hash FROM pending ORDER BY id LIMIT ?',(limit,)).fetchall():
            body=json.loads(row[1])
            if digest(body)!=row[2]:raise ValueError('Pending frame integrity check failed')
            try:response=client.post('/api/bench/readings',json=body)
            except Exception:return count,'network-unavailable'
            if response.status_code in (401,403,409):return count,'authorization-or-scope-refused'
            if response.status_code not in (200,201):return count,'portal-refused-or-unavailable'
            try:
                receipt=response.json()
                valid=(isinstance(receipt,dict) and receipt.get('stored') is True and receipt.get('scope')=='unverified-bench-readings'
                    and receipt.get('production_ready') is False and receipt.get('run_id')==body['run_id']
                    and type(receipt.get('frame_index')) is int and receipt['frame_index']==body['frame_index'] and receipt.get('content_hash')==row[2])
            except Exception:valid=False
            if not valid:return count,'invalid-portal-receipt'
            # Only remove the local pending copy after a matching central receipt.
            with self.db:self.db.execute('DELETE FROM pending WHERE id=? AND hash=?',(row[0],row[2]))
            count+=1
        return count,'ok'

    def close(self):
        self.db.close()
        self.lock.close()  # OS releases the process lock, including after crashes.


def sample(frame,run,index,source):
    capture.parse_record(canonical(frame))
    return dict(run_id=run,frame_index=index,source_type=source,
        gateway_received_at=datetime.now(timezone.utc).isoformat(timespec='microseconds'),frame=frame)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--configure',action='store_true');parser.add_argument('--list-ports',action='store_true')
    mode=parser.add_mutually_exclusive_group();mode.add_argument('--port');mode.add_argument('--fixture',type=Path);mode.add_argument('--retry-only',action='store_true')
    parser.add_argument('--confirm-sensor-only',action='store_true');parser.add_argument('--seconds',type=int,default=600)
    parser.add_argument('--config',type=Path,default=PRIVATE/'gateway.json');parser.add_argument('--spool',type=Path,default=PRIVATE/'gateway-spool.sqlite3')
    args=parser.parse_args(argv)
    if args.configure:configure();return 0
    if args.list_ports:
        from serial.tools.list_ports import comports
        for port in comports():print(port.device+' — '+port.description)
        return 0
    if not 1<=args.seconds<=86400:parser.error('Seconds must be between 1 and 86400')
    if not args.port and not args.fixture and not args.retry_only:parser.error('Select --port, --fixture or --retry-only')
    if args.port and not args.confirm_sensor_only:parser.error('Review the sensor-only wiring first, then use --confirm-sensor-only')
    config=validate_config(json.loads(args.config.read_text(encoding='utf-8')))
    if os.name!='nt' and args.config.stat().st_mode & 0o077:raise ValueError('Private gateway configuration must have mode 600: chmod 600 '+str(args.config))
    private_directory();spool=Spool(args.spool)
    import httpx
    delivered=accepted=rejected=0;failure='ok';run=secrets.token_hex(16)
    try:
        spool.bind(config)
        with httpx.Client(base_url=config['portal_url'],headers={'authorization':'Bearer '+config['token']},timeout=5,trust_env=False,follow_redirects=False) as client:
            count,failure=spool.drain(client);delivered+=count
            if failure!='ok':print('Pending delivery stopped: '+failure+'. Data retained; check the portal/configuration and use --retry-only.');return 2
            if args.retry_only:print('Pending delivery completed: '+str(delivered));return 0
            if args.fixture:
                if args.fixture.stat().st_size>1024*1024:raise ValueError('Fixture exceeds 1 MiB')
                stream=args.fixture.open('rb');source='software-fixture'
            else:
                import serial
                stream=serial.Serial(args.port,115200,timeout=1,**({'exclusive':True} if os.name!='nt' else {}));source='measured-unverified'
            deadline=time.monotonic()+args.seconds;next_delivery=0;backoff=1;pending=b'';discard=False
            try:
                while time.monotonic()<deadline:
                    raw=stream.readline(4097)
                    if not raw and args.fixture:break
                    if raw:
                        pending+=raw
                        if len(pending)>4096:discard=True;pending=b''
                        if raw.endswith(b'\n'):
                            line=pending;pending=b''
                            if discard:discard=False;rejected+=1;continue
                            if line.startswith(b'#') or not line.strip():continue
                            try:
                                text=line.decode('utf-8');capture.parse_record(text);frame=json.loads(text)
                                if frame['device_id']!=config['expected_device_id']:raise ValueError('Wrong device')
                            except (ValueError,UnicodeError):rejected+=1;continue
                            spool.add(sample(frame,run,accepted,source));accepted+=1
                    if time.monotonic()>=next_delivery:
                        count,failure=spool.drain(client);delivered+=count
                        if failure in ('authorization-or-scope-refused','invalid-portal-receipt'):break
                        backoff=1 if failure=='ok' else min(60,backoff*2);next_delivery=time.monotonic()+backoff
            except KeyboardInterrupt:pass
            finally:stream.close()
            if failure not in ('authorization-or-scope-refused','invalid-portal-receipt'):
                count,failure=spool.drain(client);delivered+=count
    finally:spool.close()
    print(canonical(dict(accepted=accepted,delivered=delivered,rejected=rejected,last_outcome=failure,source_type=source,production_ready=False)))
    return 0 if failure=='ok' else 2


if __name__=='__main__':
    try:raise SystemExit(main())
    except (ValueError,OSError) as error:print('Gateway stopped: '+str(error),file=sys.stderr);raise SystemExit(2)
