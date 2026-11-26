"""Disposable native Mosquitto mTLS fixture; never an installed service."""
from datetime import datetime,timedelta,timezone
import ipaddress
import os
from pathlib import Path
import socket
import subprocess
import sys
import importlib.util
import time



def available_broker():
    path=os.environ.get('EDGEOPS_MOSQUITTO_EXE','')
    crypto=importlib.util.find_spec('cryptography') is not None
    external=os.environ.get('EDGEOPS_PKI_PYTHON','')
    return path if path and Path(path).is_file() and (crypto or (external and Path(external).is_file())) else None


def make_pki(root):
    try:
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes,serialization
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.x509.oid import NameOID,ExtendedKeyUsageOID
    except ImportError:
        executable=os.environ.get('EDGEOPS_PKI_PYTHON','')
        if not executable or not Path(executable).is_file():raise RuntimeError('Install optional PKI test dependencies') from None
        result=subprocess.run([executable,str(Path(__file__).resolve()),'--make-pki',str(root)],
            capture_output=True,timeout=15,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        if result.returncode:raise RuntimeError('External test PKI generation failed')
        return Path(root)
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    now=datetime.now(timezone.utc);ca_key=ec.generate_private_key(ec.SECP256R1())
    ca_name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'Disposable EDGEOPS test CA')])
    ca=(x509.CertificateBuilder().subject_name(ca_name).issuer_name(ca_name).public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(minutes=5))
        .not_valid_after(now+timedelta(days=2)).add_extension(x509.BasicConstraints(ca=True,path_length=0),critical=True)
        .add_extension(x509.KeyUsage(digital_signature=True,content_commitment=False,key_encipherment=False,
            data_encipherment=False,key_agreement=False,key_cert_sign=True,crl_sign=True,
            encipher_only=False,decipher_only=False),critical=True)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()),critical=False)
        .sign(ca_key,hashes.SHA256()))
    (root/'ca.crt').write_bytes(ca.public_bytes(serialization.Encoding.PEM))
    for name in ('server','fixture-publisher','fixture-bridge'):
        key=ec.generate_private_key(ec.SECP256R1())
        subject=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,name)])
        builder=(x509.CertificateBuilder().subject_name(subject).issuer_name(ca_name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(minutes=5))
            .not_valid_after(now+timedelta(days=2)).add_extension(x509.BasicConstraints(ca=False,path_length=None),critical=True)
            .add_extension(x509.KeyUsage(digital_signature=True,content_commitment=False,key_encipherment=False,
                data_encipherment=False,key_agreement=False,key_cert_sign=False,crl_sign=False,
                encipher_only=False,decipher_only=False),critical=True)
            .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()),critical=False)
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()),critical=False)
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH if name=='server'
                else ExtendedKeyUsageOID.CLIENT_AUTH]),critical=False))
        if name=='server':builder=builder.add_extension(x509.SubjectAlternativeName([x509.DNSName('localhost')]),critical=False)
        cert=builder.sign(ca_key,hashes.SHA256())
        (root/(name+'.crt')).write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        (root/(name+'.key')).write_bytes(key.private_bytes(serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
        os.chmod(root/(name+'.key'),0o600)
    return root


class LocalBroker:
    def __init__(self,root,topic):
        self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True)
        self.pki=make_pki(self.root/'pki')
        with socket.socket() as s:s.bind(('127.0.0.1',0));self.port=s.getsockname()[1]
        acl=self.root/'acl';acl.write_text('user fixture-publisher\ntopic write '+topic+
            '\nuser fixture-bridge\ntopic read '+topic+'\n',encoding='utf-8')
        (self.root/'data').mkdir(exist_ok=True)
        config=('listener '+str(self.port)+' 127.0.0.1\nallow_anonymous false\nrequire_certificate true\n'
            'use_identity_as_username true\nmax_packet_size 16384\npersistence true\nautosave_interval 1\nlog_dest stderr\nlog_type all\n'
            'persistence_location '+(self.root/'data').as_posix()+'/\n'
            'cafile '+(self.pki/'ca.crt').as_posix()+'\n'
            'certfile '+(self.pki/'server.crt').as_posix()+'\n'
            'keyfile '+(self.pki/'server.key').as_posix()+'\nacl_file '+acl.as_posix()+'\n')
        (self.root/'mosquitto.conf').write_text(config,encoding='utf-8')
        self.log=open(self.root/'broker.log','w',encoding='utf-8')
        self.process=subprocess.Popen([available_broker(),'-c',str(self.root/'mosquitto.conf')],
            stdout=self.log,stderr=self.log,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        for _ in range(50):
            if self.process.poll() is not None:
                self.log.close();raise RuntimeError('Disposable broker failed: '+(self.root/'broker.log').read_text()[-1500:])
            try:
                with socket.create_connection(('127.0.0.1',self.port),timeout=.1):return
            except OSError:time.sleep(.1)
        self.close();raise RuntimeError('Disposable broker startup timed out')

    def close(self):
        if self.process.poll() is None:
            self.process.terminate()
            try:self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:self.process.kill();self.process.wait(timeout=5)
        if not self.log.closed:self.log.close()


if __name__=='__main__':
    if len(sys.argv)!=3 or sys.argv[1]!='--make-pki':raise SystemExit(2)
    make_pki(Path(sys.argv[2]))
