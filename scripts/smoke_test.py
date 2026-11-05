"""Smoke test: every tool and every mock vend outcome, against a throwaway JSON store.

    python scripts/smoke_test.py                       # tools in-process, MockVend
    python scripts/smoke_test.py http://127.0.0.1:8000  # also /health, auth and tool discovery on a running server
"""
import asyncio
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["JSON_STORE"] = os.path.join(tempfile.mkdtemp(), "store.json")
os.environ["VEND_PROVIDER"] = "mock"
os.environ.pop("SHEET_ID", None)

from tools import server as s  # noqa: E402

failures = []


def check(label, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + label + (f"  ({detail})" if detail else ""))
    if not cond:
        failures.append(label)


def tools_in_process():
    check("log_fuel", s.log_fuel(25, 32500, "Ade")["price_per_litre"] == 1300)
    check("log_fuel rejects zero", not s.log_fuel(0, 100)["ok"])
    check("log_diesel_on_hand", s.log_diesel_on_hand(30, "Ade")["ok"])
    check("log_meter_reading", s.log_meter_reading(300, "Ade")["ok"])
    check("log_meter_reading", s.log_meter_reading(260, "Tunde")["ok"])
    summary = s.get_energy_summary(7)
    check("get_energy_summary", {"diesel", "meter", "alerts"} <= summary.keys(), str(summary["meter"]))

    outcomes = {"62101234567": "ok", "62101234500": "invalid_meter", "62101234511": "timeout",
                "62101234522": "paid_no_token", "62101234533": "declined"}
    refs = {}
    for meter, want in outcomes.items():
        r = s.buy_units(meter, 5000, "owner")
        refs[want] = r["reference"]
        check(f"buy_units {meter} -> {want}", r["status"] == want, r.get("error") or r.get("token"))
    check("buy_units under NGN 1,000 -> declined", s.buy_units("62101234567", 500, "owner")["status"] == "declined")
    check("buy_units staff over limit -> needs_owner", s.buy_units("62101234567", 50000, "Ade")["status"] == "needs_owner")

    meter_after = s.get_energy_summary(7)["meter"]
    check("forecast survives top-up", meter_after["days_left"] is not None and meter_after["units_now"] > 260, str(meter_after))

    first = s.check_vend(refs["paid_no_token"])
    second = s.check_vend(refs["paid_no_token"])
    check("check_vend ...22 first call still pending", first["status"] == "paid_no_token")
    check("check_vend ...22 second call resolves", second["status"] == "ok" and bool(second["token"]))
    check("check_vend timeout first call still pending", s.check_vend(refs["timeout"])["status"] == "paid_no_token")
    check("check_vend timeout second call resolves", s.check_vend(refs["timeout"])["status"] == "ok")
    check("check_vend unknown reference -> declined", s.check_vend("NOPE")["status"] == "declined")


async def over_http(base):
    import httpx
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    health = httpx.get(f"{base}/health").json()
    check("/health", health.get("status") == "ok", str(health))
    no_auth = httpx.post(f"{base}/mcp", json={})
    check("/mcp without token -> 401", no_auth.status_code == 401)

    headers = {"Authorization": f"Bearer {os.environ['MCP_BEARER_TOKEN']}"}
    async with streamablehttp_client(f"{base}/mcp", headers=headers) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            names = sorted(t.name for t in (await session.list_tools()).tools)
    check("tool discovery lists six tools", len(names) == 6, ", ".join(names))
    return health


if __name__ == "__main__":
    tools_in_process()
    if len(sys.argv) > 1:
        asyncio.run(over_http(sys.argv[1].rstrip("/")))
    print(f"\n{len(failures)} failed" if failures else "\nall passed")
    sys.exit(1 if failures else 0)
