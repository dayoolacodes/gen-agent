"""Storage for energy logs.

Two backends behind one interface:
- SheetsStore: Google Sheet via gspread (what the shop owner actually opens)
- JsonStore: local file, used when GOOGLE_SA_JSON / SHEET_ID are not set

Both expose: append(tab, row), rows(tab) -> list[dict]
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

ENERGY_HEADERS = ["ts", "type", "litres", "cost_ngn", "meter_units", "logged_by", "note"]
REQUERY_HEADERS = ["ts", "reference"]
TOKEN_HEADERS = ["ts", "reference", "meter_no", "amount_ngn", "units", "token", "status", "error"]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class JsonStore:
    def __init__(self, path: str = "data/store.json"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text(json.dumps({"energy": [], "tokens": []}, indent=2))

    def _load(self) -> dict:
        return json.loads(self.path.read_text())

    def _save(self, data: dict) -> None:
        self.path.write_text(json.dumps(data, indent=2))

    def append(self, tab: str, row: dict) -> None:
        data = self._load()
        data.setdefault(tab, []).append(row)
        self._save(data)

    def rows(self, tab: str) -> list[dict]:
        return list(self._load().get(tab, []))

    def update_where(self, tab: str, key: str, value: str, patch: dict) -> bool:
        data = self._load()
        hit = False
        for r in data.get(tab, []):
            if r.get(key) == value:
                r.update(patch)
                hit = True
        self._save(data)
        return hit


class SheetsStore:
    """Requires: pip install gspread, a service-account JSON, and the sheet shared with it."""

    def __init__(self, sheet_id: str, sa_json_path: str):
        import gspread  # imported lazily so JsonStore works without it

        gc = gspread.service_account(filename=sa_json_path)
        self.sh = gc.open_by_key(sheet_id)
        self._ensure("energy", ENERGY_HEADERS)
        self._ensure("tokens", TOKEN_HEADERS)
        self._ensure("requeries", REQUERY_HEADERS)

    def _ensure(self, tab: str, headers: list[str]):
        try:
            ws = self.sh.worksheet(tab)
        except Exception:
            ws = self.sh.add_worksheet(title=tab, rows=1000, cols=len(headers))
            ws.append_row(headers)
            return
        if not ws.row_values(1):
            ws.append_row(headers)

    def append(self, tab: str, row: dict) -> None:
        ws = self.sh.worksheet(tab)
        headers = ws.row_values(1)
        ws.append_row([str(row.get(h, "")) for h in headers])

    def rows(self, tab: str) -> list[dict]:
        return self.sh.worksheet(tab).get_all_records()

    def update_where(self, tab: str, key: str, value: str, patch: dict) -> bool:
        ws = self.sh.worksheet(tab)
        headers = ws.row_values(1)
        records = ws.get_all_records()
        hit = False
        for i, r in enumerate(records, start=2):
            if str(r.get(key)) == str(value):
                for k, v in patch.items():
                    if k in headers:
                        ws.update_cell(i, headers.index(k) + 1, str(v))
                hit = True
        return hit


def get_store():
    sheet_id = os.getenv("SHEET_ID")
    sa = os.getenv("GOOGLE_SA_JSON")
    if sheet_id and sa and Path(sa).exists():
        return SheetsStore(sheet_id, sa)
    return JsonStore(os.getenv("JSON_STORE", "data/store.json"))
