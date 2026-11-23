"""Read-only bench preparation for the user's existing fixed 30-product scope."""
import csv
from datetime import date
import hashlib
import io
import json
from pathlib import Path
import re

from fastapi import HTTPException,Request
from fastapi.responses import Response
from maintenance_requests import require_role,READ_ROLES


MAX_PLAN_BYTES=64*1024
MAX_MATRIX_BYTES=256*1024
MAX_MAP_BYTES=512*1024
MATRIX_NAME='phase-01-hardware/docs/physical-connection-pack/all-30-connection-matrix.csv'
MAP_NAME='phase-01-hardware/docs/physical-connection-pack/sensor-only-reference.svg'
ROW_FIELDS={'selected_family':'GitHub part/family','quantity_basis':'Planned quantity',
            'role':'Bench role','connection':'Physical placement / connection decision',
            'pending':'Exact-part confirmation before energizing'}
MATRIX_HEADERS=['ID',*ROW_FIELDS.values(),'Actual ordered SKU / board revision',
                'Observed terminal labels','Received / inspected evidence']


def _read_source(path,project,limit):
    if not path.resolve().is_relative_to(project):raise ValueError('Source outside project')
    for part in (path,*path.parents):
        if part==project:break
        if part.is_symlink() or getattr(part,'is_junction',lambda:False)():raise ValueError('Linked source')
    if not path.is_file():raise ValueError('Missing source')
    with path.open('rb') as stream:raw=stream.read(limit+1)
    if len(raw)>limit:raise ValueError('Oversized source')
    return raw


def _unique_object(pairs):
    result={}
    for key,value in pairs:
        if key in result:raise ValueError('Duplicate plan key')
        result[key]=value
    return result


def read_preparation(root):
    """Validate bounded source snapshots; hashes establish consistency, not approval."""
    root=Path(root).absolute()
    project=root.parent.resolve()
    try:
        raw=_read_source(root/'physical-build-plan.json',project,MAX_PLAN_BYTES)
        data=json.loads(raw,object_pairs_hook=_unique_object)
        if not isinstance(data,dict):raise ValueError('Invalid plan object')
        rows=data.get('rows')
        if not isinstance(rows,list) or any(not isinstance(row,dict) for row in rows):raise ValueError('Invalid rows')
        expected=[f'BOM-{i:02}' for i in range(1,31)]
        if (len(rows)!=30 or [row['id'] for row in rows]!=expected
                or data['scope']!='physical-preparation-only'
                or data['version']!='fixed-30-physical-build-v1' or data['ordered_count_user_reported']!=30
                or data['production_ready'] is not False
                or data['additional_hardware_allowed'] is not False or data['substitution_allowed'] is not False
                or data['hardware_connected'] is not False or data['order_verified'] is not False
                or data['pins']!={'SDA':21,'SCL':22,'temperature_data':4}):
            raise ValueError('Unsupported physical plan')
        if (not isinstance(data['order_reported_on'],str)
                or date.fromisoformat(data['order_reported_on']).isoformat()!=data['order_reported_on']
                or data['source_hash_basis']!='UTF-8 CSV with LF newlines'):
            raise ValueError('Invalid source declaration')
        for key in ('source_csv_sha256','sensor_map_sha256'):
            if not isinstance(data.get(key),str) or not re.fullmatch('[0-9a-f]{64}',data[key]):raise ValueError('Invalid source hash')
        if any(not isinstance(row.get(key),str) or not row[key].strip() or len(row[key])>2000 for row in rows for key in ROW_FIELDS):raise ValueError('Invalid plan entry')
        matrix=_read_source(project/MATRIX_NAME,project,MAX_MATRIX_BYTES)
        if hashlib.sha256(matrix.replace(b'\r\n',b'\n')).hexdigest()!=data['source_csv_sha256']:raise ValueError('Changed matrix')
        reader=csv.DictReader(io.StringIO(matrix.decode('utf-8-sig')))
        if reader.fieldnames!=MATRIX_HEADERS:raise ValueError('Invalid matrix columns')
        source_rows=list(reader)
        if len(source_rows)!=30 or [row['ID'] for row in source_rows]!=[f'P{i:02}' for i in range(1,31)]:raise ValueError('Changed matrix scope')
        for row,source_row in zip(rows,source_rows):
            if None in source_row or any(row[key]!=source_row[column] for key,column in ROW_FIELDS.items()):raise ValueError('Plan row differs from matrix')
        sensor_map=_read_source(root/'physical-sensor-map.svg',project,MAX_MAP_BYTES)
        source_map=_read_source(project/MAP_NAME,project,MAX_MAP_BYTES)
        if hashlib.sha256(sensor_map).hexdigest()!=data['sensor_map_sha256'] or sensor_map!=source_map:raise ValueError('Changed map')
        data['plan_sha256']=hashlib.sha256(raw).hexdigest()
        return data,sensor_map
    except (OSError,ValueError,KeyError,TypeError,csv.Error,RecursionError):
        raise HTTPException(503,'Physical preparation plan is unavailable; no connection instructions returned')


def read_plan(root):
    return read_preparation(root)[0]


def install_routes(app,require_user,root):
    root=Path(root)
    @app.get('/api/hardware/physical-plan/arrival-pack')
    def arrival_pack(request:Request):
        require_role(require_user(request),READ_ROLES)
        from hardware_handover import build_pack
        return Response(build_pack(root), media_type='application/zip', headers={
            'Content-Disposition':'attachment; filename="edgeops-hardware-arrival-pack.zip"',
            'Cache-Control':'no-store', 'X-Content-Type-Options':'nosniff'})

    @app.get('/api/hardware/physical-plan')
    def physical_plan(request:Request):
        require_role(require_user(request),READ_ROLES)
        data=read_plan(root)
        return Response(json.dumps(data),media_type='application/json',headers={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'})

    @app.get('/api/hardware/physical-plan/sensor-map')
    def sensor_map(request:Request):
        require_role(require_user(request),READ_ROLES)
        _,sensor_map=read_preparation(root)
        return Response(sensor_map,media_type='image/svg+xml',headers={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'})
