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
import re
import string
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
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


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _ref() -> str:
    return "VND" + "".join(random.choices(string.ascii_uppercase + string.digits, k=8))


class MockVend:
    """Behaviour is driven by the meter number so every path is demoable:
      ends in 00  -> invalid_meter
      ends in 11  -> timeout
      ends in 22  -> paid_no_token (requery: still pending once, then resolves)
      ends in 33  -> declined
      anything else -> ok
    Amount under 1000 NGN -> declined (provider minimum).
    """

    TARIFF_NGN_PER_KWH = float(os.getenv("TARIFF_NGN_PER_KWH", "225"))

    def buy(self, meter_no: str, amount_ngn: float) -> VendResult:
        ref = _ref()
        m = meter_no.strip()
        if not m.isdigit() or len(m) < 11:
            return VendResult("invalid_meter", ref, m, amount_ngn, error="Meter number must be 11+ digits. No money was taken.")
        if amount_ngn < 1000:
            return VendResult("declined", ref, m, amount_ngn, error="Minimum purchase is NGN 1,000. No money was taken.")
        if m.endswith("00"):
            return VendResult("invalid_meter", ref, m, amount_ngn, error="Meter not found at DisCo. No money was taken.")
        if m.endswith("11"):
            return VendResult("timeout", ref, m, amount_ngn, error="Provider timed out after 30s")
        if m.endswith("22"):
            return VendResult("paid_no_token", ref, m, amount_ngn, error="Payment captured, token pending from DisCo")
        if m.endswith("33"):
            return VendResult("declined", ref, m, amount_ngn, error="Payment declined by issuer. No money was taken.")
        units = round(amount_ngn / self.TARIFF_NGN_PER_KWH, 1)
        token = "-".join("".join(random.choices(string.digits, k=4)) for _ in range(5))
        return VendResult("ok", ref, m, amount_ngn, units=units, token=token)

    def __init__(self, store=None):
        self.store = store  # holds the requery counter so it survives restarts

    def requery(self, reference: str) -> VendResult:
        """...22 meters stay pending on the first requery and resolve on the second."""
        orig = next((r for r in self.store.rows("tokens") if r.get("reference") == reference), None) if self.store else None
        if orig is None:
            return VendResult("declined", reference, "", 0.0,
                              error="Provider has no record of this reference, so no money was taken")
        meter_no, amount = str(orig["meter_no"]), float(orig["amount_ngn"] or 0)
        self.store.append("requeries", {"ts": _now(), "reference": reference})
        tries = sum(1 for r in self.store.rows("requeries") if r.get("reference") == reference)
        if meter_no.endswith("22") and tries < 2:
            return VendResult("paid_no_token", reference, meter_no, amount, error="Still pending at DisCo")
        units = round(amount / self.TARIFF_NGN_PER_KWH, 1)
        token = "-".join("".join(random.choices(string.digits, k=4)) for _ in range(5))
        return VendResult("ok", reference, meter_no, amount, units=units, token=token)


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
        self.timeout = float(os.getenv("VTPASS_TIMEOUT_S", "30"))  # single calls: requery, standalone checks
        # Chord abandons a tool call at 60s. buy() must finish well inside that, leaving room for a cold
        # start (about 8.5s) and the Sheet writes in server.buy_units (about 3s).
        self.budget = float(os.getenv("VTPASS_BUY_BUDGET_S", "40"))

    VERIFY_TIMEOUT_S = 8.0
    BALANCE_TIMEOUT_S = 5.0
    MIN_PAY_TIMEOUT_S = 10.0  # below this, do not start a payment we may not hear back from

    def _post(self, path: str, payload: dict, timeout: float | None = None):
        """Returns parsed JSON, or None if the body was empty or not JSON. Raises httpx errors."""
        import httpx

        r = httpx.post(f"{self.base}/{path}", json=payload, headers=self.headers, timeout=timeout or self.timeout)
        try:
            return r.json()
        except ValueError:
            return None

    @staticmethod
    def _request_id() -> str:
        # VTpass: first 12 chars must be today's date and time, YYYYMMDDHHII, Africa/Lagos.
        stamp = datetime.now(ZoneInfo("Africa/Lagos")).strftime("%Y%m%d%H%M")
        return stamp + "".join(random.choices(string.ascii_uppercase + string.digits, k=8))

    def wallet_balance(self, timeout: float | None = None) -> float | None:
        """VTpass wallet balance in NGN, or None if it could not be read. GET, so api-key + public-key.
        Note the different envelope: {"code":1,"contents":{"balance":"..."}}."""
        import httpx

        try:
            r = httpx.get(f"{self.base}/balance", timeout=timeout or self.timeout,
                          headers={"api-key": self.headers["api-key"], "public-key": os.environ["VTPASS_PUBLIC_KEY"]})
            return float(r.json()["contents"]["balance"])
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            return None

    def verify_meter(self, meter_no: str, timeout: float | None = None) -> dict:
        """Check the meter with the DisCo before paying. Returns {valid, name, error}."""
        import httpx

        try:
            data = self._post("merchant-verify", {"billersCode": meter_no, "serviceID": self.service_id,
                                                  "type": self.variation}, timeout)
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

        deadline = time.monotonic() + self.budget
        ref = self._request_id()
        v = self.verify_meter(meter_no, self.VERIFY_TIMEOUT_S)
        if not v["valid"]:
            # pay is never called on this path, so nothing can have been charged.
            status = "invalid_meter" if v["reachable"] else "declined"
            return VendResult(status, ref, meter_no, amount_ngn,
                              error=v["error"] + ". Payment was not attempted, so no money was taken.")
        before = self.wallet_balance(self.BALANCE_TIMEOUT_S)
        # Pay gets what is left of the budget after keeping enough back for the balance check afterwards.
        pay_timeout = deadline - time.monotonic() - self.BALANCE_TIMEOUT_S
        if pay_timeout < self.MIN_PAY_TIMEOUT_S:
            return VendResult("declined", ref, meter_no, amount_ngn,
                              error="Provider too slow to start a payment safely inside the time limit. "
                                    "Payment was not attempted, so no money was taken. Try again in a few minutes.")
        payload = {"request_id": ref, "serviceID": self.service_id, "billersCode": meter_no,
                   "variation_code": self.variation, "amount": amount_ngn,
                   "phone": os.getenv("VTPASS_PHONE", "08011111111")}
        try:
            res = self._map(self._post("pay", payload, pay_timeout), ref, meter_no, amount_ngn)
        except httpx.TimeoutException:
            res = VendResult("timeout", ref, meter_no, amount_ngn, error=f"Provider did not answer in {pay_timeout:.0f}s")
        except httpx.HTTPError as e:
            res = VendResult("timeout", ref, meter_no, amount_ngn, error=f"Connection to provider failed: {e}")
        return self._settle(res, before, self.wallet_balance(self.BALANCE_TIMEOUT_S))

    @staticmethod
    def _settle(res: VendResult, before: float | None, after: float | None) -> VendResult:
        """Use the wallet balance to decide what we can honestly say about money.
        A drop is checked, not an exact amount: VTpass debits amount minus commission (5,000 -> 4,925)."""
        if res.status == "ok":
            return res
        if before is None or after is None:
            if res.status == "declined":
                res.error += ". Could not read the wallet balance, so it is not confirmed whether money was taken."
            return res
        if after < before - 0.005:
            res.status = "paid_no_token"
            res.error = (f"Wallet went down by NGN {before - after:,.2f} but no token came back ({res.error}). "
                         f"Reference {res.reference}. Requery before buying again.")
        elif res.status == "declined":
            res.error += ". Wallet balance unchanged, so no money was taken."
        else:
            res.error += ". Wallet balance unchanged so far."
        return res

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
        token = _clean_token(data.get("purchased_code")) or _clean_token(data.get("token"))
        if code == "000" and status == "delivered" and token:
            return VendResult("ok", ref, meter_no, amount_ngn, units=_kwh(data.get("units")), token=token)
        if code == "015":
            return VendResult("declined", ref, meter_no, amount_ngn,
                              error="015 INVALID REQUEST ID: VTpass has no record of this request. Not checked against "
                                    "the wallet, so do not say whether money was taken; check the balance before buying again")
        if code in self.NOT_CHARGED:
            return VendResult("declined", ref, meter_no, amount_ngn, error=f"{code} {desc}".strip())
        # 000 pending/initiated, 099, 089, 014, 083, delivered without a token, anything undocumented
        return VendResult("paid_no_token", ref, meter_no, amount_ngn,
                          error=f"{code} {desc} status={status}".strip() + ". Requery before buying again")


TOKEN_RE = re.compile(r"\d{16,}")  # prepaid STS tokens are 20 digits
UNITS_RE = re.compile(r"\s*(\d+(?:\.\d+)?)")


def _clean_token(raw) -> str | None:
    """'Token : 26362054405982757802' or 'Token : 2636-2054-4059-8275-7802' -> '26362054405982757802'.
    Every non-digit is dropped first so dashed or spaced tokens still parse. None if under 16 digits."""
    m = TOKEN_RE.search(re.sub(r"\D", "", str(raw or "")))
    return m.group(0) if m else None


def _kwh(raw) -> float | None:
    """'79.9 kWh' -> 79.9. Takes the leading number; None if there is none."""
    m = UNITS_RE.match(str(raw if raw is not None else ""))
    return float(m.group(1)) if m else None


def get_provider(store=None):
    if os.getenv("VEND_PROVIDER", "mock").lower() == "vtpass":
        return VTPassVend()
    return MockVend(store)
