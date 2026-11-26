#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -x .venv-gateway/bin/python ]; then bash setup_mac.command; fi
exec .venv-gateway/bin/python mac-gateway/gateway.py --configure
