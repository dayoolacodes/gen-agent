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
