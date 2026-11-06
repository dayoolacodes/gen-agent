# Go-live note: Energy Manager for Adaeze Provisions

**What is live.** A Chord teammate, "Energy Manager", that staff and the owner message on WhatsApp. It logs diesel purchases, tank levels and meter readings to a Google Sheet, projects days of diesel and units left, gives a morning briefing (scheduled daily at 07:00 Lagos time), and buys prepaid units through the VTpass sandbox. Its six tools come from an MCP server on Google Cloud Run (`https://energy-mcp-210407125100.europe-west1.run.app/mcp`, bearer auth). Test keys and made-up data only.

**Try it.** https://chat.tsglabs.dev/c/AXtJLHL6jR6CMZrX2oTIyrBN (business "Adaeze Provisions"). For example: "bought 25 litres diesel 32,500", "tank at about 15 litres", "meter showing 98", "how are we doing?", "buy 5000 units" then "yes".

**Checked before go-live.**
- Chord: Health `ok`, discovery lists all six tools. Server: smoke test on the live URL and 18 unit tests pass.
- Real VTpass sandbox vend returned a token (79.9 kWh); requery matched.
- Simulator run (6 Nov, recorded, 2 of 50 credits): each log written once; budget alert raised; real purchase returned a token; on a timed-out purchase (mock provider) the agent said "still pending, don't buy again", then delivered the token on "check again"; the briefing recommended diesel over units after a top-up; the 07:00 schedule was created.

**Problems found in the run.**
- The agent cannot see its own earlier tool results, so it replays earlier writes. The server now ignores identical logs and purchases for 30 minutes, so the Sheet stays correct and nobody is charged twice. The agent still sometimes "corrects" itself in chat.
- VTpass took about 20s, and the simulator showed "The agent didn't answer" while the purchase succeeded. Sending "yes" again returned the same token with no new charge.
- Once the agent sent "on file" instead of the meter number. It was rejected with no charge, and the retry used the right meter.

**Known limits.** Sandbox only. The "paid but no token" path can only be shown with the mock provider, since VTpass's pending test meter fails verification. The simulator cannot show scheduled tasks. Stock on hand is an estimate; the agent asks for a fresh reading when one is over 2 days old. A deliberate second identical purchase within 30 minutes is refused.

**Watch.** Any `timeout` or `paid_no_token` row in the `tokens` tab without a later `ok`. Cloud Run logs for errors and slow VTpass calls. Wallet balance and Chord credits.

**Rollback.** Pause the teammate in Chord (reversible), untick "Enabled" on the `energy-tools` server, or route Cloud Run back to an earlier revision. Live now: skill v4, revision `energy-mcp-00010-4mz`.
