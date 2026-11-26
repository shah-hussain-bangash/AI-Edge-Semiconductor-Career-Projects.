#!/bin/bash
set -euo pipefail
if [ "$(uname -s)" != "Darwin" ]; then
  printf '%s\n' 'This launcher is for macOS Terminal on your MacBook.' 'On Windows PowerShell use: .\home.ps1 -Action Demo (or Setup / Start / Check / Update).'
  exit 1
fi
cd "$(dirname "$0")"
if [ ! -x .venv-home/bin/python ]; then
  printf '%s\n' 'Prepare the home environment first: bash home_setup.command'
  exit 1
fi
.venv-home/bin/python home-mode/manage.py update
exec bash home_setup.command
