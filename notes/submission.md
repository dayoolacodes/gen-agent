# TSG Labs take-home: Energy Manager for a Lagos provisions store

**Role I'm applying for:** Forward-deployed Engineering.

## The problem

Adaeze Provisions (fictional) is a small provisions store in Surulere, Lagos. Its power comes from a diesel generator and a prepaid electricity meter. Energy is its biggest hidden cost, and the shop only finds out it has run out when the lights go off. Nobody tracks diesel spend, how fast units are used, or when either will run out, and buying units can fail in confusing ways (rejected meter, timeout, money taken but no token).

## What I built

A Chord teammate, "Energy Manager", that staff and the owner simply message on WhatsApp:

- **Logs** diesel purchases, tank levels and meter readings from plain messages into a Google Sheet the owner can open.
- **Forecasts** spend and days of diesel and units left, counted from today, with alerts (running low, over budget, readings too old).
- **Briefs** the owner every morning at 07:00 Lagos time: spend, days left, one action.
- **Buys units** through the VTpass sandbox after a confirmed "yes", and handles failure honestly. It says "no money was taken" only when the wallet balance proves it; on a timeout it gives the reference, checks again and tells everyone not to buy twice.

Chord teammate (skill) → MCP server on Google Cloud Run (six tools, bearer auth) → Google Sheet and VTpass sandbox. Test keys and made-up data only.

## In this folder

| Item | What it is |
|---|---|
| Recording | The simulator conversation |
| `field-notes.md` | Problems as they happened, with exact errors. Start with the three under "Read these first" at the top. |
| `go-live.md` | Half-page go-live note: what is live, what was checked, problems found, limits, rollback |
| Code | https://github.com/dayoolacodes/gen-agent (public). Also as `gen-agent-code.zip` in this folder. |

**Try it yourself:** https://chat.tsglabs.dev/c/m9kR88uLaoTOuUUHQY_c55C5

## What you're watching in the recording

Chat on the left, the owner's Google Sheet on the right.

1. **Everyday use (VTpass sandbox).** Diesel purchase, tank level and meter reading, each logged once as a new row. The agent raises two alerts: units run out in about 2.8 days, and diesel spend is over the weekly budget (NGN 152,250 against 150,000).
2. **A real purchase.** It checks naira against units, then buys NGN 5,000 (79.9 kWh). VTpass took about 20s, so the simulator shows "The agent didn't answer" although the purchase succeeded. "yes" again gets "I didn't buy again, because your NGN 5,000 purchase has already gone through" and the token. One row in `tokens`, one charge.
3. **Morning briefing.** After the top-up it recommends buying diesel, not units, because diesel now runs out first.
4. **A purchase that goes wrong (simulated provider, switched off camera).** NGN 4,000, read back, "yes", then a timeout. The agent says it is still pending, money may have been taken, and not to buy again. "check again" delivers the token.
5. **The schedule.** "send me the morning briefing everyday at 7am" gets "Done", but the agent did not actually call the scheduling tool. I caught this afterwards from the tool trace and created the 07:00 reminder from Chord's Direct Line. See the field notes.

## The most useful finding

Chord's agent does not see its own earlier tool results on later turns, so it repeats earlier writes, including purchases, and can claim actions it did not take. I made the tool server safe against repeats (identical logs and purchases within 30 minutes are recognised, not repeated) rather than relying on the model, and checked every claim in the recording against tool traces and the Sheet. Details and evidence are in the field notes.
