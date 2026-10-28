"""Seed a week of made-up history for Adaeze Provisions so the first summary is not empty.

    python scripts/seed_sheet.py          # writes to the Sheet if SHEET_ID + credentials are set, else data/store.json
    python scripts/seed_sheet.py --force  # write even if the energy tab already has rows

Times are relative to now and end a few hours ago. Every row has note "seed" so it can be filtered out.
Shape: about 29 kWh a day off the meter with one NGN 20,000 top-up, about 12 litres of diesel a day,
a 20-25 litre jerrycan every two days at NGN 1,300-1,350 a litre (NGN 126,250 for the week, under budget).
"""
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.storage import get_store  # noqa: E402

# (hours ago, type, litres, cost_ngn, meter_units, logged_by)
HISTORY = [
    (160, "diesel", 25, 32500, "", "Ade"),
    (150, "meter", "", "", 180, "Ade"),
    (136, "diesel_level", 20, "", "", "Ade"),
    (126, "meter", "", "", 152, "Ade"),
    (112, "diesel", 25, 33000, "", "Tunde"),
    (102, "meter", "", "", 121, "Ade"),
    (88, "diesel_level", 21, "", "", "Ade"),
    (78, "meter", "", "", 95, "Ade"),
    (74, "meter", "", "", 183.9, "Ade"),  # after a NGN 20,000 top-up at the vendor
    (64, "diesel", 25, 33750, "", "Ade"),
    (54, "meter", "", "", 155, "Ade"),
    (40, "diesel_level", 22, "", "", "Ade"),
    (30, "meter", "", "", 126, "Ade"),
    (16, "diesel", 20, 27000, "", "Tunde"),
    (6, "meter", "", "", 98, "Ade"),
    (4, "diesel_level", 24, "", "", "Ade"),
]


def main():
    store = get_store()
    print(f"store: {type(store).__name__}")
    if store.rows("energy") and "--force" not in sys.argv:
        sys.exit("energy tab already has rows; rerun with --force to add the seed anyway")
    now = datetime.now(timezone.utc)
    for hours, kind, litres, cost, units, who in HISTORY:
        ts = (now - timedelta(hours=hours)).isoformat(timespec="seconds")
        store.append("energy", {"ts": ts, "type": kind, "litres": litres, "cost_ngn": cost,
                                "meter_units": units, "logged_by": who, "note": "seed"})
    print(f"wrote {len(HISTORY)} rows")


if __name__ == "__main__":
    main()
