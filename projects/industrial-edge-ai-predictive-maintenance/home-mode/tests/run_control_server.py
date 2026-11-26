"""Test-only watchdog to diagnose child startup without hiding timeouts."""
import faulthandler
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
faulthandler.enable()
faulthandler.dump_traceback_later(8,file=sys.stderr)
from home_server import main
try:
    raise SystemExit(main())
finally:
    faulthandler.cancel_dump_traceback_later()
