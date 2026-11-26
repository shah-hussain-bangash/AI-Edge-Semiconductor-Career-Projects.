"""Optional local portal for rehearsal. It does not create an online deployment."""
from getpass import getpass
import os
from pathlib import Path
import sqlite3
import sys

ROOT=Path(__file__).resolve().parents[1]


def main():
    private=ROOT/'.local/portal';private.mkdir(parents=True,exist_ok=True,mode=0o700)
    if os.name!='nt':os.chmod(ROOT/'.local',0o700);os.chmod(private,0o700)
    database=private/'dashboard.sqlite3'
    existing=False
    if database.exists():
        with sqlite3.connect(database) as db:
            existing=bool(db.execute("SELECT 1 FROM sqlite_master WHERE name='users'").fetchone() and db.execute('SELECT count(*) FROM users').fetchone()[0])
    os.environ['EDGEOPS_DASHBOARD_DB']=str(database)
    os.environ['EDGEOPS_SYNTHETIC_TELEMETRY_DB']=str(private/'synthetic-telemetry.sqlite3')
    os.environ['EDGEOPS_OFFLINE_EXPERIMENT_ROOT']=str(private/'experiments')
    os.environ['EDGEOPS_HTTPS_ONLY']='0'
    if not existing:
        email=input('Create your LOCAL portal administrator email: ').strip()
        password=getpass('Unique administrator password (at least 14 characters): ')
        if len(password)<14 or password!=getpass('Repeat password: '):raise SystemExit('Passwords must match and contain at least 14 characters.')
        os.environ['EDGEOPS_ADMIN_EMAIL']=email;os.environ['EDGEOPS_ADMIN_PASSWORD']=password
    else:
        os.environ.pop('EDGEOPS_ADMIN_PASSWORD',None);os.environ.pop('EDGEOPS_ADMIN_EMAIL',None)
    sys.path.insert(0,str(ROOT/'dashboard'))
    import server
    server.init_db();server.BOOTSTRAP_PASSWORD='';os.environ.pop('EDGEOPS_ADMIN_PASSWORD',None)
    if not existing:del password
    print('Local rehearsal portal: http://127.0.0.1:8877/app — keep this Terminal open. Ctrl+C stops it.')
    print('This does not publish an online portal. Sign in with your own local account.')
    import uvicorn
    uvicorn.run(server.app,host='127.0.0.1',port=8877)


if __name__=='__main__':main()
