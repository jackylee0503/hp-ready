# Test houses (HP-Ready)

12 realistic German houses to check the whole homeowner flow: form, radiator photo, exterior photo, free text and the verdict. The houses are made up (no real address, person or listing). Their numbers sit in realistic German ranges, from the Heizspiegel 2025 consumption bands and the BWP/IWU heat-load rules of thumb. The photos are real, openly licensed pictures.

| File | What |
| --- | --- |
| `cases.json` | per house: inputs, `expected_reads` (what each reader should return), `expected_house` (merged), `expected` (colour + must / must-not) |
| `texts/` | the owner's free text per house (German and English, one WhatsApp style, one prompt injection) |
| `photos.json` | radiator and exterior photos: repo photos (installer-labelled) + Wikimedia Commons links with licence and author, each looked at by eye |
| `run_cases.py` | feeds every `expected_house` to the engine, no API needed: `python assets/testcases/run_cases.py` |
| `fetch_photos.py` | downloads the Commons photos into `photos/` on your machine: `python assets/testcases/fetch_photos.py` |

## The 12 houses

| ID | House | Tests | Expected |
| --- | --- | --- | --- |
| TC-01 | 1974 terraced, partly renovated, type 22 | happy path, two-pipe photo, German text | green/yellow |
| TC-02 | 1962 Siedlungshaus, unrenovated, cast iron + single-pipe | clear red, oil in litres, photo vs text building type | red |
| TC-03 | 2014 new build, underfloor | clean green, outdoor-unit spot | green |
| TC-04 | 1905 Altbau flat, flat-level gas heating | site flag, apartment | yellow/red |
| TC-05 | 1988 semi-detached, small type 11 | radiators are the obstacle | red/yellow |
| TC-06 | 1979 bungalow "fully renovated" but 32,000 kWh | renovation vs bill contradiction | green/yellow + contradiction |
| TC-07 | Fachwerk ~1780, listed, mixed | pre-1800 year, listed-building flag | yellow/red |
| TC-08 | almost no data, radiators behind covers | "can't tell yet", retake tip | yellow |
| TC-09 | 1999 semi, wood stove all winter, towel rail photo | bill too low with its cause, towel rail ≠ radiator size | green/yellow |
| TC-10 | WhatsApp text, only €180/month advance | messy text, advance payment, unknown radiators ≠ red | yellow/green |
| TC-11 | 2001 flat on district heating | district heating edge case, no made-up price | yellow/green |
| TC-12 | prompt injection in the text | parser ignores instructions, AI never sets a colour | green/yellow |

## Found with these houses (2026-10-24, fixed on main)

- unknown radiator count + unknown size gave **red** (TC-10): now "can't tell yet"
- years before 1800 were silently dropped (TC-07): the limit is now 1000
- "180 € Abschlag im Monat" was read but never shown or used reliably (TC-10)
- "fully renovated" + very high bill did not question the renovation (TC-06)

Still open (not bugs, worth knowing for the pitch): a normal 2014 house with 10,500 kWh shows a −67 % bill-vs-area contradiction (TC-03), because the 2002-2015 row uses 50 W/m². District heating (TC-11) gets no "talk to your owners' association / contract" check.

## In the app by hand

Fill page 1 from `expected_house`, upload the photo from `photos.json` on page 2, paste the text from `texts/` on page 4, press "Read it", then compare the "We read" chips with `expected_reads` and the answer with `expected`.
