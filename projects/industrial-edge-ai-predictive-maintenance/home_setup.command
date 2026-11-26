#!/bin/bash
set -euo pipefail
if [ "$(uname -s)" != "Darwin" ]; then
  printf '%s\n' 'This launcher is for macOS Terminal on your MacBook.' 'On Windows PowerShell use: .\home.ps1 -Action Demo (or Setup / Start / Check / Update).'
  exit 1
fi
cd "$(dirname "$0")"
action="setup"
if [ "${1:-}" = "--check" ]; then action="check"; fi
for candidate in python3.14 python3.13 python3.12 python3; do
  if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; raise SystemExit(sys.version_info[:2] not in {(3,12),(3,13),(3,14)})' 2>/dev/null; then
    exec "$candidate" home-mode/manage.py "$action"
  fi
done
printf '%s\n' 'Install Python 3.12, 3.13 or 3.14 from python.org, then retry. Use a current patched release. Monterey supports the Python 3.14 macOS installer.'
exit 1
