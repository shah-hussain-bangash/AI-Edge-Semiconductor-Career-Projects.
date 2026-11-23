#!/usr/bin/env python3
"""Offline V1 capture-CSV to candidate-V2 evidence adapter. No serial/network I/O."""
import argparse
import csv
from datetime import datetime,timezone
import hashlib
import io
import json
import math
from pathlib import Path
import re
import shutil
import tempfile

FIELDS=('gateway_utc','device_id','seq','uptime_ms','ax_mps2','ay_mps2','az_mps2','temp_c','bus_v','current_ma','adxl345_valid','ds18b20_valid','ina219_valid','valid')
MAX_INPUT=16*1024*1024
MAX_ROWS=10000
ADAPTER='edgeops-v1-csv-to-v2-evidence-v1'
ATTACHMENT_FIELDS={'profile','site_id','asset_id','device_id','v1_device_id','serial_port','board_reference','configuration_ref','source_type','physical_verification','calibration','transport'}
EVIDENCE_LIMITS={'source.capture.csv':MAX_INPUT,'attachment.json':8192,'observations.jsonl':32*1024*1024,'quarantine.jsonl':32*1024*1024}
MANIFEST_FIELDS={'format','created_at','source_type','source_classification','input_rows','accepted_rows','quarantined_rows','accepted_sequence_gaps','requires_review','boot_identity','physical_source_verified','calibration_verified','hardware_connected','ready_for_ingestion','production_ready','files'}


def json_bytes(data):return (json.dumps(data,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode()
def sha(data):return hashlib.sha256(data).hexdigest()


def evidence_json(raw):
    """Strict bounded evidence JSON; duplicate keys and nonfinite numbers are invalid."""
    def pairs(items):
        result={}
        for key,value in items:
            if key in result:raise ValueError('Duplicate evidence JSON field')
            result[key]=value
        return result
    def constant(_):raise ValueError('Nonfinite evidence JSON number')
    def floating(text):
        value=float(text)
        if not math.isfinite(value):raise ValueError('Nonfinite evidence JSON number')
        return value
    try:data=json.loads(raw.decode('utf-8'),object_pairs_hook=pairs,parse_constant=constant,parse_float=floating)
    except RecursionError as error:raise ValueError('Evidence JSON nesting exceeds limit') from error
    pending=[(data,0)];count=0
    while pending:
        value,depth=pending.pop();count+=1
        if depth>8 or count>512:raise ValueError('Evidence JSON structure exceeds limit')
        if isinstance(value,dict):pending.extend((child,depth+1) for child in value.values())
        elif isinstance(value,list):pending.extend((child,depth+1) for child in value)
    return data


def evidence_lines(raw,line_limit):
    records=[];stream=io.BytesIO(raw)
    while line:=stream.readline(line_limit+1):
        if len(line)>line_limit or len(records)>=MAX_ROWS:raise ValueError('Evidence record limit exceeded')
        records.append(evidence_json(line))
    return records


def same_json(actual,expected):
    """JSON numeric equivalence never treats booleans as numeric values."""
    if type(expected) in (int,float):return type(actual) in (int,float) and actual==expected
    if type(actual) is not type(expected):return False
    if isinstance(expected,dict):return actual.keys()==expected.keys() and all(same_json(actual[key],value) for key,value in expected.items())
    if isinstance(expected,list):return len(actual)==len(expected) and all(same_json(a,b) for a,b in zip(actual,expected))
    return actual==expected


def read_file(path,limit):
    path=Path(path)
    if path.is_symlink() or getattr(path,'is_junction',lambda:False)() or not path.is_file():raise ValueError('Input must be an ordinary file')
    if path.stat().st_size>limit:raise ValueError('Input exceeds local evidence size limit')
    with path.open('rb') as stream:data=stream.read(limit+1)
    if len(data)>limit:raise ValueError('Input exceeds local evidence size limit')
    return data


def attachment(data):
    if not isinstance(data,dict) or set(data)!=ATTACHMENT_FIELDS:raise ValueError('Supply the exact serial attachment field set')
    for key,value in data.items():
        if not isinstance(value,str) or not value.strip() or len(value)>200:raise ValueError('Attachment values must be bounded nonempty strings')
    for key in ('site_id','asset_id','device_id','v1_device_id'):
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',data[key]):raise ValueError('Invalid attachment identifier')
    if (data['profile']!='edgeops.serial-attachment.v1' or data['transport']!='usb-serial'
            or data['source_type'] not in ('synthetic','measured','replayed')
            or data['physical_verification']!='unverified' or data['calibration']!='not_verified'):
        raise ValueError('Unsupported attachment provenance or verification claim')
    return data


def utc(text):
    if not isinstance(text,str) or len(text)>40 or 'T' not in text:raise ValueError('invalid-receipt-time')
    try:value=datetime.fromisoformat(text)
    except ValueError:raise ValueError('invalid-receipt-time')
    if value.tzinfo is None or value.utcoffset() is None:raise ValueError('receipt-time-without-timezone')
    return value.astimezone(timezone.utc)


def integer(text):
    if not isinstance(text,str) or not re.fullmatch(r'0|[1-9][0-9]{0,9}',text):raise ValueError('invalid-counter')
    value=int(text)
    if value>4294967295:raise ValueError('counter-out-of-range')
    return value


def number(text):
    if not isinstance(text,str) or len(text)>64:raise ValueError('invalid-number')
    if not re.fullmatch(r'-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?',text):raise ValueError('invalid-number')
    try:value=float(text)
    except ValueError:raise ValueError('invalid-number')
    if not math.isfinite(value):raise ValueError('nonfinite-number')
    return value


def flag(text):
    if text not in ('True','False'):raise ValueError('invalid-boolean')
    return text=='True'


def convert(row,mapping):
    if set(row)!=set(FIELDS) or any(value is None for value in row.values()):raise ValueError('invalid-csv-row')
    if row['device_id']!=mapping['v1_device_id']:raise ValueError('attachment-device-mismatch')
    seq=integer(row['seq']);uptime=integer(row['uptime_ms']);received=utc(row['gateway_utc'])
    flags={key:flag(row[key]) for key in ('adxl345_valid','ds18b20_valid','ina219_valid','valid')}
    if flags['valid']!=(flags['adxl345_valid'] and flags['ds18b20_valid'] and flags['ina219_valid']):raise ValueError('inconsistent-validity')
    values={key:number(row[key]) for key in ('ax_mps2','ay_mps2','az_mps2','temp_c','bus_v','current_ma')}
    a,t,i=flags['adxl345_valid'],flags['ds18b20_valid'],flags['ina219_valid']
    result={'schema_version':'2.0','event_type':'telemetry.sample','source_type':mapping['source_type'],
            'site_id':mapping['site_id'],'asset_id':mapping['asset_id'],'device_id':mapping['device_id'],
            'boot_id':None,'sequence':seq,'timestamp':{'device_uptime_ms':uptime,'device_time_utc':None,
                'gateway_received_utc':received.isoformat(),'clock_quality':'gateway_receipt_only'},
            'measurements':{'acceleration_x_mps2':values['ax_mps2'] if a else None,
                'acceleration_y_mps2':values['ay_mps2'] if a else None,'acceleration_z_mps2':values['az_mps2'] if a else None,
                'motor_case_temperature_c':values['temp_c'] if t else None,'bus_voltage_v':values['bus_v'] if i else None,
                'current_a':values['current_ma']/1000 if i else None},
            'quality':{'adxl345':'valid' if a else 'invalid','ds18b20':'valid' if t else 'invalid',
                'ina219':'valid' if i else 'invalid','calibration':'not_verified','session_quality':'unavailable'}}
    return result,(seq,uptime,received)


def normalize(raw,mapping):
    source=csv.DictReader(io.StringIO(raw.decode('utf-8-sig'),newline=''),strict=True)
    if source.fieldnames is None or len(source.fieldnames)!=len(FIELDS) or set(source.fieldnames)!=set(FIELDS):raise ValueError('Unsupported or duplicate CSV columns')
    accepted=[];quarantine=[];previous=None;ambiguous=False;gaps=0;count=0
    for row in source:
        index=source.line_num
        count+=1
        if count>MAX_ROWS:raise ValueError('Capture exceeds local row limit')
        if ambiguous:quarantine.append({'csv_line':index,'reason':'unresolved-session-or-clock-discontinuity'});continue
        try:
            record,state=convert(row,mapping)
            if previous and (state[0]<=previous[0] or state[1]<previous[1] or state[2]<previous[2]):
                ambiguous=True;raise ValueError('unresolved-session-or-clock-discontinuity')
            if previous:gaps+=max(0,state[0]-previous[0]-1)
            previous=state;accepted.append(record)
        except ValueError as error:quarantine.append({'csv_line':index,'reason':str(error)})
    return accepted,quarantine,gaps,count


def prepare(input_path,attachment_path,output):
    raw=read_file(input_path,MAX_INPUT);mapping=attachment(evidence_json(read_file(attachment_path,8192)))
    destination=Path(output).absolute()
    if destination.exists() or destination.is_symlink():raise ValueError('Output must be a new directory; existing evidence is never overwritten')
    destination.parent.mkdir(parents=True,exist_ok=True)
    stage=Path(tempfile.mkdtemp(prefix='.edgeops-capture-pending-',dir=destination.parent))
    try:
        accepted,quarantine,gaps,count=normalize(raw,mapping)
        files={'source.capture.csv':raw,'attachment.json':json_bytes(mapping),
               'observations.jsonl':b''.join(json_bytes(row) for row in accepted),
               'quarantine.jsonl':b''.join(json_bytes(row) for row in quarantine)}
        for name,data in files.items():(stage/name).write_bytes(data)
        manifest={'format':ADAPTER,'created_at':datetime.now(timezone.utc).isoformat(),
                  'source_type':mapping['source_type'],'source_classification':'operator-declared; not physical authentication',
                  'input_rows':count,'accepted_rows':len(accepted),'quarantined_rows':len(quarantine),
                  'accepted_sequence_gaps':gaps,'requires_review':bool(quarantine) or not accepted,
                  'boot_identity':'unavailable','physical_source_verified':False,'calibration_verified':False,
                  'hardware_connected':False,'ready_for_ingestion':False,'production_ready':False,
                  'files':{name:{'bytes':len(data),'sha256':sha(data)} for name,data in files.items()}}
        (stage/'manifest.json').write_bytes(json_bytes(manifest))
        verify(stage)
        if destination.exists() or destination.is_symlink():raise ValueError('Output destination appeared; refusing overwrite')
        stage.rename(destination)
        return manifest
    finally:
        if stage.exists():
            assert stage.resolve().parent==destination.parent.resolve() and stage.name.startswith('.edgeops-capture-pending-')
            shutil.rmtree(stage)


def verify(directory,*,include_report=False):
    root=Path(directory)
    if root.is_symlink() or getattr(root,'is_junction',lambda:False)():raise ValueError('Linked evidence folders are not supported')
    manifest_bytes=read_file(root/'manifest.json',65536)
    manifest=evidence_json(manifest_bytes)
    if not isinstance(manifest,dict) or set(manifest)!=MANIFEST_FIELDS:raise ValueError('Unsupported evidence manifest')
    if manifest.get('boot_identity')!='unavailable' or manifest.get('source_classification')!='operator-declared; not physical authentication':raise ValueError('Unsupported provenance claim')
    created=manifest['created_at']
    if not isinstance(created,str) or not re.fullmatch(r'\d{4}-\d\d-\d\dT(?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d(?:\.\d{1,6})?(?:Z|\+00:00)',created):raise ValueError('Unsupported evidence creation time')
    utc(created)
    expected=set(EVIDENCE_LIMITS)
    if manifest['format']!=ADAPTER or not isinstance(manifest['files'],dict) or set(manifest['files'])!=expected:raise ValueError('Unsupported evidence manifest')
    if manifest['source_type'] not in ('synthetic','measured','replayed'):raise ValueError('Unsupported source declaration')
    for key in ('input_rows','accepted_rows','quarantined_rows'):
        if type(manifest[key]) is not int or not 0<=manifest[key]<=MAX_ROWS:raise ValueError('Unsupported evidence count')
    if type(manifest['accepted_sequence_gaps']) is not int or not 0<=manifest['accepted_sequence_gaps']<=4294967295:raise ValueError('Unsupported gap count')
    if type(manifest['requires_review']) is not bool or manifest['accepted_rows']+manifest['quarantined_rows']!=manifest['input_rows']:raise ValueError('Unsupported evidence review/count declaration')
    for key in ('physical_source_verified','calibration_verified','hardware_connected','ready_for_ingestion','production_ready'):
        if manifest[key] is not False:raise ValueError('Unsupported verification claim')
    if set(path.name for path in root.iterdir())!=expected|{'manifest.json'}:raise ValueError('Unexpected or missing evidence files')
    snapshots={}
    for name,limit in EVIDENCE_LIMITS.items():
        reference=manifest['files'][name]
        if (not isinstance(reference,dict) or set(reference)!={'bytes','sha256'} or type(reference['bytes']) is not int
                or not 0<=reference['bytes']<=limit or not isinstance(reference['sha256'],str)
                or not re.fullmatch(r'[0-9a-f]{64}',reference['sha256'])):raise ValueError('Unsupported evidence file reference')
        data=read_file(root/name,limit)
        if reference!={'bytes':len(data),'sha256':sha(data)}:raise ValueError('Evidence file integrity mismatch')
        snapshots[name]=data
    mapping=attachment(evidence_json(snapshots['attachment.json']))
    records=evidence_lines(snapshots['observations.jsonl'],16384)
    rejected=evidence_lines(snapshots['quarantine.jsonl'],256)
    if (len(records)!=manifest['accepted_rows'] or len(rejected)!=manifest['quarantined_rows']
            or len(records)+len(rejected)!=manifest['input_rows'] or manifest['input_rows']>MAX_ROWS
            or manifest['source_type']!=mapping['source_type']):raise ValueError('Evidence reconciliation failed')
    normalized,expected_rejected,gaps,count=normalize(snapshots['source.capture.csv'],mapping)
    if not same_json(records,normalized) or not same_json(rejected,expected_rejected) or manifest['accepted_sequence_gaps']!=gaps or manifest['input_rows']!=count or manifest['requires_review']!=(bool(rejected) or not records):
        raise ValueError('Prepared observations do not match source transformation')
    if include_report:
        return {'format':'edgeops-offline-capture-verification-report-v1','verified_at':datetime.now(timezone.utc).isoformat(),
                'manifest_bytes':len(manifest_bytes),'manifest_sha256':sha(manifest_bytes),'manifest':manifest,
                'package_consistency_checked':True,'source_transformation_recomputed':True,
                'report_authenticated':False,'source_authenticated':False,'atomic_folder_snapshot':False,
                'ongoing_freshness_verified':False,'physical_source_verified':False,'calibration_verified':False,
                'hardware_connected':False,'ready_for_ingestion':False,'equipment_authorized':False,'production_ready':False}
    return manifest


def write_verification_report(directory,output):
    """Write a new unsigned report outside the evidence folder; never overwrite."""
    root=Path(directory).resolve();target=Path(output).absolute()
    if target.resolve().is_relative_to(root):raise ValueError('Report must be outside the evidence folder')
    if target.exists() or target.is_symlink():raise ValueError('Report must use a new filename')
    report=verify(directory,include_report=True)
    # Exclusive creation also refuses a target that appears while verification runs.
    with target.open('xb') as stream:stream.write(json_bytes(report))
    return report['manifest']


def main():
    parser=argparse.ArgumentParser(description=__doc__);commands=parser.add_subparsers(dest='command',required=True)
    create=commands.add_parser('prepare');create.add_argument('--input',required=True);create.add_argument('--attachment',required=True);create.add_argument('--output',required=True)
    check=commands.add_parser('verify');check.add_argument('directory');check.add_argument('--report',help='New JSON report filename outside the evidence folder; never overwritten')
    args=parser.parse_args()
    try:
        if args.command=='prepare':manifest=prepare(args.input,args.attachment,args.output)
        elif args.report:manifest=write_verification_report(args.directory,args.report)
        else:manifest=verify(args.directory)
    except (ValueError,OSError,KeyError,TypeError,csv.Error):parser.exit(1,'Evidence preparation failed; check the capture, attachment and output paths. Existing files were not overwritten.\n')
    print(json.dumps({key:manifest[key] for key in ('accepted_rows','quarantined_rows','requires_review','physical_source_verified','ready_for_ingestion')},sort_keys=True))
    return 2 if args.command=='prepare' and manifest['requires_review'] else 0


if __name__=='__main__':raise SystemExit(main())
