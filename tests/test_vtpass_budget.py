"""buy() must finish inside Chord's 60s tool timeout: pay only gets what is left of the budget,
and no payment starts if too little is left. No network: the VTpass calls are stubbed."""
import json
import os
import time
import unittest
from pathlib import Path

os.environ.setdefault("VTPASS_API_KEY", "test")
os.environ.setdefault("VTPASS_SECRET_KEY", "test")

from tools.vend import VTPassVend  # noqa: E402

SUCCESS = json.loads((Path(__file__).parent / "fixtures" / "vtpass_pay_success.json").read_text())


def stubbed(verify_delay=0.0):
    v = VTPassVend()
    calls = {}

    def verify(meter_no, timeout=None):
        time.sleep(verify_delay)
        return {"valid": True, "reachable": True, "error": None}

    def post(path, payload, timeout=None):
        calls[path] = timeout
        return SUCCESS

    v.verify_meter = verify
    v._post = post
    v.wallet_balance = lambda timeout=None: 1000.0
    return v, calls


class BuyBudget(unittest.TestCase):
    def test_pay_timeout_is_what_is_left_of_the_budget(self):
        v, calls = stubbed()
        self.assertEqual(v.buy("1111111111111", 5000).status, "ok")
        self.assertLessEqual(calls["pay"], v.budget - v.BALANCE_TIMEOUT_S)
        self.assertGreater(calls["pay"], v.MIN_PAY_TIMEOUT_S)

    def test_no_payment_when_too_little_time_left(self):
        v, calls = stubbed(verify_delay=0.3)
        v.budget = v.BALANCE_TIMEOUT_S + v.MIN_PAY_TIMEOUT_S + 0.2  # verify eats the slack
        res = v.buy("1111111111111", 5000)
        self.assertNotIn("pay", calls)
        self.assertEqual(res.status, "declined")
        self.assertIn("no money was taken", res.error)

    def test_default_budget_leaves_room_inside_60s(self):
        # 40s vend budget + about 8.5s cold start + about 3s of Sheet writes stays under Chord's 60s.
        self.assertLessEqual(VTPassVend().budget + 8.5 + 3, 55)


if __name__ == "__main__":
    unittest.main()
