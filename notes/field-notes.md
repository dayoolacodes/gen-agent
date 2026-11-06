# Deployment field notes

Write each problem as you hit it. Two or three real ones beat a long list.

## Template

### <short title>
- What happened (include the exact error):
- How I found the cause:
- Fix or workaround:
- What I'd change in Chord, its docs or API:

## Notes

### mcp Python SDK 2.x renamed FastMCP
- What happened: `pip install mcp` pulled 2.x; `from mcp.server.fastmcp import FastMCP` raised ModuleNotFoundError pointing at the migration guide. A mixed 1.x/2.x install then broke `mcp.types` imports until the package directory was removed by hand.
- How I found the cause: the error message named the rename; `pip show mcp` confirmed 2.x.
- Fix: pinned `mcp==1.26.0` in requirements.txt.
- What I'd change: Chord's MCP guide could state which SDK versions its Streamable HTTP client has been tested against.

### Starlette has no `@app.route`
- What happened: adding a /health route with `@app.route` on the app returned by `streamable_http_app()` raised AttributeError.
- Fix: `app.add_route("/health", health, methods=["GET"])`.

### (28 Oct) VTpass merchant-verify: secret key, not public key
- What happened: I first sent merchant-verify with `api-key` + `public-key`, following my own brief, and got HTTP 401 `{"code":"087","message":"INVALID CREDENTIALS"}`.
- How I found the cause: the VTpass Authentication page says the public key is for GET endpoints only and POST endpoints take api-key + secret-key. merchant-verify, pay and requery are all POSTs. With `secret-key` the same call returned 000 and `Customer_Name: TESTMETER1`. VTpass behaved as documented; the brief was wrong.
- Fix: merchant-verify, pay and requery send api-key + secret-key. The public key is used only for the GET balance call.
- What I'd change: the Ikeja Electric page lists no headers, so you have to cross-reference the Authentication page. A one-line "POST: api-key + secret-key" on each endpoint page would have saved the round trip.

### (28 Oct) A wrong meter verifies as code 000
- What happened: verifying 62101234567 (and every sandbox meter except 1111111111111) returned `{"code":"000","content":{"error":"This meter is not correct or is not a valid Ikeja Electric prepaid meter. Please check and try again","WrongBillersCode":true}}`. The response codes page says verification success is 020 and lists 011/012/030 for failures.
- How I found the cause: compared raw JSON for a good and a bad meter. Only `content.WrongBillersCode` and `content.error` differ.
- Fix: `verify_meter` treats the meter as invalid if `WrongBillersCode` is true or `content.error` is set, whatever the code says.
- What I'd change: return a non-000 code for a failed verification, or document that `WrongBillersCode` is the field to check.

### (28 Oct) Sandbox pay blocked: 028 PRODUCT IS NOT WHITELISTED
- What happened: every `pay` call returned `{"code":"028","response_description":"PRODUCT IS NOT WHITELISTED ON YOUR ACCOUNT","content":{"errors":""}}`, including the documented success meter 1111111111111. The sandbox wallet shows NGN 2,000,000, so balance is not the cause. Requery on the same request_id also returns 028.
- How I found the cause: the error text is explicit. 028 is checked before anything else, so even a request_id without a date (`VNDAB12CD34`, which should get 085) returns 028.
- The other test meters, called on `pay` directly because only 1111111111111 passes verification:
  - 500000000000 (unexpected response): HTTP 500, `{"code":"083","content":{"errors":"OOPS!!! SYSTEM ERROR. PLEASE CONTACT TECH SUPPORT"}}`
  - 400000000000 (no response): HTTP 200 with an empty body, returned in under a second
  - 300000000000 (timeout): hung for about 60s, then returned 028
  - 201000000000 (pending): 028
  - Requery of the 083 and empty-body request_ids: `{"code":"015","response_description":"INVALID REQUEST ID"}`
- Fix or workaround: VTPassVend follows the VTpass rule that anything unclear is pending. 083, an empty body, 099, 000 with status pending or initiated, and 000 with no token all map to `paid_no_token`, and the agent requeries. Known not-charged codes (028, 016, 018 and so on) map to `declined`. The client times out at 30s and returns `timeout`. Requery returning 015 maps to `declined`, but does not claim "no money was taken", because requery has no balance to compare against (see the wallet balance note).
- Resolved: Ikeja Electric was then whitelisted in the VTpass sandbox dashboard (self-service; no support ticket needed). A vend to 1111111111111 for NGN 5,000 returned `"code":"000"`, status `delivered`, `"token":"Token : 26362054405982757802"`, `"units":"79.9 kWh"`. Requery returned the same token. VTPassVend maps it to `ok`, token `26362054405982757802`, 79.9 units.
- What I'd change: whitelist the documented test products on new sandbox accounts by default. Also add pending and unexpected test meters that pass merchant-verify, so verify-then-pay can be tested end to end.

### [submission] (28 Oct) Wallet balance: different envelope, net debit, shared wallet
- What happened: to stop the agent saying "no money was taken" on a guess, `buy` now reads the wallet balance before and after `pay`. Three surprises:
  - `GET /api/balance` returns `{"code":1,"contents":{"balance":"1995275.00"}}`. `code` is the integer 1, not the string "000", and the key is `contents`, not `content` as on every other endpoint.
  - A NGN 5,000 vend took the balance from 2,000,200.00 to 1,995,275.00, a drop of 4,925. VTpass debits the amount minus the 1.5% commission, so "did it drop by the amount" is the wrong test.
  - Between my first session and the whitelisting, the balance moved from 2,000,000.00 to 2,000,200.00 with no vend from this code. Anything else using the same wallet shows up in the before/after comparison.
- How I found the cause: raw JSON from balance, pay and balance again, in that order.
- Fix: `wallet_balance()` parses `contents.balance` and returns None if it cannot. `buy` checks whether the balance dropped at all. If it dropped and there is no token, the result is `paid_no_token` with the reference, whatever pay said. If it is unchanged and pay was refused, the error says "no money was taken". If the balance could not be read, the error says it is not confirmed. SKILL.md now tells the agent to say "no money was taken" only when the result says so. A failed meter verification can still say it, because pay is never called on that path. Known limit: another debit on the same wallet between the two reads would look like this vend's debit. That errs towards `paid_no_token` and a requery, which is the safe side.
- Also: the pay response includes the VTpass account holder's email and phone number. VendResult keeps only status, reference, meter, amount, units, token and error, so those never reach the store, the Sheet or WhatsApp. The sandbox also returns the same token on every vend, so token values cannot be used to tell sandbox vends apart.
- What I'd change: use the same response envelope on balance as on everything else, and return the debited amount (or a `charged` flag) in the pay response, so clients do not have to infer it from two balance reads.

### (28 Oct) Three naira figures in one VTpass receipt
- What happened: the successful NGN 5,000 vend to 1111111111111 returned three different naira figures: `"amount":5000`, `"total_amount":4925` inside `content.transactions` (amount minus the NGN 75 commission, which is what left the wallet), and `"tokenAmount":1860.47` at the top level. None of them can be reconciled with `"units":"79.9 kWh"` at the shop's tariff: 79.9 kWh at NGN 225 is about NGN 17,978, and 5,000 / 79.9 is about NGN 62.58 per kWh. The response also has `"tariff":"R2 SINGLE PHASE RESIDENTIAL"`, `"taxAmount":0` and `"debtAmount":0`, so tax and arrears do not explain the gap.
- How I found the cause: compared the figures in the raw pay JSON and the matching wallet balance change (2,000,200.00 to 1,995,275.00, a drop of 4,925). I could not find what tokenAmount means in the Ikeja Electric docs, and sandbox values may not follow real DisCo arithmetic.
- Fix or workaround: the agent does not try to reconcile them. It reports what the owner asked to spend, the units bought (parsed from `units`), the token and the reference. That is what Adaeze checks against the meter display. The wallet debit (total_amount) is only used to decide whether money was taken (see the wallet balance note).
- What I'd change: define `tokenAmount` in the docs, and return units as a number, not a string with "kWh" appended.

### [submission] (28 Oct) Behind ngrok, authenticated MCP calls get 421 Invalid Host header
- What happened: with the server exposed through `ngrok http 8000`, `GET /health` returned 200 and `POST /mcp` without a token returned 401, so the tunnel looked healthy. MCP tool discovery with the bearer token then failed with `httpx.HTTPStatusError: Client error '421 Misdirected Request'`. Repeating the initialize call with curl gave the body `Invalid Host header`. Locally on 127.0.0.1 everything passed.
- How I found the cause: grepped the installed SDK for the message. In mcp 1.26.0, `FastMCP(...)` defaults to `host="127.0.0.1"`, and for that host it silently enables `TransportSecuritySettings` with `allowed_hosts=["127.0.0.1:*", "localhost:*", "[::1]:*"]` (mcp/server/fastmcp/server.py, around line 178). The process was listening on 0.0.0.0 through uvicorn, but FastMCP did not know that, so the public Host header was rejected. The 401 check passed only because our bearer middleware runs before the SDK's host check, which is why the unauthenticated smoke test missed it. The allowlist matches exact hosts or `host:*` ports only, so `*.ngrok-free.app` cannot be allowed.
- Fix: kept the protection on and added `MCP_ALLOWED_HOSTS` (comma-separated, exact hostnames) to the localhost defaults. Set it to the ngrok hostname in `.env`, restarted, and discovery through the public URL lists all six tools. Added it to `.env.example`, `render.yaml` and the README. A free ngrok hostname changes on restart, so this has to be updated each time, or use a reserved domain.
- What I'd change: Chord's MCP setup guide could warn that Python FastMCP servers behind a tunnel or proxy return 421 unless the public host is allowed. Chord's own health check should also do an authenticated `initialize`, not just reach the URL, so this shows up at registration time and not on the first WhatsApp message.

### (28 Oct) Cloud Run serves on two hostnames, and neither is known before the first deploy
- What happened: Cloud Run gave the service two URLs, `energy-mcp-210407125100.europe-west1.run.app` and `energy-mcp-meih7aeriq-ew.a.run.app`. Because of the 421 fix, `MCP_ALLOWED_HOSTS` has to list exact hostnames, and these only exist once the service is created. The comma-separated value also breaks `gcloud run services update --update-env-vars`, which uses commas to split variables.
- How I found the cause: `gcloud run services describe --format=json` lists both in the `run.googleapis.com/urls` annotation, while `status.url` gives only one.
- Fix: `scripts/deploy_cloudrun.sh` deploys with a placeholder, reads both hostnames from the annotation, then updates the service with `--update-env-vars "^;^MCP_ALLOWED_HOSTS=host1,host2"` (`^;^` switches the delimiter). Two revisions on every first deploy. /health, the 401 and six-tool discovery pass on both hostnames.
- What I'd change: Chord should register and health-check whichever single URL you give it, and its docs should say whether it follows redirects or pins the Host header, so I know whether both hostnames need allowing.

### (28 Oct) Hosted store is the Google Sheet, which behaves differently from the local JSON file
- What happened: locally the store had been `data/store.json`. On Cloud Run there is no file to mount and the disk is wiped per instance, so the hosted server uses the Sheet with credentials from `GOOGLE_SA_JSON_CONTENT`. Three differences showed up:
  - Before the Sheet was shared, gspread raised a bare `PermissionError` with no message. The real error, `APIError: [403]: The caller does not have permission`, was only visible on `__cause__`.
  - Sheets numericises cells on read by default, so a digit-only token or meter number would come back as an int and lose leading zeros. The JSON file keeps strings.
  - Every tool call is now a network round trip to Google. `get_energy_summary` over MCP from my laptop to Cloud Run took 1.86s, including the MCP initialize.
- How I found the cause: unwrapped the exception chain for the 403. For numericising, read gspread's `get_all_records` defaults before the first hosted write.
- Fix: rows are read with `numericise_ignore=["all"]`, and the code already converts numeric fields with float(). The Sheet ID, the service-account email and the "share as Editor" step are in the README.
- What I'd change: nothing on Chord's side. gspread could put the API message on its PermissionError.

### (28 Oct) Cold start on Cloud Run is about 8.5s
- What happened: the service scales to zero when idle. In the logs, a new instance went from `Starting new instance` (17:57:36.79) to `STARTUP TCP probe succeeded` (17:57:45.33), about 8.5s. That covers container start, Python imports and opening the Sheet. Locally the server is always warm. The 07:00 Lagos briefing will almost always hit a cold instance, because nothing calls the server overnight.
- How I found the cause: `gcloud logging read` on the service after deploy.
- Fix or workaround: none yet. The service runs at minimum instances 0 to stay inside the free tier. If Chord's tool-call timeout turns out to be under about 10s, setting `--min-instances 1` removes cold starts at a small monthly cost.
- What I'd change: Chord's docs should state the MCP tool-call timeout, and whether it retries a tool call that times out. A retried `buy_units` is a double purchase, so this matters for anything that moves money.

### (5 Nov) Chord answers: 60s tool timeout, simulator cannot receive scheduled tasks
- What happened: TSG Labs confirmed with the credits that "The timeout is currently 60 seconds" and "At this time, the simulator cannot receive scheduled tasks". I had asked about both because neither is in the docs I had.
- Effect on the 07:00 briefing: the schedule can be created, but its output cannot be seen in the channel simulator. For the demo the briefing has to be triggered by hand in chat ("give me the morning briefing"), which runs the same tool and skill instructions. The schedule itself can only be shown configured in the dashboard.
- Effect on buy_units: a cold start (about 8.5s) is well inside 60s. The VTpass path is not. VTPassVend makes four sequential calls (merchant-verify, balance, pay, balance), each with a 30s client timeout, so the worst case is about 120s plus Sheet writes. If Chord abandons the call at 60s, the server keeps running and pay may still succeed and debit the wallet, while the agent has been told the tool failed. A retry by the agent or the user is then a double purchase. The realistic slow case (VTpass's timeout meter hung about 60s, cut to 30s by our client, other calls under a second) comes to roughly 45s with a cold start, so it fits, but only just.
- Fix: VTPassVend.buy now has a 40s budget (`VTPASS_BUY_BUDGET_S`). Verify gets 8s, each balance read 5s, and pay gets whatever is left after keeping 5s back for the closing balance check. If less than 10s would be left for pay, it is not started and the result says no money was taken. 40s plus a cold start (about 8.5s) plus the Sheet writes (about 3s) is about 52s, under Chord's 60s. SKILL.md now forbids calling buy_units again for a purchase that may have gone through: check_vend with the reference first, and if the tool call failed with no result, escalate to Adaeze. Unit tests in `tests/test_vtpass_budget.py`.
- Measured the same day: VTpass sandbox pay to 1111111111111 took 18.09s (verify 0.50s, balance 0.34s and 0.39s). On 28 Oct the same call was under a second. The budget is for exactly this kind of swing.
- What I'd change: document the tool timeout and whether Chord retries a timed-out tool call. For tools that move money, an idempotency key that Chord passes on retries would make this safe by design. Also document that the simulator does not deliver scheduled tasks, so builders plan the demo around it.

### (5 Nov) Chord setup: what the screens actually do
- What happened: setup went in this order. Connected apps (enable "Allow approved apps", allow "Whatsapp Simulator"), approve the simulator's OAuth request, create the teammate from a skill ZIP, add the MCP server, run Health and Tools. Four things did not match what I expected or had written in the README:
  - Signing in to chat.tsglabs.dev before the Connected apps step gives "Access to Whatsapp Simulator isn't enabled for this organization. An administrator can review it under Admin › Connected apps." After enabling both toggles, "Check access again" on the same page moved on to the consent screen. TSG's email lists the toggle first; the order matters.
  - The skill shows as "Untitled skill" even though SKILL.md has `name: energy-manager` in its frontmatter, which Chord's own upload page tells you to add. The name is a separate "Skill name" field in Edit draft. Setting it there and republishing (v2, 05:27) fixed it. Re-uploading the ZIP in Edit draft showed "Replaces: SKILL.md" and "Replaces: references/shop.md", so files at the same path are replaced, not duplicated.
  - A teammate's Settings -> Tools -> "Add tool" is a link to Admin -> Channels & Tools -> Tools. MCP servers are added there, for the whole workspace. After adding `energy-tools` (Health `ok · 5733 ms`, Tools lists all six), the teammate's own Tools list still shows only the first-party connectors (Bookings, Checklist, GitHub, Paystack, Linear, Notion). There is no toggle to grant energy-tools to Energy Manager.
  - The dashboard home showed "Credits 0" while loading; the sidebar showed 50 a moment later.
- How I found the cause: worked through the dashboard in the browser and read each page's text.
- Fix or workaround: README updated with the real click path. Whether Energy Manager can call workspace MCP tools without a per-teammate grant is not confirmed yet. Checking needs a chat message, which costs credits, so it is the first thing in the test run.
- What I'd change: show custom MCP servers in each teammate's Tools list with a toggle, or say on the teammate page that workspace MCP servers apply to every teammate. Use the frontmatter `name` as the skill title.

### (5 Nov) No way to create a schedule without spending credits
- What happened: the teammate's Settings panel (Tools and connections -> Channels) has a "Briefings & schedule" section that only says "No scheduled briefings.", with no add button. Admin -> Channels & Tools -> Developer has webhooks, outbound "API credentials" for REST tools, and a route tester, but no key for Chord's own API, so the `POST /v1/teammates/{id}/schedules` route I had noted from the docs cannot be called from here. The only remaining way is to ask the teammate in chat, which costs credits, and every daily run will cost credits too. Dashboard build: 0.15.22 (build 0000000027, commit c71c07e4adc8), Required Core 0.16.0.0.
- How I found the cause: searched the teammate page and the Admin pages for any schedule control.
- Fix or workaround: the 07:00 schedule is created by one chat message during the planned test run, at the end of the window, so it does not burn credits on mornings nobody can see (the simulator cannot receive scheduled tasks anyway). The briefing content is demoed by asking for it in chat.
- What I'd change: an "Add briefing" button in Briefings & schedule (time, timezone, prompt), and a note on how many credits a scheduled run costs.

### (5 Nov) First message: workspace MCP tools work without a per-teammate grant, but the seed data had gone stale
- What happened: in Energy Manager's direct line I sent "how are we doing on fuel?". "How I did this" showed one step, `mcp__energy-tools__get_energy_summary`, 531ms. Cloud Run logs at 05:21 UTC show `ListToolsRequest` (6.85s, cold start: "Starting new instance. Reason: AUTOSCALING") then `CallToolRequest` (0.42s). So a teammate can call a workspace MCP server even though its own Tools list does not show it. The credit counter still read 50 afterwards.
- Second finding: the reply said "24 litres on hand ... roughly 2 days left. No purchases logged in the last 7 days." The seed was written on 28 Oct, eight days earlier, so purchases had aged out of the 7-day window while the 8-day-old tank and meter readings were still reported as current. That is the elapsed-time gap in the forecast: days left are counted from the last reading, not from today.
- Fix: the summary now estimates stock for today: last reading, plus litres bought since, minus burn since, floored at 0. It reports `last_reading_days_ago`, and alerts when a reading is over 2 days old ("ask staff for a fresh reading") or the estimate has hit zero ("probably run out by now"). A top-up is now logged on top of today's estimate, not the old reading. SKILL.md tells the agent to say "about" and to ask for a fresh reading when one is old. Against the stale Sheet, the new code said both diesel and units had probably run out and both readings were 8 days old, which is the useful answer for the shop. `seed_sheet.py --reset` deletes only rows tagged `note=seed` and writes a fresh week; run on the live Sheet it removed 16 and wrote 16. Tests in `tests/test_forecast.py`.
- What I'd change: nothing in Chord. The tool-call trace with timings in "How I did this" made this quick to confirm.

### (6 Nov) A simulator chat link is one conversation; the only reset is a new link
- What happened: a first recording attempt sent one message ("bought 20 litres diesel 26,000", logged at 01:14 UTC). To retake from a clean screen, reopening the link in a private window still showed the old conversation, so the history is stored against the link on the server, not in the browser.
- How I found the cause: private window and the same link gave the same chat. "Share link -> New link" issued `/c/MwDxwvjvAWqtFvfXGxPTwSfa`, and the old `/c/ut37YNbTyU6nXkMZS5JiACTU` then returned HTTP 404.
- Fix or workaround: new link for the recording; the first attempt's row was deleted from the Sheet so the screen and the Sheet agree. The go-live note has the new link.
- What I'd change: a "Reset conversation" button on the link, so a builder can retake a demo without breaking a link already shared with reviewers.

### [submission] (6 Nov) Chord's agent replays earlier write tool calls on every new message
- What happened: in the recorded simulator take, message 1 ("Bought 20litres diesel 26,000") logged one row and the agent replied "Logged". On message 2 ("tank at about 30liters") it replied "I need to correct my earlier reply. I said the purchase was logged, but it hadn't been recorded yet. It is now." and logged the diesel again plus the tank. On message 3 ("meter showing 85") it logged the diesel, the tank and the meter again. The Sheet ended with the 20 L purchase three times and the tank twice.
- How I found the cause: Cloud Run logs show one CallToolRequest at 01:22:31, two at 01:23:00, and three at 01:23:40-42 (plus one at 01:23:45). The number of write calls grows by one per turn, and the agent's own words show it could not see its earlier tool results. Each turn starts without the previous turns' tool results, so the model "catches up" by redoing them. With buy_units this would be a second purchase on the next message.
- Fix: made the server safe against replays, since the agent cannot be relied on to remember. An identical log (same type, values and sender) within 30 minutes (`DEDUPE_MINUTES`) is not added again and returns `already_logged` with the original time. An identical purchase (same meter and amount) within 30 minutes that may have taken money returns `already_bought` with the earlier status, reference and token, and is not bought again. A declined or invalid-meter attempt can be retried. SKILL.md now says to act only on the newest message and never redo earlier logs or purchases. Tests in `tests/test_dedupe.py`. On the next take the Sheet stayed clean, but the agent still replayed and then narrated the server's answer to the customer: "Correction to my last message: the 20 litres purchase (NGN 26,000) was already recorded earlier, so nothing was added twice." Skill v4 tells it to stay silent about already_logged and to treat already_bought as the answer only when the newest message is about that purchase. The take was abandoned, the replayed rows deleted, and a new chat link issued.
- What I'd change: keep tool calls and their results in the conversation history the model sees on later turns, or document that they are dropped. Pass a stable message or turn ID to MCP tools so servers can de-duplicate properly. Anyone wiring payments to Chord needs to know this before going live.

### (6 Nov) The simulator gave up on the reply while the purchase was succeeding
- What happened: on the recorded take, "yes" to "buy NGN 5,000 of units" produced "The agent didn't answer. Try sending again." in the simulator. On the server the purchase succeeded: buy_units HTTP 200 in 20.27s (request at 01:39:19 UTC), VTpass status `ok`, token 26362054405982757802, 79.9 kWh, reference 202611060239C1X6F80V, and the top-up row (85 + 79.9 = 164.9) was written. Money moved and a token existed, but the person in the chat saw nothing. That is the exact situation the agent is meant to never leave someone in.
- How I found the cause: the Cloud Run request log shows one buy call of 20.27s, well inside the 60s tool timeout TSG Labs gave me. So the limit that tripped is the simulator's own wait for a whole agent reply (model time + 20s tool call + model time), which is shorter than the tool timeout and not documented. VTpass sandbox pay itself took most of it (18.09s on 5 Nov; under 1s on 28 Oct).
- Fix or workaround: resending is safe by design. The replay protection returns `already_bought` with the same token and reference for the same meter and amount within 30 minutes, so "yes" again shows the token without a second purchase. For the retake, this take's rows (and the purchase row, recorded here) were removed from the Sheet so the retake's purchase is not refused as a repeat. A proper fix would make buy_units return at once with a reference and let check_vend collect the token, so no reply depends on VTpass speed; not done for this submission.
- What I'd change: document the simulator's reply timeout, and show "still working" rather than "didn't answer" while a tool call is in flight. Or deliver the late reply when it arrives, as WhatsApp would.
