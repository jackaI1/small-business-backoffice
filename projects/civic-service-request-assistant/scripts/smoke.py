"""Real Ollama + HTTP + browser verification, with scoped fixture cleanup on every path."""

import json
import os
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
from contextlib import ExitStack
from pathlib import Path

import httpx
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts"


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def metadata(pid):
    output = subprocess.run(
        ["ps", "-p", str(pid), "-o", "lstart=", "-o", "comm="],
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    return output or None


def listening(port):
    with socket.socket() as sock:
        sock.settimeout(0.2)
        return sock.connect_ex(("127.0.0.1", port)) == 0


class Fixtures:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.owned = []
        self.report = []

    def save(self):
        (ARTIFACTS / "resources.json").write_text(json.dumps(self.report, indent=2))

    def start(self, name, args, env, port=None):
        log = open(self.directory / f"{name}.log", "w+")
        process = subprocess.Popen(
            args, cwd=ROOT, env=env, stdout=log, stderr=log, start_new_session=True
        )
        record = {
            "owner": "scripts/smoke.py",
            "name": name,
            "pid": process.pid,
            "start": metadata(process.pid),
            "port": port,
            "cleanup": f"kill -TERM -- -{process.pid} (owned process group only)",
            "stopped": False,
        }
        self.owned.append((process, log, record))
        self.report.append(record)
        self.save()
        return process

    def wait_http(self, url, process, timeout=45):
        deadline = time.monotonic() + timeout
        with httpx.Client(trust_env=False, timeout=1) as client:
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError("Owned fixture exited before becoming ready")
                try:
                    if client.get(url).status_code == 200:
                        return
                except httpx.HTTPError:
                    pass
                time.sleep(0.2)
        raise TimeoutError(f"Fixture did not become ready on {url}")

    def browser_records(self):
        output = subprocess.run(
            ["ps", "-axo", "pid=,ppid=,comm="], capture_output=True, text=True, check=True
        ).stdout
        children = []
        parents = {os.getpid()}
        rows = [line.strip().split(None, 2) for line in output.splitlines()]
        for _ in range(6):
            for parts in rows:
                if len(parts) == 3 and int(parts[1]) in parents and int(parts[0]) not in parents:
                    pid = int(parts[0])
                    parents.add(pid)
                    if any(
                        word in parts[2].lower() for word in ("chrome", "chromium", "playwright")
                    ):
                        children.append(
                            {
                                "owner": "scripts/smoke.py browser context",
                                "pid": pid,
                                "start": metadata(pid),
                                "port": None,
                                "cleanup": "context.close(); browser.close(); Playwright.stop()",
                                "stopped": False,
                            }
                        )
        self.report.extend(children)
        self.save()
        return children

    def close(self):
        for process, log, record in reversed(self.owned):
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=12)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=5)
            record["stopped"] = process.poll() is not None
            if record["port"]:
                record["port_closed"] = not listening(record["port"])
            log.close()
        self.save()
        assert all(r["stopped"] and r.get("port_closed", True) for r in self.report), self.report


def browser_check(url, staff_token, fixtures):
    records = []
    try:
        with sync_playwright() as playwright, ExitStack() as cleanup:
            browser = playwright.chromium.launch(headless=True)
            cleanup.callback(browser.close)
            context = browser.new_context(viewport={"width": 1280, "height": 1000})
            cleanup.callback(context.close)
            page = context.new_page()
            cleanup.callback(page.close)
            records = fixtures.browser_records()
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(url)
            page.get_by_label("Location or nearest intersection").fill("Maple Road at Cedar Street")
            page.get_by_label("What did you notice?").fill("A pothole beside the east curb.")
            page.get_by_role("button", name="Send service request").click()
            expect(page.get_by_label("Your private receipt")).to_be_visible()
            receipt = page.get_by_label("Your private receipt").input_value()
            page.get_by_role("button", name="Check status").click()
            expect(page.locator("#track-result")).to_contain_text("submitted")
            page.get_by_label("Your question").fill("When should I report missed waste collection?")
            page.get_by_role("button", name="Ask a question").click()
            expect(page.locator("#faq-result")).to_contain_text(
                "Source: Waste collection guide", timeout=120000
            )
            page.screenshot(path=str(ARTIFACTS / "resident.png"), full_page=True)
            page.set_viewport_size({"width": 390, "height": 844})
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            page.screenshot(path=str(ARTIFACTS / "resident-mobile.png"), full_page=True)
            page.set_viewport_size({"width": 1280, "height": 1000})
            page.get_by_role("link", name="Staff desk", exact=True).click()
            page.get_by_label("Staff access token").fill(staff_token)
            page.get_by_role("button", name="Open queue").click()
            page.locator(".queue-item").filter(has_text="Maple Road at Cedar Street").first.click()
            for status in ["approved", "in_progress", "resolved"]:
                page.get_by_label("Next status").select_option(status)
                page.get_by_label("Decision or work note").fill("Reviewed and handled safely")
                page.get_by_role("button", name="Save status change").click()
                expect(page.locator("#detail .detail-row").first).to_contain_text(
                    status.replace("_", " ")
                )
            page.get_by_text("Preview safe list export", exact=True).click()
            page.get_by_role("button", name="Export to local list").click()
            expect(page.locator("#staff-message")).to_contain_text("Exported to local list item")
            page.screenshot(path=str(ARTIFACTS / "staff.png"), full_page=True)
            page.set_viewport_size({"width": 390, "height": 844})
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            page.screenshot(path=str(ARTIFACTS / "staff-mobile.png"), full_page=True)
            page.get_by_role("button", name="Lock desk").click()
            expect(page.locator("#workspace")).to_be_hidden()
            page.goto(url)
            page.get_by_label("Private receipt", exact=True).fill(receipt)
            page.get_by_role("button", name="Check status").click()
            expect(page.locator("#track-result")).to_contain_text("resolved")
            assert not errors, errors
    finally:
        for record in records:
            record["stopped"] = metadata(record["pid"]) != record["start"]
        fixtures.save()


def main():
    if not shutil.which("ollama"):
        raise SystemExit("Install Ollama first: https://ollama.com/download")
    ARTIFACTS.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="civic-smoke-") as directory:
        fixtures = Fixtures(directory)
        model_port, graph_port, app_port = free_port(), free_port(), free_port()
        env = {
            **os.environ,
            "OLLAMA_HOST": f"127.0.0.1:{model_port}",
            "OLLAMA_URL": f"http://127.0.0.1:{model_port}",
            "OLLAMA_NO_CLOUD": "1",
            "OLLAMA_MODELS": str(Path(directory) / "models"),
            "OLLAMA_MODEL": "qwen2.5:0.5b",
            "OLLAMA_NUM_PARALLEL": "1",
            "CIVIC_DB": str(Path(directory) / "requests.sqlite3"),
            "GRAPH_DB": str(Path(directory) / "graph.sqlite3"),
            "CIVIC_STAFF_TOKEN": secrets.token_urlsafe(32),
            "GRAPH_TOKEN": secrets.token_urlsafe(32),
            "GRAPH_BASE_URL": f"http://127.0.0.1:{graph_port}/v1.0",
        }
        try:
            ollama = fixtures.start("ollama", ["ollama", "serve"], env, model_port)
            fixtures.wait_http(env["OLLAMA_URL"] + "/api/tags", ollama)
            pull = fixtures.start("model-pull", ["ollama", "pull", env["OLLAMA_MODEL"]], env)
            assert pull.wait(timeout=420) == 0, "Model download failed"
            graph = fixtures.start(
                "graph",
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "civic.sandbox:create_sandbox",
                    "--factory",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(graph_port),
                    "--no-access-log",
                ],
                env,
                graph_port,
            )
            fixtures.wait_http(f"http://127.0.0.1:{graph_port}/openapi.json", graph)
            app = fixtures.start(
                "app",
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "civic.app:create_app",
                    "--factory",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(app_port),
                    "--no-access-log",
                ],
                env,
                app_port,
            )
            url = f"http://127.0.0.1:{app_port}"
            fixtures.wait_http(url + "/health", app)
            cases = [
                ("How do I report a pothole?", False),
                ("How do I report a streetlight outage?", False),
                ("When should I report missed waste collection?", False),
                ("How do I report park maintenance?", False),
                ("Who is the mayor?", True),
                ("How much are pothole repair fees?", True),
                ("How do I report a pothole? ada@example.invalid", True),
            ]
            evidence = []
            with httpx.Client(base_url=url, trust_env=False, timeout=120) as client:
                for question, abstains in cases:
                    response = client.post("/api/faq", json={"question": question})
                    response.raise_for_status()
                    data = response.json()
                    assert data["abstained"] == abstains, (question, data)
                    if not abstains:
                        assert data["answer"] == data["citation"]["passage"]
                    evidence.append({"question": question, **data})
                assert client.get("/api/staff/requests").status_code == 401
            browser_check(url, env["CIVIC_STAFF_TOKEN"], fixtures)
            (ARTIFACTS / "live-check.json").write_text(
                json.dumps(
                    {
                        "model": env["OLLAMA_MODEL"],
                        "faq_cases": evidence,
                        "browser": "intake, tracking, three status changes, export, lock, mobile",
                    },
                    indent=2,
                )
            )
            print(
                "PASS: 7 real-model FAQ cases and resident/staff browser workflow; "
                "screenshots in artifacts/"
            )
        except BaseException:
            for _, log, record in fixtures.owned:
                log.flush()
                with open(log.name, "rb") as source:
                    source.seek(max(0, source.seek(0, 2) - 1200))
                    content = source.read().decode(errors="replace")
                print(f"{record['name']} log tail: {content}", file=sys.stderr)
            raise
        finally:
            fixtures.close()
            print("Cleanup verified: owned processes stopped, ports closed, browser pages closed.")


if __name__ == "__main__":
    main()
