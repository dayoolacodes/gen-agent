"""Forecast counts from today, not from the last reading. Uses a throwaway JSON store and the mock provider."""
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

os.environ["JSON_STORE"] = os.path.join(tempfile.mkdtemp(), "store.json")
os.environ["VEND_PROVIDER"] = "mock"
os.environ.pop("SHEET_ID", None)
os.environ.pop("GOOGLE_SA_JSON_CONTENT", None)

from tools import server as s  # noqa: E402


def add(hours_ago, kind, litres="", cost="", units=""):
    ts = (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat(timespec="seconds")
    s.store.append("energy", {"ts": ts, "type": kind, "litres": litres, "cost_ngn": cost,
                              "meter_units": units, "logged_by": "test", "note": ""})


class Forecast(unittest.TestCase):
    def setUp(self):
        s.store._save({"energy": [], "tokens": [], "requeries": []})

    def test_stale_tank_reading_runs_down_to_empty(self):
        # 12 L/day established between two readings, last reading 24 L eight days ago.
        add(8 * 24 + 48, "diesel_level", litres=48)
        add(8 * 24, "diesel_level", litres=24)
        d = s.get_energy_summary(7)
        self.assertEqual(d["diesel"]["litres_per_day"], 12.0)
        self.assertEqual(d["diesel"]["on_hand_litres"], 0.0)
        self.assertEqual(d["diesel"]["days_left"], 0.0)
        self.assertEqual(d["diesel"]["last_reading_days_ago"], 8.0)
        self.assertTrue(any("probably run out" in a for a in d["alerts"]))
        self.assertTrue(any("Tank level last reported 8 days ago" in a for a in d["alerts"]))
        self.assertFalse(any("run out in about 0.0" in a for a in d["alerts"]))  # no duplicate countdown

    def test_fresh_tank_reading_is_used_almost_as_is(self):
        add(48 + 1, "diesel_level", litres=48)
        add(1, "diesel_level", litres=24)
        d = s.get_energy_summary(7)["diesel"]
        self.assertAlmostEqual(d["on_hand_litres"], 23.5, delta=0.1)  # 1 hour at 12 L/day
        self.assertAlmostEqual(d["days_left"], 2.0, delta=0.1)

    def test_meter_estimate_subtracts_usage_since_reading(self):
        add(24 * 3, "meter", units=156)
        add(24 * 2, "meter", units=128)  # 28 units/day; reading is two days old
        m = s.get_energy_summary(7)["meter"]
        self.assertEqual(m["units_per_day"], 28.0)
        self.assertAlmostEqual(m["units_now"], 72.0, delta=0.1)
        self.assertAlmostEqual(m["days_left"], 2.6, delta=0.1)

    def test_top_up_builds_on_todays_estimate(self):
        add(24 * 3, "meter", units=156)
        add(24 * 2, "meter", units=128)  # about 72 left today
        r = s.buy_units("62101234567", 9000, "owner")  # mock ok: 9000 / 225 = 40 units
        self.assertEqual(r["status"], "ok")
        last = sorted((x for x in s.store.rows("energy") if x["type"] == "meter"), key=s._ts)[-1]
        self.assertEqual(last["logged_by"], "system")
        self.assertAlmostEqual(float(last["meter_units"]), 112.0, delta=0.2)


if __name__ == "__main__":
    unittest.main()
