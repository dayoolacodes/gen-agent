# Deployment field notes

Write each problem as you hit it. Two or three real ones beat a long list.

## Template

### <short title>
- What happened (include the exact error):
- How I found the cause:
- Fix or workaround:
- What I'd change in Chord, its docs or API:

## Notes

### (pre-clock) mcp Python SDK 2.x renamed FastMCP
- What happened: `pip install mcp` pulled 2.x; `from mcp.server.fastmcp import FastMCP` raised ModuleNotFoundError pointing at the migration guide. A mixed 1.x/2.x install then broke `mcp.types` imports until the package directory was removed by hand.
- How I found the cause: the error message named the rename; `pip show mcp` confirmed 2.x.
- Fix: pinned `mcp==1.26.0` in requirements.txt.
- What I'd change: Chord's MCP guide could state which SDK versions its Streamable HTTP client has been tested against.

### (pre-clock) Starlette has no `@app.route`
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

### (28 Oct) Wallet balance: different envelope, net debit, shared wallet
- What happened: to stop the agent saying "no money was taken" on a guess, `buy` now reads the wallet balance before and after `pay`. Three surprises:
  - `GET /api/balance` returns `{"code":1,"contents":{"balance":"1995275.00"}}`. `code` is the integer 1, not the string "000", and the key is `contents`, not `content` as on every other endpoint.
  - A NGN 5,000 vend took the balance from 2,000,200.00 to 1,995,275.00, a drop of 4,925. VTpass debits the amount minus the 1.5% commission, so "did it drop by the amount" is the wrong test.
  - Between my first session and the whitelisting, the balance moved from 2,000,000.00 to 2,000,200.00 with no vend from this code. Anything else using the same wallet shows up in the before/after comparison.
- How I found the cause: raw JSON from balance, pay and balance again, in that order.
- Fix: `wallet_balance()` parses `contents.balance` and returns None if it cannot. `buy` checks whether the balance dropped at all. If it dropped and there is no token, the result is `paid_no_token` with the reference, whatever pay said. If it is unchanged and pay was refused, the error says "no money was taken". If the balance could not be read, the error says it is not confirmed. SKILL.md now tells the agent to say "no money was taken" only when the result says so. A failed meter verification can still say it, because pay is never called on that path. Known limit: another debit on the same wallet between the two reads would look like this vend's debit. That errs towards `paid_no_token` and a requery, which is the safe side.
- Also: the pay response includes the VTpass account holder's email and phone number. VendResult keeps only status, reference, meter, amount, units, token and error, so those never reach the store, the Sheet or WhatsApp. The sandbox also returns the same token on every vend, so token values cannot be used to tell sandbox vends apart.
- What I'd change: use the same response envelope on balance as on everything else, and return the debited amount (or a `charged` flag) in the pay response, so clients do not have to infer it from two balance reads.
