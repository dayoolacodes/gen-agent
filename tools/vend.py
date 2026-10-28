"""Electricity vending providers behind one interface.

VendResult.status is one of:
  "ok"              token issued
  "invalid_meter"   meter number rejected
  "timeout"         provider did not answer in time
  "paid_no_token"   payment captured but no token returned (the dangerous one)
  "declined"        payment failed

MockVend is deterministic so the demo and the failure cases are reproducible.
VTPassVend is a stub shaped for the VTpass sandbox; fill in once access lands.
"""
from __future__ import annotations

import os
import random
import string
from dataclasses import dataclass, asdict


@dataclass
class VendResult:
    status: str
    reference: str
    meter_no: str
    amount_ngn: float
    units: float | None = None
    token: str | None = None
    error: str | None = None

    def dict(self) -> dict:
        return asdict(self)


def _ref() -> str:
    return "VND" + "".join(random.choices(string.ascii_uppercase + string.digits, k=8))


class MockVend:
    """Behaviour is driven by the meter number so every path is demoable:
      ends in 00  -> invalid_meter
      ends in 11  -> timeout
      ends in 22  -> paid_no_token
      ends in 33  -> declined
      anything else -> ok
    Amount under 1000 NGN -> declined (provider minimum).
    """

    TARIFF_NGN_PER_KWH = float(os.getenv("TARIFF_NGN_PER_KWH", "225"))

    def buy(self, meter_no: str, amount_ngn: float) -> VendResult:
        ref = _ref()
        m = meter_no.strip()
        if not m.isdigit() or len(m) < 11:
            return VendResult("invalid_meter", ref, m, amount_ngn, error="Meter number must be 11+ digits")
        if amount_ngn < 1000:
            return VendResult("declined", ref, m, amount_ngn, error="Minimum purchase is NGN 1,000")
        if m.endswith("00"):
            return VendResult("invalid_meter", ref, m, amount_ngn, error="Meter not found at DisCo")
        if m.endswith("11"):
            return VendResult("timeout", ref, m, amount_ngn, error="Provider timed out after 30s")
        if m.endswith("22"):
            return VendResult("paid_no_token", ref, m, amount_ngn, error="Payment captured, token pending from DisCo")
        if m.endswith("33"):
            return VendResult("declined", ref, m, amount_ngn, error="Payment declined by issuer")
        units = round(amount_ngn / self.TARIFF_NGN_PER_KWH, 1)
        token = "-".join("".join(random.choices(string.digits, k=4)) for _ in range(5))
        return VendResult("ok", ref, m, amount_ngn, units=units, token=token)

    def requery(self, reference: str) -> VendResult:
        # Mock: a pending vend resolves on requery
        units = 10.0
        token = "-".join("".join(random.choices(string.digits, k=4)) for _ in range(5))
        return VendResult("ok", reference, "", 0.0, units=units, token=token)


class VTPassVend:
    """Shape only. VTpass sandbox: https://sandbox.vtpass.com/api/pay (verify in their docs).
    Env: VTPASS_API_KEY, VTPASS_SECRET_KEY, VTPASS_PUBLIC_KEY, VTPASS_SERVICE_ID (e.g. ikeja-electric), VTPASS_VARIATION (prepaid).
    """

    def __init__(self):
        import httpx  # noqa: F401

        self.base = os.getenv("VTPASS_BASE", "https://sandbox.vtpass.com/api")
        self.api_key = os.environ["VTPASS_API_KEY"]
        self.secret = os.environ["VTPASS_SECRET_KEY"]
        self.service_id = os.getenv("VTPASS_SERVICE_ID", "ikeja-electric")
        self.variation = os.getenv("VTPASS_VARIATION", "prepaid")

    def buy(self, meter_no: str, amount_ngn: float) -> VendResult:
        import httpx

        ref = _ref()
        headers = {"api-key": self.api_key, "secret-key": self.secret}
        payload = {
            "request_id": ref,
            "serviceID": self.service_id,
            "billersCode": meter_no,
            "variation_code": self.variation,
            "amount": amount_ngn,
            "phone": os.getenv("VTPASS_PHONE", "08011111111"),
        }
        try:
            r = httpx.post(f"{self.base}/pay", json=payload, headers=headers, timeout=30)
        except httpx.TimeoutException:
            return VendResult("timeout", ref, meter_no, amount_ngn, error="Provider timed out")
        data = r.json()
        content = data.get("content", {}).get("transactions", {})
        status = content.get("status")
        token = data.get("purchased_code") or data.get("token")
        if status == "delivered" and token:
            return VendResult("ok", ref, meter_no, amount_ngn, units=float(data.get("units", 0) or 0), token=str(token))
        if status in ("pending", "initiated"):
            return VendResult("paid_no_token", ref, meter_no, amount_ngn, error="Pending at provider")
        return VendResult("declined", ref, meter_no, amount_ngn, error=data.get("response_description", "Unknown"))

    def requery(self, reference: str) -> VendResult:
        import httpx

        headers = {"api-key": self.api_key, "secret-key": self.secret}
        r = httpx.post(f"{self.base}/requery", json={"request_id": reference}, headers=headers, timeout=30)
        data = r.json()
        token = data.get("purchased_code") or data.get("token")
        if token:
            return VendResult("ok", reference, "", 0.0, units=float(data.get("units", 0) or 0), token=str(token))
        return VendResult("paid_no_token", reference, "", 0.0, error="Still pending")


def get_provider():
    if os.getenv("VEND_PROVIDER", "mock").lower() == "vtpass":
        return VTPassVend()
    return MockVend()
