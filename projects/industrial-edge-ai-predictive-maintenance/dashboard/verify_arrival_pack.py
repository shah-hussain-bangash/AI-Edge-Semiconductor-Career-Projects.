"""Offline, read-only consistency check for an unopened EDGEOPS arrival ZIP.

Use a reviewed repository copy of this script. An archive cannot authenticate
itself: matching hashes are not signatures or physical acceptance.
"""
import argparse
import csv
from datetime import date
import hashlib
import io
import json
from pathlib import Path
import re
import stat
import sys
import zipfile
import zlib

LEGACY_HARDWARE_FILES=(
    'README.md','firmware/platformio.ini','firmware/src/main.cpp','requirements-build.txt',
    'scripts/record_firmware_build.py','tests/test_firmware_build.py','docs/FIRMWARE_BUILD.md',
    'scripts/capture_serial.py','scripts/prepare_capture.py','scripts/requirements.txt',
    'tests/test_capture.py','tests/test_prepare_capture.py','tests/requirements.txt',
    'examples/offline-capture/synthetic.capture.csv','examples/offline-capture/synthetic.attachment.json',
    'docs/WIRING_AND_SAFETY.md','docs/OFFLINE_CAPTURE_HANDOFF.md',
    'docs/physical-connection-pack/README.md','docs/physical-connection-pack/connection-guide.html',
    'docs/physical-connection-pack/all-30-connection-matrix.csv',
    'docs/physical-connection-pack/sensor-only-reference.svg',
)
V2_HARDWARE_FILES=LEGACY_HARDWARE_FILES+('scripts/summarize_capture.py','tests/test_capture_summary.py',
                                      'validation/FIRST-HARDWARE-ACCEPTANCE.md')
HARDWARE_FILES=V2_HARDWARE_FILES+('firmware/include/checked_sensors.h','tests/test_checked_sensor_reads.py',
    'tests/fixtures/checked_sensor_reads.cpp','docs/CHECKED_SENSOR_READS.md')
CONTRACT_FILES=('telemetry-v2.schema.json','tests/test_telemetry_v2_contract.py',
                'examples/telemetry-v2.synthetic-valid.json','examples/telemetry-v2.synthetic-partial.json')
SOURCE_FILES=tuple('phase-01-hardware/'+name for name in HARDWARE_FILES)+tuple(
    'enterprise-architecture/contracts/'+name for name in CONTRACT_FILES)+('dashboard/verify_arrival_pack.py',)
EXPECTED_FILES=frozenset(SOURCE_FILES)|{'receipt-worksheet.csv','physical-plan.json','START-HERE.md','manifest.json'}
LEGACY_EXPECTED_FILES=EXPECTED_FILES-{'phase-01-hardware/'+name for name in HARDWARE_FILES if name not in LEGACY_HARDWARE_FILES}
V2_EXPECTED_FILES=EXPECTED_FILES-{'phase-01-hardware/'+name for name in HARDWARE_FILES if name not in V2_HARDWARE_FILES}
FORMAT_FILES={'edgeops-arrival-pack-v1':LEGACY_EXPECTED_FILES,'edgeops-arrival-pack-v2':V2_EXPECTED_FILES,
              'edgeops-arrival-pack-v3':EXPECTED_FILES}
MAX_ARCHIVE=8*1024*1024
MAX_FILE=512*1024
MAX_TOTAL=2*1024*1024
MAX_MANIFEST=64*1024
ROW_FIELDS={'selected_family':'GitHub part/family','quantity_basis':'Planned quantity','role':'Bench role',
            'connection':'Physical placement / connection decision','pending':'Exact-part confirmation before energizing'}
WORKSHEET_HEADERS=['Product ID','BOM ID','Selected family','Planned quantity','Bench role',
                   'Actual received model / board revision','Received date','Label / photo reference',
                   'Inspection notes / unresolved issue','Record status']


class PackError(ValueError):
    """The archive cannot be confirmed as the supported unchanged preparation pack."""


def require(condition,message):
    if not condition:raise PackError(message)


def unique_object(pairs):
    result={}
    for key,value in pairs:
        require(key not in result,'Duplicate JSON key')
        result[key]=value
    return result


def decode_json(raw):
    return json.loads(raw,object_pairs_hook=unique_object)


def verify_bytes(raw):
    """Read bounded members in memory. Never extract, import or run archive content."""
    try:
        require(len(raw)<=MAX_ARCHIVE,'Archive exceeds the supported size')
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            entries=archive.infolist();names=[entry.filename for entry in entries]
            require(len(names)==len(set(names)) and frozenset(names) in FORMAT_FILES.values(),'Missing, duplicate or unexpected archive entries')
            require(sum(entry.file_size for entry in entries)<=MAX_TOTAL+MAX_MANIFEST,'Expanded archive exceeds the supported size')
            files={}
            for entry in entries:
                mode=entry.external_attr>>16
                require(not entry.is_dir() and not stat.S_ISLNK(mode) and stat.S_IFMT(mode) in (0,stat.S_IFREG),'Unsupported archive entry type')
                require(not entry.flag_bits&1 and entry.compress_type in (zipfile.ZIP_STORED,zipfile.ZIP_DEFLATED),'Unsupported encrypted/compression format')
                limit=MAX_MANIFEST if entry.filename=='manifest.json' else MAX_FILE
                require(0<=entry.file_size<=limit,'Archive member exceeds the supported size')
                with archive.open(entry) as stream:content=stream.read(limit+1)
                require(len(content)==entry.file_size and len(content)<=limit,'Archive member length differs')
                files[entry.filename]=content
        manifest=decode_json(files['manifest.json'])
        require(isinstance(manifest,dict) and isinstance(manifest.get('format'),str)
                and manifest['format'] in FORMAT_FILES,'Unsupported manifest')
        expected_files=FORMAT_FILES[manifest['format']]
        require(set(files)==expected_files,'Archive inventory differs from its declared version')
        for key in ('order_verified','hardware_connected','calibration_verified','production_ready','substitution_allowed','additional_hardware_allowed'):
            require(manifest.get(key) is False,'Manifest claims unsupported physical authority')
        require(type(manifest.get('ordered_count_user_reported')) is int and manifest['ordered_count_user_reported']==30,'Unsupported hardware scope')
        require(type(manifest.get('received_count_verified')) is int and manifest['received_count_verified']==0,'Unsupported receipt claim')
        records=manifest.get('files')
        require(isinstance(records,dict) and set(records)==expected_files-{'manifest.json'},'Manifest membership differs')
        for name,record in records.items():
            require(isinstance(record,dict) and set(record)=={'bytes','sha256'},'Unsupported manifest file record')
            content=files[name]
            require(type(record['bytes']) is int and record['bytes']==len(content),'Manifest file length differs')
            require(isinstance(record['sha256'],str) and re.fullmatch('[0-9a-f]{64}',record['sha256']) is not None and hashlib.sha256(content).hexdigest()==record['sha256'],'Manifest file hash differs')
        plan=decode_json(files['physical-plan.json'])
        require(isinstance(plan,dict) and plan.get('scope')=='physical-preparation-only' and plan.get('version')=='fixed-30-physical-build-v1','Unsupported physical plan')
        for key in ('order_verified','hardware_connected','production_ready','substitution_allowed','additional_hardware_allowed'):
            require(plan.get(key) is False,'Plan claims unsupported physical authority')
        require(type(plan.get('ordered_count_user_reported')) is int and plan['ordered_count_user_reported']==30,'Unsupported plan scope')
        require(plan.get('pins')=={'SDA':21,'SCL':22,'temperature_data':4},'Unsupported reference pins')
        require(plan.get('source_hash_basis')=='UTF-8 CSV with LF newlines','Unsupported source hash basis')
        require(isinstance(plan.get('order_reported_on'),str) and date.fromisoformat(plan['order_reported_on']).isoformat()==plan['order_reported_on'],'Unsupported order declaration')
        require(isinstance(plan.get('plan_sha256'),str) and re.fullmatch('[0-9a-f]{64}',plan['plan_sha256']) is not None,'Unsupported plan reference')
        rows=plan.get('rows')
        require(isinstance(rows,list) and len(rows)==30 and all(isinstance(row,dict) for row in rows),'Unsupported plan rows')
        require([row.get('id') for row in rows]==[f'BOM-{i:02}' for i in range(1,31)],'Unsupported plan identities')
        require(all(isinstance(row.get(key),str) and row[key].strip() and len(row[key])<=2000 for row in rows for key in ROW_FIELDS),'Unsupported plan fields')
        matrix=files['phase-01-hardware/docs/physical-connection-pack/all-30-connection-matrix.csv']
        require(hashlib.sha256(matrix.replace(b'\r\n',b'\n')).hexdigest()==plan.get('source_csv_sha256'),'Matrix reference differs')
        reader=csv.DictReader(io.StringIO(matrix.decode('utf-8-sig')))
        require(reader.fieldnames==['ID',*ROW_FIELDS.values(),'Actual ordered SKU / board revision','Observed terminal labels','Received / inspected evidence'],'Unsupported matrix columns')
        matrix_rows=list(reader)
        require(len(matrix_rows)==30 and [row.get('ID') for row in matrix_rows]==[f'P{i:02}' for i in range(1,31)],'Unsupported matrix identities')
        require(all(None not in source and all(row[key]==source[column] for key,column in ROW_FIELDS.items()) for row,source in zip(rows,matrix_rows)),'Plan and matrix fields differ')
        require(hashlib.sha256(files['phase-01-hardware/docs/physical-connection-pack/sensor-only-reference.svg']).hexdigest()==plan.get('sensor_map_sha256'),'Map reference differs')
        worksheet=csv.DictReader(io.StringIO(files['receipt-worksheet.csv'].decode('utf-8-sig')))
        require(worksheet.fieldnames==WORKSHEET_HEADERS,'Unsupported worksheet columns')
        worksheet_rows=list(worksheet)
        require(len(worksheet_rows)==30,'Unsupported worksheet count')
        for index,(row,source) in enumerate(zip(worksheet_rows,rows),1):
            expected=[f'P{index:02}',source['id'],source['selected_family'],source['quantity_basis'],source['role'],'','','','','awaiting-delivery-unverified']
            require(None not in row and [row.get(key) for key in WORKSHEET_HEADERS]==expected,'Worksheet differs from the unopened arrival template')
        return {'scope':'offline-arrival-pack-file-consistency','file_consistency':'passed','pack_format':manifest['format'],
                'archive_sha256':hashlib.sha256(raw).hexdigest(),'files_checked':len(records),
                'hardware_categories':30,'received_count_verified':0,'signature_verified':False,
                'source_authenticity_verified':False,'physical_acceptance_verified':False,
                'hardware_connected':False,'equipment_authorized':False,'production_ready':False,
                'note':'Files match the supported pack structure and its internal references. This does not verify origin, signatures, source correctness, received parts or physical compatibility. Independently review the repository. Edit a separate worksheet copy after receipt.'}
    except PackError:raise
    except (OSError,ValueError,TypeError,KeyError,AttributeError,RecursionError,csv.Error,zipfile.BadZipFile,NotImplementedError,RuntimeError,EOFError,zlib.error):
        raise PackError('Unreadable or unsupported arrival archive') from None


def verify_file(path):
    with Path(path).open('rb') as stream:raw=stream.read(MAX_ARCHIVE+1)
    return verify_bytes(raw)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive',help='Unchanged EDGEOPS hardware arrival ZIP; no extraction is performed')
    args=parser.parse_args(argv)
    try:result=verify_file(args.archive)
    except (OSError,PackError):
        print(json.dumps({'file_consistency':'failed','production_ready':False,'physical_acceptance_verified':False,
                          'note':'Archive unavailable, damaged or outside the supported unopened-pack structure. Obtain a fresh download and compare reviewed repository sources; no files were extracted or changed.'}))
        return 2
    print(json.dumps(result,indent=2))
    return 0


if __name__=='__main__':sys.exit(main())
