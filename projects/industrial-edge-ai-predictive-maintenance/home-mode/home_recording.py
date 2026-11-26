"""Bounded raw USB recording. No physical acceptance or device authentication."""
import argparse
import hashlib
import io
import os
from pathlib import Path
import platform
import re
import math
import threading
import time
import zipfile
from home_core import BOUNDARY, canonical, strict_json, utc_now, validate_settings, parse_line

MAX_BYTES = 16 * 1024 * 1024
MAX_CHUNKS = 10000


class CaptureLimit(ValueError): pass


class Recorder:
    def __init__(self, directory, session_id, settings, seconds, monotonic=time.monotonic,
                 max_bytes=MAX_BYTES, max_chunks=MAX_CHUNKS):
        if type(seconds) is not int or not 10 <= seconds <= 600: raise ValueError('Recording duration must be 10–600 seconds')
        if not isinstance(session_id,str) or not re.fullmatch('[a-f0-9]{32}',session_id): raise ValueError('Invalid capture identity')
        settings = validate_settings(settings)
        if settings['mode'] == 'demo': raise ValueError('Raw USB recording requires ESP32-only or sensor mode; demo is not USB')
        self.lock = threading.RLock(); self.clock = monotonic; self.start = monotonic()
        self.seconds = seconds; self.settings = settings; self.session_id = session_id
        self.directory = Path(directory) / session_id
        self.directory.mkdir(parents=True, exist_ok=False, mode=0o700)
        if os.name != 'nt': self.directory.chmod(0o700)
        self.files = {}; self.hashes = {}; self.counts = dict(accepted=0,rejected=0,diagnostic=0,partial=0)
        self.total = self.chunks = self.line_start = 0; self.withheld = 0
        self.finished = False; self.broken = False; self.reason = None; self.started_at = utc_now()
        self.last_receipt = self.started_at; self.last_elapsed = 0.
        self.max_bytes = max_bytes; self.max_chunks = max_chunks
        try:
            for name in ('wire.bin', 'frames.jsonl'):
                descriptor = os.open(self.directory/name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                self.files[name] = os.fdopen(descriptor, 'wb', buffering=0); self.hashes[name] = hashlib.sha256()
        except Exception:
            for stream in self.files.values(): stream.close()
            raise

    def elapsed(self): return max(0., self.clock() - self.start)
    def expired(self): return self.elapsed() >= self.seconds

    def _write(self, name, raw):
        try:
            if self.files[name].write(raw) != len(raw): raise OSError('Incomplete recording write')
            self.hashes[name].update(raw)
        except OSError:
            self.broken = True; raise

    def write(self, raw):
        with self.lock:
            if self.finished: raise ValueError('Recording already closed')
            if not isinstance(raw,bytes) or not 1<=len(raw)<=4097: raise ValueError('Use a bounded nonempty serial read')
            if self.total + len(raw) > self.max_bytes:
                self.withheld += len(raw); raise CaptureLimit('byte-limit')
            if self.chunks >= self.max_chunks:
                self.withheld += len(raw); raise CaptureLimit('chunk-limit')
            self.last_receipt = utc_now(); self.last_elapsed = self.elapsed()
            self._write('wire.bin', raw); self.total += len(raw); self.chunks += 1

    def classify(self, kind, sample=None):
        with self.lock:
            if kind not in self.counts: raise ValueError('Unsupported frame classification')
            event = dict(offset=self.line_start, bytes=self.total-self.line_start, kind=kind,
                         received_at=self.last_receipt, elapsed_seconds=self.last_elapsed, sample=sample)
            raw = (canonical(event) + '\n').encode('utf-8')
            if len(raw) > 4096: raise CaptureLimit('index-event-limit')
            self._write('frames.jsonl',raw)
            self.line_start=self.total; self.counts[kind] += 1

    def finish(self, reason):
        with self.lock:
            if self.finished: return
            self.reason = reason
            try:
                if self.broken: raise OSError('Recording storage failed; incomplete files preserved')
                if self.total > self.line_start: self.classify('partial')
                elapsed=self.elapsed()
                for stream in self.files.values(): stream.flush(); os.fsync(stream.fileno())
                inventory={name:dict(bytes=stream.tell(),sha256=self.hashes[name].hexdigest()) for name,stream in self.files.items()}
                manifest=dict(format='edgeops-raw-usb-v1',session_id=self.session_id,settings=self.settings,
                    source='simulated' if self.settings['mode']=='esp32-only' else 'serial-unverified',
                    started_at_host_utc=self.started_at,ended_at_host_utc=utc_now(),
                    requested_seconds=self.seconds,elapsed_monotonic_seconds=elapsed,stop_reason=reason,
                    deadline_reached=elapsed>=self.seconds,read_timeout_seconds=0.5,
                    timing_scope='after port open through final byte classification, before fsync; a final read may cross the deadline',
                    raw_bytes=self.total,read_chunks=self.chunks,withheld_read_bytes=self.withheld,
                    frame_counts=dict(self.counts),max_bytes=self.max_bytes,max_chunks=self.max_chunks,
                    parser_acceptance_is_physical_verification=False,database_history_is_separate=True,
                    host_system=platform.system(),python_version=platform.python_version(),
                    recorder_source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),baud=115200,
                    firmware_source_commit=None,firmware_binary_sha256=None,device_clock_verified=False,
                    physical_acceptance='pending',calibration_references_included=False,
                    files=inventory,**BOUNDARY)
                with open(self.directory/'manifest.json','xb') as stream:
                    stream.write((canonical(manifest)+'\n').encode('utf-8'));stream.flush();os.fsync(stream.fileno())
                if os.name!='nt': (self.directory/'manifest.json').chmod(0o600)
                self.finished=True
            except Exception:
                self.broken = True; raise
            finally:
                for stream in self.files.values(): stream.close()

    def status(self):
        with self.lock:
            return dict(session_id=self.session_id,active=not self.finished and not self.broken,
                finalized=self.finished,requested_seconds=self.seconds,
                elapsed_seconds=self.elapsed() if not self.finished else self.final_elapsed(),
                raw_bytes=self.total,frame_counts=dict(self.counts),stop_reason=self.reason,
                physical_acceptance='pending')

    def final_elapsed(self):
        return strict_json((self.directory/'manifest.json').read_text(encoding='utf-8'))['elapsed_monotonic_seconds']


def verify(directory):
    directory=Path(directory)
    if directory.is_symlink() or any(p.is_symlink() for p in directory.iterdir()): raise ValueError('Capture links are not supported')
    if {p.name for p in directory.iterdir()} != {'manifest.json','wire.bin','frames.jsonl'}:
        raise ValueError('Incomplete or unexpected capture inventory')
    if (directory/'manifest.json').stat().st_size>16384: raise ValueError('Manifest too large')
    manifest=strict_json((directory/'manifest.json').read_text(encoding='utf-8'))
    if manifest['format']!='edgeops-raw-usb-v1' or manifest['physical_acceptance']!='pending' or any(manifest.get(k) is not False for k in ('production_ready','hardware_verified','calibration_verified','equipment_authorized')):
        raise ValueError('Unsupported capture labels')
    settings=validate_settings(manifest['settings'])
    source='simulated' if settings['mode']=='esp32-only' else 'serial-unverified'
    if settings['mode']=='demo' or manifest['source']!=source: raise ValueError('Unexpected source classification')
    if set(manifest['files'])!={'wire.bin','frames.jsonl'}: raise ValueError('Unexpected file names')
    for key,lower,upper in [('requested_seconds',10,600),('max_bytes',1,MAX_BYTES),('max_chunks',1,MAX_CHUNKS),('raw_bytes',0,MAX_BYTES),('read_chunks',0,MAX_CHUNKS),('withheld_read_bytes',0,4097)]:
        if type(manifest[key]) is not int or not lower<=manifest[key]<=upper: raise ValueError('Invalid capture bounds')
    elapsed=manifest['elapsed_monotonic_seconds']
    if type(elapsed) not in (int,float) or not math.isfinite(elapsed) or elapsed<0: raise ValueError('Invalid elapsed time')
    if manifest['deadline_reached'] is not (elapsed>=manifest['requested_seconds']): raise ValueError('Inconsistent deadline status')
    if manifest['stop_reason'] not in ('manual-stop','duration-elapsed','serial-or-storage-error','byte-limit','chunk-limit','index-event-limit'): raise ValueError('Unknown stop reason')
    if manifest['raw_bytes']>manifest['max_bytes'] or manifest['read_chunks']>manifest['max_chunks']: raise ValueError('Capture exceeds declared bounds')

    payloads={}
    for name,bound in (('wire.bin',MAX_BYTES),('frames.jsonl',(MAX_CHUNKS+1)*4096)):
        path=directory/name
        if path.is_symlink() or path.stat().st_size>bound: raise ValueError('Capture file outside bounds')
        raw=path.read_bytes(); meta=manifest['files'][name]
        if len(raw)!=meta['bytes'] or hashlib.sha256(raw).hexdigest()!=meta['sha256']: raise ValueError('Capture hash mismatch')
        payloads[name]=raw
    counts=dict(accepted=0,rejected=0,diagnostic=0,partial=0);offset=0
    for line in payloads['frames.jsonl'].splitlines():
        if len(line)>4096: raise ValueError('Frame index exceeds bounds')
        event=strict_json(line)
        if type(event['offset']) is not int or event['offset']!=offset or type(event['bytes']) is not int or event['bytes']<1 or event['kind'] not in counts:
            raise ValueError('Frame index does not reconcile')
        tick=event['elapsed_seconds']
        if type(tick) not in (int,float) or not math.isfinite(tick) or not 0<=tick<=elapsed: raise ValueError('Frame clock outside recording bounds')
        if counts['partial']: raise ValueError('Partial bytes must be the final event')
        piece=payloads['wire.bin'][offset:offset+event['bytes']]
        if len(piece)!=event['bytes']: raise ValueError('Index references bytes beyond capture')
        if event['kind']!='partial':
            try: parsed=parse_line(piece,settings['mode'],settings['expected_device_id'])
            except (ValueError,UnicodeError,RecursionError):
                if event['kind']!='rejected' or event['sample'] is not None: raise ValueError('Incorrect rejection classification')
            else:
                expected_kind='accepted' if parsed else 'diagnostic'
                if expected_kind!=event['kind'] or canonical(parsed)!=canonical(event['sample']): raise ValueError('Recorded classification does not reproduce')
        elif event['sample'] is not None: raise ValueError('Partial bytes cannot be accepted')
        offset+=event['bytes'];counts[event['kind']]+=1
    if offset!=len(payloads['wire.bin']) or counts!=manifest['frame_counts'] or offset!=manifest['raw_bytes']:
        raise ValueError('Raw byte/count reconciliation failed')
    return manifest,payloads


def package(directory):
    manifest,payloads=verify(directory)
    payloads['manifest.json']=(canonical(manifest)+'\n').encode('utf-8')
    output=io.BytesIO()
    with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED) as archive:
        for name,raw in payloads.items(): archive.writestr(name,raw)
    return output.getvalue()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('verify','pack'));parser.add_argument('directory',type=Path)
    parser.add_argument('--output',type=Path);args=parser.parse_args()
    if args.action=='verify':
        manifest,_=verify(args.directory);print(canonical(manifest))
    else:
        if args.output is None: parser.error('pack requires --output with a new filename')
        raw=package(args.directory)
        descriptor=os.open(args.output,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(descriptor,'wb') as stream: stream.write(raw)
        print('Raw capture package saved; physical acceptance remains pending.')


if __name__=='__main__':
    try: main()
    except (ValueError,OSError,KeyError,TypeError) as error: raise SystemExit('Capture check failed: '+str(error))
