"""Loopback-only demo control; no PID lookup, forced kills or automatic USB stop."""
import json
from pathlib import Path
import re
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener, ProxyHandler, HTTPRedirectHandler
from home_core import ROOT, ProcessLock, instance_identity, strict_json


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*_args,**_kwargs): return None


def request(port,path,body=None,token=None,timeout=2):
    if type(port) is not int or not 1024<=port<=65535: raise ValueError('Use a local web port from 1024 to 65535')
    url='http://127.0.0.1:'+str(port)
    headers={}
    if body is not None: headers={'Content-Type':'application/json','Origin':url,'X-Edgeops-Home-Token':token or ''}
    req=Request(url+path,data=None if body is None else json.dumps(body).encode('utf-8'),headers=headers)
    # Ignore environment proxies and refuse redirects: anti-forgery tokens never
    # leave this fixed loopback destination.
    opener=build_opener(ProxyHandler({}),NoRedirect())
    with opener.open(req,timeout=timeout) as response:
        if response.headers.get_content_type()!='application/json': raise ValueError('Unexpected local service response')
        raw=response.read(65537)
        if len(raw)>65536: raise ValueError('Status response exceeds 64 KiB')
        result=strict_json(raw)
        if not isinstance(result,dict): raise ValueError('Unexpected status shape')
        return result


def checked_status(port,directory):
    state=request(port,'/api/status')
    if state.get('scope')!='edgeops-lightweight-home' or state.get('production_ready') is not False:
        raise ValueError('This port does not identify an EDGEOPS home bench')
    matches=type(state.get('shutdown_protocol')) is int and state.get('shutdown_protocol')==1 and state.get('instance_identity')==instance_identity(directory)
    return state,matches


def status(port=8878,directory=None):
    directory=Path(directory) if directory else ROOT/'.local/home'
    try: state,matches=checked_status(port,directory)
    except (OSError,URLError,ValueError):
        return dict(reachable=False,url='http://127.0.0.1:'+str(port)+'/app',message='No valid local EDGEOPS status response; no process was changed')
    return dict(reachable=True,url='http://127.0.0.1:'+str(port)+'/app',
        matches_checkout_and_data=matches,mode=state.get('settings',{}).get('mode'),
        reader_state=state.get('state'),fresh=state.get('fresh'),
        safe_demo_stop_available=matches and state.get('settings',{}).get('mode')=='demo' and not state.get('recording'),
        message='No process or reader was changed. Legacy or different-checkout servers are not stopped.')


def stop_demo(port=8878,directory=None,wait_seconds=8):
    directory=Path(directory) if directory else ROOT/'.local/home'
    try: state,matches=checked_status(port,directory)
    except (OSError,URLError,ValueError): raise ValueError('No verified local server response; no shutdown was sent') from None
    if not matches: raise ValueError('Legacy server, different checkout or different data directory; no shutdown was sent. Use the original Terminal or the reviewed legacy procedure.')
    if state.get('settings',{}).get('mode')!='demo' or state.get('recording'):
        raise ValueError('USB/recording sessions are preserved; this helper stops demos only')
    identity=state.get('instance_id');token=state.get('write_token')
    if not isinstance(identity,str) or not re.fullmatch('[a-f0-9]{32}',identity) or not isinstance(token,str) or not re.fullmatch('[a-f0-9]{64}',token):
        raise ValueError('Unsupported instance identity; no shutdown was sent')
    try: receipt=request(port,'/api/shutdown',{'instance_id':identity},token)
    except (OSError,URLError,ValueError): raise ValueError('Graceful stop was refused or not confirmed; no process was force-killed') from None
    if receipt.get('stopping') is not True or receipt.get('instance_id')!=identity: raise ValueError('Unexpected stop receipt; inspect the server before updating')
    deadline=time.monotonic()+wait_seconds
    while time.monotonic()<deadline:
        try:
            current=request(port,'/api/status',timeout=.5)
            if current.get('instance_id')!=identity: raise ValueError('Another service appeared on this port; no further shutdown was sent')
        except (OSError,URLError):
            lock=directory/'server.lock'
            if not lock.is_file(): raise ValueError('Server response ended but its process lock is missing; stop not verified')
            try:
                with ProcessLock(lock): pass
            except (ValueError,OSError): pass
            else: return dict(stopped=True,url='http://127.0.0.1:'+str(port)+'/app',message='Verified demo stopped and selected session lock released. Source and data preserved.')
        time.sleep(.1)
    raise ValueError('Shutdown requested but lock release was not confirmed. No process was force-killed; retry Status before updating.')
