#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -x .venv-home/bin/python ]; then
  printf '%s\n' 'Prepare the home environment first: bash home_setup.command'
  exit 1
fi
.venv-home/bin/python home-mode/manage.py update
exec bash home_setup.command
