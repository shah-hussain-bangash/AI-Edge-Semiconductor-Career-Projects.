"""Durable-before-ACK checks and real local Mosquitto mTLS integration."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import ssl
import threading
import time
import unittest
from unittest.mock import patch

import httpx
from edge_delivery import Spool
import mqtt_ingress
import test_service_credentials as fixture
try:
    from paho.mqtt import client as mqtt
    from mqtt_test_support import available_broker,LocalBroker
except ImportError:
    mqtt=None
    def available_broker():return None
    LocalBroker=None


class MqttIngressTests(unittest.TestCase):
    login=fixture.ServiceCredentialTests.login
    post=fixture.ServiceCredentialTests.post
    issue=fixture.ServiceCredentialTests.issue
    revoke=fixture.ServiceCredentialTests.revoke
    envelope=fixture.ServiceCredentialTests.envelope

    def setUp(self):
        fixture.ServiceCredentialTests.setUp(self)
        self.issued=self.issue().json();self.token=self.issued['token']
        self.path=Path(self.temp.name)/'mqtt-spool.sqlite3'
        self.spool=Spool(self.path)
        self.ingress=mqtt_ingress.DurableIngress(self.spool,'test-site','test-asset','test-device',1)

    def test_ack_happens_after_durable_commit_and_duplicate_reuses_identity(self):
        acknowledgements=[]
        def ack():
            self.assertEqual(Spool(self.path).status()['counts']['pending'],1)
            acknowledgements.append(True);return 0
        payload=json.dumps(self.envelope()).encode()
        first=self.ingress.accept(self.ingress.topic,payload,1,False,ack)
        second=self.ingress.accept(self.ingress.topic,payload,1,False,ack)
        self.assertTrue(first['created']);self.assertFalse(second['created'])
        self.assertEqual(first['event_key'],second['event_key']);self.assertEqual(len(acknowledgements),2)

    def test_invalid_scope_source_retained_qos_and_duplicate_json_are_never_acked(self):
        valid=json.dumps(self.envelope()).encode();measured=self.envelope();measured['observation']['source_type']='measured'
        foreign=self.envelope();foreign['observation']['site_id']='other'
        cases=[('other-topic',valid,1,False),(self.ingress.topic,valid,0,False),
            (self.ingress.topic,valid,1,True),(self.ingress.topic,b'{}',1,False),
            (self.ingress.topic,json.dumps(measured).encode(),1,False),
            (self.ingress.topic,json.dumps(foreign).encode(),1,False),
            (self.ingress.topic,b'{"binding_revision":1,"binding_revision":2}',1,False),
            (self.ingress.topic,b'x'*8193,1,False)]
        called=[]
        for args in cases:
            with self.assertRaises(mqtt_ingress.IngressRefused):self.ingress.accept(*args,lambda:called.append(True))
        self.assertEqual(called,[]);self.assertEqual(self.spool.status()['usage']['records'],0)

    def test_capacity_disk_failure_conflict_and_ack_loss_preserve_boundaries(self):
        payload=json.dumps(self.envelope()).encode();called=[]
        for exception in (OverflowError(),OSError()):
            with patch.object(self.spool,'enqueue',side_effect=exception):
                with self.assertRaises(mqtt_ingress.IngressRefused):
                    self.ingress.accept(self.ingress.topic,payload,1,False,lambda:called.append(True))
        self.assertEqual(called,[])
        with self.assertRaises(mqtt_ingress.IngressRefused):
            self.ingress.accept(self.ingress.topic,payload,1,False,lambda:1)
        self.assertEqual(self.spool.status()['usage']['records'],1)
        replay=self.ingress.accept(self.ingress.topic,payload,1,False,lambda:0)
        self.assertFalse(replay['created'])
        changed=self.envelope();changed['observation']['measurements']['acceleration_x_mps2']=1
        with self.assertRaises(mqtt_ingress.IngressRefused):
            self.ingress.accept(self.ingress.topic,json.dumps(changed).encode(),1,False,lambda:called.append(True))
        self.assertEqual(called,[])

    def report_body(self,**changes):
        return {'run_id':'a'*32,'sequence':0,'state':'connecting','topic':self.ingress.topic,
            'client_id':'fixture-bridge','interval_seconds':1,'received':0,'accepted_messages':0,
            'ack_requests':0,'refused':0,'last_event_key':None,'last_error':'none',**changes}

    def heartbeat(self,body):
        return self.edge.post('/api/edge/mqtt-heartbeat',json=body,headers={'Authorization':'Bearer '+self.token})

    def test_report_scope_retries_leases_counter_integrity_and_revocation(self):
        self.assertEqual(self.heartbeat(self.report_body(topic='foreign')).status_code,403)
        self.assertEqual(self.heartbeat(self.report_body(ack_requests=1)).status_code,422)
        first=self.heartbeat(self.report_body());self.assertEqual(first.status_code,200)
        self.assertEqual(first.json(),self.heartbeat(self.report_body()).json())
        self.assertEqual(self.heartbeat(self.report_body(run_id='b'*32)).status_code,409)
        self.assertEqual(self.heartbeat(self.report_body(sequence=1,state='connected',received=1,accepted_messages=1)).status_code,200)
        self.assertEqual(self.heartbeat(self.report_body(sequence=2,state='connected')).status_code,409)
        report=self.http.get('/api/mqtt-ingress').json();self.assertEqual(report['reports'][0]['observation'],'recent-report')
        self.assertNotIn(self.token,json.dumps(report));self.assertFalse(report['broker_connection_verified_by_server'])
        self.revoke(self.issued['credential']);self.assertEqual(self.heartbeat(self.report_body(sequence=2)).status_code,401)
        self.assertEqual(self.http.get('/api/mqtt-ingress').json()['reports'][0]['observation'],'credential-inactive')
        for role in ('operator','auditor'):
            self.login(role);self.assertEqual(self.http.get('/api/mqtt-ingress').status_code,200)
        self.http.cookies.clear();self.assertEqual(self.http.get('/api/mqtt-ingress').status_code,401)

    @unittest.skipUnless(available_broker(),'Set EDGEOPS_MOSQUITTO_EXE for real broker tests')
    def test_real_mtls_broker_to_durable_spool_and_central_worker(self):
        from service_delivery_worker import run_once
        broker=LocalBroker(Path(self.temp.name)/'broker',self.ingress.topic);self.addCleanup(broker.close)
        # Route real MQTT to a disposable HTTP application through an in-process HTTP transport.
        # A separate browser rehearsal covers the same path over actual loopback HTTP.
        original=httpx.Client
        def send(request):return self.edge.post(request.url.path,content=request.content,headers={
            'Authorization':request.headers['authorization'],'content-type':'application/json'})
        factory=lambda **kwargs:original(**kwargs,transport=httpx.MockTransport(send))
        stop=threading.Event()
        with patch.object(mqtt_ingress.httpx,'Client',side_effect=factory),ThreadPoolExecutor(max_workers=1) as pool:
            job=pool.submit(mqtt_ingress.run,self.path,'http://127.0.0.1:8877',self.token,
                host='localhost',port=broker.port,ca=broker.pki/'ca.crt',cert=broker.pki/'fixture-bridge.crt',
                key=broker.pki/'fixture-bridge.key',site='test-site',asset='test-asset',device='test-device',
                revision=1,interval=1,max_seconds=10,stop=stop)
            for _ in range(80):
                data=self.http.get('/api/mqtt-ingress').json()['reports']
                if data and data[0]['state']=='connected':break
                time.sleep(.05)
            self.assertTrue(data and data[0]['state']=='connected',
                str(job.result(timeout=1) if job.done() else data)+' | '+(broker.root/'broker.log').read_text()[-1300:])
            publisher=mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
            context=ssl.create_default_context(cafile=str(broker.pki/'ca.crt'))
            context.load_cert_chain(str(broker.pki/'fixture-publisher.crt'),str(broker.pki/'fixture-publisher.key'))
            publisher.tls_set_context(context);publisher.connect('localhost',broker.port);publisher.loop_start()
            try:
                for _ in range(2):publisher.publish(self.ingress.topic,json.dumps(self.envelope()),qos=1).wait_for_publish(timeout=3)
                for _ in range(80):
                    if self.spool.status()['usage']['records']==1:break
                    time.sleep(.05)
                self.assertEqual(self.spool.status()['usage']['records'],1)
                time.sleep(.2);stop.set();result=job.result(timeout=10)
                self.assertEqual(result['accepted_messages'],2);self.assertEqual(result['ack_requests'],2)
                self.assertEqual(self.spool.status()['counts']['pending'],1)
                run_once(self.path,'http://127.0.0.1:8877',self.token)
                self.assertEqual(self.spool.status()['counts']['delivered'],1)
            finally:publisher.disconnect();publisher.loop_stop();stop.set()

    @unittest.skipUnless(available_broker(),'Set EDGEOPS_MOSQUITTO_EXE for real broker tests')
    def test_real_broker_refuses_missing_client_certificate_and_wrong_hostname(self):
        broker=LocalBroker(Path(self.temp.name)/'tls-broker',self.ingress.topic);self.addCleanup(broker.close)
        context=ssl.create_default_context(cafile=str(broker.pki/'ca.crt'))
        context.maximum_version=ssl.TLSVersion.TLSv1_2
        import socket
        with self.assertRaises(ssl.SSLError):
            with socket.create_connection(('127.0.0.1',broker.port),timeout=2) as raw:
                context.wrap_socket(raw,server_hostname='localhost')
        context.load_cert_chain(str(broker.pki/'fixture-bridge.crt'),str(broker.pki/'fixture-bridge.key'))
        with self.assertRaises(ssl.SSLCertVerificationError) as mismatch:
            with socket.create_connection(('127.0.0.1',broker.port),timeout=2) as raw:
                context.wrap_socket(raw,server_hostname='wrong-host.invalid')
        self.assertIn('hostname',mismatch.exception.verify_message.lower())

    @unittest.skipUnless(available_broker(),'Set EDGEOPS_MOSQUITTO_EXE for real broker tests')
    def test_real_broker_rejects_publish_using_read_only_bridge_certificate(self):
        broker=LocalBroker(Path(self.temp.name)/'acl-broker',self.ingress.topic);self.addCleanup(broker.close)
        connected=threading.Event();outcome=threading.Event();codes=[]
        client=mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,protocol=mqtt.MQTTv5)
        context=ssl.create_default_context(cafile=str(broker.pki/'ca.crt'))
        context.load_cert_chain(str(broker.pki/'fixture-bridge.crt'),str(broker.pki/'fixture-bridge.key'))
        client.tls_set_context(context)
        client.on_connect=lambda c,u,f,r,p:connected.set() if r.value==0 else None
        client.on_publish=lambda c,u,m,r,p:(codes.append(r.value),outcome.set())
        client.connect('localhost',broker.port);client.loop_start()
        try:
            self.assertTrue(connected.wait(3))
            client.publish(self.ingress.topic,json.dumps(self.envelope()),qos=1)
            self.assertTrue(outcome.wait(3));self.assertGreaterEqual(codes[0],128)
        finally:client.disconnect();client.loop_stop()

    @unittest.skipUnless(available_broker(),'Set EDGEOPS_MOSQUITTO_EXE for real broker tests')
    def test_real_broker_redelivers_unacked_message_after_bridge_restart(self):
        broker=LocalBroker(Path(self.temp.name)/'replay-broker',self.ingress.topic);self.addCleanup(broker.close)
        original=httpx.Client
        def send(request):return self.edge.post(request.url.path,content=request.content,headers={
            'Authorization':request.headers['authorization'],'content-type':'application/json'})
        factory=lambda **kwargs:original(**kwargs,transport=httpx.MockTransport(send))
        def launch(pool,stop,ready):return pool.submit(mqtt_ingress.run,self.path,'http://127.0.0.1:8877',self.token,
            host='localhost',port=broker.port,ca=broker.pki/'ca.crt',cert=broker.pki/'fixture-bridge.crt',
            key=broker.pki/'fixture-bridge.key',site='test-site',asset='test-asset',device='test-device',
            revision=1,interval=1,max_seconds=10,stop=stop,ready_signal=ready)
        publisher=mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        context=ssl.create_default_context(cafile=str(broker.pki/'ca.crt'))
        context.load_cert_chain(str(broker.pki/'fixture-publisher.crt'),str(broker.pki/'fixture-publisher.key'))
        publisher.tls_set_context(context);publisher.connect('localhost',broker.port);publisher.loop_start()
        stop=threading.Event();ready=threading.Event()
        try:
            with patch.object(mqtt_ingress.httpx,'Client',side_effect=factory),ThreadPoolExecutor(max_workers=1) as pool:
                with patch.object(mqtt.Client,'ack',return_value=mqtt.MQTT_ERR_NO_CONN):
                    first=launch(pool,stop,ready);self.assertTrue(ready.wait(4))
                    publisher.publish(self.ingress.topic,json.dumps(self.envelope()),qos=1).wait_for_publish(timeout=3)
                    result=first.result(timeout=8);self.assertEqual(result['stop_reason'],'ack-unavailable')
                self.assertEqual(self.spool.status()['usage']['records'],1)
                stop=threading.Event();ready=threading.Event();second=launch(pool,stop,ready)
                self.assertTrue(ready.wait(4));time.sleep(.5);stop.set();replayed=second.result(timeout=8)
                self.assertEqual(replayed['accepted_messages'],1);self.assertEqual(replayed['ack_requests'],1)
                self.assertEqual(self.spool.status()['usage']['records'],1)
        finally:stop.set();publisher.disconnect();publisher.loop_stop()


if __name__=='__main__':unittest.main()
