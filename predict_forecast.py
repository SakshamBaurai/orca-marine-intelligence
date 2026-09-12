"""
ORCA Forecast Pipeline Root Entrypoint
Allows running 'python predict_forecast.py' directly from the workspace root.
"""
import runpy
import sys
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parent
TARGET_SCRIPT = ROOT_DIR / "core_scripts" / "predict_forecast.py"

if not TARGET_SCRIPT.exists():
    raise FileNotFoundError(f"Could not find core script at: {TARGET_SCRIPT}")

runpy.run_path(str(TARGET_SCRIPT), run_name="__main__")
