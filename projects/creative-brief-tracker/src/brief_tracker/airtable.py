"""Small Airtable REST client: paged reads and idempotent, ten-record upserts."""

import time
from urllib.parse import quote

import httpx


class AirtableError(RuntimeError):
    """Safe error with no server response body or authentication details."""


class Airtable:
    def __init__(
        self,
        base_id,
        token,
        *,
        endpoint="https://api.airtable.com/v0",
        transport=None,
        sleep=time.sleep,
    ):
        # Prevent accidental token disclosure to a configurable remote service.
        # The sandbox is a special case with a fixed fake credential.
        url = httpx.URL(endpoint)
        local = url.host in ("127.0.0.1", "localhost") and token == "sandbox-only"
        if endpoint != "https://api.airtable.com/v0" and not local:
            raise ValueError("Only Airtable or the local sandbox endpoint is allowed")
        if not base_id or not token:
            raise ValueError("AIRTABLE_BASE_ID and AIRTABLE_TOKEN are required")
        self.url = f"{endpoint.rstrip('/')}/{quote(base_id, safe='')}"
        self.schema_url = f"{endpoint.rstrip('/')}/meta/bases/{quote(base_id, safe='')}/tables"
        self.sleep = sleep
        self.last = None
        self.requests = 0
        self.http = httpx.Client(
            headers={"Authorization": f"Bearer {token}"},
            timeout=20,
            transport=transport,
            follow_redirects=False,
        )

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.http.close()

    def _request(self, method, table, *, schema=False, **kwargs):
        for attempt in range(3):
            if self.last is not None:
                self.sleep(max(0, 0.21 - (time.monotonic() - self.last)))
            self.last = time.monotonic()
            self.requests += 1
            try:
                url = self.schema_url if schema else f"{self.url}/{quote(table, safe='')}"
                response = self.http.request(method, url, **kwargs)
            except httpx.TransportError:
                if method != "POST" and attempt < 2:
                    self.sleep(2**attempt)
                    continue
                raise AirtableError("Airtable network request failed") from None
            if (
                method != "POST"
                and (response.status_code == 429 or response.status_code >= 500)
                and attempt < 2
            ):
                self.sleep(30 if response.status_code == 429 else 2**attempt)
                continue
            if response.is_error:
                raise AirtableError(
                    f"Airtable HTTP {response.status_code}; check base, schema, "
                    "token scopes or quota"
                )
            if response.status_code != 200:
                raise AirtableError(f"Unexpected Airtable HTTP {response.status_code}")
            try:
                return response.json()
            except ValueError:
                raise AirtableError("Invalid JSON from Airtable") from None
        raise AssertionError("unreachable")

    def schema_request(self, method, body=None):
        # Table creation is not idempotent: never retry POST automatically.
        # A subsequent setup command discovers tables created before an interruption.
        return self._request(method, "", schema=True, **({"json": body} if body else {}))

    def list_records(self, table):
        records, params, offsets = [], {"pageSize": 100}, set()
        while True:
            page = self._request("GET", table, params=params)
            records.extend(page["records"])
            offset = page.get("offset")
            if not offset:
                return records
            if offset in offsets:
                raise AirtableError("Repeated pagination offset")
            offsets.add(offset)
            params["offset"] = offset

    def upsert(self, table, fields):
        result = []
        for start in range(0, len(fields), 10):
            page = self._request(
                "PATCH",
                table,
                json={
                    "performUpsert": {"fieldsToMergeOn": ["Key"]},
                    "records": [{"fields": f} for f in fields[start : start + 10]],
                },
            )
            result.extend(page["records"])
        return result
