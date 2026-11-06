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
| Recording | The simulator conversation, in three parts (see below) |
| `field-notes.md` | Problems as they happened, with exact errors. The three marked `[submission]` are the strongest. |
| `go-live.md` | Half-page go-live note: what is live, what was checked, problems found, limits, rollback |
| Code | [REPO LINK OR ZIP] |

**Try it yourself:** https://chat.tsglabs.dev/c/AXtJLHL6jR6CMZrX2oTIyrBN

## What you're watching in the recording

1. **Everyday use (VTpass sandbox).** Diesel, tank level and meter reading are each logged once; the Sheet updates alongside. The summary raises a real alert: diesel spend NGN 152,250 against a NGN 150,000 weekly budget.
2. **A real purchase.** "buy 5000 units", read back, "yes". VTpass took about 20s and the simulator showed "The agent didn't answer", although the purchase had succeeded. Sending "yes" again returns the same token with no second charge (one row in `tokens`). This is the replay protection described in the field notes.
3. **Morning briefing.** After the top-up it recommends buying diesel, not units, because diesel now runs out first.
4. **A purchase that goes wrong (simulated provider).** "buy 4000 units" times out. The agent gives the reference, says it is still pending, money may have been taken, and not to buy again. "check again" delivers the token. The simulated tariff differs from the sandbox, which the agent notices.

The daily 07:00 schedule was created afterwards, outside the recording. It shows as a reminder on the teammate in Chord, since the simulator cannot show scheduled tasks.

## The most useful finding

Chord's agent does not see its own earlier tool results on later turns, so it repeats earlier writes, including purchases. I made the tool server safe against this (identical logs and purchases within 30 minutes are recognised, not repeated) rather than relying on the model. Details and evidence are in the field notes.
