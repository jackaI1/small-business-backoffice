"""Atomic immutable imports; reruns reuse a content hash rather than duplicating cash."""

import json
from dataclasses import asdict
from datetime import date
from decimal import Decimal
from importlib.resources import files
from uuid import uuid4

import psycopg
from psycopg.types.json import Jsonb

from .models import Account, Dataset, Entry, Flow, Rate


def json_default(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, date):
        return value.isoformat()
    raise TypeError(type(value).__name__)


def dumps(value):
    return json.dumps(value, default=json_default, indent=2)


def initialize(conn):
    conn.execute(files("cashforecast").joinpath("schema.sql").read_text())


def store(conn, data: Dataset):
    # Serializes simultaneous import of the same hash, without blocking other datasets.
    conn.execute("SELECT pg_advisory_xact_lock(%s)", (int(data.id[:15], 16),))
    inserted = conn.execute(
        "INSERT INTO datasets(id) VALUES (%s) ON CONFLICT DO NOTHING RETURNING id", (data.id,)
    ).fetchone()
    if not inserted:
        return False
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO accounts VALUES (%s,%s,%s,%s,%s,%s)",
            [(data.id, *asdict(a).values()) for a in data.accounts],
        )
        for source, rows in (("bank", data.bank), ("ledger", data.ledger)):
            cur.executemany(
                "INSERT INTO entries VALUES (%s,%s,%s,%s,%s,%s,%s)",
                [(data.id, source, *asdict(e).values()) for e in rows],
            )
        cur.executemany(
            "INSERT INTO expected_flows VALUES (%s,%s,%s,%s,%s,%s,%s)",
            [(data.id, *asdict(f).values()) for f in data.flows],
        )
        cur.executemany(
            "INSERT INTO fx_rates VALUES (%s,%s,%s,%s)",
            [(data.id, *asdict(r).values()) for r in data.rates],
        )
    return True


def retrieve(conn, dataset_id: str) -> Dataset:
    if not conn.execute("SELECT 1 FROM datasets WHERE id=%s", (dataset_id,)).fetchone():
        raise ValueError("unknown dataset hash")
    accounts = tuple(
        Account(*r)
        for r in conn.execute(
            "SELECT id,currency,balance_date,bank_opening,ledger_opening FROM accounts "
            "WHERE dataset_id=%s ORDER BY id",
            (dataset_id,),
        )
    )

    def entries(source):
        return tuple(
            Entry(*r)
            for r in conn.execute(
                "SELECT id,account,posted_date,amount,reference FROM entries "
                "WHERE dataset_id=%s AND source=%s ORDER BY posted_date,id",
                (dataset_id, source),
            )
        )

    flows = tuple(
        Flow(*r)
        for r in conn.execute(
            "SELECT id,account,due,amount,description,settled_bank_id FROM expected_flows "
            "WHERE dataset_id=%s ORDER BY due,id",
            (dataset_id,),
        )
    )
    rates = tuple(
        Rate(*r)
        for r in conn.execute(
            "SELECT currency,rate_date,cad_per_unit FROM fx_rates WHERE dataset_id=%s "
            "ORDER BY currency,rate_date",
            (dataset_id,),
        )
    )
    return Dataset(dataset_id, accounts, entries("bank"), entries("ledger"), flows, rates)


def save_run(conn, dataset_id, as_of, window, minimum, result):
    run_id = str(uuid4())
    result["run_id"] = run_id
    conn.execute(
        "INSERT INTO report_runs(id,dataset_id,as_of,date_window,minimum_cad,result) "
        "VALUES (%s,%s,%s,%s,%s,%s)",
        (run_id, dataset_id, as_of, window, minimum, Jsonb(result, dumps=dumps)),
    )
    return run_id


def connect(url):
    return psycopg.connect(url, connect_timeout=10)
