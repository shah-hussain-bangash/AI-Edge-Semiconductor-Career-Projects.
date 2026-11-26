"""Private local encryption key loader. Keys never enter API responses or Git."""
import os
from pathlib import Path


def cipher(path=None):
    from cryptography.fernet import Fernet
    configured=path or os.environ.get('EDGEOPS_PRIVATE_KEY_FILE','')
    if not configured:raise ValueError('Private key file is not configured')
    target=Path(configured)
    if target.is_symlink() or not target.is_file() or not 40<=target.stat().st_size<=128:raise ValueError('Private key file unavailable')
    if os.name!='nt' and target.stat().st_mode&0o077:raise ValueError('Private key file permissions must be restricted to its owner')
    return Fernet(target.read_bytes().strip())


def configured():
    try:cipher();return True
    except (ValueError,OSError,ImportError):return False


def generate(path):
    from cryptography.fernet import Fernet
    target=Path(path)
    if not target.parent.is_dir():raise ValueError('Choose an existing protected parent directory')
    descriptor=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(descriptor,'wb') as stream:stream.write(Fernet.generate_key()+b'\n');stream.flush();os.fsync(stream.fileno())


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=['generate']);parser.add_argument('--output',required=True);args=parser.parse_args()
    try:generate(args.output)
    except (ValueError,OSError,ImportError):raise SystemExit('Key generation refused. Check dependencies and a new filename in a protected directory.')
    print('Private key saved to the selected new file. Keep an independent protected copy; no key printed.')
