# CLAUDE.md

## What this is
Take-home exercise for TSG Labs (Paystack's venture studio). Build a Chord AI teammate on WhatsApp that does one useful job for a real business end to end. Scored on: integration (25%), deployment field notes (25%), problem choice (20%), customer thinking (15%), communication (15%). Role being applied for: Forward-deployed Engineering, which weights integration and field notes most.

## The problem chosen
A Lagos provisions store (fictional: Adaeze Provisions, Surulere) runs a diesel generator and a prepaid meter. Energy is its biggest hidden cost and it only finds out it is out of power when the lights go off. The agent logs diesel purchases and meter readings from staff over WhatsApp, projects when diesel or units will run out, sends a morning briefing, and buys prepaid units when the owner confirms, handling vend failures honestly (invalid meter, timeout, paid but no token, declined).

## Architecture
- Chord teammate: skill in `skill/SKILL.md` + `skill/references/shop.md`. Upload as folder, mark SKILL.md as Instructions, publish.
- Custom tool = remote MCP server (Chord only supports hosted MCP over Streamable HTTP at a public HTTPS URL; loopback blocked). Code in `tools/`. Bearer auth via `MCP_BEARER_TOKEN`.
- Storage: Google Sheet (gspread) if `SHEET_ID` + `GOOGLE_SA_JSON_CONTENT` (raw JSON) or `GOOGLE_SA_JSON` (file path) set, else `data/store.json`. Tabs `energy`, `tokens`, `requeries`. Sheet is project `adaeze-energy`, shared with `energy-agent@adaeze-energy.iam.gserviceaccount.com`, seeded via `scripts/seed_sheet.py` (rows tagged `note=seed`).
- Vending: `MockVend` (deterministic by meter suffix) is the code default; `VTPassVend` is complete against the VTpass sandbox (Ikeja Electric prepaid, verify then pay, wallet balance checked before and after). Deployed with `VEND_PROVIDER=vtpass`.
- Deploy: Google Cloud Run, project `adaeze-energy`, region `europe-west1`, service `energy-mcp`, via `bash scripts/deploy_cloudrun.sh` (Dockerfile build, env from `.env`, then sets `MCP_ALLOWED_HOSTS` to both Cloud Run hostnames). Not render.yaml; that file is kept but has never been deployed. The user runs the deploy script themselves: Claude Code's permission check blocks Claude from pushing secrets to a public service.
- Live: `https://energy-mcp-210407125100.europe-west1.run.app/mcp` (also `https://energy-mcp-meih7aeriq-ew.a.run.app`). /health, 401 without token and six-tool discovery verified on both. Scales to zero; cold start about 8.5s.
- Morning briefing: Chord schedule, DAILY 07:00 Africa/Lagos.

## Hard rules from the brief
- Test keys and made-up data only. No real customer data, live keys, or personal numbers.
- Agent must be built and run on Chord. Leave it live for reviewers.
- AI tools are allowed; the README must say briefly how they were used.
- 5-day window starts when Chord credits and simulator access arrive, not before.

## Done so far
- MCP server with six tools (log_fuel, log_diesel_on_hand, log_meter_reading, get_energy_summary, buy_units, check_vend), bearer auth, /health. `mcp` pinned to 1.26.0.
- VTpass sandbox: real vend to 1111111111111 succeeded (token, 79.9 kWh); requery confirmed. Token and units parsing unit-tested (`python -m unittest discover tests`).
- Forecast: top-ups logged as meter readings, burn rates from consumption intervals only, diesel days left from tank readings.
- Smoke test: `python scripts/smoke_test.py [base_url]`, all passing locally and against Cloud Run.
- Field notes in `notes/field-notes.md`; the three strongest are marked `[submission]`.
- Repo: private, `github.com/dayoolacodes/gen-agent`.

## Still to do (in order)
1. On Chord credits: register the MCP server with the Cloud Run URL above (auth_type bearer, `MCP_BEARER_TOKEN`), run tool discovery and health check, upload and publish the skill, get a first in-app reply.
2. Full WhatsApp simulator conversation incl. a buy with token, and the paid_no_token path with check_vend (use the mock meter ...22 or note why VTpass sandbox cannot produce it).
3. Schedule for the morning briefing. Watch for cold-start timeouts at 07:00; `--min-instances 1` if needed.
4. Field notes as problems happen. Go-live note (half page). README "AI tools used". 3-minute recording.
5. Submit: role preference + problem statement, live agent, repo (make public or add reviewers), recording, field notes, go-live note, via Google Drive link.

## Conventions
- Keep field notes in `notes/field-notes.md`, written at the moment a problem is hit, with exact error text.
- Do not add features beyond the brief. A small agent that works end to end with honest notes beats an ambitious one that half runs.
- British English, no em dashes in prose.
