#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
for candidate in python3.12 python3.13 python3.11 python3; do
  if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; raise SystemExit(not ((3,11)<=sys.version_info[:2]<=(3,13)))' 2>/dev/null; then
    exec "$candidate" mac-gateway/setup.py "$@"
  fi
done
printf '%s\n' 'Install a supported Python 3.11–3.13 from python.org, then run this again. Python 3.12 is the tested reference.'
exit 1
