"""One-pass service-credential delivery to explicit loopback HTTP, synthetic only."""
import argparse
import json
import os
import re
from urllib.parse import urlsplit

import httpx
from edge_delivery import Spool


def validate_target(server, token):
    target = urlsplit(server)
    if (target.scheme != 'http' or target.hostname not in ('127.0.0.1', 'localhost', '::1')
            or target.username or target.password or target.query or target.fragment
            or target.path not in ('', '/')):
        raise ValueError('Service worker requires an explicit loopback HTTP origin')
    if not isinstance(token, str) or not re.fullmatch(r'edgeops_svc_[0-9a-f]{64}', token):
        raise ValueError('Supply the scoped service credential through EDGEOPS_SERVICE_TOKEN')


def run_once(spool_path, server, token):
    validate_target(server, token)
    with httpx.Client(base_url=server.rstrip('/'), timeout=10, follow_redirects=False, trust_env=False) as client:
        def send(envelope):
            response = client.post('/api/edge/observations', json=envelope,
                                   headers={'Authorization': 'Bearer ' + token})
            try:
                data = response.json()
            except ValueError:
                data = {}
            return response.status_code, data
        return Spool(spool_path).attempt(send)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--spool', required=True)
    parser.add_argument('--server', required=True)
    args = parser.parse_args()
    try:
        result = run_once(args.spool, args.server, os.environ.get('EDGEOPS_SERVICE_TOKEN'))
    except Exception:
        parser.exit(1, 'Service delivery unavailable; verify local origin, scoped credential and spool. No secrets logged.\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
