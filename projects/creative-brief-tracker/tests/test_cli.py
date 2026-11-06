import json
import os
import subprocess
import sys


def test_demo_runs_without_credentials_and_writes_outputs(tmp_path):
    env = {k: v for k, v in os.environ.items() if not k.startswith("AIRTABLE_")}
    run = subprocess.run(
        [sys.executable, "-m", "brief_tracker", "demo", "--out", str(tmp_path / "drafts")],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert run.returncode == 0, run.stderr
    summary = json.loads(run.stdout)
    assert summary["tasks"] == 8
    assert summary["overdue_approvals"] == 2
    assert summary["overloaded"] == 1
    assert summary["drafts"] == 3
    assert summary["sandbox"]["closed"] is True
    assert len(list((tmp_path / "drafts").glob("*.eml"))) == 3


def test_live_command_missing_credentials_is_clear():
    env = {k: v for k, v in os.environ.items() if not k.startswith("AIRTABLE_")}
    run = subprocess.run(
        [sys.executable, "-m", "brief_tracker", "remind"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert run.returncode == 2
    assert "AIRTABLE_BASE_ID and AIRTABLE_TOKEN" in run.stderr
    assert "Traceback" not in run.stderr
