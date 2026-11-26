"""Finite native broker -> mTLS bridge -> spool -> real HTTP rehearsal helper."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import ssl
import sys
import tempfile
import threading
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from paho.mqtt import client as mqtt
from edge_delivery import Spool
from mqtt_ingress import run,exact_topic
from service_delivery_worker import run_once
from mqtt_test_support import LocalBroker


def rehearse(server):
    token=os.environ['EDGEOPS_SERVICE_TOKEN'];site='mqtt-site';asset='MTR-001';device='mqtt-browser-device'
    topic=exact_topic(site,asset,device);stop=threading.Event();ready=threading.Event()
    with tempfile.TemporaryDirectory(prefix='edgeops-mqtt-http-') as folder:
        root=Path(folder);broker=LocalBroker(root/'broker',topic);spool=root/'edge.sqlite3'
        publisher=None
        try:
            with ThreadPoolExecutor(max_workers=1) as pool:
                job=pool.submit(run,spool,server,token,host='localhost',port=broker.port,
                    ca=broker.pki/'ca.crt',cert=broker.pki/'fixture-bridge.crt',key=broker.pki/'fixture-bridge.key',
                    site=site,asset=asset,device=device,revision=1,interval=1,max_seconds=15,
                    stop=stop,ready_signal=ready)
                try:
                    if not ready.wait(8):raise RuntimeError('MQTT bridge did not become ready')
                    publisher=mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
                    context=ssl.create_default_context(cafile=str(broker.pki/'ca.crt'))
                    context.load_cert_chain(str(broker.pki/'fixture-publisher.crt'),str(broker.pki/'fixture-publisher.key'))
                    publisher.tls_set_context(context);publisher.connect('localhost',broker.port);publisher.loop_start()
                    observation={'schema_version':'2.0','event_type':'telemetry.sample','source_type':'synthetic',
                        'site_id':site,'asset_id':asset,'device_id':device,'boot_id':'mqtt-http-rehearsal','sequence':0,
                        'timestamp':{'device_uptime_ms':0,'device_time_utc':datetime.now(timezone.utc).isoformat(),
                            'gateway_received_utc':datetime.now(timezone.utc).isoformat(),'clock_quality':'device_clock_verified'},
                        'measurements':{'acceleration_x_mps2':0,'acceleration_y_mps2':0,'acceleration_z_mps2':0,
                            'motor_case_temperature_c':None,'bus_voltage_v':None,'current_a':None},
                        'quality':{'adxl345':'valid','ds18b20':'not_connected','ina219':'not_connected',
                            'calibration':'unknown','session_quality':'verified'}}
                    for sequence in (0,0,1):
                        observation['sequence']=sequence
                        publisher.publish(topic,json.dumps({'binding_revision':1,'observation':observation}),qos=1).wait_for_publish(timeout=3)
                    for _ in range(80):
                        if Spool(spool).status()['usage']['records']==2:break
                        time.sleep(.05)
                    if Spool(spool).status()['usage']['records']!=2:raise RuntimeError('Durable MQTT edge acceptance missing')
                    time.sleep(.2);stop.set();summary=job.result(timeout=10)
                    if summary['accepted_messages']!=3 or summary['ack_requests']!=3:raise RuntimeError('MQTT acknowledgement boundary mismatch')
                    run_once(spool,server,token);run_once(spool,server,token)
                    if Spool(spool).status()['counts']['delivered']!=2:raise RuntimeError('Central receipt reconciliation failed')
                    return {'mqtt_messages':3,'unique_edge_records':2,'central_delivered':2,
                        'bridge_stop_reason':summary['stop_reason'],'production_ready':False,'hardware_connected':False}
                finally:
                    stop.set()
                    if publisher:publisher.disconnect();publisher.loop_stop()
        except Exception as error:
            # Broker logs contain only disposable client IDs/topics and TLS diagnostics,
            # never the HTTP bearer token or MQTT payload bodies.
            print('MQTT fixture failure category: '+type(error).__name__,file=sys.stderr)
            print((broker.root/'broker.log').read_text(encoding='utf-8')[-1500:],file=sys.stderr)
            raise
        finally:broker.close()


if __name__=='__main__':
    try:print(json.dumps(rehearse(sys.argv[1])))
    except Exception as error:
        safe_reasons={'MQTT bridge did not become ready','Durable MQTT edge acceptance missing',
            'MQTT acknowledgement boundary mismatch','Central receipt reconciliation failed'}
        if str(error) in safe_reasons or str(error).startswith('Disposable broker failed:'):
            print(str(error),file=sys.stderr)
        print('Disposable MQTT rehearsal failed; no credentials or payloads logged.',file=sys.stderr)
        raise SystemExit(1)
