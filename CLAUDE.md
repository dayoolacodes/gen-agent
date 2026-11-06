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

## Conventions
- Keep field notes in `notes/field-notes.md`, written at the moment a problem is hit, with exact error text.
- Do not add features beyond the brief. A small agent that works end to end with honest notes beats an ambitious one that half runs.
- British English, no em dashes in prose.
