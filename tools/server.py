"""Energy MCP server for a Lagos provisions store.

Run locally:   python -m tools.server        (http://127.0.0.1:8000/mcp)
Expose:        ngrok http 8000               (Chord needs a public HTTPS URL)
Register in Chord with auth_type "bearer" and auth_token = MCP_BEARER_TOKEN.
"""
from __future__ import annotations

import hmac
import os
import threading
from datetime import datetime, timedelta, timezone

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from tools.storage import get_store, now_iso
from tools.vend import get_provider

store = get_store()
vend = get_provider(store)

GEN_LITRES_PER_HOUR = float(os.getenv("GEN_LITRES_PER_HOUR", "1.8"))  # 7.5kVA diesel at half load, rough
MAX_UNATTENDED_NGN = float(os.getenv("MAX_UNATTENDED_NGN", "20000"))
DIESEL_ALERT_DAYS = float(os.getenv("DIESEL_ALERT_DAYS", "1"))
STALE_READING_DAYS = float(os.getenv("STALE_READING_DAYS", "2"))  # older than this: ask staff for a fresh one
# Chord's agent replays earlier write tool calls on later turns (field notes, 6 Nov), and staff resend
# messages. An identical log or purchase inside this window is treated as the same one, not a new one.
DEDUPE_MINUTES = float(os.getenv("DEDUPE_MINUTES", "30"))
# The shop's meter lives in server config, not in the model's hands: in testing the model once sent
# "on file" as the meter number and once asked staff to type it.
SHOP_METER_NO = os.getenv("SHOP_METER_NO", "1111111111111")
# A purchase logged within this many minutes after a tank reading is taken to be already in that
# reading ("bought 25 litres, tank now at 15" means 15 including the 25).
SAME_MESSAGE_MINUTES = float(os.getenv("SAME_MESSAGE_MINUTES", "5"))
_buy_lock = threading.Lock()  # duplicate check and vend happen as one step

# FastMCP's DNS-rebinding guard only accepts localhost Host headers by default, so behind ngrok or
# Render every request gets 421 "Invalid Host header". List the public host(s), comma-separated,
# exact match only (no *.ngrok-free.app wildcards), e.g. MCP_ALLOWED_HOSTS=abcd.ngrok-free.app
PUBLIC_HOSTS = [h.strip() for h in os.getenv("MCP_ALLOWED_HOSTS", "").split(",") if h.strip()]
security = TransportSecuritySettings(
    allowed_hosts=["127.0.0.1:*", "localhost:*", "[::1]:*", *PUBLIC_HOSTS],
    allowed_origins=["http://127.0.0.1:*", "http://localhost:*", "http://[::1]:*",
                     *(f"https://{h}" for h in PUBLIC_HOSTS)],
)

mcp = FastMCP("energy-tools", stateless_http=True, json_response=True, transport_security=security)


@mcp.tool()
def log_fuel(litres: float, cost_ngn: float, logged_by: str = "staff", note: str = "") -> dict:
    """Record a diesel purchase for the generator. Use when staff report buying fuel."""
    if litres <= 0 or cost_ngn <= 0:
        return {"ok": False, "error": "litres and cost_ngn must be positive"}
    row = {"ts": now_iso(), "type": "diesel", "litres": litres, "cost_ngn": cost_ngn,
           "meter_units": "", "logged_by": logged_by, "note": note}
    out = _append_once(row, ("type", "litres", "cost_ngn", "logged_by"))
    return {**out, "price_per_litre": round(cost_ngn / litres, 2)}


@mcp.tool()
def log_meter_reading(units: float, logged_by: str = "staff", note: str = "") -> dict:
    """Record the prepaid meter balance in kWh units. Use when staff report what the meter shows."""
    if units < 0:
        return {"ok": False, "error": "units cannot be negative"}
    row = {"ts": now_iso(), "type": "meter", "litres": "", "cost_ngn": "",
           "meter_units": units, "logged_by": logged_by, "note": note}
    return _append_once(row, ("type", "meter_units", "logged_by"))


@mcp.tool()
def log_diesel_on_hand(litres: float, logged_by: str = "staff", note: str = "") -> dict:
    """Record how much diesel is left in the generator tank and jerrycans, in litres. Use when staff say
    things like 'tank at about 15 litres' or 'diesel left 10L'. Not for purchases; use log_fuel for those."""
    if litres < 0:
        return {"ok": False, "error": "litres cannot be negative"}
    row = {"ts": now_iso(), "type": "diesel_level", "litres": litres, "cost_ngn": "",
           "meter_units": "", "logged_by": logged_by, "note": note}
    return _append_once(row, ("type", "litres", "logged_by"))


@mcp.tool()
def get_energy_summary(days: int = 7) -> dict:
    """Summarise diesel spend and meter trend over the last N days, with projected days until diesel
    and prepaid units run out. Use for 'how much have we spent', 'are we running low', daily briefings.
    on_hand_litres and units_now are estimates for right now: the last reading minus what has been
    used since. last_reading_days_ago says how old that reading is."""
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

    burn = _diesel_litres_per_day(rows) or (round(litres_per_day, 2) if litres_per_day else None)
    on_hand, tank_age = _diesel_on_hand(rows, burn)
    diesel_days_left = round(on_hand / burn, 1) if on_hand is not None and burn else None

    units_per_day = _units_per_day(meters)
    meter_now, meter_age = _units_now(meters, units_per_day)
    days_units_left = round(meter_now / units_per_day, 1) if meter_now is not None and units_per_day else None

    alerts = []
    if on_hand == 0:
        alerts.append("Diesel has probably run out by now (estimate from the last tank reading)")
    if meter_now == 0:
        alerts.append("Prepaid units have probably run out by now (estimate from the last meter reading)")
    if tank_age is not None and tank_age > STALE_READING_DAYS:
        alerts.append(f"Tank level last reported {tank_age:.0f} days ago; ask staff for a fresh reading")
    if meter_age is not None and meter_age > STALE_READING_DAYS:
        alerts.append(f"Meter last read {meter_age:.0f} days ago; ask staff for a fresh reading")
    if meter_now and days_units_left is not None and days_units_left < 3:
        alerts.append(f"Prepaid units will run out in about {days_units_left} days")
    if on_hand and diesel_days_left is not None and diesel_days_left < DIESEL_ALERT_DAYS:
        alerts.append(f"Diesel will run out in about {diesel_days_left} days")
    if daily_spend and daily_spend * 7 > float(os.getenv("WEEKLY_DIESEL_BUDGET_NGN", "150000")):
        alerts.append("Diesel spend is above the weekly budget")
    if not diesel and not meters:
        alerts.append("No energy data logged yet")

    return {
        "window_days": days,
        "diesel": {"litres": litres, "spend_ngn": spend, "daily_spend_ngn": daily_spend,
                   "est_gen_hours_per_day": round(est_hours_run, 1), "purchases": len(diesel),
                   "on_hand_litres": on_hand, "litres_per_day": burn, "days_left": diesel_days_left,
                   "last_reading_days_ago": tank_age},
        "meter": {"units_now": meter_now, "units_per_day": units_per_day, "days_left": days_units_left,
                  "last_reading_days_ago": meter_age},
        "alerts": alerts,
    }


@mcp.tool()
def buy_units(amount_ngn: float, requested_by: str, meter_no: str = "") -> dict:
    """Buy prepaid electricity units for the shop's meter. Only call after the person has confirmed the
    amount with a yes. requested_by is the name of the person asking (e.g. Adaeze, Ade, Tunde).
    The shop's meter number is filled in by the server; leave meter_no empty.
    Returns a token on success, or a typed failure: invalid_meter, timeout, paid_no_token, declined.
    already_bought means this person already bought this amount in the last 30 minutes: show that
    purchase's token and reference, nothing new was bought."""
    meter = meter_no.strip() if meter_no.strip().isdigit() else SHOP_METER_NO
    who = (requested_by or "").strip() or "unknown"
    if amount_ngn <= 0:
        return {"ok": False, "status": "declined", "error": "Amount must be a positive naira amount. No money was taken."}
    if amount_ngn > MAX_UNATTENDED_NGN and who.lower() not in ("owner", "adaeze"):
        return {"ok": False, "status": "needs_owner",
                "error": f"Amounts above NGN {MAX_UNATTENDED_NGN:,.0f} need Adaeze to confirm. Nothing was bought."}
    with _buy_lock:
        earlier = _recent_purchase(meter, amount_ngn, who)
        if earlier:
            return {"ok": earlier.get("status") == "ok", "already_bought": True,
                    "status": earlier.get("status"), "reference": earlier.get("reference"),
                    "meter_no": meter, "amount_ngn": amount_ngn, "units": earlier.get("units") or None,
                    "token": earlier.get("token") or None, "bought_at": earlier.get("ts"),
                    "error": f"{who} already bought NGN {amount_ngn:,.0f} for this meter at {earlier.get('ts')}, "
                             f"reference {earlier.get('reference')}. Nothing new was bought. If it has no token, "
                             f"use check_vend with that reference."}
        res = vend.buy(meter, amount_ngn)
        store.append("tokens", {"ts": now_iso(), "reference": res.reference, "meter_no": res.meter_no,
                                "amount_ngn": res.amount_ngn, "units": res.units or "", "token": res.token or "",
                                "status": res.status, "error": res.error or "", "requested_by": who})
    _log_top_up(res)
    return {"ok": res.status == "ok", **res.dict()}


@mcp.tool()
def check_vend(reference: str) -> dict:
    """Re-check a purchase that was paid but returned no token. Use when a previous buy_units
    returned status paid_no_token or timeout. Returns the token if the provider has now issued it."""
    before = next((r for r in store.rows("tokens") if r.get("reference") == reference), None)
    res = vend.requery(reference)
    if res.status == "ok":
        store.update_where("tokens", "reference", reference,
                           {"status": "ok", "token": res.token, "units": res.units, "error": ""})
        if before is None or before.get("status") != "ok":  # already counted when it first went ok
            _log_top_up(res)
    return {"ok": res.status == "ok", **res.dict()}


@mcp.tool()
def get_recent_activity(hours: float = 24) -> dict:
    """What has already been logged and bought in the last N hours, newest first: diesel purchases,
    tank levels, meter readings and every unit purchase with its status, token and reference.
    Call this before saying anything about an earlier purchase or log, because you cannot see the
    results of tool calls from earlier messages. Never say a purchase did not happen without checking."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    logs = [{k: r.get(k) for k in ("ts", "type", "litres", "cost_ngn", "meter_units", "logged_by")}
            for r in store.rows("energy") if _ts(r) >= cutoff and r.get("note") != "seed"]
    buys = [{k: r.get(k) for k in ("ts", "reference", "amount_ngn", "units", "token", "status", "requested_by", "error")}
            for r in store.rows("tokens") if _ts(r) >= cutoff]
    return {"hours": hours, "shop_meter_no": SHOP_METER_NO,
            "purchases": list(reversed(buys)), "logs": list(reversed(logs))}


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


def _diesel_litres_per_day(rows: list[dict]) -> float | None:
    """Litres burned per day between consecutive tank readings: earlier level + litres bought in
    between - later level. Returns None until there are two usable tank readings."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=RATE_WINDOW_DAYS)
    levels = sorted([r for r in rows if r.get("type") == "diesel_level" and _ts(r) >= cutoff], key=_ts)
    buys = [r for r in rows if r.get("type") == "diesel"]
    used = 0.0
    span_days = 0.0
    for a, b in zip(levels, levels[1:]):
        bought = sum(float(r["litres"] or 0) for r in buys if _ts(a) < _purchase_time(r, levels) <= _ts(b))
        dl = float(a["litres"]) + bought - float(b["litres"])
        if dl <= 0:
            continue
        used += dl
        span_days += max((_ts(b) - _ts(a)).total_seconds() / 86400, 1 / 24)
    return round(used / span_days, 2) if span_days else None


def _same(a, b) -> bool:
    try:
        return float(a) == float(b)
    except (TypeError, ValueError):
        return str(a).strip().lower() == str(b).strip().lower()


def _recent(r: dict) -> bool:
    return datetime.now(timezone.utc) - _ts(r) <= timedelta(minutes=DEDUPE_MINUTES)


def _append_once(row: dict, keys: tuple) -> dict:
    """Append a log row unless the same entry was logged in the last DEDUPE_MINUTES."""
    for r in reversed(store.rows("energy")):
        if _recent(r) and all(_same(r.get(k), row[k]) for k in keys):
            return {"ok": True, "already_logged": True, "logged": r,
                    "note": f"Already recorded at {r['ts']}; not added again."}
    store.append("energy", row)
    return {"ok": True, "logged": row}


def _recent_purchase(meter_no: str, amount_ngn: float, requested_by: str) -> dict | None:
    """A purchase by the same person, for the same meter and amount, in the last DEDUPE_MINUTES that may
    have taken money. Keyed on the person too: a different person buying the same amount is a new purchase."""
    for r in reversed(store.rows("tokens")):
        if (_recent(r) and _same(r.get("meter_no"), meter_no) and _same(r.get("amount_ngn"), amount_ngn)
                and _same(r.get("requested_by") or "unknown", requested_by)
                and r.get("status") not in ("invalid_meter", "declined")):
            return r
    return None


def _age_days(r: dict) -> float:
    return max((datetime.now(timezone.utc) - _ts(r)).total_seconds() / 86400, 0.0)


def _purchase_time(buy: dict, levels: list[dict]) -> datetime:
    """When a purchase entered the tank, for the maths. A purchase logged within SAME_MESSAGE_MINUTES after
    a tank reading is treated as already included in that reading."""
    t = _ts(buy)
    for lv in levels:
        gap = (t - _ts(lv)).total_seconds() / 60
        if 0 <= gap <= SAME_MESSAGE_MINUTES:
            return _ts(lv) - timedelta(seconds=1)
    return t


def _diesel_on_hand(rows: list[dict], burn: float | None) -> tuple[float | None, float | None]:
    """Estimated litres right now: last tank reading + litres bought since - burn since, floored at 0.
    Returns (litres, age of the tank reading in days). (None, None) if nobody has reported the tank yet."""
    levels = sorted([r for r in rows if r.get("type") == "diesel_level"], key=_ts)
    if not levels:
        return None, None
    last = levels[-1]
    age = _age_days(last)
    bought = sum(float(r["litres"] or 0) for r in rows
                 if r.get("type") == "diesel" and _purchase_time(r, levels) > _ts(last))
    est = float(last["litres"]) + bought - (burn or 0) * age
    return round(max(est, 0.0), 1), round(age, 1)


def _units_now(meters: list[dict], units_per_day: float | None) -> tuple[float | None, float | None]:
    """Estimated units right now: last meter reading - usage since, floored at 0.
    Returns (units, age of the reading in days). (None, None) if there are no readings."""
    if not meters:
        return None, None
    last = meters[-1]
    age = _age_days(last)
    est = float(last["meter_units"]) - (units_per_day or 0) * age
    return round(max(est, 0.0), 1), round(age, 1)


def _log_top_up(res) -> None:
    """After a successful vend, record the new meter balance so the forecast does not go stale.
    Skipped if there is no earlier reading to add to; the next staff reading fixes it."""
    if res.status != "ok" or not res.units:
        return
    meters = sorted([r for r in store.rows("energy") if r.get("type") == "meter"], key=_ts)
    if not meters:
        return
    now_est, _ = _units_now(meters, _units_per_day(meters))  # the old reading has been used since
    units = round(now_est + float(res.units), 1)
    store.append("energy", {"ts": now_iso(), "type": "meter", "litres": "", "cost_ngn": "",
                            "meter_units": units, "logged_by": "system", "note": f"top-up {res.reference}"})


def _ts(r: dict) -> datetime:
    return datetime.fromisoformat(str(r["ts"]))


class BearerAuth(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/mcp"):
            expected = os.getenv("MCP_BEARER_TOKEN", "")
            if not expected:  # fail closed: no token configured means nobody gets in
                return JSONResponse({"error": "server has no MCP_BEARER_TOKEN set"}, status_code=503)
            got = request.headers.get("authorization", "")
            if not hmac.compare_digest(got.encode(), f"Bearer {expected}".encode()):
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
