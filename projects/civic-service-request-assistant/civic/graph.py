from urllib.parse import quote

import httpx

from civic.privacy import export_fields


class GraphExport:
    def __init__(self, settings, store, client=None):
        self.settings, self.store, self.client = settings, store, client

    def export(self, request_id):
        if not self.settings.graph_token:
            raise ValueError("Configure GRAPH_TOKEN and start the local Graph sandbox.")
        s = self.settings
        path = f"/sites/{quote(s.site, safe='')}/lists/{quote(s.list_id, safe='')}/items"
        # Serialize exports and workflow writes. No blind retry of non-idempotent POST.
        with self.store.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM requests WHERE id=?", (request_id,)).fetchone()
            if not row:
                raise KeyError(request_id)
            row = dict(row)
            fields = export_fields(row)
            method, body = "POST", {"fields": fields}
            if row["graph_id"]:
                path += f"/{quote(row['graph_id'], safe='')}/fields"
                method, body = "PATCH", fields
            kwargs = dict(json=body, headers={"Authorization": f"Bearer {s.graph_token}"})
            if self.client:
                response = self.client.request(method, s.graph_url + path, **kwargs)
            else:
                with httpx.Client(timeout=10, trust_env=False) as client:
                    response = client.request(method, s.graph_url + path, **kwargs)
            response.raise_for_status()
            item_id = row["graph_id"]
            if not item_id:
                data = response.json()
                if (
                    not isinstance(data, dict)
                    or not isinstance(data.get("id"), str)
                    or not data["id"]
                ):
                    raise ValueError("Graph response did not contain an item ID")
                item_id = data["id"]
            db.execute("UPDATE requests SET graph_id=? WHERE id=?", (item_id, request_id))
        return {"id": item_id, "fields": fields}
