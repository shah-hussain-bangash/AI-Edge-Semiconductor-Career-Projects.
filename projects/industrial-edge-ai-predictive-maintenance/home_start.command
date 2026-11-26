#!/bin/bash
set -euo pipefail
if [ "$(uname -s)" != "Darwin" ]; then
  printf '%s\n' 'This launcher is for macOS Terminal on your MacBook.' 'On Windows PowerShell use: .\home.ps1 -Action Demo (or Setup / Start / Check / Update).'
  exit 1
fi
cd "$(dirname "$0")"
if [ ! -x .venv-home/bin/python ]; then bash home_setup.command; fi
.venv-home/bin/python home-mode/manage.py verify
exec .venv-home/bin/python home-mode/home_server.py "$@"
