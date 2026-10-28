# CLAUDE.md

## What this is
Take-home exercise for TSG Labs (Paystack's venture studio). Build a Chord AI teammate on WhatsApp that does one useful job for a real business end to end. Scored on: integration (25%), deployment field notes (25%), problem choice (20%), customer thinking (15%), communication (15%). Role being applied for: Forward-deployed Engineering, which weights integration and field notes most.

## The problem chosen
A Lagos provisions store (fictional: Adaeze Provisions, Surulere) runs a diesel generator and a prepaid meter. Energy is its biggest hidden cost and it only finds out it is out of power when the lights go off. The agent logs diesel purchases and meter readings from staff over WhatsApp, projects when diesel or units will run out, sends a morning briefing, and buys prepaid units when the owner confirms, handling vend failures honestly (invalid meter, timeout, paid but no token, declined).

## Architecture
- Chord teammate: skill in `skill/SKILL.md` + `skill/references/shop.md`. Upload as folder, mark SKILL.md as Instructions, publish.
- Custom tool = remote MCP server (Chord only supports hosted MCP over Streamable HTTP at a public HTTPS URL; loopback blocked). Code in `tools/`. Bearer auth via `MCP_BEARER_TOKEN`.
- Storage: Google Sheet (gspread) if `SHEET_ID` + `GOOGLE_SA_JSON` set, else `data/store.json`.
- Vending: `MockVend` (deterministic by meter suffix) by default; `VTPassVend` stub for the sandbox, `VEND_PROVIDER=vtpass`.
- Morning briefing: Chord schedule, DAILY 07:00 Africa/Lagos.

## Hard rules from the brief
- Test keys and made-up data only. No real customer data, live keys, or personal numbers.
- Agent must be built and run on Chord. Leave it live for reviewers.
- AI tools are allowed; the README must say briefly how they were used.
- 5-day window starts when Chord credits and simulator access arrive, not before.

## Pre-clock work done
- MCP server written and smoke-tested locally: all 5 tools, HTTP transport, 401 without token, tool discovery OK.
- `mcp` pinned to 1.26.0 (2.x renamed FastMCP and broke imports). See notes/field-notes.md.

## Still to do (in order)
1. Run server locally, test with MCP Inspector, expose with ngrok or deploy via render.yaml.
2. Google Sheet + service account (optional but good for the owner demo).
3. VTpass or BuyPower sandbox sign-up; fill in `VTPassVend` if access lands, else keep mock and note why.
4. On credits: upload skill, register MCP server, discover tools, health check, first in-app reply.
5. Full WhatsApp simulator conversation incl. a buy with token, and the paid_no_token path with check_vend.
6. Schedule for the morning briefing.
7. Field notes as problems happen. Go-live note (half page). README "AI tools used". 3-minute recording.
8. Submit: role preference + problem statement, live agent, repo, recording, field notes, go-live note, via Google Drive link.

## Conventions
- Keep field notes in `notes/field-notes.md`, written at the moment a problem is hit, with exact error text.
- Do not add features beyond the brief. A small agent that works end to end with honest notes beats an ambitious one that half runs.
- British English, no em dashes in prose.
