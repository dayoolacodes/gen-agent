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

1. Admin -> Channels & Tools -> Tools tab -> Custom tools (MCP) -> Add server. (The "Add tool" link in a
   teammate's settings sends you here.) Name `energy-tools`, URL `https://<host>/mcp`, Auth type `bearer`,
   Auth token = `MCP_BEARER_TOKEN` (no "Bearer " prefix), Transport `streamable_http`, Allowed tools blank.
2. The server row's menu has Health and Tools. Health showed `ok · 5733 ms` on a cold instance; Tools listed
   all six. The same is available over the API (`POST /v1/workspaces/{ws}/mcp-servers`, then `.../tools`
   and `.../health`; check `status` in the health body, not just HTTP 200).

## Skill

Home -> Create a teammate -> upload `skill/` as a ZIP (SKILL.md and references/shop.md at the root).
Chord marks `SKILL.md` as Instructions on its own. Teammate: name "Energy Manager", role "Power and fuel for
Adaeze Provisions", autonomy "Act independently" (purchases are still gated by the skill's confirm step).

For the WhatsApp simulator: Admin -> Connected apps -> enable "Allow approved apps" and allow
"Whatsapp Simulator", then sign in at chat.tsglabs.dev and approve the access request.
Test messages: `bought 25 litres diesel 32,500` / `tank at about 15 litres` / `meter showing 1200` /
`how are we doing on fuel` / `buy 5000 units`.

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

I used Claude Code (Claude Opus) as a pair programmer throughout.

- **Drafted with the assistant:** the MCP server and tools, the VTpass integration, the forecast logic, the unit and smoke tests, the Dockerfile and Cloud Run deploy script, and first drafts of the field notes, this README and the go-live note.
- **Run and checked live:** every VTpass behaviour in the field notes comes from real sandbox calls with the raw JSON kept, not from the docs. The assistant also worked through the Chord dashboard in my browser (Connected apps, teammate, MCP server, Health and Tools checks).
- **Mine:** choosing the problem and the shop, every decision on trade-offs (hosting, autonomy, the purchase time budget, demo plan), all account sign-ins and consent screens, pasting secrets, and running the deploys. Claude Code's permission check blocked the assistant from sending secrets to Cloud Run itself, so I ran the deploy script. I reviewed each change before it was committed.
