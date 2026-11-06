"""Plan sequential tasks backward using inclusive Monday-to-Friday work days."""

import math
import re
from datetime import date, timedelta


def key(value):
    if not isinstance(value, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", value):
        raise ValueError("Keys must contain 1-80 letters, numbers, underscores or hyphens")
    return value


def number(value, label):
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value < 0
    ):
        raise ValueError(f"{label} must be a finite nonnegative number")
    return value


def parse_date(value):
    return value if type(value) is date else date.fromisoformat(value)


def previous_weekday(day):
    while day.weekday() > 4:
        day -= timedelta(days=1)
    return day


def back(day, count):
    for _ in range(count):
        day = previous_weekday(day - timedelta(days=1))
    return day


def workback(final_due, steps):
    """Return copies with start/due dates; each task ends before the next starts.

    A weekend final date rolls back to Friday. A one-day task starts and ends
    on the same day. Holidays are not excluded.
    """
    due = previous_weekday(parse_date(final_due))
    if not isinstance(steps, list) or not steps:
        raise ValueError("At least one ordered step is required")
    seen = set()
    for step in steps:
        step_key = key(step.get("key"))
        if step_key in seen:
            raise ValueError("Step keys must be unique")
        seen.add(step_key)
        key(step.get("assignee"))
        if not isinstance(step.get("name"), str) or not step["name"].strip():
            raise ValueError("Every step needs a name")
        if type(step.get("days")) is not int or not 1 <= step["days"] <= 260:
            raise ValueError("Step days must be an integer from 1 to 260")
        number(step.get("hours"), "Hours")
        if type(step.get("approval", False)) is not bool:
            raise ValueError("Approval must be true or false")
    tasks = []
    for step in reversed(steps):
        start = back(due, step["days"] - 1)
        tasks.append({**step, "start": start.isoformat(), "due": due.isoformat()})
        due = back(start, 1)
    return list(reversed(tasks))
