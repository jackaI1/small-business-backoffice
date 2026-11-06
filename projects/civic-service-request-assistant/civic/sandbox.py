"""Persistent loopback Graph contract sandbox. Synthetic records only."""

import os
import secrets
import sqlite3
from contextlib import closing
from uuid import uuid4

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

COLUMNS = {
    "Title": str,
    "RequestId": str,
    "ServiceType": str,
    "Department": str,
    "Status": str,
    "CreatedAt": str,
    "UpdatedAt": str,
    "Version": int,
}


class Item(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fields: dict


def create_sandbox(db_path=None, token=None):
    import json

    path = db_path or os.getenv("GRAPH_DB", "graph.sqlite3")
    access = token if token is not None else os.getenv("GRAPH_TOKEN", "")
    with closing(sqlite3.connect(path)) as db:
        db.execute(
            "CREATE TABLE IF NOT EXISTS items "
            "(id TEXT PRIMARY KEY, site TEXT, list_id TEXT, fields TEXT)"
        )
        db.commit()
    app = FastAPI(title="Local Graph sandbox", docs_url=None, redoc_url=None)

    def auth(authorization: str = Header(default="")):
        if not access or not secrets.compare_digest(authorization, f"Bearer {access}"):
            raise HTTPException(401, "Sandbox token required")

    def validate(fields):
        if set(fields) != set(COLUMNS) or any(
            type(fields[k]) is not kind for k, kind in COLUMNS.items()
        ):
            raise HTTPException(422, "Fields must match the documented service-request schema")

    prefix = "/v1.0/sites/{site}/lists/{list_id}/items"

    @app.exception_handler(HTTPException)
    async def graph_error(request, error):
        return JSONResponse(
            {"error": {"code": str(error.status_code), "message": error.detail}},
            status_code=error.status_code,
        )

    @app.get(prefix, dependencies=[Depends(auth)])
    def items(site: str, list_id: str):
        with closing(sqlite3.connect(path)) as db:
            rows = db.execute(
                "SELECT id,fields FROM items WHERE site=? AND list_id=?", (site, list_id)
            ).fetchall()
        return {"value": [{"id": row[0], "fields": json.loads(row[1])} for row in rows]}

    @app.post(prefix, status_code=201, dependencies=[Depends(auth)])
    def create(site: str, list_id: str, item: Item):
        validate(item.fields)
        item_id = str(uuid4())
        with closing(sqlite3.connect(path)) as db:
            db.execute(
                "INSERT INTO items VALUES (?,?,?,?)",
                (item_id, site, list_id, json.dumps(item.fields)),
            )
            db.commit()
        return {"id": item_id, "fields": item.fields}

    @app.patch(prefix + "/{item_id}/fields", dependencies=[Depends(auth)])
    def update(site: str, list_id: str, item_id: str, fields: dict):
        validate(fields)
        with closing(sqlite3.connect(path)) as db:
            changed = db.execute(
                "UPDATE items SET fields=? WHERE id=? AND site=? AND list_id=?",
                (json.dumps(fields), item_id, site, list_id),
            ).rowcount
            db.commit()
        if not changed:
            raise HTTPException(404, "Item not found")
        return fields

    return app
