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

### (28 Oct) VTpass merchant-verify rejects the public key
- What happened: verifying meter 1111111111111 with headers `api-key` + `public-key` returned HTTP 401 `{"code":"087","message":"INVALID CREDENTIALS"}`.
- How I found the cause: the Ikeja Electric page lists no headers. The Authentication page says GET uses api-key + public-key and POST uses api-key + secret-key. merchant-verify is a POST. The same call with `secret-key` returned 000 and `Customer_Name: TESTMETER1`.
- Fix: all three VTpass calls (merchant-verify, pay, requery) send api-key + secret-key. The public key is only used for GETs, which this agent does not make.
- What I'd change: put the required headers on every endpoint page, not only on the Authentication page.

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
- Fix or workaround: VTPassVend follows the VTpass rule that anything unclear is pending. 083, an empty body, 099, 000 with status pending or initiated, and 000 with no token all map to `paid_no_token`, and the agent requeries. Requery returning 015 maps to `declined` with "no money was taken". Known not-charged codes (028, 016, 018 and so on) map to `declined`. The client times out at 30s and returns `timeout`. The success mapping (strip the "Token : " prefix, parse "79.9 kWh") is only checked against the documented response shape, not a live vend. MockVend stays the default for the demo. Next step: ask VTpass support to whitelist ikeja-electric on the sandbox account (not yet requested).
- What I'd change: whitelist the documented test products on new sandbox accounts by default. Also add pending and unexpected test meters that pass merchant-verify, so verify-then-pay can be tested end to end.
