"""Read-only index of private raw recordings, including records from prior boots."""
from pathlib import Path
import re
from home_core import strict_json
from home_recording import package


def folder_for(directory,identity):
    if not isinstance(identity,str) or not re.fullmatch('[a-f0-9]{32}',identity):raise ValueError('Invalid recording ID')
    root=Path(directory)/'captures';folder=root/identity
    if root.is_symlink() or getattr(root,'is_junction',lambda:False)() or folder.is_symlink() or getattr(folder,'is_junction',lambda:False)() or folder.resolve().parent!=root.resolve():raise ValueError('Recording links are not supported')
    return folder


def listing(directory,offset=0,limit=20,active_id=None):
    if type(offset) is not int or not 0<=offset<=10000 or type(limit) is not int or not 1<=limit<=100:raise ValueError('Invalid recording page')
    root=Path(directory)/'captures'
    if not root.exists():return dict(items=[],total=0,offset=offset,limit=limit,physical_acceptance='pending')
    if root.is_symlink() or getattr(root,'is_junction',lambda:False)():raise ValueError('Recording root cannot be linked')
    entries=[];scanned=0
    for item in root.iterdir():
        scanned+=1
        if scanned>10000:raise ValueError('Recording library exceeds index bound; archive folders deliberately')
        if re.fullmatch('[a-f0-9]{32}',item.name):entries.append(item.name)
    entries.sort(reverse=True);items=[]
    for identity in entries[offset:offset+limit]:
        item=dict(id=identity,state='incomplete',downloadable=False,physical_acceptance='pending')
        try:
            folder=folder_for(directory,identity);path=folder/'manifest.json'
            if identity==active_id:item['state']='recording'
            elif not path.is_file():pass
            elif path.is_symlink() or path.stat().st_size>16384:raise ValueError('Invalid manifest')
            else:
                manifest=strict_json(path.read_text(encoding='utf-8'))
                if manifest.get('format')!='edgeops-raw-usb-v1' or manifest.get('session_id')!=identity or manifest.get('physical_acceptance')!='pending' or any(manifest.get(k) is not False for k in ('production_ready','hardware_verified','calibration_verified','equipment_authorized')):raise ValueError('Invalid verification labels')
                item.update(state='finalized-unchecked',downloadable=True,started_at=manifest.get('started_at_host_utc'),
                    mode=manifest.get('settings',{}).get('mode'),source=manifest.get('source'),
                    stop_reason=manifest.get('stop_reason'),raw_bytes=manifest.get('raw_bytes'))
        except (OSError,ValueError,KeyError,TypeError):item.update(state='invalid',downloadable=False)
        items.append(item)
    return dict(items=items,total=len(entries),offset=offset,limit=limit,physical_acceptance='pending')


def download(directory,identity,active_id=None):
    if identity==active_id:raise ValueError('Active recording cannot be downloaded as finalized')
    return package(folder_for(directory,identity))


def office_download(directory,identity,active_id=None):
    if identity==active_id:raise ValueError('Active recording must finish before office export')
    from office_handoff import package as office_package
    return office_package(folder_for(directory,identity))
