#!/bin/bash
set -euo pipefail
if [ "$(uname -s)" != "Darwin" ]; then
  printf '%s\n' 'Use this on the Mac in macOS Terminal. Windows: .\home.ps1 -Action Backup or Restore.'
  exit 1
fi
cd "$(dirname "$0")"
case "${1:-}" in backup|verify-backup|restore) ;; *) printf '%s\n' 'Usage: bash home_data.command backup [--output NEW_FOLDER]' 'Or: verify-backup --backup FOLDER' 'Or: restore --backup FOLDER --destination NEW_FOLDER'; exit 1 ;; esac
if [ ! -x .venv-home/bin/python ]; then printf '%s\n' 'Complete home_setup.command first.'; exit 1; fi
.venv-home/bin/python home-mode/manage.py verify
exec .venv-home/bin/python home-mode/manage.py "$@"
