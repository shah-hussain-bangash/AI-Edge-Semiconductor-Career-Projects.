"""Explicit local worker for configured email and encrypted-backup jobs.

Installation does not start this process or enable delivery/scheduling.
"""
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import secrets
import time
import local_notifications
import operational_notifications
import platform_operations
import protected_recovery


def valid_admin(db,identifier,revision):
    actor=db.execute('SELECT * FROM users WHERE id=?',(identifier,)).fetchone()
    return bool(actor and actor['role']=='admin' and not actor['disabled'] and local_notifications.account_revision(db,identifier)==revision)


def backup_pass(database,db_path):
    ready=platform_operations.backup_ready()
    if not ready['private_key_ready'] or not ready['output_directory_ready']:return dict(state='unconfigured')
    with database() as db:
        db.execute('BEGIN IMMEDIATE');policy=db.execute('SELECT * FROM platform_backup_policy WHERE singleton=1').fetchone()
        if (policy and policy['enabled'] and valid_admin(db,policy['issuer_id'],policy['issuer_revision'])
            and time.time()-policy['last_queued']>=policy['interval_hours']*3600):
            if db.execute('SELECT count(*) FROM platform_backup_jobs').fetchone()[0]<100:
                identity=secrets.token_hex(16)
                db.execute('INSERT INTO platform_backup_jobs VALUES(?,?,?,?,\'pending\',?,NULL,NULL,NULL,NULL)',
                    (identity,policy['issuer_id'],policy['issuer_revision'],secrets.token_hex(16),platform_operations.now()))
                db.execute('UPDATE platform_backup_policy SET last_queued=? WHERE singleton=1',(time.time(),))
        job=db.execute("SELECT * FROM platform_backup_jobs WHERE state='pending' OR (state='running' AND lease_until<?) ORDER BY created_at LIMIT 1",(time.time(),)).fetchone()
        if not job:return dict(state='idle')
        if not valid_admin(db,job['creator_id'],job['creator_revision']):
            db.execute("UPDATE platform_backup_jobs SET state='cancelled',finished_at=?,last_error='issuer-access-changed' WHERE id=?",(platform_operations.now(),job['id']))
            return dict(state='cancelled',id=job['id'])
        db.execute("UPDATE platform_backup_jobs SET state='running',lease_until=? WHERE id=?",(time.time()+900,job['id']))
        job=dict(job)
    folder=Path(os.environ['EDGEOPS_PROTECTED_BACKUP_DIR'])
    output=folder/('edgeops-backup-'+job['id']+'.enc')
    try:
        if output.exists() or output.is_symlink():raise FileExistsError('Existing output requires reconciliation')
        # Optional stores are explicit environment inputs, not assumptions about
        # what exists beside a database. Home USB data remains a separate backup.
        artifacts=os.environ.get('EDGEOPS_OFFLINE_EXPERIMENT_ROOT') or None
        spool=os.environ.get('EDGEOPS_BACKUP_DELIVERY_SPOOL') or None
        report=protected_recovery.backup(db_path,Path(os.environ['EDGEOPS_PRIVATE_KEY_FILE']),output,artifacts,spool)
        report['artifact_name']=output.name
    except FileExistsError:
        state='blocked';error='existing-output-needs-reconciliation';report=None
    except Exception:
        state='failed';error='protected-backup-failed-review-private-storage';report=None
    else:state='completed';error=None
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        db.execute('UPDATE platform_backup_jobs SET state=?,finished_at=?,lease_until=NULL,report=?,last_error=? WHERE id=?',
                   (state,platform_operations.now(),json.dumps(report,sort_keys=True) if report else None,error,job['id']))
    return dict(state=state,id=job['id'])


def run_once(database,db_path):
    identifier=secrets.token_hex(16);error=None
    try:
        email=operational_notifications.deliver(database)
        backup=backup_pass(database,db_path)
        result=dict(email=email,backup=backup)
    except Exception:
        error='worker-pass-failed';raise
    finally:
        with database() as db:db.execute('INSERT INTO platform_worker_status VALUES(1,?,?,?) ON CONFLICT(singleton) DO UPDATE SET last_pass=excluded.last_pass,worker_id=excluded.worker_id,last_error=excluded.last_error',
                                       (time.time(),identifier,error))
    return result


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    choice=parser.add_mutually_exclusive_group(required=True);choice.add_argument('--once',action='store_true');choice.add_argument('--loop',action='store_true')
    parser.add_argument('--interval-seconds',type=int,default=60);args=parser.parse_args()
    if not 30<=args.interval_seconds<=3600:parser.error('Use a polling interval from 30 through 3600 seconds')
    from server import database,DB_PATH
    if not DB_PATH.is_file():raise SystemExit('Configured dashboard database missing. No database, job or message created.')
    try:
        while True:
            print(json.dumps(run_once(database,DB_PATH),sort_keys=True),flush=True)
            if args.once:break
            time.sleep(args.interval_seconds)
    except KeyboardInterrupt:pass
    except Exception:raise SystemExit('Platform worker unavailable; inspect private configuration and retained job status. No credentials printed.')
