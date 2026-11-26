"""Explicit continuous synthetic HTTP runner; not an installed OS service or broker."""
import argparse
import json
import os
from pathlib import Path
import secrets
import signal
import threading
from datetime import datetime

import httpx
from edge_delivery import Spool
from service_delivery_worker import run_once, validate_target


class RunnerLock:
    """OS-released nonblocking lock for one resolved spool pathname."""
    def __init__(self, spool):
        self.path = Path(str(Path(spool).resolve())+'.runner.lock')
        self.stream = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.stream = open(self.path, 'a+b')
        if self.path.stat().st_size == 0:
            self.stream.write(b'\0');self.stream.flush()
        self.stream.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self.stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.stream.close();self.stream = None
            raise RuntimeError('Another runner holds this spool lock') from None
        return self

    def __exit__(self, *args):
        if self.stream:
            self.stream.close();self.stream = None


class RunnerDenied(Exception):
    pass


class Reporter:
    def __init__(self, client, token, interval):
        self.client = client;self.token = token;self.interval = interval
        self.run_id = secrets.token_hex(16);self.sequence = 0;self.pending = None

    def report(self, state, counts, outcome):
        # Retry an exact pending report before publishing changed counters. This
        # reconciles a lost response without replaying work or taking a new lease.
        flush = self.pending is not None
        if self.pending is None:
            self.pending = {'run_id': self.run_id, 'sequence': self.sequence,
                'state': state, 'interval_seconds': self.interval,
                'passes': counts['passes'], 'attempts': counts['attempts'],
                'pass_errors': counts['pass_errors'], 'last_outcome': outcome}
        try:
            response = self.client.post('/api/edge/heartbeat', json=self.pending,
                                       headers={'Authorization': 'Bearer '+self.token})
            if response.status_code in (401, 403, 409):
                raise RunnerDenied('credential-or-runner-lease-denied')
            if response.status_code != 200:
                return False
            data = response.json()
            if (not isinstance(data, dict) or data.get('scope') != 'local-synthetic-runner-status'
                    or data.get('production_ready') is not False or data.get('hardware_connected') is not False
                    or data.get('broker_connected') is not False or data.get('run_id') != self.pending['run_id']
                    or type(data.get('sequence')) is not int or data['sequence'] != self.pending['sequence']):
                return False
            for key in ('report_received_at','report_lease_until'):
                if not isinstance(data.get(key),str) or datetime.fromisoformat(data[key]).utcoffset() is None:
                    return False
        except (httpx.HTTPError, ValueError):
            return False
        self.sequence += 1;self.pending = None
        return self.report(state, counts, outcome) if flush else True


def run(spool_path, server, token, *, interval=5, max_passes=None, stop=None, failure_budget=5):
    validate_target(server, token)
    if type(interval) is not int or not 1 <= interval <= 300:
        raise ValueError('Interval must be 1–300 seconds')
    if max_passes is not None and (type(max_passes) is not int or not 1 <= max_passes <= 100000):
        raise ValueError('Finite run requires 1–100000 passes')
    if type(failure_budget) is not int or not 1 <= failure_budget <= 20:
        raise ValueError('Failure budget must be 1–20')
    stop = stop or threading.Event()
    counts = {'passes': 0, 'attempts': 0, 'pass_errors': 0}
    failures = 0;pass_failures = 0;outcome = 'not-attempted';reason = 'stop-requested'
    with RunnerLock(spool_path), httpx.Client(base_url=server.rstrip('/'), timeout=10,
            follow_redirects=False, trust_env=False) as client:
        reporter = Reporter(client, token, interval)
        try:
            while not stop.is_set():
                if not reporter.report('running', counts, outcome):
                    failures += 1;outcome = 'heartbeat-unavailable'
                    if failures >= failure_budget:
                        reason = 'heartbeat-failure-budget';break
                    stop.wait(interval);continue
                failures = 0
                counts['passes'] += 1
                try:
                    result = run_once(spool_path, server, token)
                    if result.get('attempted'):
                        counts['attempts'] += 1
                        rows = Spool(spool_path).status(event_key=result['event_key'])['records']
                        outcome = rows[0]['state'] if rows else 'pass-error'
                    else:
                        outcome = 'idle'
                    pass_failures = 0
                except Exception:
                    # Store no exception strings, request bodies, tokens or paths.
                    counts['pass_errors'] += 1;pass_failures += 1;outcome = 'pass-error'
                if not reporter.report('running', counts, outcome):
                    failures += 1
                if pass_failures >= failure_budget:
                    reason = 'pass-error-budget';break
                if max_passes is not None and counts['passes'] >= max_passes:
                    reason = 'pass-limit';break
                stop.wait(interval)
        except RunnerDenied as error:
            reason = str(error)
        finally:
            try:
                reporter.report('stopped', counts, outcome)
            except RunnerDenied:
                pass
    return {**counts, 'last_outcome': outcome, 'stop_reason': reason,
            'production_ready': False, 'hardware_connected': False, 'broker_connected': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--spool', required=True)
    parser.add_argument('--server', required=True)
    parser.add_argument('--interval', type=int, default=5)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--max-passes', type=int)
    mode.add_argument('--forever', action='store_true')
    args = parser.parse_args();stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())
    try:
        result = run(args.spool, args.server, os.environ.get('EDGEOPS_SERVICE_TOKEN'),
                     interval=args.interval, max_passes=args.max_passes, stop=stop)
    except Exception:
        parser.exit(1, 'Runner unavailable; verify local origin, credential, spool access and duplicate-runner lock. No secrets logged.\n')
    print(json.dumps(result))
    if result['stop_reason'] not in ('pass-limit', 'stop-requested'):
        parser.exit(2)


if __name__ == '__main__':
    main()
