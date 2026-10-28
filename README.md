# Energy manager agent for a Lagos provisions store (Chord take-home)

A Chord teammate on WhatsApp that logs generator diesel and prepaid meter readings,
projects when power will run out, and buys electricity units when the owner says so.

## Layout

```
skill/          SKILL.md + references/shop.md   -> upload as the Chord skill
tools/          MCP server (FastMCP, Streamable HTTP) -> register in Chord as a tool server
  server.py     five tools: log_fuel, log_meter_reading, get_energy_summary, buy_units, check_vend
  storage.py    Google Sheet (gspread) or local JSON, same interface
  vend.py       vending providers: MockVend (deterministic) and VTPassVend (sandbox stub)
notes/          field-notes.md (written as problems are hit) and go-live note
```

## Run the tool server

```
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # set MCP_BEARER_TOKEN
export $(cat .env | xargs)
python -m tools.server          # http://127.0.0.1:8000/mcp , /health
```

Expose it publicly (Chord blocks loopback/private URLs): `ngrok http 8000` for testing,
or deploy with `render.yaml`.

## Register in Chord

Chord app: Teammate settings -> Tools -> Add tool, or via API
(`POST /v1/workspaces/{ws}/mcp-servers`) with
`{"name":"energy-tools","url":"https://<host>/mcp","auth_type":"bearer","auth_token":"<MCP_BEARER_TOKEN>","transport":"streamable_http"}`.
Then run tool discovery (`POST .../mcp-servers/{id}/tools`) and health (`POST .../health`);
check `status` in the health body, not just HTTP 200.

## Skill

Upload `skill/` as a folder or ZIP. Mark `SKILL.md` as Instructions. Publish, then test in-app
with: `bought 25 litres diesel 32,500` / `meter showing 1200` / `how are we doing on fuel` /
`buy 5000 units`.

## Demo meter numbers (mock provider)

62101234567 ok | ...00 invalid_meter | ...11 timeout | ...22 paid_no_token | ...33 declined

## Schedule (morning briefing)

`POST /v1/teammates/{id}/schedules` with cadence DAILY 07:00 Africa/Lagos and task_prompt
"Run get_energy_summary for 1 day and write the morning note."

## Google Sheet (optional, owner-facing)

Create a sheet, share it with a service account, set `SHEET_ID` and `GOOGLE_SA_JSON`.
Tabs `energy` and `tokens` are created on first run.

## AI tools used

(Fill in briefly: what was drafted with an assistant, what was written and verified by hand.)
