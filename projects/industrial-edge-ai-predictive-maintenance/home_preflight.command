#!/bin/bash
# Read-only host/port inventory: no installs, serial opens, database or config writes.
set -euo pipefail
if [ "$(uname -s)" != "Darwin" ]; then
  printf '%s\n' 'This report is for macOS Terminal on the home MacBook.' 'Office Windows: use .\home.ps1 -Action Check and OFFICE_WINDOWS.md.'
  exit 1
fi
case "$0" in */*) cd "${0%/*}" ;; esac
printf '%s\n' 'EDGEOPS MAC PREFLIGHT — READ ONLY' 'Physical MacBook / ESP32 acceptance: PENDING'
printf 'macOS version: '; sw_vers -productVersion
printf 'Architecture: '; uname -m
printf 'Reported model: '; sysctl -n hw.model 2>/dev/null || printf '%s\n' 'Unavailable'
memory_bytes="$(sysctl -n hw.memsize 2>/dev/null || true)"
case "$memory_bytes" in ''|*[!0-9]*) printf '%s\n' 'Reported memory: unavailable' ;; *) printf 'Reported memory: %s MiB\n' "$((memory_bytes / 1048576))" ;; esac
printf '%s\n' 'Supported Python: 3.12, 3.13, 3.14. Required external runtime: pyserial==3.5.'
found_python=0
for candidate in python3.14 python3.13 python3.12 python3; do
  candidate_path="$(command -v "$candidate" 2>/dev/null || true)"
  [ -n "$candidate_path" ] && [ -x "$candidate_path" ] || continue
  # Apple's stub can trigger Command Line Tools installation. Do not execute it.
  [ "$candidate_path" != '/usr/bin/python3' ] || continue
  if version="$("$candidate_path" -I -S -B -c 'import sys; print(sys.version.split()[0]); sys.exit(0 if sys.version_info[:2] in {(3,12),(3,13),(3,14)} else 1)' 2>/dev/null)"; then
    printf 'Supported interpreter found: %s (%s)\n' "$version" "$candidate_path"
    found_python=1
    break
  fi
done
[ "$found_python" -eq 1 ] || printf '%s\n' 'Supported interpreter not found in PATH. Install a supported Python before setup.'
if [ -x .venv-home/bin/python ]; then
  printf '%s\n' 'Home environment exists; dependencies are NOT verified by this report.'
else
  printf '%s\n' 'Home environment not prepared yet. Run bash home_setup.command after reviewing HOME_MAC.md.'
fi
git_path="$(command -v git 2>/dev/null || true)"
printf 'Git path (not executed): %s\n' "${git_path:-not found}"
printf '%s\n' 'Serial device names (listed only; no port opened):'
shopt -s nullglob
ports=(/dev/cu.*)
if [ "${#ports[@]}" -eq 0 ]; then
  printf '%s\n' 'No /dev/cu.* devices found. Board/cable/driver verification remains pending.'
else
  printf '  %s\n' "${ports[@]}"
fi
printf '%s\n' 'Listing a device does not prove it is an ESP32 or that measurements are valid.' 'No installation, firmware upload, reader, dashboard, network request or acceptance update was started.' 'Next: follow TONIGHT_MAC.md. Physical verification remains PENDING.'
