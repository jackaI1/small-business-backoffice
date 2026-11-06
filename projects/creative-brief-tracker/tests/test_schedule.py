from datetime import date

import pytest

from brief_tracker.schedule import workback

STEPS = [
    {"key": "design", "name": "Design", "assignee": "artist", "days": 3, "hours": 12},
    {
        "key": "review",
        "name": "Review",
        "assignee": "lead",
        "days": 2,
        "hours": 2,
        "approval": True,
    },
]


def test_workback_inclusive_weekdays():
    tasks = workback("2026-11-16", STEPS)
    assert [(t["start"], t["due"]) for t in tasks] == [
        ("2026-11-10", "2026-11-12"),
        ("2026-11-13", "2026-11-16"),
    ]
    assert tasks[0]["hours"] == 12
    assert "start" not in STEPS[0]


def test_weekend_final_moves_to_friday():
    assert workback("2026-11-15", STEPS)[-1]["due"] == "2026-11-13"


@pytest.mark.parametrize(
    "steps",
    [
        [],
        [dict(STEPS[0], days=0)],
        [dict(STEPS[0], days=True)],
        [dict(STEPS[0], days=1.5)],
        [dict(STEPS[0], hours=-1)],
        [dict(STEPS[0], hours=float("nan"))],
        [dict(STEPS[0], name="")],
        [dict(STEPS[0], assignee="")],
        [dict(STEPS[0], key="../bad")],
        [STEPS[0], STEPS[0]],
        [dict(STEPS[0], approval="yes")],
    ],
)
def test_invalid_steps(steps):
    with pytest.raises(ValueError):
        workback("2026-11-16", steps)


def test_invalid_date():
    with pytest.raises(ValueError):
        workback("next Monday", STEPS)


def test_date_object():
    assert workback(date(2026, 11, 16), STEPS)[-1]["due"] == "2026-11-16"
