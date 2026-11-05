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
- Credits arrived (email received by 5 Nov). Simulator: chat.tsglabs.dev, after enabling Admin Panel > Connections > Connected Apps > Allow Approved Apps in the Chord dashboard.
- Chord tool-call timeout is 60s (TSG Labs). The simulator cannot receive scheduled tasks, so demo the briefing by asking for it in chat; show the schedule configured in the dashboard.

## Done so far
- MCP server with six tools (log_fuel, log_diesel_on_hand, log_meter_reading, get_energy_summary, buy_units, check_vend), bearer auth, /health. `mcp` pinned to 1.26.0.
- VTpass sandbox: real vend to 1111111111111 succeeded (token, 79.9 kWh); requery confirmed. Token and units parsing unit-tested (`python -m unittest discover tests`).
- Forecast: top-ups logged as meter readings, burn rates from consumption intervals only, diesel days left from tank readings.
- Smoke test: `python scripts/smoke_test.py [base_url]`, all passing locally and against Cloud Run.
- Field notes in `notes/field-notes.md`; the three strongest are marked `[submission]`.
- Repo: private, `github.com/dayoolacodes/gen-agent`.

## Still to do (in order)
1. Chord setup DONE 5 Nov (no credits used): Connected apps enabled and simulator approved; teammate "Energy Manager" (id ffea5a31-7db9-4f93-b21d-74c808f9f313, autonomy Act independently) with skill v1; MCP server `energy-tools` added under Admin > Channels & Tools > Tools, Health ok, six tools discovered. Open question: the teammate's Tools list does not show energy-tools, so whether it can call it is confirmed only by the first chat message.
   Testing rule: every chat message costs credits (50 total). Do all non-chat work first, then one planned test run.
2. Full WhatsApp simulator conversation incl. a buy with token, and the paid_no_token path with check_vend (use the mock meter ...22 or note why VTpass sandbox cannot produce it).
3. Schedule for the morning briefing. Watch for cold-start timeouts at 07:00; `--min-instances 1` if needed.
4. Field notes as problems happen. Go-live note (half page). README "AI tools used". 3-minute recording.
5. Submit: role preference + problem statement, live agent, repo (make public or add reviewers), recording, field notes, go-live note, via Google Drive link.

## Conventions
- Keep field notes in `notes/field-notes.md`, written at the moment a problem is hit, with exact error text.
- Do not add features beyond the brief. A small agent that works end to end with honest notes beats an ambitious one that half runs.
- British English, no em dashes in prose.
