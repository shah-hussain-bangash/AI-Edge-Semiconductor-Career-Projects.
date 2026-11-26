"""Test harness: close stdin to deliver the same KeyboardInterrupt as Ctrl+C."""
import _thread
from pathlib import Path
import sys
import threading
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from home_server import main


def interrupt_when_parent_closes_pipe():
    sys.stdin.buffer.read()
    _thread.interrupt_main()


threading.Thread(target=interrupt_when_parent_closes_pipe, daemon=True).start()
raise SystemExit(main())
