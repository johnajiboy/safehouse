"""Load the sample reports used in the demo.

Run:  python -m safehome.seed
With an API key set, every report is read by Claude, which takes a little while.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta

from . import config, service, store


def reported_time(item: dict, now: datetime) -> datetime:
    """Sample reports say how long ago they arrived, so deadlines vary on the dashboard."""
    if "hours_ago" in item:
        return now - timedelta(hours=item["hours_ago"])
    when = now - timedelta(hours=1)
    stepped = 0
    while stepped < item.get("working_days_ago", 0):
        when -= timedelta(days=1)
        if when.weekday() < 5:
            stepped += 1
    return when


def load_sample_data() -> None:
    store.reset()
    now = datetime.now()
    with open(config.DATA_DIR / "sample_reports.json", encoding="utf-8") as f:
        items = json.load(f)
    for item in items:
        case = service.submit_report(item["text"], item["address"], item["area"],
                                     reported_at=reported_time(item, now))
        print(f"{case.ref}  {case.level:15} {case.hazard:24} {case.address}")
    store.log("System", f"Loaded {len(items)} sample reports")


if __name__ == "__main__":
    load_sample_data()
