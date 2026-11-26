#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -x .venv-portal/bin/python ]; then bash setup_mac.command --portal; fi
exec .venv-portal/bin/python mac-gateway/local_portal.py
