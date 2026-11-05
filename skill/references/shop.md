# Adaeze Provisions (all details fictional, test data only)

- Shop: Adaeze Provisions, 14 Ogunlana Drive, Surulere, Lagos. Open 7am to 10pm, seven days.
- Owner: Adaeze. She confirms purchases above NGN 20,000 and reads the morning briefing.
- Staff who message: Ade (morning shift), Tunde (evening shift). They buy diesel, check how much is left in the tank, and read the meter.

## Power setup

- Generator: 7.5kVA diesel, runs roughly 6 to 8 hours a day during outages, about 1.8 litres per hour.
- Diesel usually bought in 20 to 25 litre jerrycans from the filling station on Adelabu Street.
- Prepaid meter: Ikeja Electric, meter number 1111111111111 (VTpass sandbox test meter; use this for every purchase).
- Tariff: about NGN 225 per kWh (Band A). Units are kWh.
- Weekly diesel budget: NGN 150,000. Above that, Adaeze wants to know.

## Thresholds

- Warn when prepaid units are projected to run out within 3 days.
- Warn when diesel is projected to run out within 1 day.
- Warn when diesel spend is on track to exceed the weekly budget.

## Test meter numbers (for builders, not for staff)

The live tool server uses the VTpass sandbox, where 1111111111111 verifies and returns a token. Other numbers are rejected as invalid meters.

When the tool server runs the mock provider instead (one demo take), the outcome comes from the last two digits. The shop meter 1111111111111 ends in 11, so under the mock it gives the timeout path:

| Meter number  | Outcome        |
|---------------|----------------|
| 62101234567   | ok, token issued |
| 62101234500   | invalid_meter  |
| 62101234511   | timeout; first check_vend still pending, second gives the token |
| 62101234522   | paid_no_token; first check_vend still pending, second gives the token |
| 62101234533   | declined       |

Amounts under NGN 1,000 are declined by the provider minimum.
