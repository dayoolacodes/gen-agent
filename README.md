# Energy manager agent for a Lagos provisions store (Chord take-home)

A Chord teammate on WhatsApp that logs generator diesel and prepaid meter readings,
projects when power will run out, and buys electricity units when the owner says so.

## Layout

```
skill/          SKILL.md + references/shop.md   -> upload as the Chord skill
tools/          MCP server (FastMCP, Streamable HTTP) -> register in Chord as a tool server
  server.py     six tools: log_fuel, log_diesel_on_hand, log_meter_reading, get_energy_summary, buy_units, check_vend
  storage.py    Google Sheet (gspread) or local JSON, same interface
  vend.py       vending providers: MockVend (deterministic, default) and VTPassVend (VTpass sandbox)
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

Chord blocks loopback and private URLs, so the server has to be public.

**Live deploy (Google Cloud Run, europe-west1):** `https://energy-mcp-210407125100.europe-west1.run.app/mcp`
(also served at `https://energy-mcp-meih7aeriq-ew.a.run.app`). To redeploy: `bash scripts/deploy_cloudrun.sh`.
It reads `.env`, sends the service-account JSON as `GOOGLE_SA_JSON_CONTENT`, deploys from the `Dockerfile`,
then sets `MCP_ALLOWED_HOSTS` to both Cloud Run hostnames. Without that, every MCP call gets 421 "Invalid Host header".

For a quick test from a laptop, `ngrok http 8000` works too; set `MCP_ALLOWED_HOSTS` to the ngrok hostname
and restart. `render.yaml` is kept as an alternative but has not been deployed.

## Register in Chord

Chord app: Teammate settings -> Tools -> Add tool, or via API
(`POST /v1/workspaces/{ws}/mcp-servers`) with
`{"name":"energy-tools","url":"https://<host>/mcp","auth_type":"bearer","auth_token":"<MCP_BEARER_TOKEN>","transport":"streamable_http"}`.
Then run tool discovery (`POST .../mcp-servers/{id}/tools`) and health (`POST .../health`);
check `status` in the health body, not just HTTP 200.

## Skill

Upload `skill/` as a folder or ZIP. Mark `SKILL.md` as Instructions. Publish, then test in-app
with: `bought 25 litres diesel 32,500` / `tank at about 15 litres` / `meter showing 1200` / `how are we doing on fuel` /
`buy 5000 units`.

## Demo meter numbers (mock provider)

62101234567 ok | ...00 invalid_meter | ...11 timeout | ...22 paid_no_token | ...33 declined

## Schedule (morning briefing)

`POST /v1/teammates/{id}/schedules` with cadence DAILY 07:00 Africa/Lagos and task_prompt
"Run get_energy_summary for 1 day and write the morning note."

## Google Sheet (optional, owner-facing)

Create a sheet, share it with a service account as Editor, set `SHEET_ID` and either `GOOGLE_SA_JSON`
(file path) or `GOOGLE_SA_JSON_CONTENT` (the raw JSON). Tabs `energy`, `tokens` and `requeries` are created
on first run. `python scripts/seed_sheet.py` adds a week of made-up history so the first summary is not empty.

## AI tools used

(Fill in briefly: what was drafted with an assistant, what was written and verified by hand.)
