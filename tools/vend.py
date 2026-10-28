"""Electricity vending providers behind one interface.

VendResult.status is one of:
  "ok"              token issued
  "invalid_meter"   meter number rejected
  "timeout"         provider did not answer in time
  "paid_no_token"   payment captured but no token returned (the dangerous one)
  "declined"        payment failed

MockVend is deterministic so the demo and the failure cases are reproducible.
VTPassVend talks to the VTpass sandbox (Ikeja Electric prepaid).
"""
from __future__ import annotations

import os
import random
import string
from dataclasses import dataclass, asdict
from datetime import datetime
from zoneinfo import ZoneInfo


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
    """VTpass sandbox, Ikeja Electric prepaid. Docs: vtpass.com/documentation.
    Env: VTPASS_API_KEY, VTPASS_SECRET_KEY, VTPASS_SERVICE_ID (ikeja-electric), VTPASS_VARIATION (prepaid).

    All three calls here are POSTs, so they authenticate with api-key + secret-key. The public key only
    works on GET; merchant-verify with it returns 087 INVALID CREDENTIALS (see field notes).
    VTpass rule: anything unclear is treated as pending and requeried, never as failed.
    """

    # Codes that mean the request was refused and the wallet was not charged.
    NOT_CHARGED = {"010", "011", "012", "013", "015", "016", "017", "018", "021", "022", "023", "024",
                   "027", "028", "030", "034", "035", "040", "085", "087", "091"}

    def __init__(self):
        self.base = os.getenv("VTPASS_BASE", "https://sandbox.vtpass.com/api")
        self.headers = {"api-key": os.environ["VTPASS_API_KEY"], "secret-key": os.environ["VTPASS_SECRET_KEY"]}
        self.service_id = os.getenv("VTPASS_SERVICE_ID", "ikeja-electric")
        self.variation = os.getenv("VTPASS_VARIATION", "prepaid")
        self.timeout = float(os.getenv("VTPASS_TIMEOUT_S", "30"))

    def _post(self, path: str, payload: dict):
        """Returns parsed JSON, or None if the body was empty or not JSON. Raises httpx errors."""
        import httpx

        r = httpx.post(f"{self.base}/{path}", json=payload, headers=self.headers, timeout=self.timeout)
        try:
            return r.json()
        except ValueError:
            return None

    @staticmethod
    def _request_id() -> str:
        # VTpass: first 12 chars must be today's date and time, YYYYMMDDHHII, Africa/Lagos.
        stamp = datetime.now(ZoneInfo("Africa/Lagos")).strftime("%Y%m%d%H%M")
        return stamp + "".join(random.choices(string.ascii_uppercase + string.digits, k=8))

    def verify_meter(self, meter_no: str) -> dict:
        """Check the meter with the DisCo before paying. Returns {valid, name, error}."""
        import httpx

        try:
            data = self._post("merchant-verify", {"billersCode": meter_no, "serviceID": self.service_id,
                                                  "type": self.variation})
        except httpx.HTTPError as e:
            return {"valid": False, "reachable": False, "error": f"Could not reach provider to verify meter: {e}"}
        content = (data or {}).get("content") or {}
        # A wrong meter still comes back as code 000; the signal is WrongBillersCode / content.error.
        if not data or data.get("code") != "000" or content.get("WrongBillersCode") or content.get("error"):
            err = content.get("error") or (data or {}).get("response_description") or (data or {}).get("message")
            return {"valid": False, "reachable": True, "error": err or "Meter verification failed"}
        return {"valid": True, "reachable": True, "name": content.get("Customer_Name"),
                "can_vend": content.get("Can_Vend"), "error": None}

    def buy(self, meter_no: str, amount_ngn: float) -> VendResult:
        import httpx

        ref = self._request_id()
        v = self.verify_meter(meter_no)
        if not v["valid"]:
            if not v["reachable"]:
                return VendResult("declined", ref, meter_no, amount_ngn, error=v["error"] + ". No payment was attempted.")
            return VendResult("invalid_meter", ref, meter_no, amount_ngn, error=v["error"])
        payload = {"request_id": ref, "serviceID": self.service_id, "billersCode": meter_no,
                   "variation_code": self.variation, "amount": amount_ngn,
                   "phone": os.getenv("VTPASS_PHONE", "08011111111")}
        try:
            data = self._post("pay", payload)
        except httpx.TimeoutException:
            return VendResult("timeout", ref, meter_no, amount_ngn, error=f"Provider did not answer in {self.timeout:.0f}s")
        except httpx.HTTPError as e:
            return VendResult("timeout", ref, meter_no, amount_ngn, error=f"Connection to provider failed: {e}")
        return self._map(data, ref, meter_no, amount_ngn)

    def requery(self, reference: str) -> VendResult:
        import httpx

        try:
            data = self._post("requery", {"request_id": reference})
        except httpx.HTTPError as e:
            return VendResult("paid_no_token", reference, "", 0.0, error=f"Requery failed, still unknown: {e}")
        return self._map(data, reference, "", 0.0)

    def _map(self, data, ref: str, meter_no: str, amount_ngn: float) -> VendResult:
        if not data:
            return VendResult("paid_no_token", ref, meter_no, amount_ngn,
                              error="Empty or unreadable response from provider; status unknown")
        code = str(data.get("code", ""))
        desc = data.get("response_description") or (data.get("content") or {}).get("errors") or ""
        tx = (data.get("content") or {}).get("transactions") or {}
        status = tx.get("status")
        meter_no = meter_no or str(tx.get("unique_element") or "")
        amount_ngn = amount_ngn or float(data.get("amount") or tx.get("amount") or 0)
        token = _clean_token(data.get("token") or data.get("purchased_code"))
        if code == "000" and status == "delivered" and token:
            return VendResult("ok", ref, meter_no, amount_ngn, units=_kwh(data.get("units")), token=token)
        if code == "015":
            return VendResult("declined", ref, meter_no, amount_ngn,
                              error="015 INVALID REQUEST ID: provider has no record of this purchase, so no money was taken")
        if code in self.NOT_CHARGED:
            return VendResult("declined", ref, meter_no, amount_ngn, error=f"{code} {desc}".strip())
        # 000 pending/initiated, 099, 089, 014, 083, delivered without a token, anything undocumented
        return VendResult("paid_no_token", ref, meter_no, amount_ngn,
                          error=f"{code} {desc} status={status}".strip() + ". Requery before buying again")


def _clean_token(raw) -> str | None:
    if not raw:
        return None
    s = str(raw)
    if ":" in s:  # VTpass prefixes with "Token : "
        s = s.split(":", 1)[1]
    return s.strip() or None


def _kwh(raw) -> float | None:
    if raw in (None, ""):
        return None
    try:
        return float(str(raw).lower().replace("kwh", "").strip())
    except ValueError:
        return None


def get_provider():
    if os.getenv("VEND_PROVIDER", "mock").lower() == "vtpass":
        return VTPassVend()
    return MockVend()
