"""mTLS MQTT QoS1 -> durable synthetic edge spool. No automatic central commitment."""
import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import signal
import ssl
import threading
import time

import httpx
from acquisition_registry import DeliveryInput
from edge_delivery import Spool
from service_delivery_runner import RunnerLock
from service_delivery_worker import validate_target


class IngressRefused(Exception):pass
class ReportDenied(Exception):pass


def exact_topic(site,asset,device):
    if any(not isinstance(value,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',value)
           for value in (site,asset,device)):
        raise ValueError('Use exact supported synthetic scope identifiers')
    return 'edgeops/synthetic/'+site+'/'+asset+'/'+device+'/telemetry'


def unique_object(pairs):
    result={}
    for key,value in pairs:
        if key in result:raise ValueError('Duplicate JSON member')
        result[key]=value
    return result


class DurableIngress:
    def __init__(self,spool,site,asset,device,revision):
        if type(revision) is not int or revision<1:raise ValueError('Exact binding revision required')
        self.spool=spool;self.scope=(site,asset,device);self.revision=revision
        self.topic=exact_topic(site,asset,device);self.lock=threading.Lock()
        self.stats={'received':0,'accepted_messages':0,'ack_requests':0,'refused':0,
                    'last_event_key':None,'last_error':'none'}

    def refuse(self,code):
        self.stats['refused']+=1;self.stats['last_error']=code
        raise IngressRefused(code)

    def accept(self,topic,payload,qos,retained,ack):
        with self.lock:
            self.stats['received']+=1
            if topic!=self.topic:self.refuse('out-of-scope')
            if qos!=1 or retained or not isinstance(payload,bytes) or not 1<=len(payload)<=8192:
                self.refuse('invalid-message')
            try:
                body=DeliveryInput.model_validate(json.loads(payload.decode('utf-8'),object_pairs_hook=unique_object))
            except (ValueError,UnicodeError):self.refuse('invalid-message')
            if ((body.observation.site_id,body.observation.asset_id,body.observation.device_id)!=self.scope
                    or body.binding_revision!=self.revision):self.refuse('out-of-scope')
            try:receipt=self.spool.enqueue(body.model_dump(mode='json'))
            except OverflowError:self.refuse('capacity-refused')
            except ValueError:self.refuse('identity-conflict')
            except Exception:self.refuse('spool-unavailable')
            self.stats['accepted_messages']+=1;self.stats['last_event_key']=receipt['event_key']
            try:
                if ack()!=0:raise RuntimeError('ack refused')
            except Exception:
                self.stats['last_error']='ack-unavailable';raise IngressRefused('ack-unavailable') from None
            self.stats['ack_requests']+=1;self.stats['last_error']='none'
            return receipt

    def snapshot(self):
        with self.lock:return dict(self.stats)


class ReportClient:
    def __init__(self,client,token,topic,client_id,interval):
        self.client=client;self.token=token;self.topic=topic;self.client_id=client_id
        self.interval=interval;self.run_id=secrets.token_hex(16);self.sequence=0;self.pending=None

    def send(self,state,stats):
        flush=self.pending is not None
        if self.pending is None:self.pending={'run_id':self.run_id,'sequence':self.sequence,'state':state,
            'topic':self.topic,'client_id':self.client_id,'interval_seconds':self.interval,**stats}
        try:
            response=self.client.post('/api/edge/mqtt-heartbeat',json=self.pending,
                                      headers={'Authorization':'Bearer '+self.token})
            if response.status_code in (401,403,409):raise ReportDenied('credential-or-bridge-lease-denied')
            if response.status_code!=200:return False
            data=response.json()
            if (not isinstance(data,dict) or data.get('scope')!='local-synthetic-mqtt-ingress'
                    or data.get('production_ready') is not False or data.get('hardware_connected') is not False
                    or data.get('broker_connection_verified_by_server') is not False
                    or data.get('run_id')!=self.pending['run_id'] or type(data.get('sequence')) is not int
                    or data['sequence']!=self.pending['sequence']):return False
            for key in ('report_received_at','report_lease_until'):
                if not isinstance(data.get(key),str) or datetime.fromisoformat(data[key]).utcoffset() is None:return False
        except (httpx.HTTPError,ValueError):return False
        self.sequence+=1;self.pending=None
        return self.send(state,stats) if flush else True


def run(spool_path,server,token,*,host,port,ca,cert,key,site,asset,device,revision,
        client_id=None,interval=5,max_seconds=None,stop=None,ready_signal=None):
    validate_target(server,token)
    topic=exact_topic(site,asset,device)
    if not isinstance(host,str) or not host or any(c.isspace() for c in host):raise ValueError('Explicit broker hostname required')
    if type(port) is not int or not 1<=port<=65535:raise ValueError('Invalid broker port')
    if type(interval) is not int or not 1<=interval<=300:raise ValueError('Invalid report interval')
    if max_seconds is not None and (type(max_seconds) is not int or not 1<=max_seconds<=3600):raise ValueError('Invalid finite duration')
    client_id=client_id or 'edge-'+hashlib.sha256(topic.encode()).hexdigest()[:16]
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,23}',client_id):raise ValueError('Stable MQTT client ID required')
    context=ssl.create_default_context(ssl.Purpose.SERVER_AUTH,cafile=str(ca))
    context.minimum_version=ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(str(cert),str(key))
    from paho.mqtt import client as mqtt
    mqttc=mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,client_id=client_id,clean_session=False,
                      protocol=mqtt.MQTTv311,manual_ack=True,reconnect_on_failure=False)
    mqttc.tls_set_context(context);mqttc.connect_timeout=10
    stop=stop or threading.Event();ready=threading.Event();closing=False;reason='stop-requested'
    error=['none'];ingress=DurableIngress(Spool(spool_path),site,asset,device,revision)
    def fail(code):error[0]=code;stop.set();ready.set()
    def on_connect(client,userdata,flags,result,properties):
        if getattr(result,'value',result)!=0:fail('broker-unavailable');return
        if client.subscribe(topic,qos=1)[0]!=mqtt.MQTT_ERR_SUCCESS:fail('broker-unavailable')
    def on_subscribe(client,userdata,mid,reasons,properties):
        if len(reasons)!=1 or getattr(reasons[0],'value',reasons[0])!=1:fail('broker-unavailable');return
        ready.set()
    def on_message(client,userdata,message):
        try:ingress.accept(message.topic,message.payload,message.qos,message.retain,
                           lambda:client.ack(message.mid,message.qos))
        except IngressRefused as refused:fail(str(refused))
        except Exception:fail('spool-unavailable')
    def on_disconnect(client,userdata,flags,result,properties):
        if not closing:fail('broker-unavailable')
    mqttc.on_connect=on_connect;mqttc.on_subscribe=on_subscribe
    mqttc.on_message=on_message;mqttc.on_disconnect=on_disconnect
    lock_target=Path(str(Path(spool_path).resolve())+'.mqtt-ingress')
    with RunnerLock(lock_target),httpx.Client(base_url=server.rstrip('/'),timeout=10,
            follow_redirects=False,trust_env=False) as client:
        reporter=ReportClient(client,token,topic,client_id,interval)
        try:
            if not reporter.send('connecting',ingress.snapshot()):
                reason='report-unavailable'
            else:
                mqttc.connect(host,port,keepalive=30);mqttc.loop_start()
                if not ready.wait(10) or error[0]!='none':reason='broker-unavailable'
                else:
                    if ready_signal is not None:ready_signal.set()
                    started=time.monotonic();next_report=0;failures=0
                    while not stop.is_set():
                        if max_seconds is not None and time.monotonic()-started>=max_seconds:
                            reason='duration-limit';break
                        if time.monotonic()>=next_report:
                            if reporter.send('connected',ingress.snapshot()):failures=0
                            else:failures+=1
                            if failures>=5:reason='report-unavailable';break
                            next_report=time.monotonic()+interval
                        stop.wait(.1)
                    if error[0]!='none':reason=error[0]
        except ReportDenied as denied:reason=str(denied)
        except Exception:reason='broker-unavailable'
        finally:
            closing=True
            try:mqttc.disconnect();mqttc.loop_stop()
            except Exception:pass
            stats=ingress.snapshot()
            if error[0]!='none':stats['last_error']=error[0]
            elif reason=='report-unavailable':stats['last_error']='report-unavailable'
            try:reporter.send('stopped',stats)
            except ReportDenied:pass
    return {**ingress.snapshot(),'stop_reason':reason,'production_ready':False,'hardware_connected':False}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('spool','server','host','ca','cert','key','site','asset','device'):
        parser.add_argument('--'+name,required=True)
    parser.add_argument('--port',type=int,default=8883)
    parser.add_argument('--revision',type=int,required=True)
    parser.add_argument('--client-id')
    parser.add_argument('--interval',type=int,default=5)
    mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--seconds',type=int)
    mode.add_argument('--forever',action='store_true')
    args=parser.parse_args();stop=threading.Event()
    for sig in (signal.SIGINT,signal.SIGTERM):signal.signal(sig,lambda *_:stop.set())
    try:
        result=run(args.spool,args.server,os.environ.get('EDGEOPS_SERVICE_TOKEN'),host=args.host,port=args.port,
            ca=args.ca,cert=args.cert,key=args.key,site=args.site,asset=args.asset,device=args.device,
            revision=args.revision,client_id=args.client_id,interval=args.interval,max_seconds=args.seconds,stop=stop)
    except Exception:parser.exit(1,'MQTT ingress unavailable; verify private TLS files, exact scope, credential and spool. No secrets logged.\n')
    print(json.dumps(result))
    if result['stop_reason'] not in ('duration-limit','stop-requested'):parser.exit(2)


if __name__=='__main__':main()
