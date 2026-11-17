"""Resilient dev server launcher that bootstraps .venv on fresh containers."""

from __future__ import annotations

import os
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV_DIR = ROOT / ".venv"
VENV_PYTHON = VENV_DIR / "bin" / "python"
VENV_PIP = VENV_DIR / "bin" / "pip"
VENV_UVICORN = VENV_DIR / "bin" / "uvicorn"
REQUIREMENTS = ROOT / "requirements.txt"


def ensure_venv() -> None:
    if VENV_UVICORN.exists():
        return

    print("[edge-lab] Bootstrapping Python virtual environment...", flush=True)
    if not VENV_PYTHON.exists():
        subprocess.run(
            [sys.executable, "-m", "venv", "--without-pip", str(VENV_DIR)],
            check=True,
        )

    if not VENV_PIP.exists():
        tmp_get_pip = Path("/tmp/get-pip.py")
        urllib.request.urlretrieve("https://bootstrap.pypa.io/get-pip.py", tmp_get_pip)
        try:
            subprocess.run([str(VENV_PYTHON), str(tmp_get_pip)], check=True)
        finally:
            tmp_get_pip.unlink(missing_ok=True)

    subprocess.run([str(VENV_PIP), "install", "-r", str(REQUIREMENTS)], check=True)


def main() -> None:
    ensure_venv()
    os.execv(
        str(VENV_UVICORN),
        [str(VENV_UVICORN), "app.main:app", "--host", "0.0.0.0", "--port", "3000"],
    )


if __name__ == "__main__":
    main()
