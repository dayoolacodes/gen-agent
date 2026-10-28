"""Energy MCP server for a Lagos provisions store.

Run locally:   python -m tools.server        (http://127.0.0.1:8000/mcp)
Expose:        ngrok http 8000               (Chord needs a public HTTPS URL)
Register in Chord with auth_type "bearer" and auth_token = MCP_BEARER_TOKEN.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from mcp.server.fastmcp import FastMCP
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from tools.storage import get_store, now_iso
from tools.vend import get_provider

store = get_store()
vend = get_provider()

GEN_LITRES_PER_HOUR = float(os.getenv("GEN_LITRES_PER_HOUR", "1.8"))  # 7.5kVA diesel at half load, rough
MAX_UNATTENDED_NGN = float(os.getenv("MAX_UNATTENDED_NGN", "20000"))

mcp = FastMCP("energy-tools", stateless_http=True, json_response=True)


@mcp.tool()
def log_fuel(litres: float, cost_ngn: float, logged_by: str = "staff", note: str = "") -> dict:
    """Record a diesel purchase for the generator. Use when staff report buying fuel."""
    if litres <= 0 or cost_ngn <= 0:
        return {"ok": False, "error": "litres and cost_ngn must be positive"}
    row = {"ts": now_iso(), "type": "diesel", "litres": litres, "cost_ngn": cost_ngn,
           "meter_units": "", "logged_by": logged_by, "note": note}
    store.append("energy", row)
    return {"ok": True, "logged": row, "price_per_litre": round(cost_ngn / litres, 2)}


@mcp.tool()
def log_meter_reading(units: float, logged_by: str = "staff", note: str = "") -> dict:
    """Record the prepaid meter balance in kWh units. Use when staff report what the meter shows."""
    if units < 0:
        return {"ok": False, "error": "units cannot be negative"}
    row = {"ts": now_iso(), "type": "meter", "litres": "", "cost_ngn": "",
           "meter_units": units, "logged_by": logged_by, "note": note}
    store.append("energy", row)
    return {"ok": True, "logged": row}


@mcp.tool()
def get_energy_summary(days: int = 7) -> dict:
    """Summarise diesel spend and meter trend over the last N days, with projected days until diesel
    and prepaid units run out. Use for 'how much have we spent', 'are we running low', daily briefings."""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    rows = store.rows("energy")
    diesel = [r for r in rows if r.get("type") == "diesel" and _ts(r) >= since]
    meters = sorted([r for r in rows if r.get("type") == "meter"], key=_ts)

    litres = sum(float(r["litres"] or 0) for r in diesel)
    spend = sum(float(r["cost_ngn"] or 0) for r in diesel)
    daily_spend = round(spend / days, 2) if days else 0
    litres_per_day = litres / days if days else 0
    # Assume stock on hand is whatever was bought in the window minus burn; crude but honest.
    est_hours_run = litres_per_day / GEN_LITRES_PER_HOUR if GEN_LITRES_PER_HOUR else 0

    meter_now = float(meters[-1]["meter_units"]) if meters else None
    units_per_day = _units_per_day(meters)
    days_units_left = round(meter_now / units_per_day, 1) if meter_now is not None and units_per_day else None

    alerts = []
    if days_units_left is not None and days_units_left < 3:
        alerts.append(f"Prepaid units will run out in about {days_units_left} days")
    if daily_spend and daily_spend * 7 > float(os.getenv("WEEKLY_DIESEL_BUDGET_NGN", "150000")):
        alerts.append("Diesel spend is above the weekly budget")
    if not diesel and not meters:
        alerts.append("No energy data logged yet")

    return {
        "window_days": days,
        "diesel": {"litres": litres, "spend_ngn": spend, "daily_spend_ngn": daily_spend,
                   "est_gen_hours_per_day": round(est_hours_run, 1), "purchases": len(diesel)},
        "meter": {"units_now": meter_now, "units_per_day": units_per_day, "days_left": days_units_left},
        "alerts": alerts,
    }


@mcp.tool()
def buy_units(meter_no: str, amount_ngn: float, requested_by: str = "owner") -> dict:
    """Buy prepaid electricity units for the shop's meter. Only call after the owner confirms the amount.
    Returns a token on success, or a typed failure: invalid_meter, timeout, paid_no_token, declined."""
    if amount_ngn > MAX_UNATTENDED_NGN and requested_by != "owner":
        return {"ok": False, "status": "needs_owner",
                "error": f"Amounts above NGN {MAX_UNATTENDED_NGN:,.0f} need the owner to confirm"}
    res = vend.buy(meter_no, amount_ngn)
    store.append("tokens", {"ts": now_iso(), "reference": res.reference, "meter_no": res.meter_no,
                            "amount_ngn": res.amount_ngn, "units": res.units or "", "token": res.token or "",
                            "status": res.status, "error": res.error or ""})
    _log_top_up(res)
    return {"ok": res.status == "ok", **res.dict()}


@mcp.tool()
def check_vend(reference: str) -> dict:
    """Re-check a purchase that was paid but returned no token. Use when a previous buy_units
    returned status paid_no_token or timeout. Returns the token if the provider has now issued it."""
    res = vend.requery(reference)
    if res.status == "ok":
        store.update_where("tokens", "reference", reference,
                           {"status": "ok", "token": res.token, "units": res.units, "error": ""})
        _log_top_up(res)
    return {"ok": res.status == "ok", **res.dict()}


RATE_WINDOW_DAYS = 14  # how far back to look when working out the burn rate


def _units_per_day(meters: list[dict]) -> float | None:
    """kWh used per day, from consecutive readings where units fell. Intervals where units rose
    contain a top-up, so they say nothing about consumption and are skipped."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=RATE_WINDOW_DAYS)
    recent = [m for m in meters if _ts(m) >= cutoff]
    used = 0.0
    span_days = 0.0
    for a, b in zip(recent, recent[1:]):
        du = float(a["meter_units"]) - float(b["meter_units"])
        if du <= 0:
            continue
        used += du
        span_days += max((_ts(b) - _ts(a)).total_seconds() / 86400, 1 / 24)
    return round(used / span_days, 2) if span_days else None


def _log_top_up(res) -> None:
    """After a successful vend, record the new meter balance so the forecast does not go stale.
    Skipped if there is no earlier reading to add to; the next staff reading fixes it."""
    if res.status != "ok" or not res.units:
        return
    meters = sorted([r for r in store.rows("energy") if r.get("type") == "meter"], key=_ts)
    if not meters:
        return
    units = round(float(meters[-1]["meter_units"]) + float(res.units), 1)
    store.append("energy", {"ts": now_iso(), "type": "meter", "litres": "", "cost_ngn": "",
                            "meter_units": units, "logged_by": "system", "note": f"top-up {res.reference}"})


def _ts(r: dict) -> datetime:
    return datetime.fromisoformat(str(r["ts"]))


class BearerAuth(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        expected = os.getenv("MCP_BEARER_TOKEN")
        if expected and request.url.path.startswith("/mcp"):
            if request.headers.get("authorization") != f"Bearer {expected}":
                return JSONResponse({"error": "unauthorized"}, status_code=401)
        return await call_next(request)


async def health(_):
    return JSONResponse({"status": "ok", "provider": type(vend).__name__, "store": type(store).__name__})


app = mcp.streamable_http_app()
app.add_middleware(BearerAuth)
app.add_route("/health", health, methods=["GET"])


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
