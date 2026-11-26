"""Cold, bounded home backups and verified restore to NEW directories only."""
from contextlib import closing
import hashlib
import os
from pathlib import Path,PurePosixPath
import secrets
import shutil
import sqlite3
import time
from home_core import ROOT,ProcessLock,canonical,strict_json,validate_settings,utc_now

MAX_TOTAL=512*1024*1024
MAX_FILE=256*1024*1024
MAX_FILES=5000


def linked(path):return path.is_symlink() or getattr(path,'is_junction',lambda:False)()


def relative_name(text):
    if not isinstance(text,str) or not text or ':' in text or '\\' in text or '\0' in text:raise ValueError('Unsafe backup path')
    path=PurePosixPath(text)
    if path.is_absolute() or any(p in ('','.','..') or p.endswith((' ','.')) for p in text.split('/')):raise ValueError('Unsafe backup path')
    for part in path.parts:
        stem=part.split('.')[0].upper()
        if stem in {'CON','PRN','AUX','NUL'} or (len(stem)==4 and stem[:3] in ('COM','LPT') and stem[3] in '123456789'):raise ValueError('Nonportable backup filename')
    return path


def inventory(root):
    root=Path(root)
    if linked(root):raise ValueError('Linked backup/data roots are not supported')
    result={};total=0
    for current,dirs,files in os.walk(root,followlinks=False):
        for name in dirs:
            if linked(Path(current)/name):raise ValueError('Linked directories are not supported')
        for name in files:
            path=Path(current)/name
            if linked(path) or not path.is_file():raise ValueError('Only regular files can be backed up')
            rel=path.relative_to(root).as_posix();relative_name(rel)
            size=path.stat().st_size;total+=size
            if size>MAX_FILE or total>MAX_TOTAL or len(result)>=MAX_FILES:raise ValueError('Backup exceeds file/count/512 MiB bounds; nothing is silently truncated')
            result[rel]=path
    return result


def digest(path):
    hash=hashlib.sha256();size=0
    with open(path,'rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):
            size+=len(chunk)
            if size>MAX_FILE:raise ValueError('File exceeds backup bound')
            hash.update(chunk)
    return dict(bytes=size,sha256=hash.hexdigest())


def validate_database(path):
    with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True)) as db:
        if db.execute('PRAGMA quick_check').fetchall()!=[('ok',)]:raise ValueError('Database integrity check failed')
        columns={row[1] for row in db.execute('PRAGMA table_info(home_samples)')}
        required={'id','session_id','received_at','source','payload_json','content_hash'}
        if columns!=required:raise ValueError('Unsupported home database schema')
        count=0
        for session,received,source,raw,checksum in db.execute('SELECT session_id,received_at,source,payload_json,content_hash FROM home_samples'):
            count+=1
            if count>100000 or hashlib.sha256(raw.encode()).hexdigest()!=checksum:raise ValueError('History content/count check failed')
            sample=strict_json(raw);canonical(sample)
            if sample.get('session_id')!=session or sample.get('received_at')!=received or sample.get('source')!=source or source not in ('simulated','serial-unverified'):raise ValueError('History metadata check failed')
            if any(sample.get(k) is not False for k in ('production_ready','hardware_verified','calibration_verified','equipment_authorized')):raise ValueError('History verification labels must remain unverified')
        return count


def validate_data(root,files):
    if 'RESTORE_INCOMPLETE' in files:raise ValueError('Incomplete restore cannot be treated as valid home data')
    if 'config.json' in files:
        path=Path(root)/'config.json'
        if path.stat().st_size>4096:raise ValueError('Configuration too large')
        validate_settings(strict_json(path.read_text(encoding='utf-8')))
    return validate_database(Path(root)/'history.sqlite3') if 'history.sqlite3' in files else 0


def private_new_directory(target):
    target=Path(target)
    if target.exists() or linked(target):raise ValueError('Destination already exists; no files were overwritten')
    resolved=target.resolve()
    try:rel=resolved.relative_to(ROOT.resolve())
    except ValueError:pass
    else:
        if not rel.parts or rel.parts[0]!='.local':raise ValueError('Use a private .local destination or a directory outside this checkout')
    target.mkdir(parents=True,exist_ok=False,mode=0o700)
    if os.name!='nt':target.chmod(0o700)
    return target


def copy_private(source,target):
    target.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    descriptor=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with open(source,'rb') as incoming,os.fdopen(descriptor,'wb') as outgoing:
        size=0
        for chunk in iter(lambda:incoming.read(1024*1024),b''):
            size+=len(chunk)
            if size>MAX_FILE:raise ValueError('Source grew beyond backup bounds')
            outgoing.write(chunk)
        outgoing.flush();os.fsync(outgoing.fileno())


def create(source,output=None):
    source=Path(source)
    if not source.is_dir() or linked(source):raise ValueError('Choose an existing home data directory')
    output=Path(output) if output else ROOT/'.local/backups'/('home-'+time.strftime('%Y%m%d-%H%M%S')+'-'+secrets.token_hex(4))
    if output.resolve()==source.resolve() or source.resolve() in output.resolve().parents:raise ValueError('A backup must be outside the source data directory')
    if output.exists() or linked(output):raise ValueError('Backup destination exists; nothing overwritten')
    with ProcessLock(source/'server.lock'):
        files=inventory(source)
        files={name:path for name,path in files.items() if name not in ('server.lock','history.sqlite3-wal','history.sqlite3-shm')}
        if not files:raise ValueError('No home data to back up')
        validate_data(source,files)
        target=private_new_directory(output);data=target/'data';data.mkdir(mode=0o700)
        for name,path in files.items():
            destination=data/name
            if name=='history.sqlite3':
                fd=os.open(destination,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600);os.close(fd)
                started=time.monotonic()
                def progress(*_):
                    if time.monotonic()-started>30:raise TimeoutError('SQLite backup timed out')
                with closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True)) as original,closing(sqlite3.connect(destination)) as backup:
                    original.backup(backup,pages=128,progress=progress,sleep=.1)
                    backup.execute('PRAGMA journal_mode=DELETE').fetchone()
            else:copy_private(path,destination)
        saved=inventory(data);rows=validate_data(data,saved)
        manifest=dict(format='edgeops-home-backup-v1',created_at=utc_now(),rows=rows,
            excludes=['server.lock','history.sqlite3-wal','history.sqlite3-shm'],
            files={name:digest(path) for name,path in saved.items()},
            physical_acceptance='pending',production_ready=False,hardware_verified=False,calibration_verified=False)
        fd=os.open(target/'backup-manifest.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'w',encoding='utf-8') as stream:stream.write(canonical(manifest)+'\n');stream.flush();os.fsync(stream.fileno())
    verify(target)
    return dict(backup=str(target),files=len(saved),rows=rows,backup_integrity_verified=True,physical_acceptance='pending')


def verify(folder):
    folder=Path(folder)
    if linked(folder) or {p.name for p in folder.iterdir()}!={'data','backup-manifest.json'}:raise ValueError('Incomplete or unexpected backup inventory')
    manifest_path=folder/'backup-manifest.json'
    if linked(manifest_path) or manifest_path.stat().st_size>2*1024*1024:raise ValueError('Invalid backup manifest')
    manifest=strict_json(manifest_path.read_text(encoding='utf-8'))
    if manifest.get('format')!='edgeops-home-backup-v1' or manifest.get('physical_acceptance')!='pending' or any(manifest.get(k) is not False for k in ('production_ready','hardware_verified','calibration_verified')):raise ValueError('Unsupported backup labels')
    if not isinstance(manifest.get('files'),dict) or not 1<=len(manifest['files'])<=MAX_FILES:raise ValueError('Invalid backup file count')
    files=inventory(folder/'data')
    if set(files)!=set(manifest['files']):raise ValueError('Backup file inventory mismatch')
    for name,meta in manifest['files'].items():
        relative_name(name)
        if meta!=digest(files[name]):raise ValueError('Backup checksum mismatch')
    rows=validate_data(folder/'data',files)
    if manifest.get('rows')!=rows:raise ValueError('Backup row count mismatch')
    return manifest


def restore(folder,destination):
    manifest=verify(folder);folder=Path(folder);destination=Path(destination)
    if destination.exists() or linked(destination):raise ValueError('Restore destination exists; original data was preserved')
    target=private_new_directory(destination)
    marker=target/'RESTORE_INCOMPLETE'
    fd=os.open(marker,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600);os.close(fd)
    for name in manifest['files']:copy_private(folder/'data'/name,target/name)
    restored=inventory(target);restored.pop('RESTORE_INCOMPLETE',None);validate_data(target,restored)
    for name,meta in manifest['files'].items():
        if digest(target/name)!=meta:raise ValueError('Restored checksum mismatch; incomplete destination preserved for review')
    marker.unlink()
    return dict(restored=str(target),files=len(restored),rows=manifest['rows'],physical_acceptance='pending',production_ready=False)
