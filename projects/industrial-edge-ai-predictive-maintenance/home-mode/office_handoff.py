"""Private review package for office processing; never a training approval."""
import csv
import hashlib
import io
import zipfile
from home_core import canonical,contract,utc_now
from home_recording import verify,package as raw_package


def package(folder):
    manifest,files=verify(folder)
    if manifest['settings']['mode']!='sensors' or manifest['source']!='serial-unverified':
        raise ValueError('Office sensor export refuses demo and ESP32-only test recordings')
    from home_core import strict_json
    stream=io.StringIO(newline='');writer=csv.DictWriter(stream,fieldnames=contract.FIELDS);writer.writeheader()
    count=0;groups=dict(adxl345_valid=0,ds18b20_valid=0,ina219_valid=0)
    for line in files['frames.jsonl'].splitlines():
        event=strict_json(line)
        if event['kind']!='accepted':continue
        wire=files['wire.bin'][event['offset']:event['offset']+event['bytes']].decode('utf-8').strip()
        record=contract.parse_record(wire);record['gateway_utc']=event['received_at'];writer.writerow(record);count+=1
        for key in groups:groups[key]+=int(record[key])
    if not count:raise ValueError('No structured sensor records to export; raw failures remain available')
    payloads={'source.capture.csv':stream.getvalue().encode('utf-8'),'source-capture.zip':raw_package(folder)}
    report=dict(format='edgeops-office-transfer-v1',created_at=utc_now(),session_id=manifest['session_id'],
        source='serial-unverified',csv_records=count,raw_frame_counts=manifest['frame_counts'],valid_group_counts=groups,
        excluded_records_preserved_in_raw_zip=True,units=dict(acceleration='m/s^2',temperature='C',bus_voltage='V',current_ma='mA'),
        conversion_note='V1 current stays in mA; the existing offline adapter converts to A once. No velocity or spectral inference.',
        hardware_verified=False,calibration_verified=False,production_ready=False,training_approved=False,
        physical_acceptance='pending',requires_review=True,firmware_source_commit=manifest['firmware_source_commit'],
        files={name:dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest()) for name,raw in payloads.items()})
    payloads['handoff.json']=(canonical(report)+'\n').encode('utf-8')
    output=io.BytesIO()
    with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED) as archive:
        for name,raw in payloads.items():archive.writestr(name,raw)
    return output.getvalue()
