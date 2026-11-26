#!/bin/bash
set -euo pipefail
if [ "$(uname -s)" != "Darwin" ]; then printf '%s\n' 'Use this optional login service only in macOS Terminal. No service was changed.' 'Office Windows remains manual: .\home.ps1 -Action Demo.'; exit 1; fi
cd "$(dirname "$0")"
if [ ! -x .venv-home/bin/python ]; then printf '%s\n' 'Complete home_setup.command first.'; exit 1; fi
exec .venv-home/bin/python home-mode/mac_service.py "$@"
