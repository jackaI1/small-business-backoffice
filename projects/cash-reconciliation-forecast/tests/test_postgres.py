import json
import os
import subprocess
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

import psycopg
import pytest

from cashforecast import db
from cashforecast.cli import run

pytestmark = pytest.mark.postgres
SOURCE = Path(__file__).resolve().parents[1] / "data/synthetic"


def test_real_postgres_roundtrip_and_idempotent_import(postgres_url, sample):
    with db.connect(postgres_url) as conn:
        db.initialize(conn)
        assert db.store(conn, sample)
        assert not db.store(conn, sample)
        loaded = db.retrieve(conn, sample.id)
        assert set(loaded.bank) == set(sample.bank)
        assert set(loaded.ledger) == set(sample.ledger)
        assert loaded.accounts == tuple(sorted(sample.accounts, key=lambda a: a.id))
        assert conn.execute("SELECT count(*) FROM entries").fetchone()[0] == 28


def test_import_rolls_back_on_failure(postgres_url, sample):
    with pytest.raises(RuntimeError):
        with db.connect(postgres_url) as conn:
            db.initialize(conn)
            db.store(conn, sample)
            raise RuntimeError("simulated interrupted import")
    with db.connect(postgres_url) as conn:
        db.initialize(conn)
        assert conn.execute("SELECT count(*) FROM datasets").fetchone()[0] == 0


def test_database_enforces_no_orphan_entry(postgres_url, sample):
    with db.connect(postgres_url) as conn:
        db.initialize(conn)
        db.store(conn, sample)
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        with db.connect(postgres_url) as conn:
            conn.execute(
                "INSERT INTO entries VALUES (%s,'bank','orphan','missing','2026-10-31',1,'x')",
                (sample.id,),
            )


def test_pipeline_reuses_dataset_and_keeps_run_audit(postgres_url, tmp_path):
    for _ in range(2):
        result = run(postgres_url, SOURCE, date(2026, 10, 31), Decimal("15000"), 3, tmp_path)
    assert result["forecast"]["opening_cad"] == Decimal("60406.88")
    with db.connect(postgres_url) as conn:
        assert conn.execute("SELECT count(*) FROM datasets").fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM entries").fetchone()[0] == 28
        assert conn.execute("SELECT count(*) FROM report_runs").fetchone()[0] == 2
        stored = conn.execute(
            "SELECT result FROM report_runs WHERE id=%s", (result["run_id"],)
        ).fetchone()[0]
    assert stored["forecast"]["opening_cad"] == "60406.88"
    assert json.loads((tmp_path / "results.json").read_text())["run_id"] == result["run_id"]
    assert (tmp_path / "cash-report.xlsx").stat().st_size > 10000


def test_installed_cli(postgres_url, tmp_path):
    env = dict(os.environ, DATABASE_URL=postgres_url)
    output = subprocess.run(
        [
            sys.executable,
            "-m",
            "cashforecast.cli",
            "--input",
            str(SOURCE),
            "--as-of",
            "2026-10-31",
            "--output",
            str(tmp_path),
        ],
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )
    assert "8 cleared pairs; 1 amount variances; 7 unmatched records" in output.stdout
    assert "13 weeks; opening CAD 60406.88" in output.stdout
