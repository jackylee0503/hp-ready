# HP-Ready Triage: Design Document

WATT THE HACK Munich, 2026-10-24. Challenge #4 by nuuEnergy: *"Can AI tell whether a home is ready for clean heating?"*
Status: pre-event design, reviewed (engineering review, CEO review, two spec reviews, one outside review), then aligned to the organiser's own pages on 2026-10-23 evening (`docs/challenge/`, they win on conflict). Build spec for the coding agent: `CLAUDE.md`.

## 1. Problem

**Organiser's mission** (`docs/challenge/02_mission.md`): most homeowners never get past "Would a heat pump even work in my home?"; many wrongly assume they need underfloor heating or a full renovation, and today only a technician's visit answers it. Build a tool that gives a **homeowner** an honest first answer in under three minutes from what they already have (bill, a few building facts, smartphone photos). It must tell them (1) ready or not: green / yellow / red with a reason they understand, and (2) what's still open: what the tool can't tell and what a technician has to check on site.

**Our business angle on top:** nuuEnergy is a Munich heat-pump installer with its own craftspeople (hubs in Munich, Hamburg, Cologne). Every lead today needs a site visit; installer time is the bottleneck, and many visits end with "not like this" or "come back with different parts".

**Goal:** from what the homeowner already knows, answer:
1. Is the house heat-pump ready (green / yellow / red, organiser meanings), and why, in one sentence?
2. What's still open, and is it an obstacle or only "can't tell yet"? What in the data contradicts itself?
3. If someone goes, what should they bring and check?

**Non-goals:** replacing the installer's room-by-room heat-load calculation (DIN EN 12831), quoting prices or subsidies, deciding with an LLM.

## 2. Users

| User | Needs | Screen |
| --- | --- | --- |
| Homeowner (the organiser's core user) | "Does it work for my house, and why? What's still open?" in under 3 minutes | 🏠 Homeowner answer card |
| nuuEnergy sales / dispatch | Which leads to visit first, which can get a remote quote | 📊 Evaluation (lead score, visit type) |
| Installer | What to bring, what to check on site | 🔧 Installer prep sheet |
| Judges | Our results for the 2 evaluation buildings (inputs public, references hidden), honest uncertainty | 📊 Evaluation + 🏠 card |

## 3. Approach

**The LLM reads, physics decides.**

```
 CSV/JSON row ──► loader ──► House ──────────────► engine ──► Result ──► app (3 tabs)
   │                ▲  (regex: counts, U-values)     │
   │ free-text      │                                 ├─ heating load = k × W/m²(age, renovation) × area
   └─ notes ──► LLM NotesObs (facts + quotes)         ├─ contradiction checks (2b)
                (cached, keyword fallback)            ├─ radiator output → required flow temperature
                                                      ├─ Monte Carlo (N=500, seed 0) → probabilities, p10-p90
                                                      ├─ JAZ band → cost
                                                      └─ installer brief → visit type, parts, checklist
 P1: bill / radiator photo ──► extract (per-mission schema) ──► merge into House
```

Why this split: the judges score against real reference values, and the organiser warns that cases contradict themselves. A model that "decides" cannot explain itself or show calibrated uncertainty; a physics chain can show every step (the Rechenweg) and every assumption.

## 4. Data findings

### Dev set (3 buildings, references given)

| ID | Built | Area | Consumption | Notes | Reference load | Verdict |
| --- | --- | --- | --- | --- | --- | --- |
| B-01 | 2001 | 195 m² | 10,000 kWh LPG | 14 radiators, preset valves; good U-values, "no renovation documented" | 9.6 kW | green |
| B-02 | 2005 | 180 m² | 15,500 kWh gas | underfloor + 1 radiator, wood stove all winter, solar thermal DHW | 9.7 kW | green |
| B-03 | 1970 | 200 m² | 40,000 kWh oil | 15 radiators, 12 valves to replace, cavity + roof insulation, top floor not lived in | 14.5 kW | yellow |

What we learned:
- **Consumption-based load fails.** With the organiser's bill method (η 0.88, 1,000 kWh hot water per person) matching the references needs about 500 / 1,250 / 2,290 full-load hours: a 4-5× spread caused by the wood stove, habits and LPG (the organiser calls 1,800-2,100 h realistic). One parameter cannot fit it, so it stays a cross-check that is always shown.
- **Reference loads move with age and area** (49 / 54 / 72 W/m²), so the primary method is `k × W/m²(age, renovation) × area` using German trade rules of thumb (BDH/VdZ, Viessmann).
- **Planted contradictions are visible:** B-01 bill vs area load (2.4 vs 10.8 kW, −78 %) and "no renovation" vs better-than-code U-values; B-02 wood stove; B-03 unused top floor.
- **Two of three houses sit on the 55 / 60 °C edges.** Calibration choices flip colours, so we report probabilities and never add parameters to hit 3/3.

Calibration result (one parameter): **k = 1.01**, leave-one-out error +20 % / −9 % / −8 %. Colours: B-01 54.0 °C green, B-02 underfloor green, B-03 58.2 °C yellow (3/3). Monte Carlo p50: B-01 54.6 °C, B-03 58.8 °C. Rechecked after the organiser alignment (2026-10-23): unchanged, because the bill method is only a cross-check and the three dev houses keep their W/m² values.

### Evaluation set (B-04, B-05: inputs public, references hidden)

| ID | Built | Area | Consumption | Notes | First estimate from the spec (scratch calculation) |
| --- | --- | --- | --- | --- | --- |
| B-04 | 1987 | 160 m² | 25,000 kWh oil (2,500 L, consistent) | semi-detached, 12 radiators with valve blocks, **single-pipe**, no renovation info | area-age 13.7 kW (86 W/m²), bill 9.5 kW (−31 %, no flag); flow ~72 °C (Monte Carlo p50 ~72 °C, red 0.90) → red as an obstacle; even all-large radiators give ~62 °C |
| B-05 | 2006 | 125 m² | 27,000 kWh gas | **mixed**: underfloor + 8 radiators; 14 rooms; no extra insulation; double low-e; solar thermal | area-age 6.3 kW (50 W/m²), bill 11.1 kW (+76 %) → contradiction; radiator circuit ~44 °C (p50 ~44 °C, green 0.73); if the bill is right and the area is understated, ~55 °C, on the green/yellow edge |

What we learned:
- **B-04's trap is the single-pipe system.** The organiser's rule caps it at yellow anyway; physics with the documented 12 radiators already says above 60 °C unless they are large. The answer is "obstacle" with a path to yellow (more radiator output at the end of the loop or lower heat loss), not "can't tell yet".
- **B-05's trap is the area.** 14 rooms in 125 m² (~9 m² per room) and a bill that implies ~220 m² of heated area point the same way: the documented area probably misses heated rooms. We keep the documented area for the verdict, widen the range and ask "is all heated area included?".
- **B-05 is the only `mixed` case:** the radiator circuit decides (radiator share 8 radiators / 14 rooms).
- These are first estimates from the spec, not engine output. The real engine recomputes them on the day.

## 5. Key models and assumptions

- **Heating load:** table of W/m² by age band (≤1978 130/80/50, 1979-94 85/70/50, 1995-2001 80/55/50, 2002-15 50, ≥2016 35 for unrenovated/partially/fully renovated), ±20 %. Every unrenovated and fully-renovated value sits inside the organiser's guardrail band; "partially" sits between. The partially-renovated column is used when notes name insulation work or the wall U-value is below 0.7 × the age reference. The bill-based load is always shown beside it (η 0.88, 1,000 kWh hot water per person, 1,800-2,100 full-load hours).
- **Radiators:** EN 442 output law `Φ = Φ_n (ΔT/50)^1.3`; ratings from manufacturer tables (Type 22 600×1000 ≈ 1.67 kW, Type 33 600×1200 ≈ 2.68 kW). Sizes small/medium/large = 0.7 / 1.5 / 2.2 kW; unknown size drawn 0.25/0.5/0.25.
- **Required flow temperature:** supply temperature that holds 20 °C at the design outdoor temperature with the existing radiators. Bands 55/60 °C come from the challenge JAZ table.
- **Fixed challenge assumptions:** electricity 0.26 €/kWh, gas 0.11 €/kWh, oil 1.70 €/L, JAZ 4.0 / 3.5 / 2.8.
- **Efficiency basis:** η 0.88 by default (organiser), so costs stay comparable with other teams. Only a known boiler type refines it: gas bills are upper heating value (Hs), η 0.88 / 0.80; oil at 10 kWh/L is lower value (Hi), η 0.95 / 0.85.
- **Pipe system:** confirmed single-pipe adds 5-10 K and caps green at yellow (organiser rule); unknown in a 1960-1979 house widens the range upward; never inferred from a valve block alone.
- **Mixed heating:** the radiator circuit decides; its share of the load is radiators / rooms.
- **Verdict:** organiser meanings. Green = likely suitable; yellow = checks remain (55-60 °C, site flags, single-pipe) or can't tell yet (missing core data, never red); red = an obstacle (>60 °C with the data we have). Colour of the Monte Carlo p50, then the caps; if no colour reaches 60 % probability, show the top two colours.

## 6. Scope and priorities

| Priority | Content |
| --- | --- |
| P0-a | Loader + LLM notes (cached) + engine + Monte Carlo + calibration + Evaluation tab |
| P0-b | Homeowner wizard (typed description + exterior photo → radiator photo → bill or listing → confirm; the LLM reads, the user confirms) + answer card: colour, reason, what's still open, next step. Both official bonuses live here |
| P0-c | Pre-filled quote request + installer visit prep sheet |
| P1 | Entropy-based next question, more than one retake, boiler nameplate photo |
| P2 | CSV batch upload, energy-certificate photo, degree-day method, polish |

## 7. Risks

| Risk | Mitigation |
| --- | --- |
| New houses (homeowner input, other leads) word notes differently | LLM notes extraction is the main path, keywords only as fallback (with negation handling); the 5 known notes are cached |
| Reference load computed differently than we assume | Ask the mentor first; k is refit in minutes |
| Houses on colour edges | Probabilities and "uncertain: 🟢/🟡" instead of false certainty |
| B-04 hidden verdict is yellow while we say red | Show the probabilities, that even large radiators need ~62 °C, and the path to yellow; never soften physics to guess the reference |
| API down / no key | Notes cache committed early; keyword fallback; P0 runs offline |
| Wi-Fi fails during the pitch | Local run is the primary path anyway; screen recording as backup |
| Pre-written code not allowed | Treat this repo as research notes, rebuild P0-a/b on the day, cut P0-c and P1 |
| Organiser pages disagree (3 vs 2 evaluation buildings) | Ask on the day; plan for the 2 in the data |
| Cloud link (if used) asks judges to log in | Test the URL in an incognito window, set Sharing to public |

## 8. Decision log

| When | Decision | Why |
| --- | --- | --- |
| Before | kNN on a synthetic visit DB → physics engine | Judged against real references; synthetic data is indefensible |
| Eng review | Radiator rating table, Hs-based η, site flags never force red, drop the "25 % shortfall" rule, calibrate one parameter, clip display at 70 °C | Verdict hinged on undefined constants; overfitting with 3 points |
| Eng review | Bills: LLM extracts raw numbers only, engine converts; per-mission schemas; source-priority merge; cache extraction; resize photos | LLM must not calculate; Streamlit reruns; phone photo limits |
| Eng review | One Claude session; commit named files only; `/review` → `/hp-review`; deadline-first timeline; deploy the night before | Avoid two agents corrupting each other; first-time participant |
| Dev data | Primary load = area × age × k (was consumption ÷ 2000 h); contradiction checks; CSV mapping; fuels lpg/district/electric | Consumption needed 625-2,400 h; organiser says cases are contradictory |
| CEO D2/D3 | Add installer visit prep; add batch lead triage | nuuEnergy runs its own installers; scalability on screen |
| CEO D4/D5 | Photo retake loop → P2; photo extraction → P1 | Evaluation data has no photos; P0 overloaded |
| CEO D7 | Unused area → heated area × 0.85 | Documented fact in B-03 notes |
| CEO D8 | Wall U-value below 0.7 × age reference → renovated column (k 1.01, dev 3/3) | B-01's U-values beat 2001 code; planted contradiction |
| CEO D9 | LLM notes extraction is P0 core (cached) | Hidden cases may use other words; AI must be visible |
| CEO D10 | Simple Monte Carlo in P0; verdict = p50 colour; <0.6 max probability → uncertain | Uncertainty is 20 points; mode is biased by the radiator-size tail |
| CEO D11 | Batch CSV upload → P2; Evaluation table gets lead score and visit type | Only 5 real rows exist |
| 2026-10-23 21:20 | Aligned to the organiser's Notion pages (now `docs/challenge/`): homeowner answer card with "what's still open" → P0-b, installer → P0-c, demo opens with the homeowner; colours = organiser meanings (missing data yellow "can't tell yet", red only for an obstacle); η 0.88 and 1,000 kWh hot water per person; both load methods shown with their range; W/m² table split partially/fully, all inside the organiser bands (dev calibration unchanged); confirmed single-pipe caps green at yellow; mixed heating defined; rooms-vs-area contradiction; cost above 60 °C at JAZ 2.8 as a lower bound; local browser run primary; evaluation inputs added to `data/` | The organiser pages define the user, the colours and the guardrail numbers; the evaluation inputs turned out to be public |
| 2026-10-23 22:37 | Homeowner flow: 4 required tap questions (year band, area, heating surfaces, insulation), the rest optional; next-step box by verdict (quote / on-site check / one more question / path to yellow); pre-filled quote request (homeowner adds name, contact, postcode; mailto draft + JSON download, nothing sent or stored) in P0-c next to the installer sheet | As homeowners, Junwoo and Mohammed found getting a quote online means long forms; our result already holds what those forms ask, so the homeowner's next step costs one tap |
| 2026-10-23 23:10 | Homeowner input becomes a 4-step wizard: typed description (+ optional exterior photo) → radiator photo → bill or sale listing → "is this right?"; the LLM reads each step (one mission each), the engine merges by a source rule and asks only gaps that change the colour (≤2). Typing only, no voice. Bill reading and the outdoor-unit photo (both official bonuses) move into P0-b. Renovation "don't know" that flips the colour → yellow "can't tell yet" plus that question. Fictional demo inputs with expected values in `assets/demo/` | A form calculator already exists for free (UBA/ifeu "Gebäudecheck Wärmepumpe", Dec 2025, room by room); our edge is no typing of numbers, no guessing and a hand-over. Scratch run on the persona: house facts and radiator size move the verdict most (88 → 70 → 59 °C), the bill not at all. Sale listings carry certificate data, which adds buyers as a second user |
| 2026-10-23 23:40 | Quote request and installer prep sheet become one A4 "Pre-visit sheet" PDF: the installer recommendation on top, then Confirmed (with source), Estimated (with range and method), Check on site, Bring, the radiator photo. The 🔧 Installer tab shows the same page | Mohammed's idea: the installer reads one page and knows in a minute whether the trip is worth it (no wasted visits), the homeowner can send it to any installer, and it is a tangible thing to show in the demo |
| 2026-10-24 morning | Roles: Junwoo owns schema, loader, notes cache, extract, app; friend `potatohater8` owns engine + calibrate (steps 0-9) behind `evaluate(House) -> Result`; step 10 agreed later | Friend knows the domain; one owner per file avoids merge conflicts |
| 2026-10-24 morning | Schema field names frozen (renames forbidden, additions via Junwoo to main); fuel precedence: bill raw values → annual_fuel_kwh → annual_fuel_liters × 10 → advance payment, `annual_*` only per-year stated values; `jaz_bucket` is a fixed enum | A bill's printed kWh covers its own period, so only the engine may scale it; one owner of the meaning avoids double conversion |
| 2026-10-24 morning | `claude-sonnet-5-5` rejects forced `tool_choice`: `llm_tool` uses `auto` + "call exactly one tool", effort low, max_tokens ≥ 8000; "No renovation documented" means unknown (None), not "no insulation" | Live 400 on the first cache build; principle 2 |
| 2026-10-24 late morning | Tracer engine (`engine.py` built straight from the spec) merged to `main` before the engine owner's version | The app ran end to end with no physics; B-04/B-05 results secured early; the owner reshapes a running engine instead of an empty one. Dev 3/3, k 1.0094, LOO +19.8/−9.4/−7.9; B-04 red, B-05 green |
| 2026-10-24 late morning | Evaluation and Installer tabs redesigned to the canvas "HP-Ready Evaluation & Installer" (spec in Korean from the team): KPI cards, 8-column table, detail cards; ranked leads, KPI strip, What it takes / Bring / Flags / standard checks; contact form only in the Homeowner flow; Material icon font fix | Judges and installers are different readers from the homeowner; `st.metric` truncated values; icon ligatures leaked as text |
| 2026-10-24 late morning | "Flags" = site flags + installer checklist minus the 4 always-checks, same count in both tabs | The table counted contradictions only (B-04 showed 0 despite single-pipe) |
| 2026-10-24 noon | `Result` gains structured `options`, `radiators`, `flags`, `always_checks` (engine fills numbers/kinds, the app writes sentences); `check_result(h, r)` contract checker; the app prefers structured fields and falls back to parsing | The UI regex-parsed engine sentences, so any wording change silently blanked numbers; engine wording bug ("12 kW at 55 °C" is a 75 °C rating) |
| 2026-10-24 noon | Safety nets for engine swaps: frozen `engine_tracer.py` used per building when `engine.py` fails (marked "tracer"); `data/baseline_results.json` + `python loader.py --save-baseline / --compare-baseline`, differences shown in Evaluation; cache key includes the engine file's mtime | The engine owner may rewrite the engine; the demo must not break and changes must be visible |
| 2026-10-24 noon | ML only as a component, not as the whole engine: seam `engine.w_per_m2_for` with `set_w_model` / `HP_W_MODEL`, `features(h)` contract (None stays None), table fallback on any model failure, `example_table_model` proves the plumbing (no differences) | 3 labelled buildings cannot train a model; generated buildings are forbidden; a learned W/m² from public German typology data (IWU/TABULA, certificate statistics) or Phase-2 visit outcomes fits the physics chain and keeps the Rechenweg |
| 2026-10-24 early afternoon | Team direction: an ML team owns the logic (aiming at a paper); Junwoo owns UI + architecture that survives logic changes. Three Python modules (`modules/bill_recognizer.py`, `image_validation.py`, `calculation.py`) behind `orchestrator.py` (in-process registry, `HP_MODULE_<NAME>` override, never raises, fallbacks to `extract.py` / `engine.py` / `engine_tracer.py`); JSON contract draft v1 in `CONTRACT.md` + `contracts/` exported from `schema.py`; page 1 of the Homeowner wizard is a form (LLM reading being phased out). An earlier "JS modules" plan was a miscommunication: Python only | The logic will change; the UI and the demo must not. One contract, fallbacks per module, teammates plug in without editing our files |
| 2026-10-24 afternoon | CLAUDE.md principles rewritten: "Core principles" (physics engine decides) → 8 **Invariants** that hold for any logic (LLM is a parser and optional; unknown = null; one contract, UI never computes; every verdict explains itself; no made-up data, train only on real data; red is earned; ask only what matters; measured, not claimed) + **Current implementation** (physics = replaceable baseline for comparison) + Team and ownership (ML team owns logic, Junwoo UI/architecture). Supersedes "ML only as a component" above. Wizard reordered after a UI review: 1/4 dropdowns, 2/4 radiator, 3/4 bill, 4/4 optional free text (LLM only on demand) | The ML team will replace the logic for a paper; principles tied to physics would make every agent argue against it. Reviewers dislike unprompted LLM calls and free typing |

## 9. Domain primer

- **Heat pump:** moves heat from outside air; 1 kWh electricity → 3-4 kWh heat. The yearly average ratio is the **JAZ**.
- **Why flow temperature (Vorlauftemperatur) is everything:** a heat pump is more efficient the cooler the water it has to make. "Does it work?" = "does lukewarm water keep the house warm?"
- **55 / 60 °C:** band edges of the challenge JAZ table (≤55 → 3.5, 55-60 → 2.8, above 60 not covered).
- **Heating load (Heizlast):** heat the house loses on the coldest design day, in kW. We estimate it from area and age, and cross-check with the bill.
- **Radiator output:** radiators give less heat with cooler water; at 55/45 °C about half of the 75 °C rating. Old houses often have oversized radiators, so more pass than people expect.
- **Single vs two-pipe (Ein-/Zweirohr):** in single-pipe systems later radiators get cooler water, so the flow temperature must be higher and balancing is harder. Common in 1960s-70s buildings, especially apartment blocks. Not a deal-breaker, but rarely a clean green without an on-site check. The system belongs to the building, not one radiator, and a valve block alone can't tell you which it is.
- **Traffic light (organiser):** 🟢 likely suitable on the available information; 🟡 potentially suitable, but important checks remain or there is too little data; 🔴 not enough evidence for a positive assessment. Missing data is never by itself a reason for red.
- **Full-load hours (Volllaststunden):** hours the heating would run at full power to deliver a year's heat; ~2,000 h in Germany (1,800-2,100). Annual heat ÷ full-load hours ≈ heating load.
- **Myths:** underfloor heating is not required; a full renovation is not required.
- **Monte Carlo:** instead of guessing one value for an unknown, draw 500 plausible values and run the engine 500 times; the spread gives ranges and colour probabilities.
- **Calibration:** 3 dev buildings train, 2 evaluation buildings (inputs public, references hidden) test. Fitting many numbers to 3 points overfits.
- **Typical installer visit:** check heating and consumption → room-by-room load vs radiator output → pipes and hydraulic balancing → outdoor-unit spot and noise distance → space for tanks → electrical supply → quote, subsidy, install, commissioning. We prefill the first three at whole-house level; the rest goes on the installer checklist.
