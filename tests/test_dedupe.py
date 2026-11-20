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
        first = s.buy_units(5000, "owner", meter_no="62101234567")
        again = s.buy_units(5000, "owner", meter_no="62101234567")
        self.assertEqual(first["status"], "ok")
        self.assertTrue(again["already_bought"])
        self.assertEqual(again["reference"], first["reference"])
        self.assertEqual(again["token"], first["token"])
        self.assertEqual(len(s.store.rows("tokens")), 1)

    def test_pending_purchase_is_not_bought_again(self):
        first = s.buy_units(5000, "owner", meter_no="62101234522")  # mock: paid_no_token
        again = s.buy_units(5000, "owner", meter_no="62101234522")
        self.assertEqual(first["status"], "paid_no_token")
        self.assertTrue(again["already_bought"])
        self.assertIn("check_vend", again["error"])
        self.assertEqual(len(s.store.rows("tokens")), 1)

    def test_declined_purchase_can_be_retried_and_other_amounts_go_through(self):
        s.buy_units(5000, "owner", meter_no="62101234533")  # mock: declined
        self.assertNotIn("already_bought", s.buy_units(5000, "owner", meter_no="62101234533"))
        s.buy_units(5000, "owner", meter_no="62101234567")
        self.assertNotIn("already_bought", s.buy_units(4000, "owner", meter_no="62101234567"))
        self.assertEqual(len(s.store.rows("tokens")), 4)



class ReviewerFindings(unittest.TestCase):
    """Fixes for what TSG's reviewers hit on 8 Nov."""

    def setUp(self):
        s.store._save({"energy": [], "tokens": [], "requeries": []})

    def test_same_amount_by_another_person_is_a_new_purchase(self):
        tunde = s.buy_units(7000, "Tunde", meter_no="62101234567")
        adaeze = s.buy_units(7000, "Adaeze", meter_no="62101234567")
        self.assertNotIn("already_bought", adaeze)
        self.assertNotEqual(tunde["reference"], adaeze["reference"])
        self.assertTrue(s.buy_units(7000, "Tunde", meter_no="62101234567")["already_bought"])

    def test_meter_comes_from_config_not_the_model(self):
        r = s.buy_units(5000, "Adaeze", meter_no="on file")
        self.assertEqual(r["meter_no"], s.SHOP_METER_NO)
        self.assertEqual(s.buy_units(5000, "Ade")["meter_no"], s.SHOP_METER_NO)

    def test_check_vend_on_a_confirmed_purchase_does_not_add_units_again(self):
        s.store.append("energy", {"ts": s.now_iso(), "type": "meter", "litres": "", "cost_ngn": "",
                                  "meter_units": 98, "logged_by": "Ade", "note": ""})
        r = s.buy_units(5000, "Ade", meter_no="62101234567")  # mock ok: 22.2 units
        s.check_vend(r["reference"])
        s.check_vend(r["reference"])
        tops = [x for x in s.store.rows("energy") if x["logged_by"] == "system"]
        self.assertEqual(len(tops), 1)

    def test_recent_activity_shows_earlier_purchases(self):
        r = s.buy_units(5000, "Ade", meter_no="62101234567")
        act = s.get_recent_activity(1)
        self.assertEqual(act["purchases"][0]["reference"], r["reference"])
        self.assertEqual(act["purchases"][0]["requested_by"], "Ade")

    def test_tank_reading_in_the_same_message_includes_the_purchase(self):
        s.log_diesel_on_hand(15, "Ade")
        s.log_fuel(25, 32500, "Ade")  # "bought 25 litres, tank now at about 15"
        self.assertLessEqual(s.get_energy_summary(7)["diesel"]["on_hand_litres"], 15)

    def test_non_positive_amount_refused(self):
        self.assertEqual(s.buy_units(-5000, "Adaeze")["status"], "declined")
        self.assertEqual(s.buy_units(0, "Adaeze")["status"], "declined")


if __name__ == "__main__":
    unittest.main()
