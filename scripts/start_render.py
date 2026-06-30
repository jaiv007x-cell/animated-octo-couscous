from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def start_process(args: list[str]) -> subprocess.Popen:
    return subprocess.Popen(args, cwd=ROOT)


def main() -> int:
    port = os.environ.get("PORT", "8501")
    os.environ.setdefault("API_BASE_URL", "http://127.0.0.1:8000")
    os.environ.setdefault("STREAMLIT_SERVER_HEADLESS", "true")
    os.environ.setdefault("STREAMLIT_BROWSER_GATHER_USAGE_STATS", "false")
    Path(ROOT / "storage" / "docs").mkdir(parents=True, exist_ok=True)
    Path(ROOT / "storage" / "snapshots").mkdir(parents=True, exist_ok=True)

    api = start_process([
        sys.executable,
        "-m",
        "uvicorn",
        "app.main:app",
        "--host",
        "127.0.0.1",
        "--port",
        "8000",
    ])
    children = [api]

    if os.environ.get("TELEGRAM_ENABLE_POLLING", "").lower() in {"1", "true", "yes"}:
        children.append(start_process([sys.executable, "scripts/run_telegram_bot.py"]))

    ui = start_process([
        sys.executable,
        "-m",
        "streamlit",
        "run",
        "streamlit_app.py",
        "--server.address",
        "0.0.0.0",
        "--server.port",
        port,
    ])
    children.append(ui)

    def stop_children(*_args) -> None:
        for proc in children:
            if proc.poll() is None:
                proc.terminate()

    signal.signal(signal.SIGTERM, stop_children)
    signal.signal(signal.SIGINT, stop_children)

    while True:
        for proc in children:
            code = proc.poll()
            if code is not None:
                stop_children()
                return code
        time.sleep(2)


if __name__ == "__main__":
    raise SystemExit(main())
