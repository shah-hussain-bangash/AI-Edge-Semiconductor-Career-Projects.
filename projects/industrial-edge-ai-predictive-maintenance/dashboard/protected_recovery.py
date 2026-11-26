"""Bounded authenticated encryption of verified backups; never overwrites live data.

Fernet operates in memory: this local tool supports up to 64 MiB uncompressed
backup payloads. Larger deployments need a separately qualified backup service.
"""
import argparse
import io
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import tempfile
import zipfile
import private_crypto
import recovery

MAX_PLAINTEXT=64*1024*1024
MAX_TOKEN=90*1024*1024


def _cleanup(stage,parent):
    resolved=Path(stage).resolve();parent=Path(parent).resolve()
    if resolved.parent!=parent or not resolved.name.startswith('.edgeops-private-'):
        raise ValueError('Refuse cleanup outside this operation staging directory')
    shutil.rmtree(resolved)


def seal(directory,key,output):
    root=Path(directory).resolve();destination=Path(output).absolute()
    if destination.resolve().is_relative_to(root):raise ValueError('Encrypted output must be outside the original backup')
    manifest=recovery.verify_backup(root)
    names=['manifest.json']+[item['path'] for item in manifest['files']]
    total=sum((root/name).stat().st_size for name in names)
    if total>MAX_PLAINTEXT:raise ValueError('Verified backup exceeds this bounded encryption tool size')
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w',zipfile.ZIP_STORED) as archive:
        for name in sorted(names):archive.writestr(name,(root/name).read_bytes())
    if stream.tell()>MAX_PLAINTEXT:raise ValueError('Backup archive exceeds the encryption bound')
    encrypted=private_crypto.cipher(key).encrypt(stream.getvalue())
    descriptor=os.open(destination,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(descriptor,'wb') as output_file:output_file.write(encrypted);output_file.flush();os.fsync(output_file.fileno())
    return dict(encrypted=True,bytes=len(encrypted),database_snapshot_verified=True,
                key_included=False,off_machine_copy_created=False,production_ready=False)


def unseal(source,key,output):
    source=Path(source);destination=Path(output).absolute()
    if destination.exists() or destination.is_symlink():raise ValueError('Choose a new unpacking directory')
    if source.is_symlink() or not source.is_file() or source.stat().st_size>MAX_TOKEN:raise ValueError('Encrypted file outside supported bounds')
    # Authentication occurs before staging or extraction.
    raw=private_crypto.cipher(key).decrypt(source.read_bytes())
    if len(raw)>MAX_PLAINTEXT:raise ValueError('Decrypted archive exceeds bounds')
    stage=Path(tempfile.mkdtemp(prefix='.edgeops-private-',dir=destination.parent))
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            entries=archive.infolist();names=[item.filename for item in entries]
            if len(entries)>recovery.MAX_FILES+1 or len(names)!=len(set(name.casefold() for name in names)) or sum(item.file_size for item in entries)>MAX_PLAINTEXT:raise ValueError('Unsupported encrypted inventory')
            reserved={'con','prn','aux','nul'}|{'com'+str(i) for i in range(1,10)}|{'lpt'+str(i) for i in range(1,10)}
            for item in entries:
                name=PurePosixPath(item.filename);mode=item.external_attr>>16
                if (name.is_absolute() or '..' in name.parts or name.as_posix()!=item.filename or '\\' in item.filename or ':' in item.filename
                    or any(part.endswith((' ','.')) or part.split('.')[0].casefold() in reserved for part in name.parts)
                    or item.is_dir() or item.flag_bits&1 or stat.S_ISLNK(mode) or item.compress_type!=zipfile.ZIP_STORED):raise ValueError('Unsupported encrypted archive path or type')
                target=stage/item.filename;target.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
                descriptor=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
                with os.fdopen(descriptor,'wb') as stream:stream.write(archive.read(item));stream.flush();os.fsync(stream.fileno())
        recovery.verify_backup(stage)
        destination.mkdir(mode=0o700,exist_ok=False)
        marker=destination/'RESTORE_INCOMPLETE';marker.write_text('Unpacking is incomplete; do not use this directory.\n',encoding='utf-8')
        target=destination/'backup';target.mkdir(mode=0o700)
        for path in stage.rglob('*'):
            if not path.is_file():continue
            relative=path.relative_to(stage);to=target/relative;to.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
            descriptor=os.open(to,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            with path.open('rb') as incoming,os.fdopen(descriptor,'wb') as outgoing:shutil.copyfileobj(incoming,outgoing);outgoing.flush();os.fsync(outgoing.fileno())
        recovery.verify_backup(target);marker.unlink()
        return dict(decrypted_backup=str(target),integrity_verified=True,live_database_replaced=False,
                    next_step='Use recovery.py restore into another new directory; existing sessions and live integrations are revoked there.',production_ready=False)
    finally:_cleanup(stage,destination.parent)


def backup(database,key,output,artifacts=None,delivery_spool=None):
    destination=Path(output).absolute()
    if destination.exists() or destination.is_symlink():raise ValueError('Encrypted destination already exists')
    stage=Path(tempfile.mkdtemp(prefix='.edgeops-private-',dir=destination.parent))
    try:
        snapshot=stage/'snapshot'
        recovery.create_backup(database,snapshot,artifacts=artifacts,delivery_spool=delivery_spool)
        result=seal(snapshot,key,destination)
        result.update(scope='Configured dashboard database and explicitly supplied stores only',
                      coordinated_cross_store_snapshot=False,includes_home_mode=False)
        return result
    finally:_cleanup(stage,destination.parent)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['seal','unseal','backup'])
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--key',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--artifacts',type=Path);parser.add_argument('--delivery-spool',type=Path)
    args=parser.parse_args()
    if args.action!='backup' and (args.artifacts or args.delivery_spool):parser.error('Additional stores apply only to backup')
    try:
        result=backup(args.source,args.key,args.output,args.artifacts,args.delivery_spool) if args.action=='backup' else seal(args.source,args.key,args.output) if args.action=='seal' else unseal(args.source,args.key,args.output)
        print(__import__('json').dumps(result,sort_keys=True))
    except Exception:raise SystemExit('Protected recovery refused. Check the key, integrity, limits and a new private destination; no live database replaced.')


if __name__=='__main__':main()
