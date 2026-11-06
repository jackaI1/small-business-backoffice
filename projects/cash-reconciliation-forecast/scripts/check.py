"""Run PostgreSQL tests and the demo with an owned, automatically cleaned-up cluster.

Requires initdb, postgres and pg_ctl on PATH (brew install postgresql@16 on macOS).
No existing cluster is touched. Output artifacts remain; server data is temporary.
"""

import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    missing = [exe for exe in ("initdb", "postgres", "pg_ctl") if not shutil.which(exe)]
    if missing:
        raise SystemExit(f"Add PostgreSQL bin directory to PATH; missing {', '.join(missing)}")
    with tempfile.TemporaryDirectory(prefix="cash-forecast-pg-") as temp:
        folder = Path(temp)
        data, log = folder / "data", folder / "postgres.log"
        subprocess.run(
            [
                "initdb",
                "-D",
                str(data),
                "-A",
                "trust",
                "-U",
                "postgres",
                "--no-locale",
                "--encoding=UTF8",
            ],
            stdout=subprocess.DEVNULL,
            check=True,
        )
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        env = dict(os.environ, TEST_DATABASE_URL=f"postgresql://postgres@127.0.0.1:{port}/postgres")
        env["DATABASE_URL"] = env["TEST_DATABASE_URL"]
        with log.open("w") as stream:
            proc = subprocess.Popen(
                [
                    "postgres",
                    "-D",
                    str(data),
                    "-h",
                    "127.0.0.1",
                    "-p",
                    str(port),
                    "-k",
                    str(folder),
                ],
                stdout=stream,
                stderr=stream,
            )
        ownership = {
            "owner": "scripts/check.py",
            "pid": proc.pid,
            "port": port,
            "started": subprocess.check_output(
                ["ps", "-p", str(proc.pid), "-o", "lstart="], text=True
            ).strip(),
            "cleanup": ["pg_ctl", "-D", str(data), "-m", "fast", "-w", "stop"],
        }
        print(json.dumps(ownership), flush=True)
        old_handlers = {}

        def interrupted(signum, frame):
            raise KeyboardInterrupt

        try:
            for sig in (signal.SIGINT, signal.SIGTERM):
                old_handlers[sig] = signal.signal(sig, interrupted)
            for _ in range(100):
                if proc.poll() is not None:
                    raise RuntimeError("temporary PostgreSQL exited before readiness")
                with socket.socket() as sock:
                    if sock.connect_ex(("127.0.0.1", port)) == 0:
                        break
                time.sleep(0.1)
            else:
                raise RuntimeError("temporary PostgreSQL did not become ready")
            subprocess.run(
                [sys.executable, "-m", "pytest", "-q", "--tb=short"], cwd=ROOT, env=env, check=True
            )
            subprocess.run(
                [
                    "cash-forecast",
                    "--input",
                    "data/synthetic",
                    "--as-of",
                    "2026-10-31",
                    "--output",
                    "output/demo",
                ],
                cwd=ROOT,
                env=env,
                check=True,
            )
        finally:
            for sig, handler in old_handlers.items():
                signal.signal(sig, handler)
            if proc.poll() is None:
                try:
                    stopped = subprocess.run(
                        ownership["cleanup"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        timeout=20,
                    )
                    if stopped.returncode:
                        proc.terminate()
                except subprocess.TimeoutExpired:
                    proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=10)
            with socket.socket() as sock:
                closed = sock.connect_ex(("127.0.0.1", port)) != 0
            print(
                json.dumps(
                    {
                        "pid": proc.pid,
                        "exited": proc.returncode is not None,
                        "port": port,
                        "port_closed": closed,
                    }
                ),
                flush=True,
            )
            if not closed:
                raise RuntimeError("temporary PostgreSQL port is still listening")


if __name__ == "__main__":
    main()
