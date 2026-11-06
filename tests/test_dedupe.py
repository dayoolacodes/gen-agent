"""Chord's agent replays earlier write calls on later turns, so identical logs and purchases inside
DEDUPE_MINUTES must not be recorded or bought twice. Throwaway JSON store, mock provider."""
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

os.environ.setdefault("JSON_STORE", os.path.join(tempfile.mkdtemp(), "store.json"))
os.environ["VEND_PROVIDER"] = "mock"
os.environ.pop("SHEET_ID", None)
os.environ.pop("GOOGLE_SA_JSON_CONTENT", None)

from tools import server as s  # noqa: E402


class Dedupe(unittest.TestCase):
    def setUp(self):
        s.store._save({"energy": [], "tokens": [], "requeries": []})

    def test_replayed_logs_are_recorded_once(self):
        first = s.log_fuel(20, 26000, "Adaeze")
        again = s.log_fuel(20, 26000, "Adaeze")
        s.log_diesel_on_hand(30, "Adaeze")
        s.log_diesel_on_hand(30, "Adaeze")
        s.log_meter_reading(85, "Adaeze")
        s.log_meter_reading(85, "Adaeze")
        self.assertNotIn("already_logged", first)
        self.assertTrue(again["already_logged"])
        self.assertEqual(again["price_per_litre"], 1300)
        self.assertEqual(len(s.store.rows("energy")), 3)

    def test_same_entry_outside_window_is_new(self):
        old = (datetime.now(timezone.utc) - timedelta(minutes=s.DEDUPE_MINUTES + 5)).isoformat(timespec="seconds")
        s.store.append("energy", {"ts": old, "type": "diesel", "litres": 20, "cost_ngn": 26000,
                                  "meter_units": "", "logged_by": "Adaeze", "note": ""})
        self.assertNotIn("already_logged", s.log_fuel(20, 26000, "Adaeze"))
        self.assertEqual(len(s.store.rows("energy")), 2)

    def test_replayed_purchase_is_not_bought_again(self):
        first = s.buy_units("62101234567", 5000, "owner")
        again = s.buy_units("62101234567", 5000, "owner")
        self.assertEqual(first["status"], "ok")
        self.assertTrue(again["already_bought"])
        self.assertEqual(again["reference"], first["reference"])
        self.assertEqual(again["token"], first["token"])
        self.assertEqual(len(s.store.rows("tokens")), 1)

    def test_pending_purchase_is_not_bought_again(self):
        first = s.buy_units("62101234522", 5000, "owner")  # mock: paid_no_token
        again = s.buy_units("62101234522", 5000, "owner")
        self.assertEqual(first["status"], "paid_no_token")
        self.assertTrue(again["already_bought"])
        self.assertIn("check_vend", again["error"])
        self.assertEqual(len(s.store.rows("tokens")), 1)

    def test_declined_purchase_can_be_retried_and_other_amounts_go_through(self):
        s.buy_units("62101234533", 5000, "owner")  # mock: declined
        self.assertNotIn("already_bought", s.buy_units("62101234533", 5000, "owner"))
        s.buy_units("62101234567", 5000, "owner")
        self.assertNotIn("already_bought", s.buy_units("62101234567", 4000, "owner"))
        self.assertEqual(len(s.store.rows("tokens")), 4)


if __name__ == "__main__":
    unittest.main()
