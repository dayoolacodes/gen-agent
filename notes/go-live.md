# Go-live note: Energy Manager for Adaeze Provisions

**What is live.** A Chord teammate, "Energy Manager" (workspace Dayo, autonomy "Act independently"), that staff and the owner message on WhatsApp. It logs diesel purchases, tank levels and meter readings to a Google Sheet, projects days of diesel and units left, gives a three-line morning briefing, and buys prepaid units through the VTpass sandbox. Its tools come from one MCP server on Google Cloud Run: `https://energy-mcp-210407125100.europe-west1.run.app/mcp` (bearer auth, six tools). All data is made up and all keys are sandbox keys.

**How to try it.** Simulator chat link: [TO FILL after the test run]. Try: "bought 25 litres diesel 32,500", "tank at about 15 litres", "meter showing 98", "how are we doing on fuel", "buy 5000 units" then "yes".

**Checked before go-live.**
- Chord: Health `ok`, tool discovery lists all six tools.
- Server: smoke test passes on the live URL (/health, 401 without a token, discovery, every tool, every mock vend outcome). 9 unit tests pass (token and units parsing, purchase time budget).
- VTpass sandbox: real vend to meter 1111111111111 returned a token and 79.9 kWh; requery matched.
- A purchase is bounded to about 52s worst case (cold start included), under Chord's 60s tool timeout.
- In the simulator: [TO FILL: tool call confirmed, purchase with token, timeout then pending then token via check_vend, briefing on request, anything that failed].

**Known limits.**
- Sandbox only. The "paid but no token" path was shown with the mock provider, because VTpass's pending test meter fails verification before payment.
- The 07:00 briefing is scheduled, but the simulator cannot show scheduled tasks, so the demo asks for it in chat.
- Stock on hand is an estimate from the last reading and the usual burn. If staff stop sending readings, the agent says the reading is old and asks for a new one.
- Each Chord message uses credits.

**What to watch.**
- `tokens` tab in the Sheet: any `paid_no_token` or `timeout` row without a later `ok` needs a check before anyone buys again.
- Cloud Run logs for errors and slow VTpass calls (sandbox pay has taken between 1s and 18s).
- VTpass sandbox wallet balance, and Chord credits.

**Rollback.**
- Pause the teammate in Chord (reversible, history kept).
- Untick "Enabled" on the `energy-tools` server.
- Route Cloud Run traffic back to an earlier revision, or redeploy with `VEND_PROVIDER=mock`.
