"""Token and units parsing against a real VTpass sandbox pay response (28 Oct, email and phone redacted).

    python -m unittest discover tests
"""
import json
import os
import unittest
from pathlib import Path

os.environ.setdefault("VTPASS_API_KEY", "test")
os.environ.setdefault("VTPASS_SECRET_KEY", "test")

from tools.vend import VTPassVend, _clean_token, _kwh  # noqa: E402

SUCCESS = json.loads((Path(__file__).parent / "fixtures" / "vtpass_pay_success.json").read_text())


class TokenAndUnits(unittest.TestCase):
    def test_token_is_digit_run_from_purchased_code(self):
        self.assertEqual(_clean_token(SUCCESS["purchased_code"]), "26362054405982757802")

    def test_dashed_token_parses(self):
        self.assertEqual(_clean_token("Token : 2636-2054-4059-8275-7802"), "26362054405982757802")

    def test_units_leading_number_as_float(self):
        self.assertEqual(_kwh(SUCCESS["units"]), 79.9)
        self.assertIsInstance(_kwh(SUCCESS["units"]), float)

    def test_success_response_maps_to_ok(self):
        res = VTPassVend()._map(SUCCESS, "2026102812073b9c0f1d", "1111111111111", 5000)
        self.assertEqual((res.status, res.token, res.units), ("ok", "26362054405982757802", 79.9))

    def test_no_digit_run_means_no_token(self):
        for raw in (None, "", "Token : N/A", "Token : 12345"):
            self.assertIsNone(_clean_token(raw))
        res = VTPassVend()._map({**SUCCESS, "purchased_code": "Token : N/A", "token": "N/A"}, "R", "m", 5000)
        self.assertEqual(res.status, "paid_no_token")

    def test_units_without_a_number(self):
        self.assertIsNone(_kwh("N/A"))
        self.assertIsNone(_kwh(None))


if __name__ == "__main__":
    unittest.main()
