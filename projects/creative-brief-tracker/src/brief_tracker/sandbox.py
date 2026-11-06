"""Scoped localhost Airtable subset for demos, not a production service."""

import json
import os
import subprocess
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from urllib.parse import parse_qs, unquote, urlsplit


@contextmanager
def sandbox(page_size=100):
    tables = {t: [] for t in ("Assignees", "Briefs", "Deliverables", "Approvals")}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def reply(self, code, payload):
            body = json.dumps(payload).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def table(self):
            path = urlsplit(self.path).path.split("/")
            if len(path) != 4 or path[1:3] != ["v0", "appSandbox"]:
                self.reply(404, {})
                return None
            name = unquote(path[3])
            if self.headers.get("Authorization") != "Bearer sandbox-only":
                self.reply(401, {})
                return None
            if name not in tables:
                self.reply(404, {})
                return None
            return tables[name]

        def do_GET(self):
            rows = self.table()
            if rows is None:
                return
            params = parse_qs(urlsplit(self.path).query)
            start = int(params.get("offset", ["0"])[0])
            limit = min(page_size, int(params.get("pageSize", ["100"])[0]))
            payload = {"records": deepcopy(rows[start : start + limit])}
            if start + limit < len(rows):
                payload["offset"] = str(start + limit)
            self.reply(200, payload)

        def do_PATCH(self):
            rows = self.table()
            if rows is None:
                return
            try:
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
                if (
                    body.get("performUpsert") != {"fieldsToMergeOn": ["Key"]}
                    or not 1 <= len(body["records"]) <= 10
                ):
                    raise ValueError("Unsupported batch")
                if any(not r["fields"].get("Key") for r in body["records"]):
                    raise ValueError("Missing Key")
            except (ValueError, KeyError, TypeError):
                self.reply(422, {})
                return
            result = []
            for entry in body["records"]:
                fields = entry["fields"]
                matches = [r for r in rows if r["fields"]["Key"] == fields["Key"]]
                if matches:
                    record = matches[0]
                    record["fields"].update(fields)
                else:
                    record = {
                        "id": f"rec{sum(len(t) for t in tables.values()) + 1:014d}",
                        "fields": dict(fields),
                    }
                    rows.append(record)
                result.append(deepcopy(record))
            self.reply(200, {"records": result})

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    thread = Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.05}, name="brief-tracker-sandbox"
    )
    pid = os.getpid()
    process_start = subprocess.check_output(
        ["ps", "-p", str(pid), "-o", "lstart="], text=True
    ).strip()
    metadata = {
        "owner": "brief-tracker sandbox context",
        "pid": pid,
        "process_start": process_start,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "port": server.server_port,
        "endpoint": f"http://127.0.0.1:{server.server_port}/v0",
        "cleanup": f"context exit; interrupt owning command with kill -INT {pid}",
        "closed": False,
    }
    thread.start()
    try:
        yield metadata
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        metadata["closed"] = not thread.is_alive() and server.socket.fileno() == -1
        if not metadata["closed"]:
            raise RuntimeError("Sandbox cleanup did not finish")
