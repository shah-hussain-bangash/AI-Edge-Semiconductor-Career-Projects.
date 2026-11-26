"""Loopback-only home dashboard. Python standard library + pinned pySerial, no cloud login."""
import argparse
import csv
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
from pathlib import Path
import secrets
import re
import platform
import sys
from urllib.parse import parse_qs, urlsplit

from session_export import build_package, summarize
from home_core import BOUNDARY, CHANNELS, ROOT, Controller, ProcessLock, Store, load_settings, serial_ports, strict_json

WEB = Path(__file__).resolve().parent / 'web'
HEADERS = {
    'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff',
    'Referrer-Policy': 'no-referrer', 'X-Frame-Options': 'DENY',
    'Content-Security-Policy': "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; base-uri 'none'; frame-ancestors 'none'; form-action 'self'",
}


class HomeServer(ThreadingHTTPServer):
    daemon_threads = True
    def __init__(self, port, controller):
        self.controller = controller; self.write_token = secrets.token_hex(32)
        super().__init__(('127.0.0.1', port), Handler)


class Handler(BaseHTTPRequestHandler):
    server_version = 'EDGEOPS-Home/1'
    def setup(self):
        super().setup(); self.connection.settimeout(5)
    def log_message(self, *_): pass

    def send(self, code, body, kind='application/json; charset=utf-8', extra=None):
        payload = json.dumps(body, allow_nan=False).encode() if isinstance(body, (dict, list)) else body
        self.send_response(code)
        for key, value in HEADERS.items(): self.send_header(key, value)
        for key, value in (extra or {}).items(): self.send_header(key, value)
        self.send_header('Content-Type', kind); self.send_header('Content-Length', str(len(payload)))
        self.end_headers(); self.wfile.write(payload)

    def allowed_host(self):
        try:
            host = urlsplit('http://' + self.headers.get('Host', ''))
            return host.hostname in ('localhost', '127.0.0.1') and host.port == self.server.server_port and not host.username and not host.password
        except ValueError: return False

    def do_GET(self):
        if not self.allowed_host(): self.send(403, {'error': 'Use the local dashboard URL'}); return
        route = urlsplit(self.path)
        try:
            if route.path == '/api/status':
                self.send(200, {**self.server.controller.status(), 'write_token': self.server.write_token, 'host_platform': platform.system()}); return
            if route.path == '/api/ports':
                self.send(200, {'ports': serial_ports(), **BOUNDARY}); return
            if route.path == '/api/capture.zip':
                if route.query: raise ValueError('Capture export takes no query parameters')
                payload = self.server.controller.recording_package()
                self.send(200, payload, 'application/zip', {'Content-Disposition': 'attachment; filename="edgeops-capture.zip"'})
                return
            if route.path in ('/api/session', '/api/session.zip'):
                if route.query: raise ValueError('Session exports take no query parameters')
                snapshot = self.server.controller.session_snapshot()
                if route.path == '/api/session': self.send(200, summarize(snapshot)); return
                payload = build_package(snapshot)
                self.send(200, payload, 'application/zip', {'Content-Disposition': 'attachment; filename="edgeops-session-' + snapshot['session_id'] + '.zip"'})
                return
            if route.path in ('/api/history', '/api/history.csv'):
                query = parse_qs(route.query)
                if set(query) - {'limit'} or len(query.get('limit', ['60'])) != 1: raise ValueError('Unsupported history query')
                limit = int(query.get('limit', ['60'])[0]); data = self.server.controller.store.history(limit)
                if route.path == '/api/history': self.send(200, data); return
                stream = io.StringIO(newline='')
                fields = ['received_at', 'session_id', 'source', 'mode', 'kind', 'device_id', 'device_sequence', 'device_uptime_ms'] + [c[0] for c in CHANNELS] + ['hardware_verified', 'calibration_verified', 'production_ready']
                writer = csv.DictWriter(stream, fieldnames=fields); writer.writeheader()
                for item in reversed(data['items']):
                    writer.writerow({**{key: item.get(key) for key in fields if key not in item['values']}, **item['values']})
                self.send(200, stream.getvalue().encode(), 'text/csv; charset=utf-8', {'Content-Disposition': 'attachment; filename="edgeops-home-last-60.csv"'}); return
            assets = {'/': ('index.html', 'text/html; charset=utf-8'), '/app': ('index.html', 'text/html; charset=utf-8'),
                      '/home.js': ('home.js', 'text/javascript; charset=utf-8'), '/home.css': ('home.css', 'text/css; charset=utf-8')}
            if route.path in assets:
                name, kind = assets[route.path]; self.send(200, (WEB / name).read_bytes(), kind); return
            self.send(404, {'error': 'Not found'})
        except (ValueError, json.JSONDecodeError): self.send(422, {'error': 'Invalid request or retained data; no values inferred'})
        except Exception: self.send(503, {'error': 'Local data or serial enumeration unavailable'})

    def do_POST(self):
        if not self.allowed_host(): self.send(403, {'error': 'Use the local dashboard URL'}); return
        expected_origin = 'http://' + self.headers['Host']
        token = self.headers.get('X-Edgeops-Home-Token', '')
        if self.headers.get('Origin') != expected_origin or not re.fullmatch('[a-f0-9]{64}', token) or not hmac.compare_digest(token, self.server.write_token):
            self.send(403, {'error': 'Refresh this local dashboard before changing the connection'}); return
        if self.headers.get('Content-Type', '').split(';')[0].strip().lower() != 'application/json' or self.headers.get('Transfer-Encoding'):
            self.send(415, {'error': 'Use a bounded JSON request'}); return
        try:
            length = int(self.headers.get('Content-Length', '-1'))
            if not 0 <= length <= 4096: self.send(413, {'error': 'Request exceeds 4 KiB'}); return
            body = strict_json(self.rfile.read(length).decode('utf-8'))
            if self.path == '/api/record':
                if not isinstance(body, dict) or set(body) != {'settings','seconds'}: raise ValueError('Use settings and seconds')
                if type(body['seconds']) is not int: raise ValueError('Use an integer duration')
                self.server.controller.start(body['settings'], record_seconds=body['seconds'])
            elif self.path == '/api/connect': self.server.controller.start(body)
            elif self.path == '/api/disconnect' and body == {}: self.server.controller.stop()
            else: self.send(404, {'error': 'Not found'}); return
            self.send(200, self.server.controller.status())
        except (ValueError, UnicodeError): self.send(422, {'error': 'Check the mode, serial port and firmware device ID; saved data is retained'})
        except Exception: self.send(503, {'error': 'Connection change failed; check the local Terminal and refresh'})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=('esp32-only', 'sensors', 'demo'))
    parser.add_argument('--port', help='Serial port, for example /dev/cu.usbserial-0001')
    parser.add_argument('--device-id'); parser.add_argument('--connect', action='store_true')
    parser.add_argument('--web-port', type=int, default=8878)
    parser.add_argument('--data-dir', type=Path, default=ROOT / '.local/home')
    args = parser.parse_args(argv)
    if not 1024 <= args.web_port <= 65535: parser.error('Web port must be between 1024 and 65535')
    with ProcessLock(args.data_dir / 'server.lock'):
        settings = load_settings(args.data_dir)
        for arg, field in ((args.mode, 'mode'), (args.port, 'port'), (args.device_id, 'expected_device_id')):
            if arg is not None: settings[field] = arg
        controller = Controller(Store(args.data_dir / 'history.sqlite3'), settings, args.data_dir)
        try: server = HomeServer(args.web_port, controller)
        except OSError: raise ValueError('Web port is in use. Stop your existing home session or choose --web-port 8879; no process was stopped.') from None
        try:
            if args.connect: controller.start(settings)
            print('EDGEOPS HOME: http://127.0.0.1:' + str(server.server_port) + '/app', flush=True)
            print('Keep this Terminal open. Ctrl+C stops the dashboard and closes serial. No Wi-Fi or remote upload is started.', flush=True)
            server.serve_forever(poll_interval=0.25)
        except KeyboardInterrupt: pass
        finally:
            try: controller.stop()
            finally: server.server_close()
    return 0


if __name__ == '__main__':
    try: raise SystemExit(main())
    except (ValueError, OSError) as error: print('Home mode stopped: ' + str(error), file=sys.stderr); raise SystemExit(1)
