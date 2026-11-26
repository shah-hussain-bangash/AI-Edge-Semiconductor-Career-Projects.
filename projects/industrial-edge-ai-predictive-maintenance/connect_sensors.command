#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -x .venv-gateway/bin/python ]; then bash setup_mac.command; fi
if [ ! -f .local/gateway.json ]; then
  printf '%s\n' 'Configure your portal URL and scoped bench token first: bash configure_gateway.command'
  exit 1
fi
.venv-gateway/bin/python mac-gateway/gateway.py --list-ports
printf '%s\n' 'Close other serial monitors. Select the exact /dev/cu.* port for your verified ESP32 board.'
read -r -p 'Serial port: ' serial_port
printf '%s\n' 'Sensor-only capture: motor, driver and 12V motor supply must remain disconnected. Review the guide and exact board/pinouts first.'
read -r -p 'Type SENSOR-ONLY to confirm that review: ' confirmation
if [ "$confirmation" != SENSOR-ONLY ]; then exit 1; fi
exec .venv-gateway/bin/python mac-gateway/gateway.py --port "$serial_port" --confirm-sensor-only --seconds 600
