#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -x .venv-home/bin/python ]; then bash home_setup.command; fi
.venv-home/bin/python home-mode/manage.py verify
exec .venv-home/bin/python home-mode/home_server.py "$@"
