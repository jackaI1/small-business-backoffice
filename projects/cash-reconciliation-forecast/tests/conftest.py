import os
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import make_conninfo

from cashforecast.inputs import load_csv

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def sample():
    return load_csv(ROOT / "data/synthetic")


@pytest.fixture
def postgres_url():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("set TEST_DATABASE_URL or run python scripts/check.py for PostgreSQL tests")
    schema = "test_cash_" + uuid4().hex
    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        try:
            yield make_conninfo(url, options=f"-csearch_path={schema}")
        finally:
            conn.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))
