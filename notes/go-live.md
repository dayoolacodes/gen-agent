# Go-live note: Energy Manager for Adaeze Provisions

**What is live.** A Chord teammate, "Energy Manager", that staff and the owner message on WhatsApp. It logs diesel purchases, tank levels and meter readings to a Google Sheet, projects days of diesel and units left, gives a morning briefing (scheduled daily at 07:00 Lagos time), and buys prepaid units through the VTpass sandbox. Its six tools come from an MCP server on Google Cloud Run (`https://energy-mcp-210407125100.europe-west1.run.app/mcp`, bearer auth). Test keys and made-up data only.

**Try it.** https://chat.tsglabs.dev/c/m9kR88uLaoTOuUUHQY_c55C5 (business "Adaeze Provisions"). For example: "bought 25 litres diesel 32,500", "tank at about 15 litres", "meter showing 98", "how are we doing?", "buy 5000 units" then "yes".

**Checked before go-live.**
- Chord: Health `ok`, discovery lists all six tools. Server: smoke test on the live URL and 18 unit tests pass.
- Real VTpass sandbox vend returned a token (79.9 kWh); requery matched.
- Simulator run (6 Nov, recorded, 3 of 50 credits used): each log written once; alerts raised (units in 2.8 days, diesel spend over budget); a real VTpass purchase returned a token; the briefing then recommended diesel over units; a timed-out purchase (mock provider) got "still pending, money may have been taken, don't buy again", then the token on "check again".

**Problems found in the run.**
- The agent cannot see its own earlier tool results, so it replays earlier writes. The server now ignores identical logs and purchases for 30 minutes, so the Sheet stays correct and nobody is charged twice. The agent still sometimes "corrects" itself in chat.
- VTpass took about 20s, and the simulator showed "The agent didn't answer" while the purchase succeeded. Sending "yes" again returned the same token with no new charge.
- Asked for a daily 07:00 briefing in the simulator, the agent replied "Done" without calling the scheduling tool. I created it in the Direct Line afterwards (`schedule_reminder`, daily at 07:00 Africa/Lagos), and it now shows on the teammate.
- On the first purchase, after clarifying naira versus units, it bought on "okay 5000naira is fine" without reading back meter and amount again, though it had said it would. It never states the meter number, only "the one on file". In an earlier take it once sent "on file" as the meter number (rejected, no charge).

**Known limits.** Sandbox only. The "paid but no token" path can only be shown with the mock provider, since VTpass's pending test meter fails verification. The simulator cannot show scheduled tasks. Stock on hand is an estimate; the agent asks for a fresh reading when one is over 2 days old. A deliberate second identical purchase within 30 minutes is refused.

**Watch.** Any `timeout` or `paid_no_token` row in the `tokens` tab without a later `ok`. Cloud Run logs for errors and slow VTpass calls. Wallet balance and Chord credits.

**Rollback.** Pause the teammate in Chord (reversible), untick "Enabled" on the `energy-tools` server, or route Cloud Run back to an earlier revision. Live now: skill v4, revision `energy-mcp-00012-h54` (VTpass).
