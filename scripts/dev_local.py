import os
import signal
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable
RUNTIME_ROOT = Path.home() / ".autozs"
DATABASE_PATH = ROOT / "dev.db"


def main() -> None:
    RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "apps" / "api")
    env["DATABASE_URL"] = f"sqlite:///{DATABASE_PATH}"
    env["REDIS_URL"] = "redis://localhost:6379/0"
    env["CORS_ORIGINS"] = "http://127.0.0.1:3000,http://localhost:3000"
    env["CORS_ORIGIN_REGEX"] = "(https?://.*|chrome-extension://.*)"

    api = subprocess.Popen(
        [
            PYTHON,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8000",
        ],
        cwd=RUNTIME_ROOT,
        env=env,
    )
    web = subprocess.Popen(
        [
            PYTHON,
            "-m",
            "http.server",
            "3000",
            "--bind",
            "127.0.0.1",
            "--directory",
            str(ROOT / "apps" / "local_dashboard"),
        ],
        cwd=RUNTIME_ROOT,
        env=env,
    )

    print("Local dashboard: http://127.0.0.1:3000", flush=True)
    print("API docs:        http://127.0.0.1:8000/docs", flush=True)
    print("Press Ctrl+C to stop.", flush=True)

    def stop(_: int, __: object) -> None:
        for process in (web, api):
            process.terminate()
        raise SystemExit(0)

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)

    try:
        api.wait()
    finally:
        web.terminate()


if __name__ == "__main__":
    main()
