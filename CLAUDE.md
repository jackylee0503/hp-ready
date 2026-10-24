# HP-Ready Triage (WATT THE HACK Munich, nuuEnergy challenge #4)

Build spec for the coding agent. The organiser's own pages (mission, technical guardrails, data, single/two-pipe background, deliverables, judging) are in `docs/challenge/`; they win over everything else and this file implements them. Background, rationale and the decision history live in `docs/DESIGN.md`; the pitch lives in `docs/PITCH.md`; the original Korean plan is `docs/CLAUDE.ko.md` (outdated, reference only, this file wins on conflict).

**Talk to the user (Junwoo) in Korean.** He is a first-time hackathon participant with no domain or statistics background. Explain in plain words, do the interpretation yourself, never hand it back to him.

## One line

Give a **homeowner** an honest first answer in under three minutes, from what they already have (energy bill, a few building facts, photos): is the home heat-pump ready (green / yellow / red) with a reason they understand, and **what is still open** that a technician has to check on site. The same result tells nuuEnergy how sure we are, what contradicts itself in the data and what the installer should bring.
The LLM only **reads**, and only when the homeowner asks for it. The **decision logic** (today a physics baseline, later the team's models) sits behind one contract and can be replaced without touching the UI. Unknowns become ranges and probabilities, never invented numbers.

## Team and ownership (2026-10-24)

- **Logic: the ML team** (aiming at a paper). They own three ML modules and any model code they plug in through `orchestrator.py` (`HP_MODULE_<NAME>`); they may replace the physics entirely. The split (user-confirmed, 2026-10-24 afternoon):
  ```
  Table (House) is filled by:
    1/4 dropdowns + typed integers (homeowner)
    2/4 radiator photo → ML module 1 "pipe_classifier": single-pipe vs two-pipe
    3/4 bill (photo/PDF) → module 2 "bill_recognizer": **LLM parser (Claude vision)** → raw bill numbers (decision 2026-10-24: the OCR attempt was not usable)
    4/4 optional free text → LLM parser, ONLY on "Read it", fills ONLY fields still empty after 1-3
  Then ML module 3 "calculation": finds internal contradictions + produces the Result → result screens
  ```
  Files: `modules/pipe_classifier.py`, `modules/bill_recognizer.py`, `modules/calculation.py`. Input conflicts (same field from two sources, form vs bill/photo) are asked by the UI before the calculation and arrive resolved in `House.conflicts`; internal contradictions are module 3's `Result.contradictions` (`CONTRACT.md` "Pipeline").
- **UI and architecture: Junwoo** (with Claude). `app.py`, `orchestrator.py`, `schema.py`, `CONTRACT.md`/`contracts/`, `loader.py`, `extract.py`. Goal: **any logic that honours the contract plugs in and the app, the demo and the evaluation keep working.**
- When helping the ML team, help them build the model they want; enforce the invariants below, not the physics baseline.

## Invariants (hold for any logic, never break)

1. **The LLM is a parser, and optional.** It only fills schema fields from text or images it is given (no verdicts, recommendations or arithmetic), it runs only when the homeowner explicitly asks (pressing "Read it" on free text, or uploading a bill to be read) (e.g. the optional free-text step), and every answer is reachable without it (dropdowns, bill and photo modules, fallbacks).
2. **Unknown stays empty.** Unsure or missing = `null`, never `0` or a guess; every value carries a source and a confidence (0-1). Models must accept `null` inputs.
3. **One contract.** `schema.py` (exported to `contracts/`, described in `CONTRACT.md`) defines every input and output once. Logic lives behind `orchestrator.py` modules; the UI never computes a verdict or a number, it only renders `Result` fields. Contract changes go through Junwoo and are versioned.
4. **Every verdict explains itself and its uncertainty.** A colour always comes with probabilities or a range, a one-sentence reason, what is still open, and a trace (calculation steps, or for a learned model its inputs and their contributions) that a judge can follow.
5. **No made-up data presented as real.** Train and calibrate only on real data (organiser buildings, public datasets, real visit outcomes); never generated buildings or visits shown as real, never the 2 evaluation buildings' hidden references. Prices and JAZ come only from the fixed assumptions below; never installation cost or subsidy amounts ("installer quote needed").
6. **Red is earned.** Red means an obstacle in the data we have (organiser: "insufficient evidence for a positive assessment"), never just missing data; missing data is yellow "can't tell yet". Every red carries a reason and a "this gets you to yellow" path.
7. **Ask only what matters.** At most two follow-up questions: the unknowns or conflicts that move the verdict most.
8. **Measured, not claimed.** Any logic is reported the same way: dev verdicts vs reference, heat-load error with leave-one-out, and the difference to the saved baseline (`python loader.py --compare-baseline`). A change that is not measured is not presented.

## Current implementation (replaceable)

- The decision logic today is the **physics baseline** `engine.py` (area × age heating load × one calibrated `k`, EN 442 radiator law, Monte Carlo), with `engine_tracer.py` as the frozen fallback. It stays as the **baseline the team's models are compared against** (paper ablation), not as the required method. Sections "Engine", "Fixed assumptions" and "Data mapping" below describe this baseline.
- Inputs today: page-1 dropdowns, radiator photo, bill, optional free text. Photo and bill go to the team's modules (`pipe_classifier`, `bill_recognizer`) when they are implemented, else to `extract.py` in **cache-only** mode (the committed demo reads; a fallback never calls the LLM by itself, `HP_LLM_FALLBACK=1` re-enables a live call).

## Situation

- One-day hackathon, 2026-10-24 09:00-19:00, TUM campus. Deliverables (`docs/challenge/06_deliverables_bonus.md`): a working prototype that runs in a standard browser (organiser: "runs locally"), our results for the 2 evaluation buildings shown in the pitch, a live demo (not slides).
- Data: 5 real, anonymised nuuEnergy buildings, all in `data/` (CSV + JSON). 3 dev cases (`buildings_dev`: B-01..B-03) carry `reference_heating_load_kw` and `expected_verdict` (green/yellow/red only). 2 evaluation cases (`buildings_eval`: B-04, B-05) have **public inputs**; only their reference values are hidden and the jury compares against those. **No photos** in the data. Fields are what a homeowner realistically knows; empty = not documented.
- Organiser: **"Some cases are deliberately contradictory."** Finding contradictions scores points (engine step 2b).
- Organiser: **"Missing data does not automatically mean a building is unsuitable."** The tool must separate "there is an obstacle" from "we can't tell yet from this data" (engine step 6).
- Code quality and tests do not matter. The demo must not break.

## Judging and where we score

| Criterion | Pts | What the jury asks (`docs/challenge/07_evaluation_criteria.md`) | Our answer |
| --- | --- | --- | --- |
| Technical execution & reliability | 25 | Does it work? Calculations plausible? Handles different building cases? | Runs locally in the browser, works without API (notes cache + keyword fallback), deterministic; handles radiators / underfloor / mixed, single-pipe, LPG, district, electric; every W/m² value sits inside the organiser's guardrail bands |
| Problem-solution fit & user value | 25 | Solves the homeowner's actual problem? Understandable, useful, actionable? | Homeowner answer card in under 3 minutes: colour + one-sentence reason + "what's still open / what a technician checks" + what would move it to green; installer prep sheet for nuuEnergy |
| Explainability & uncertainty | 20 | Assumptions transparent? Identifies missing information, avoids misleading conclusions? | "Obstacle" vs "can't tell yet", colour probabilities, p10-p90 ranges, both heating-load methods side by side, contradictions with "which source we trusted and why", Rechenweg |
| Innovation & smart use of tech | 15 | Creative? AI used meaningfully, not as a gimmick? | LLM reads messy notes (with quotes), bills and photos; physics decides |
| Feasibility & scalability | 15 | Could become a real product? Works across many homes without manual effort? | ~1 API call per building (cached), same function scores any lead CSV, assumptions swap out, Phase 2 calibrates on real visits |

Organiser motto: *"I can't tell from this data, a technician must check X and Y" beats a confident wrong number.*
Scoring enum is green/yellow/red only, so always output `best_color`; uncertainty and contradictions are flags next to it.
Show the four key terms with tooltips, using the organiser's wording (`docs/challenge/01_one_pager.md`): Heizlast, Vorlauftemperatur, JAZ, Ein-/Zweirohr.

## Priorities (build strictly in this order)

- **P0-a Scoring path**: `loader.py` → `engine.py` → `calibrate.py` → 📊 Evaluation tab.
  - Text fields (`building_notes`, `radiator_info`, `energy_carrier_detail`): numbers (radiator count, valves, litres, U-values) by regex. Facts (extra heat source, solar thermal, unused area, insulation work, renovation hints) by **LLM `NotesObs` as the main path**, with a quote per fact, cached in `data/notes_cache.json` (5 buildings = 5 calls). Keyword fallback only if cache and API are both missing (show "rule-based analysis"). The fallback must respect negation: "No additional insulation" (B-05), "without low-e coating" (B-03), "No renovation documented" (B-01), "kein/keine" are not facts of insulation or renovation.
  - **Monte Carlo is P0**: N=500, seed 0, vectorised numpy (see engine step 7).
  - Evaluation tab: 3 dev buildings vs reference (error %), leave-one-out, the 2 evaluation buildings (B-04, B-05) with ranges, plus `lead_score` and visit-type columns.
  - Every result has a **Rechenweg** expander: area × W/m² × k → heating load (consumption-based load shown beside it) → ΣΦ_n → required flow temperature → JAZ → cost, each step with its number and assumption, plus contradictions and which source we trusted.
  - Cut order inside P0-a if late (from the end): Rechenweg detail → leave-one-out table → secondary contradiction rules. Never cut LLM notes or Monte Carlo.
- **P0-b 🏠 Homeowner wizard + answer card**: the organiser's core user, who is lazy and should not fill a form: a 4-step wizard where the LLM reads a typed description, photos and the bill ("Homeowner inputs" below). Build order inside P0-b: text step → bill → radiator photo → exterior photo → listing; if late, cut from the end, never the text step or the bill. Inputs → traffic light with probabilities, one-sentence reason ("obstacle" or "can't tell yet" spelled out), **"What's still open"** list (`open_checks`, step 6c), cost, flow-temperature scale (p10-p90 band), one "this would make it more accurate" hint, and the **next-step box** (`next_step`, step 10). The same card is shown for each of the 5 loaded buildings. Time it: inputs to answer in under 3 minutes.
- **P0-c 📄 Pre-visit PDF (quote request and installer prep sheet in one page)**: built only from engine output (steps 9 and 10). The homeowner adds only name, e-mail or phone and postcode and gets a one-page PDF to send to any installer; the 🔧 Installer tab shows the same page. Building selector = the 5 loaded buildings + the current Homeowner house. If time runs out, cut P0-c before P0-b; inside P0-c keep the PDF, cut installer-tab polish first.
- **P1**: entropy-based next question, retake loop beyond one retake, boiler nameplate photo (kW, year, condensing).
- **P2**: CSV upload batch triage (rules only, 0 LLM calls), Installer polish, degree-day method, log-mean numeric solve, energy-certificate photo.
- Both official bonuses now sit in P0-b: bill reading (step 3) and the outdoor-unit spot from the exterior photo (step 1).
- **Cut**: per-postcode design temperature lookup, fine-grained radiator lookup (3 sizes only).

## Timeline (10 h, adjust to the real deadline)

First thing on the day: get the submission deadline and pitch slot. Build time = deadline − opening/team formation − 1.5 h (freeze + pitch prep). If shorter than 10 h, cut P1, then from the end of P0-b's build order.

| Time | Work |
| --- | --- |
| 0:00-0:30 | Data is already in `data/`: check the organiser files did not change on the day, build or refresh `notes_cache.json` |
| 0:30-3:00 | P0-a, **secure the B-04 / B-05 results here** |
| 3:00-6:15 | P0-b wizard + answer card: answer card first (from the engine), then the steps in build order (text → bill → radiator → exterior → listing) with the demo cache |
| 6:15-7:15 | P0-c quote request (+ a minimal installer sheet) |
| 7:15-7:30 | Buffer; P1 only if everything above works |
| 7:30-8:30 | Local run check (+ Cloud link if used), freeze caches, rehearse the happy path 3× and time the homeowner flow (< 3 min) |
| 8:30 | **Code freeze** |
| 8:30-10:00 | Pitch prep and rehearsal |

## Pre-event milestones (agent: check these first every session and tell the user the first open one)

- [x] M0 repo, venv, deps (`C:\dev\hp-ready`, private GitHub, pinned pandas<3, pyarrow<22, pillow<12 because Windows Smart App Control blocks newer wheels)
- [x] M1 eng review applied, radiator rating table sourced (Kermi/Buderus EN 442)
- [x] M1b dev data applied (area-age load, k=1.01, contradiction rules, U-value renovation hint, P0 Monte Carlo → dev 3/3)
- [x] M1c organiser pages and all 5 buildings in the repo (`docs/challenge/`, `data/`), spec aligned to them (2026-10-23 evening, see `docs/DESIGN.md` decision log).
- [x] M2 (done 2026-10-23 22:30, user confirmed the key works) **API check (required before the event, LLM notes are P0)**: user pastes `ANTHROPIC_API_KEY = "..."` into `.streamlit/secrets.toml` (and Cloud Secrets if Cloud is used); one real call with `claude-sonnet-5-5` succeeds. If it fails, read the error and check the model ID first. After M2, `data/notes_cache.json` for all 5 buildings can be built tonight (their notes are public, 5 calls); if pre-written work turns out not to be allowed (M5), rebuild it on the day.
- [x] M3 Cloud first deploy ("HP-Ready (setup)" shows). Now optional (organiser: runs locally in a browser): if used, Secrets with M2, record the URL here: `https://hp-nuuai.streamlit.app` (redeployed 2026-10-24, public, checked logged-out; old mhdjackymcn retired), open it in an incognito window; a private-repo app may require login, then switch Sharing to public.
- [ ] M4 demo inputs: done in `assets/demo/` (fictional, labelled: house texts, gas bill as PDF and photo, a sale listing, expected values in its README) plus the 5 labelled radiator photos in `data/pipe_photos/`. Still to take: one exterior photo of a house (no people or number plates); optional: the real SWM sample bill (link in "Extraction missions"). Own photos go in `samples/` (raw files are gitignored).
- [ ] M5 first 30 minutes on the day: deadline and pitch slot, data terms, **whether pre-written code is allowed** (via `/intake`). If not allowed: keep `app.py` as the empty shell, treat k=1.01, tables and rules as research notes, write code on the day, and cut P0-c and P1 first.

## Stack

- Teammate modules are plain Python behind `orchestrator.py` (no Node, no new dependencies); the app runs on the fallbacks when they are missing or failing.
- Python 3.11, Streamlit, Pydantic, pandas, numpy, Anthropic API. Model `claude-sonnet-5-5`. It rejects forced `tool_choice` (`any`/`tool`, 400): `loader.llm_tool` uses `auto` + "always call exactly one tool" in the system prompt, effort `low`, `max_tokens` ≥ 8000 (thinking is always on and counts toward it).
- API key: `st.secrets["ANTHROPIC_API_KEY"]`, else environment variable. Never hard-code.
- Run: locally with `streamlit run app.py` in a standard browser is the primary demo path (organiser: "runs locally in a standard browser"). Streamlit Community Cloud (Python 3.11) is an optional share link and backup; if used, wake it 10 minutes before the pitch. Keep a screen recording.
- Data: `data/` is committed (anonymised, private repo; reconfirm terms on the day). Raw bills/photos in `samples/` are gitignored; commit only redacted copies with `git add -f`.

## Files (create no others)

- `schema.py`: Pydantic `House`, `Result`, `NotesObs`, photo schemas (`BillObs`, `RadiatorObs`, `ExteriorObs`), fixed constants, photo-mission texts.
- `loader.py`: CSV/JSON → `House` (+ reference dict for dev cases). Must run without photos. Every set exists as both CSV and JSON: read the JSON (typed booleans and nulls), CSV only if the JSON is missing, one row per `building_id` (5 buildings, not 10).
- `engine.py`: physics, contradictions, Monte Carlo, traffic light, next question, installer brief.
- `engine_tracer.py`: frozen copy of the original engine; `app.py` uses it per building only when `engine.py` fails. Never edit.
- `calibrate.py`: fit k on the 3 dev cases (one parameter, geometric mean of log ratios), leave-one-out.
- `extract.py` (P0-b): wizard inputs (text, exterior photo, radiator photo, bill, listing) → `House` via per-mission tool-use schemas; resize photos to 1568 px JPEG before sending; cache by content hash.
- `app.py`: Streamlit, tabs `🏠 Homeowner` / `📊 Evaluation` (MVP); `🔧 Installer` only with `HP_SHOW_INSTALLER=1` (code kept). Page 1 has 4 fictional example-house cards (`EXAMPLES`: fill the form, attach photo + bill through the demo cache, pre-fill the page-4 text). Renders any `calculation` result with just the MVP core (`CONTRACT.md` "MVP": colour, G/Y/R probabilities, heat load kW, flow temperature °C); absent extras are hidden, a missing reason becomes a neutral sentence from colour + temperature.
- `orchestrator.py`: calls the three ML modules in-process through `REGISTRY` (`HP_MODULE_<NAME>="pkg.mod:func"` overrides one), never raises, falls back to `extract.py` cache-only (inputs) and `engine.py` → `engine_tracer.py` (result). Switches `HP_MODULES=0`, `HP_MODULES_ONLY=1`, `HP_LLM_FALLBACK=1`.
- `modules/` (`pipe_classifier.py` ML 1, `bill_recognizer.py` ML 2, `calculation.py` ML 3, ML team): `run(request) -> reply` per `CONTRACT.md`; skeletons until `IMPLEMENTED = True`; CLI `python -m modules.<name> < request.json`.
- `CONTRACT.md` + `contracts/` (JSON Schemas exported from `schema.py`, real examples): the module contract, envelope, time limits, fallbacks (§6).
- `data/buildings_dev.*` and `data/buildings_eval.*` (organiser files, do not edit), `data/notes_cache.json`, `data/baseline_results.json` (engine regression snapshot, `python loader.py --save-baseline`), `data/pipe_photos/` (organiser photos + `labels.json`); `assets/demo/` (fictional demo inputs with expected values, committed; regenerate with its script); `samples/` (`samples/cached_extract.json` = demo-mode reads, committed); `docs/` (`docs/challenge/` = organiser pages, do not edit; `docs/TEAM_GIT.md` = branch workflow; `docs/superpowers/plans/` = implementation plans); root docs for teammates `FLOW.md` (data flow, where to change what) and `ENGINE_PLAN.md` (engine tasks, expected numbers, structured output, model seam); `requirements.txt`; `.streamlit/config.toml` (theme); `.streamlit/secrets.toml` (gitignored).

## Interface contract

Field names in `schema.py` are frozen (2026-10-24): no renames; new fields only through Junwoo, pushed straight to `main`. The engine owner gets the list of `Result` fields the UI reads (plan Task 9) and must fill them.

```python
# schema.py
class House(BaseModel):                      # all value fields Optional
    confidence: dict[str, float] = {}       # field -> 0..1
    source: dict[str, str] = {}             # field -> data | text | photo | bill | listing | confirmed (step 4) | notes_llm | rule | prior
    missing: dict[str, str] = {}            # field -> not_visible | blurry | ambiguous | wrong_object
class Params(BaseModel): ...                # k (only calibrated value, default 1.01), efficiencies, DHW, single-pipe penalty
class Step(BaseModel): label: str; value: str; assumption: str | None
class Result(BaseModel): ...                # fields below + trace: list[Step]

# loader.py
def load_buildings(path="data/") -> list[tuple[str, House, dict | None]]   # (id, House, reference or None)
def parse_notes(text: str, use_llm: bool = True) -> NotesObs               # cache first, then LLM, then keywords

# engine.py
def evaluate(h: House, p: Params = DEFAULT, n: int = 500, seed: int = 0) -> Result   # point estimate + Monte Carlo, deterministic
def next_question(h: House) -> str | None                                           # P0: fixed order; P1: entropy / effort
def installer_brief(h: House, r: Result) -> Result                                  # fills visit_type, parts, installer_checklist
def quote_request(h: House, r: Result) -> dict                                      # pre-filled request (step 10); the app adds contact fields
def handover_pdf(h: House, r: Result, contact: dict) -> bytes                       # the one-page A4 pre-visit sheet (step 10), reportlab

# calibrate.py
def fit(buildings) -> Params
def leave_one_out(buildings) -> pd.DataFrame

# extract.py (P0-b)
def extract(file_bytes: bytes, mime: str, mission: str) -> House          # missions: house_text (text/plain), exterior, radiator, bill, listing
def merge(base: House, new: House) -> House                                # per-field source priority, confidence only breaks ties
```

`python engine.py` prints the 3 dev cases (expect B-01 green, B-02 green, B-03 yellow), the 2 evaluation cases (B-04 can never be green: single-pipe cap) and an example house with its Rechenweg (smoke check).

## Fixed assumptions (given by the challenge, do not change)

| Item | Value |
| --- | --- |
| Heat pump electricity | 0.26 €/kWh |
| Gas | 0.11 €/kWh |
| Heating oil | 1.70 €/L (≈10 kWh/L → 0.17 €/kWh) |
| JAZ underfloor | 4.0 |
| JAZ radiators ≤55 °C | 3.5 |
| JAZ radiators 55-60 °C | 2.8 |
| Radiators >60 °C | not in table → red (obstacle); cost shown at JAZ 2.8 as a lower bound |

Gas heat ≈ 0.11/η ≈ 12.5 ct/kWh at η 0.88 (oil ≈ 19.3 ct); worst HP case 0.26/2.8 ≈ 9.3 ct, so ≤60 °C always saves running cost. Break-even JAZ ≈ 2.1 against gas.

## Data mapping (code adapts to the data)

| CSV | House | Notes |
| --- | --- | --- |
| `construction_year` | `build_year` | |
| `floor_area_m2` | `living_area_m2` | rounded |
| `renovation_status` | `renovation` (unrenovated/partially/fully/None) | often empty |
| `heat_distribution` | `heat_distribution` (radiators/underfloor/mixed) | |
| `annual_consumption_kwh` | `annual_fuel_kwh` | |
| `energy_carrier` + `energy_carrier_detail` | `fuel_type` (gas/lpg/oil/district/electric) | "LPG"/"Flüssiggas" → lpg; litres → check against kWh |
| `radiator_info` | `radiator_count`, `valves_to_replace`, `hydraulic_balanced` | regex `(\d+)\s*radiators?`, `(\d+)\s*valves`; "balanced"/"abgeglichen" → True; "preset"/"voreingestellt" only → None + note "preset valves, balancing to check"; "presettable" (B-03, B-05: valves that can be preset) → None + note "presettable valves, balancing to check"; "valve blocks" (B-04) says nothing about the pipe system |
| `pipe_system` | `pipe_system` (two_pipe/single_pipe) | data spells `two-pipe` / `single-pipe`; `unknown` → None (step 3b) |
| `flow_temperature_c` | `current_flow_temp_c` | often empty |
| `persons_in_household` | `occupants` | |
| `hot_water_via_heating` | `dhw_by_boiler` | yes/no in CSV, true/false in JSON |
| `rooms` | `rooms` | radiator-count fallback |
| `building_notes` | `notes` + `NotesObs` | LLM facts with quotes, cached |
| `location` | `region` | "Munich area (82xxx)" → munich |
| `reference_heating_load_kw`, `expected_verdict` | reference dict | dev only |

`NotesObs` (facts only, each with a one-line quote `evidence`): `u_values` {windows, wall, roof, floor, basement}, `extra_heat_source` (wood_stove/tiled_stove/heat_pump/none), `extra_source_all_winter`, `solar_thermal_dhw` (B-05 says only "Solar thermal system present": DHW use is likely but say so), `unheated_area_note`, `insulation_measures` (list; an explicit "no additional insulation" is an empty list with its quote), `glazing` (e.g. double low-e, double without low-e), `building_type` (detached/semi_detached/terraced/apartment; B-04 "Semi-detached house").

Other `House` fields (wizard text, photos, step-4 confirmations): `building_type`, `monthly_advance_eur`, `boiler_condensing`, `radiator_size` (small/medium/large), `windows`, `roof_insulated`, `walls_insulated`, site flags `listed_building`, `outdoor_unit_space`, `flat_level_gas_heating`, bill raw values (`kwh_printed`, `m3`, `zustandszahl`, `brennwert`, `liters`, `period_start`, `period_end`, `bill_carrier` as printed, `bill_total_eur` for display only).

## Homeowner inputs (P0-b): a 4-step wizard

> **Update 2026-10-24 (team decision, after a UI review):** the wizard is **1/4 "Your house"**: integers typed (year built, living area, yearly use in kWh or litres, people, rooms, radiators; empty = don't know), categories as dropdowns with "Don't know" (type, renovation, heating surfaces, fuel, radiator size, hot water), `*` on the fields that move the colour most (year, area, heating surfaces, renovation, radiator count and size), and the line "If you don't know everything, it's okay."; **2/4 radiator photo**, **3/4 bill**, **4/4 "Anything else? (optional)"**: free text read by the LLM parser only when the homeowner presses "Read it"; conflict questions sit at the top of page 4; "Show my answer" works without it. The form wins over text on owner facts; the bill wins on use, the photo on radiators. (Year bands were used briefly and dropped; an old `evidence["build_year"] = "band …"` still means "treat as the band".) Bill and photo go through `orchestrator.py` to the team's modules, `extract.py` only as a **cache-only** fallback (never a live LLM call unless `HP_LLM_FALLBACK=1`). **Page 4 fills blanks only and never asks:** the text ranks lowest (`notes_llm`), a disagreement with a filled field is not a question but one muted "Not used (already set): …" note; conflict questions remain for form vs bill/photo. Form values merge with owner-text priority (internal source `"text"`, shown as "form"; `CONTRACT.md` §4). The text below describes the original design.

The homeowner types and snaps instead of filling a form. One thing per screen, progress "1/4", every step after the first can be skipped. Typing only, no voice in the app (phone keyboards can dictate into the text box anyway). The LLM reads each step as soon as it is sent (`extract`, one mission per step), so the user sees what we understood and an unreadable photo is retaken right there (one retake).

| Step | Screen | Mission | What it fills |
| --- | --- | --- | --- |
| 1/4 | "Tell us about your house": one text box with an example sentence as placeholder, plus an optional exterior photo ("rough is fine") | `house_text`, `exterior` | year, living area, building type, renovation hints, heating surfaces, carrier, yearly use, people, radiator count · from the photo: building type, rough era (always low confidence), windows, outdoor-unit spot (official bonus 2) |
| 2/4 | "Your biggest radiator, from the side, pipes in view" with an example photo, or skip | `radiator` | type 11/22/33, size class, valves, pipe-system cues (`unknown` when unsure) |
| 3/4 | "Got a bill or a listing?" (optional): bill as photo, PDF or app screenshot, or a sale listing / energy certificate screenshot | `bill` or `listing`, detected from the image | bill: raw consumption numbers, carrier, period, total € (display only) · listing: year, area, rooms, building type, carrier, certificate kWh/(m²·a), modernisation notes |
| 4/4 | "Is this right?": the core fields as chips with their source ("from your text: '1972'") | none | asks only what is missing or conflicting **and** changes the colour, at most 2 questions, "don't know" allowed → answer card |

Core fields for a verdict: year, living area, heating surfaces (radiators / underfloor / both). Still missing after step 4 → `unclear` → yellow "can't tell yet". Never asked: pipe system, flow temperature, U-values, boiler type.

**Which source wins** (engine `merge`; the LLM only reports what each input says): things owners know (year, area, people) → their text > listing or certificate > photo; things owners don't know (radiator type, pipes) → photo > text; consumption → bill > listing or certificate > text. An age read from the exterior photo never overrides a stated year. A disagreement that changes the colour → one question in step 4 (or one retake); one that doesn't → a note "we used X because …".
Listing or certificate consumption: kWh/(m²·a) refers to the certificate area A_N; without it, A_N ≈ 1.2 × living area (1.35 with a heated basement), shown as a range with low confidence, hot water included.
Demo inputs with expected values: `assets/demo/README.md`.

## Result

- `best_color` (green/yellow/red, always set, rule in step 6), `traffic_light` (adds `unclear`), `verdict_basis` (`likely_suitable` / `checks_remain` / `cannot_tell_yet` / `obstacle`, the organiser's colour meanings), `boundary` (max colour probability < 0.6), `reason` (one sentence for the homeowner), `reason_category` (temperature/insulation_first/pipe_system).
- `open_checks`: list of {item, why} in homeowner words: what we could not tell from the data and what a technician must check on site (step 6c). `hints`: insulation hint above 75 W/m² (step 2), myth-buster line.
- `p_green`, `p_yellow`, `p_red`; `required_flow_temp_c` and `heat_load_kw` as p10/p50/p90; `heat_load_bill_kw` (bill method, low/mid/high over 1,800 / 2,000 / 2,100 full-load hours); `specific_load_w_m2`; `jaz_bucket`; `cost_now_eur`, `cost_hp_eur`, `saving_eur`.
- `contradictions`: list of {what, sources, trusted, why}; `site_flags`.
- `confidence`, `lead_score`, `visit_type` (remote_quote/visit_with_parts/hold), `parts` {radiators_to_swap: (lo, mid, hi), valves, balancing: needed/check/None}, `installer_checklist`, `next_photo`.
- `next_step`: {kind: quote/site_check/answer_question/path_to_yellow, label, detail} for the homeowner's next-step box (step 10).

## Engine (`engine.py`)

**0. Site flags are not red reasons.** Listed building, no outdoor-unit space, flat-level gas heating: keep the physics colour, add to `site_flags`, put at the top of the installer checklist, cap green at yellow. Red only if a mentor or the data says it is a hard stop.

**1. Fuel to heat (cost and cross-check).** Organiser method (`03_technical_guardrails.md` §1b). **Fuel precedence:** bill raw values (when any is present) → `annual_fuel_kwh` → `annual_fuel_liters × 10` → advance payment. `annual_fuel_kwh` / `annual_fuel_liters` only ever hold values stated per year (data, homeowner text); a bill's printed kWh stays in `kwh_printed`. Bill conversion is done here, never by the LLM: `kwh_printed`, else `m3 × zustandszahl × brennwert` (either factor missing → `m3 × 10`, organiser value), oil `litres × 10`, scaled to 365 days. Advance payment only: `monthly × 12 / price`, range −30 %..+10 %, low confidence.
`Q_heat = annual_fuel_kwh × η` (useful heat). **η = 0.88 by default** (organiser: the old boiler loses about 12 %), so our numbers stay comparable with every other team. Only when the boiler type is known (stated in the text, or a photo): gas condensing 0.88 / non-condensing 0.80, oil condensing 0.95 / non-condensing 0.85 (Hs/Hi basis, say so in the Rechenweg). LPG like gas, note "real LPG price may be higher". District heating and direct electric: η 1.0, current cost "price not provided".
`Q_space = Q_heat − Q_dhw`, `Q_dhw = 1,000 kWh × occupants` (organiser) if `dhw_by_boiler`, halved with solar thermal (our assumption, label it).
Bill-based heating load `heat_load_bill_kw` = `Q_space / 2,000 h`, low/high `Q_space / 2,100` .. `Q_space / 1,800` (organiser: realistic 1,800-2,100 full-load hours).
`current_flow_temp_c` is shown, not used for the verdict; if our result is >10 K above it, log a contradiction.

**Required flow temperature** = supply water temperature that keeps 20 °C indoors with the existing radiators at the local design outdoor temperature (Auslegungsvorlauftemperatur). 55/60 °C are the challenge's JAZ bands, not our choice.

**2. Heating load (Heizlast): area × age is primary.** With the organiser's bill method the consumption-based load needs about 500-2,290 full-load hours to match the dev references (organiser: realistic 1,800-2,100), so it cannot be calibrated with one parameter.
`P_load = k × w(age, renovation) × heated_area`

| Built | Unrenovated / unknown W/m² | Partially renovated W/m² | Fully renovated W/m² | Organiser band (`03_technical_guardrails.md` §1a) |
| --- | --- | --- | --- | --- |
| ≤1978 | 130 | 80 | 50 | unrenovated, before 1979: 120-180 · renovated: 40-60 |
| 1979-1994 | 85 | 70 | 50 | 1980s-1990s: 80-120 · renovated: 40-60 |
| 1995-2001 | 80 | 55 | 50 | 1980s-1990s: 80-120 (low edge: Wärmeschutzverordnung 1995) · renovated: 40-60 |
| 2002-2015 | 50 | 50 | 50 | built 2002+: 40-60 |
| ≥2016 | 35 | 35 | 35 | low-energy / new build: 15-40 |

Every unrenovated and fully-renovated value sits inside the organiser's band; "partially renovated" has no organiser band and sits between the unrenovated and renovated bands. Sources: organiser guardrails, German trade rules of thumb (BDH/VdZ, Viessmann tables). Show "first estimate, not a DIN EN 12831 calculation" and the organiser band next to the value in the Rechenweg. Monte Carlo ±20 %.
Use the partially-renovated column when the renovation status is empty but (a) notes name insulation work, or (b) the wall U-value is below 0.7 × the age reference (≤1978 1.0, 1979-94 0.6, 1995-2001 0.5, 2002-15 0.35, ≥2016 0.24 W/m²K, estimated). Log it as a contradiction ("no renovation documented vs better-than-code U-values"). Dev calibration is unchanged by this table (B-01 → 55, B-02 → 50, B-03 → 80).
**Renovation unknown** (empty in the data, or "don't know"): compute the colour with the unrenovated and with the partially-renovated column. Same colour → keep it (unrenovated column, as before). Different colours → `cannot_tell_yet` (yellow) and `next_question` = "Was the house insulated or were windows replaced since it was built?". Otherwise "don't know" would turn a 1972 house with 10 large radiators confidently red (scratch run, p50: 72 °C read as unrenovated vs 59 °C partly renovated). None of the 5 data buildings changes: B-04 is red either way, B-02 and B-05 have the same value in both columns, B-01 uses the U-value rule.
Unused area in the notes: heated area × 0.85 (Monte Carlo 0.7-1.0); keep the radiator count and add "radiators/valves on the unused floor" to the installer checklist.
**k = 1.01** (only calibrated parameter, recompute on the day with `calibrate.py`). Leave-one-out error B-01 +20 %, B-02 −9 %, B-03 −8 %.
W/m² comes through one seam, `engine.w_per_m2_for`: this table by default, or a learned model via `engine.set_w_model` / `HP_W_MODEL` (input `engine.features`, table fallback on failure; see `ENGINE_PLAN.md`).
The bill-based load (step 1) is a cross-check only, but it is **always shown beside the area-age load, with the combined range when they differ** (organiser: "if you have both, show both, and show the range"). The verdict uses area-age.
`specific_load_w_m2 = P_load / heated area` (p50). Above 75 W/m² → hint "better windows or insulation may be worth it" (organiser threshold); never a red reason by itself.

**2b. Contradiction checks** (engine decides; the LLM only supplies facts). Each hit adds {what, sources, trusted, why} and widens that value's range.
- Consumption load vs area-age load differs by more than ±40 % → trust area-age; cause from notes (extra heat source all winter → consumption too low; unused area → area too high; rooms say the area is too small → see next rule; else "habits or record error, installer to check").
- Rooms vs area: under 10 m² per room (B-05: 14 rooms in 125 m², ~9 m²) → "documented area may not include all heated rooms (basement, attic?)". Verdict still uses the documented area, but if the bill is also >40 % above the area-age load, widen the area upward in the Monte Carlo to the bill-implied area `heat_load_bill_kw / (k × w)` (cap 2×) and ask in `open_checks`.
- Extra heat source all winter → consumption is a lower bound only.
- Unused area → area × 0.85.
- No renovation recorded but insulation work or better-than-code U-values → partially-renovated column.
- DHW via boiler and solar thermal → halve DHW.
- Carrier gas but detail LPG → correct to lpg.
- Litres and kWh both present and differ by more than ±15 %.
- Our flow temperature >10 K above `current_flow_temp_c`.
- Old building with underfloor heating → likely retrofit, log only.
Dev cases (η 0.88, DHW 1,000 kWh/person): B-01 (bill 2.4 kW vs ~10.8 kW area load, −78 %; gas/LPG; U-values), B-02 (wood stove all winter, solar thermal, −33 % so caught by the wood-stove rule, not the ±40 % rule), B-03 (unused top floor; bill +21 %, no flag).
Evaluation cases: B-04 (bill −31 %, no flag; litres and kWh agree; single-pipe, step 3b), B-05 (bill +76 % → flagged; 14 rooms in 125 m², rooms-vs-area rule).

**3. Radiator output (DIN EN 442).**
Underfloor → 35-40 °C, JAZ 4.0. Radiators: `Φ = Φ_n × (ΔT/50)^1.3`, Φ_n at 75/65/20 °C.
**Mixed** (an underfloor circuit plus a radiator circuit, e.g. B-05): the heat pump must deliver the radiator circuit's temperature (the underfloor circuit is mixed down), so the verdict and JAZ follow the radiator circuit. Radiator share of the load = `radiator_count / rooms` (cap 1.0); rooms unknown → U(0.5, 1.0), point 0.75 (estimated). Required temperature from `P_load × share` against the radiators' ΣΦ_n; show "underfloor circuit fine at ~35 °C" beside it.
Approximation: `ΔT_need = 50 × (P_load / ΣΦ_n)^(1/1.3)`, `T_flow = 20 + ΔT_need + spread/2`, spread 8 K. Single-pipe: step 3b.

| Size | Typical | Φ_n | Monte Carlo |
| --- | --- | --- | --- |
| small | Type 11, 600 × ~800 | 0.7 kW | 0.5-0.9 |
| medium | Type 22, 600 × 800-1000 | 1.5 kW | 1.3-1.7 |
| large | Type 22 600 × 1200 or Type 33 600 × 1000-1200 | 2.2 kW | 2.0-2.7 |

Source: Kermi therm-x2 Type 22 600×800 1,333 W, 600×1000 1,666 W, 600×1200 1,999 W; Type 33 600×1000 2,236 W, 600×1200 2,683 W; Buderus Type 22 600×1000 1,688 W (energiefluss24.de). Small is estimated (one panel ≈ half of Type 22).
Radiator count: data → `rooms × 1.3` → `area / 18`. Unknown size → Monte Carlo draws small/medium/large with 0.25/0.5/0.25 (estimated); point estimate uses medium.
Display clip: above 70 °C show ">70 °C" (red, temperature).
Dev check (k 1.01): point estimate B-01 54.0 °C green ✅, B-03 58.2 °C yellow ✅. Monte Carlo B-01 p50 54.6 °C (G 0.52 / Y 0.20 / R 0.28), B-03 p50 58.8 °C (G 0.33 / Y 0.23 / R 0.44). 3/3 with one parameter.

**3b. Pipe system** (organiser background, `docs/challenge/05_single_vs_two_pipe.md`). If `pipe_system` is given, use it.
- **single-pipe (confirmed):** flow temperature +5..10 K (Monte Carlo U(5, 10), point +7.5 K, estimated). Green is capped at yellow (organiser: "a confirmed single-pipe system is rarely a clean green without an on-site check"); `reason_category = pipe_system` when it decides the colour. Path to yellow and checklist name the organiser's options, no prices: larger radiators at the end of the loop, a higher flow temperature, converting parts of the system; check bypasses and balancing.
- **unknown:** never guess it from "two connections at the radiator" or "valve block" alone (both exist in either system). Built 1960-1979 (single-pipe was common then, especially in apartment buildings): widen the Monte Carlo upward with a penalty drawn from U(0, 10) K and say why. Other years: no penalty. Radiator buildings always get the organiser sentence in `open_checks`.
- **two-pipe:** no penalty.

**4. JAZ band.** Underfloor 4.0 / ≤55 3.5 / 55-60 2.8 / >60 none (cost: step 5).

**5. Cost.** `cost_now = annual_fuel_kwh × price`, `cost_hp = Q_heat / JAZ × 0.26`, `saving = cost_now − cost_hp`. Above 60 °C the table has no JAZ: show the cost at JAZ 2.8 as a lower bound ("at least this much, the real running cost is higher"; organiser: running hotter is the expensive way). A bill's own € amount (P1) is shown as "your bill says", never used in the comparison (fixed prices keep all teams comparable).

**6. Traffic light** (organiser meanings, `docs/challenge/02_mission.md`).

| Colour | Organiser meaning | `verdict_basis` | Our rule |
| --- | --- | --- | --- |
| 🟢 green | Likely suitable based on available information | `likely_suitable` | underfloor, or p50 flow temperature ≤55 °C, and no cap applies |
| 🟡 yellow | Potentially suitable, but important checks remain, less data | `checks_remain` | p50 55-60 °C, or a green capped by site flags (step 0) or by a confirmed single-pipe system (step 3b) |
| 🟡 yellow | (same) | `cannot_tell_yet` | `unclear`: area/age or radiator count missing (a count from any fallback counts as present), or the colour depends on an unknown renovation status (step 2). Never red. |
| 🔴 red | Insufficient evidence for a positive assessment | `obstacle` | p50 flow temperature >60 °C with core data present |

`best_color` = colour of the Monte Carlo p50 flow temperature, then the caps; `unclear` → yellow. Red needs more evidence than green: high demand without radiator info → unclear (yellow), not red. The homeowner reason always says which case it is: "there is an obstacle: …" or "we can't tell yet: …".

**6b. Path to yellow (physics only, no prices).** Radiator output to add: `ΣΦ_n,needed(55 °C) − ΣΦ_n` kW, or heat-loss reduction needed: `1 − P_allowed(55 °C) / P_load`. Do not say which insulation achieves it. Single-pipe: add the loop options from step 3b.

**6c. What's still open (`open_checks`, organiser output #2).** Homeowner words, most decisive first, at most about 6 lines:
1. Missing core fields that moved the result (from `next_question`): "We don't know X; with it the answer gets sharper."
2. Each contradiction (step 2b) as a plain question, e.g. "Your bill and your house size disagree: is all heated area included?"
3. Assumed values that decide the colour: radiator type and size when not documented (known small or old radiators: organiser says "flag as needs checking", so a technician checks room by room); the pipe system when unknown (organiser sentence: "Heating pipe system unclear. A technician should check whether this is a single-pipe system, because that can require a higher flow temperature.").
4. Always (organiser, `03_technical_guardrails.md` §4): exact heating load, electrical capacity, where the outdoor unit can go.
The installer checklist (step 9) carries the same items in installer words.

**7. Uncertainty (Monte Carlo, P0).** N=500, seed 0, numpy vectors (no per-sample Pydantic objects), cached with `st.cache_data`. Draw: W/m² × U(0.8, 1.2); radiator size as above × U(0.85, 1.15); unused area × U(0.7, 1.0); single-pipe penalty U(5, 10) K, unknown pipe in a 1960-1979 house U(0, 10) K (step 3b); mixed radiator share U(0.5, 1.0) when rooms are unknown (step 3); contradicted values widened (e.g. area up to the bill-implied area, step 2b). Output colour probabilities and p10/p50/p90.
`best_color` = colour of the p50 flow temperature (not the most frequent colour: the radiator-size tail pushes the mode toward red, B-03 shows this). Max probability < 0.6 → `boundary`, show the top two colours with probabilities ("uncertain: 🟢/🟡").

**8. Next question.** P0 (wizard step 4 and the answer card): core fields first (year > living area > heating surfaces), then a renovation status that flips the colour (step 2), then radiator size, then yearly use; at most 2 questions in step 4. P1: the unknown whose fixing reduces colour entropy most, divided by effort.

**9. Installer visit prep (`installer_brief`).**
Visit type, first match wins:
0. `boundary` → visit with parts (decide on site)
1. red → hold + path to yellow + keep the lead
2. unclear → visit with parts + one photo request
3. yellow, any contradiction, or green with confidence < 0.7 → visit with parts
4. green, no contradictions, confidence ≥ 0.7 → remote quote

`confidence` = mean of 5 core fields (area, age, fuel amount, radiator count, radiator size); data value or confirmed in step 4: 0.9, read by the LLM from text/photo/bill/listing: its confidence capped at 0.8, regex fallback 0.5, missing/unknown 0.3; −0.1 per contradiction; unclear caps at 0.5; floor 0.1. `lead_score = (p_green + p_yellow) × confidence`.
Parts (physics only): radiators to swap ≈ `ceil(ΣΦ_n shortfall at 55 °C / (2.2 − current size))`, unknown size = medium; shortfall ≤ 0 → 0; already large and short → "swapping is not enough, add radiators or check per room"; underfloor → n/a (attached radiators "check"). Range from Monte Carlo. Valves to replace from data. Hydraulic balancing: True → "check", otherwise "needed".
Checklist: one line per contradiction ("check X on site"), site flags, pipe system if unknown, single-pipe loop checks (step 3b), then always the organiser's technician list (`03_technical_guardrails.md`): exact heating load (DIN EN 12831) and room-by-room radiator sizing, electrical capacity and meter cabinet, hydraulics and balancing, outdoor-unit position, sound distance and permits.

**10. Next step and quote request** (the homeowner's "so what do I do now?"; getting a quote today means long forms).
Next-step box under the answer card, one primary button:

| Verdict | Primary button | Detail line |
| --- | --- | --- |
| green | "Get a quote" | "a remote quote is likely possible" when `visit_type` is remote_quote, else "an installer will want a short look first" |
| yellow, `checks_remain` | "Request a short on-site check" | "they will look at: …" (top 2-3 `open_checks`) |
| yellow, `cannot_tell_yet` | "Answer one more question" (`next_question`) | secondary button: "or request a check" |
| red | "See what gets you to yellow" (step 6b) | secondary button: "talk to an installer anyway" |

Every button opens the same quote request with a matching subject (quote / on-site check / advice). `quote_request(h, r)` pre-fills it from what we already have: the house facts with their source, our result (colour and probabilities, heating load and flow temperature ranges, contradictions), `open_checks`, visit type and parts (step 9), photos attached so far (P1). The homeowner adds only name, e-mail or phone, and postcode.
**Output: one A4 page, the "Pre-visit sheet" PDF** (`handover_pdf`, reportlab; add `reportlab` to `requirements.txt`, it is pure Python; the demo bill in `assets/demo/` was made with it). Layout as in `docs/design/Handover.dc.html`:
1. Header "Pre-visit sheet", request type, date; contact line (name · phone or e-mail · postcode) and a one-line house summary.
2. **For the installer** box on top: the visit type in words (remote quote possible / short visit with parts / hold: not without changes), colour with probabilities, required flow temperature with range, one instruction ("check the radiator sizes first"). This lets an installer decide in a minute whether the trip is worth it.
3. Two columns. Left: **✓ Confirmed** (item · value · source: owner / bill / photo / data) and **~ Estimated** (item · value with range · how: area × age, bill ÷ 2,000 h, radiator model, owner's words, photo, fixed prices). Right: **? Check on site** (`open_checks` plus the organiser's always-checks), **Bring** (parts from step 9), the radiator photo with a caption. A field is "confirmed" only when stated by the owner, read from a bill or listing, or in the data; everything the engine or a photo inferred is "estimated".
4. Footer: first estimate, not a DIN EN 12831 calculation; fixed challenge prices; no installation cost or subsidies; nothing stored; "Page 1 of 1". The bill photo itself is not included, only its numbers.
Ink-friendly: black text, ≥ 12 px (9 pt), badges carry words ("✓ Confirmed", "~ Estimated", "? Check on site") so it reads in grayscale. Built-in Helvetica covers €, °, ², umlauts and "–"; use "~" instead of "≈" unless a TTF font is registered.
Also "Open as e-mail": a mailto draft (subject + short body asking to attach the PDF, no recipient: we do not invent nuuEnergy's address). The JSON of the same data stays an optional extra for CRMs such as nuuOS (say "could", nothing is integrated). The app sends nothing and stores nothing: contact details live only in `st.session_state` and on the PDF the homeowner downloads.

## Extraction missions (P0-b)

One mission per wizard step, each with its own tool-use schema; the LLM returns raw values with a one-line quote or image note as evidence and a confidence, `null` when unsure, never a verdict or arithmetic:
- `house_text` (step 1): year, living area, building type, renovation hints, heating surfaces, carrier, yearly use (number + unit as written), people, radiator count and size words. Reuses the `NotesObs` approach; keyword fallback with negation handling.
- `exterior` (step 1, optional): building type, era range (always low confidence), windows, visible facade insulation, a plausible outdoor-unit spot or "no visible space" (official bonus 2).
- `radiator` (step 2): panel type 11/22/33, size class, valve type, pipe-system cues (below).
- `bill` (step 3): `BillObs` raw numbers only (official bonus: consumption, energy carrier, costs).
- `listing` (step 3, auto-detected instead of `bill`): year, living area, rooms, building type, carrier, certificate type and kWh/(m²·a), modernisation notes.
A photo of the wrong thing or an unreadable one → `missing` = wrong_object / blurry, one retake request with a concrete tip.
Pipe-system cues for the `radiator` mission (organiser table): one pipe along the wall or skirting, tapped at each radiator → single-pipe; H-block with an extra adjustable side port (bypass) → single-pipe; valve at the top, separate return at the bottom, two separate pipes → two-pipe; H-block without side port → two-pipe likely; one bottom connection or bathroom multiblock → usually unknown. The system belongs to the building, not one radiator. Unsure → `unknown` with a reason, never a guess. Test set: `data/pipe_photos/labels.json` (07 must come back unknown).
Demo inputs: `assets/demo/` (fictional bill, listing, house texts, expected values). A real-format bill, if wanted: the public Stadtwerke München sample bill (annual kWh on page 1), https://www.swm.de/dam/doc/kundenservice/rechnung/musterrechnung-erklaerung.pdf
`merge` priority: the source rule in "Homeowner inputs"; LLM confidence only breaks ties within one source.
Retake: one per photo in P0-b; more than one is P1.

## Screens (`app.py`): UI design, locked 2026-10-23

Source of truth: the design canvas "HP-Ready homeowner flow" and its files in `docs/design/` (layout, order, exact copy). Build it as drawn; the numbers on it are examples from the scratch calculation, the engine supplies the real ones.
**Evaluation and Installer tabs (redesigned 2026-10-24):** source of truth is the canvas "HP-Ready Evaluation & Installer" (https://claude.ai/artifact/KMm2fjQHZd8USDTBtLgeDq). Evaluation is for judges/developers (KPI cards, 8-column table, detail cards; no quote button, no homeowner copy); Installer is for installers (third person, ranked leads, KPI strip, What it takes / Bring / Flags for this house / standard checks; no contact form). Shared display helpers live in `app.py` under `# ---- ui components` (pills, bars, flow scale, `human_*` text converters); never show raw `[]`, `True/False`, snake_case or "MC". The app writes sentences from structured `Result` fields (`options`, `radiators`, `flags`, `always_checks`) and only parses engine text as a fallback. The descriptions below for those two tabs are superseded where they differ.

**Rule: show little, open on tap.** Every homeowner screen leads with one headline and one short line; everything else sits in tap-to-open rows (`st.expander`), one open at a time where possible, never in paragraphs.

**Look (tokens).** Font Inter 400/500/600/700 (fallback system sans). Ground `#F3F5F7`; cards `#FFFFFF`, border `1px #E2E6EA`, radius 16-20 px; ink and primary buttons `#14213D`; secondary text `#4A5565`; inputs border `1.5px #C9D0D8`, radius 12-14 px; chips: white with `1px #E2E6EA` border, unsure chips dashed `1.5px #9AA5B1` with grey text; confirmation green text `#1E5E37` on `#E7F4EC`; info boxes `#EAF1F8`. Traffic light: green `#1E7A46`, yellow `#F2B705` (dark text on it), red `#B42318`; always with a word, never colour alone. Headline 28 px/700, body 15-16 px, small 13 px; primary button 54 px tall, radius 14; every touch target ≥ 44 px. No emoji in the UI (✓ is fine).

**Phone flow, one column** (copy in quotes is exact):
- **1/4** "Tell us about your house" · "Year, size, heating. Whatever you know." · text box "Your house" · "✓ We read" chips (e.g. 1972 · 140 m² · Terraced · Partly insulated · Gas ~18,000 kWh · 10 radiators · dashed "Large?") · dashed button "Photo of the outside · optional" · "Next".
- **2/4** "Your biggest radiator" · "From the side, pipes in view." · the photo · "✓ We read" chips · "Why? ›" opens the reasons · one line "Size unclear. One side shot?" with "Retake" (only when something is unreadable) · "Next" / "Skip".
- **3/4** "Bill or listing?" · "Optional. Photo, PDF or screenshot." · preview · chips (e.g. Gas · 2025, 18,002 kWh, green "Matches your text") · "Only the numbers are kept." · "Next" / "Skip".
- **4/4** "Is this right?" · "Tap to fix." · one row per field: label, value, source pill (text / photo / bill / listing) · "✓ No questions for you", or at most 2 questions · "When do we ask? ›" · "Show my answer".
- **Answer**: traffic light + headline + status word, one sentence (what it needs + the one thing that would settle it) · rows "How sure › 58 % green", "Water temperature › ≈ 54 °C" (scale 35-70 °C, band p10-p90, marks 45 ideal / 55 efficient / 60 pricier), "Running cost › save ~€800/yr", "What's still open › 4 things", "How we got this ›" (the Rechenweg: both load methods, W/m² hint, myth line) · next-step button (step 10) + one short line.
- **Quote request**: "Your request is ready" · "Just add how to reach you." · "What's on the PDF ›" (confirmed · estimated · to check) · Name, E-mail or phone, Postcode · primary "PDF for the installer" (`st.download_button`) · "Open as e-mail" · "One page any installer reads in a minute. Nothing is stored."

**Headline words by verdict:** green → "Green" / "Likely suitable" ("Green, just" when `boundary`); yellow `checks_remain` → "Yellow" / "Some checks remain"; yellow `cannot_tell_yet` → "Yellow" / "Can't tell yet"; red → "Red" / "Not without changes". The one sentence names the obstacle or the missing piece.

**Web (desktop ≥ 1024 px): the same app, wider.** One Streamlit app serves phone and desktop; nothing is built twice. Top bar: "HP-Ready" and the tabs Homeowner · Evaluation (`st.tabs`, Homeowner first; Installer only with `HP_SHOW_INSTALLER=1`, out of the MVP).
- **Homeowner**: two columns (`st.columns([3, 2])`). Left: the current wizard step, photo and "We read" chips side by side, Back / Next / Skip as normal-width buttons. Right: "What we know so far", one row per field with its value and source pill, filling up step by step ("tap to fix"), and a one-line hint for the next step. On the answer: left the answer card with the same rows, right the quote request in a card outlined in ink ("Get a quote" · "What's on the PDF ›" · 3 fields · "PDF for the installer" · "Open as e-mail").
- **Evaluation** (the pitch screen): 3 stat tiles (dev verdicts 3/3 · leave-one-out errors · 1 calibrated number), then one table: Building · Set · Verdict · How sure (mini green/yellow/red bar) · Water temp (p50 and p10-p90) · Heating load (ours · reference or bill) · Flags · Visit. Dev rows show "✓" when the verdict matches the reference. Selecting a row fills a details panel below: why (2-3 lines), contradictions with the source we trusted, what the AI read (quote → meaning).
- **Installer**: lead list on the left (B-01…B-05 and the current homeowner house, with colour dots), on the right the same content as the pre-visit PDF: title, visit badge, one sentence, 3 chips (load, water temperature, radiators), then "Path to yellow · Bring · Check on site", and a "Download PDF" button.
- At phone width Streamlit stacks the columns; the stack must look like the phone flow above.

**Streamlit mapping.** Theme in `.streamlit/config.toml` (primaryColor `#14213D`, backgroundColor `#F3F5F7`, secondaryBackgroundColor `#FFFFFF`, textColor `#14213D`, font sans serif); wizard step in `st.session_state.step`, progress as 4 small bars; chips, traffic light and the temperature scale as small HTML snippets via `st.markdown(..., unsafe_allow_html=True)` with the tokens above; rows as `st.expander`; text box `st.text_area`; uploads `st.file_uploader` (+ `st.camera_input` on laptops); buttons `st.button` full width.

- 🏠 Homeowner (first tab): the 4-step wizard ("Homeowner inputs"), each step showing what was read as chips right after sending → traffic light (two colours when uncertain) + reason, with "obstacle" or "can't tell yet" spelled out → **What's still open** (`open_checks`) → flow-temperature scale 35-70 °C with the p10-p90 band and marks at 45 °C (ideal), 55 °C (efficient), 60 °C (works, costs more) → cost → one improvement hint (plus the insulation hint above 75 W/m²) → **next-step box** (step 10) → 📨 quote request panel: the pre-filled summary, 3 contact fields, "Open as e-mail" and "Download request". Where it fits, one myth-buster line: underfloor heating and a full renovation are not required. Uploads: `st.file_uploader` (photos, PDFs, screenshots; rear camera on phones), plus `st.camera_input` on laptops.
- 📊 Evaluation: 5 buildings; dev cases beside their references; **B-04 and B-05 with ranges and their answer card** (the deliverable); both heating-load methods side by side; contradictions; "facts the AI found in the notes + quotes"; `lead_score` and visit type. **The pitch shows the evaluation results here.**
- 🔧 Installer: building selector → one prep sheet: visit-type badge, parts list, on-site checklist, load and flow temperature (p10-p90), missing fields.
- Demo-mode toggle (P0-b): use `samples/cached_extract.json` (extractions of the `assets/demo/` inputs) instead of live LLM calls.

## Working rules

- One Claude session, build order: schema → loader (+ notes cache) → engine → calibrate → Evaluation → Homeowner answer card (with next-step box) → wizard + extract (text → bill → radiator → exterior → listing) → quote_request + handover_pdf + request panel → installer_brief + Installer tab (shows the same page) → (P1). If a teammate joins, split with git worktrees, never two sessions in one folder.
- After each passing `/check`, commit only the files you changed (never `git add -A`). Never work 30 min without a commit; roll back to the last commit if broken.
- `/hp-review` after P0-a, after P0-b and before the freeze. New information on the day goes through `/intake`.
- Keep function signatures; add new functions if needed. Wrap every LLM and file call in try/except, fall back to cache, show it small on screen.
- Streamlit reruns the script on every click: cache `parse_notes` and `extract` by content hash, keep the house in `st.session_state`, never call the API twice for the same input.
- Store extracted numbers only; never keep raw bills, names or addresses.
- One feature at a time, then `streamlit run app.py` on the happy path. Short explanations, straight to code.
- When engine.py changes: python loader.py --compare-baseline, then check_result shows nothing; save a new baseline only for intended changes.

## Demo (P0 only, default)

1. 🏠 Homeowner: the homeowner's question first. Type the persona sentence (`assets/demo/house_persona_en.txt`), add a radiator photo (`data/pipe_photos/`) and the bill (`assets/demo/bill_demo_gas_2025_photo.jpg`), well under 3 minutes → step 4 shows what was read and from where → colour with probabilities, reason, what's still open, scale, cost → press the next-step button: the quote request is already filled in, only name, contact and postcode are left → "PDF for the installer": show the page (confirmed vs estimated vs to check, the installer recommendation on top). Then `house_minimal_en.txt` → yellow "can't tell yet" + one question (missing data is not red); `house_conflict_en.txt` with the gas bill → step 4 asks "oil or gas?".
2. 📊 Evaluation: dev accuracy and leave-one-out → **B-04 and B-05 results** → B-05 contradiction (125 m² but 14 rooms and a bill +76 % above the area-age load; we trust area-age, widen the range and ask "is all heated area included?") → B-01 contradiction (bill ~2.4 kW vs area and age ~11 kW, −78 %; trusting area-age; installer to check habits/LPG) → AI-found facts with quotes (B-02 "A wood stove is used all winter").
3. 🔧 Installer: B-04 → single-pipe, red with a path to yellow and the loop checks; or B-03 → visit with parts: about N radiators, 12 valves, balancing, check the unused top floor.
4. Rechenweg once; same input twice → same result.
Optional live moment: snap a real radiator on stage; Demo-mode cache if the call is slow or fails. Backup: screen recording.

## Pitch lines

- "'Would a heat pump even work in my home?' Today only a technician's visit answers that. We answer it in under three minutes, and we say what we can't tell."
- "Missing data isn't a no. We say 'can't tell yet' and name the one thing that would settle it."
- "Getting one quote today means hours of forms. Here it takes three minutes, and the request is already filled in." (Use a number only if you measured it yourself.)
- "The installer gets one page: what's confirmed, what's estimated, what to check. They know in a minute whether the trip is worth it."
- "In Germany, the scarcest resource isn't energy. It's the installer's time."
- "The LLM only reads, and only if you ask it to. The logic decides, and it shows its work. Nothing is made up." (Old line, physics baseline only: "The LLM reads. Physics decides.")
- "Real data contradicts itself. We show which source we trusted and why."
- "We don't cancel site visits. We make them short and precise."
- Phase 2: calibrate on nuuEnergy's real visit outcomes.

## Do not

- Login, database server, test code, refactoring.
- Let the LLM output verdicts, colours or numbers.
- Output prices, installation cost or subsidies beyond the fixed assumptions.
- Generate fake buildings or visits.
- Send quote requests or store names and contacts (PDF download and mailto draft only), or invent a recipient address.
- Add features in the last hour (code freeze).

## On-site information protocol (whenever the user pastes something new)

1. Classify: deliverable/judging, data format, reference values, domain fact, constraint (time/team/rules), feedback.
2. Three-line plain summary (in Korean).
3. Conflicts: name the sections of this file it touches, or "no conflict".
4. Minimal edit proposal, changed lines only. Touch the Invariants (1-8) only if the new info demands it.
5. Priority impact on P0/P1/P2/timeline; when time shrinks cut P2, then P1.
6. After the user says "ㅇㅋ", edit this file, add one line to the decision log in `docs/DESIGN.md` (with time), tick open questions.
7. Explain unfamiliar terms in one line using `docs/DESIGN.md` → Domain primer.

Playbook: data file → print all columns, mapping table, adapt `schema.py`; reference = heating load → refit k; reference = flow temperature → refit the radiator table scale; verdict only → keep 55/60 bands, refit the radiator scale; cost/JAZ → check our cost formula matches theirs. Judging/rule notice → update judging table and timeline; "code must be written during the event" → tell the user what exists and wait. Mentor says a domain fact → engine first; a preference → priorities only. Screenshot only → read it, say what is unreadable.

## Open questions

- [ ] Submission deadline and pitch slot
- [ ] **How did nuuEnergy compute the reference heating load?** (rule-of-thumb area/age, U-value DIN 12831, consumption) → first question to the mentor; refit k and the table accordingly
- [x] Evaluation data format: same fields as dev without the two reference columns; inputs are public in `data/buildings_eval.*`
- [ ] Deliverables page says "3 evaluation buildings", the data and the one-pager say 2 → ask on the day, plan for 2
- [ ] Does the jury compare the heating load (kW) for B-04/B-05 as well as the colour? (their hidden "reference values" include both) → decides how big the load range is on screen
- [ ] Mentor, first hour (show the pre-visit PDF from `docs/design/Handover.dc.html` on a phone, then ask): "When an installer comes back from a visit with 'not like this', what was missing beforehand?" · "What does an installer need to know before driving out, and is there an intake form in nuuOS we should match?" · "Do site visits cost the homeowner anything?" (decides whether the pitch may say "no wasted visit fee" or only "no wasted trips"). Answers → new PDF fields if we can sense them (text, photo, bill), otherwise new "Check on site" lines; log in `docs/DESIGN.md`.
- [x] Team roles (2026-10-24): **Junwoo** owns LLM input/output and the contract: `schema.py`, `loader.py` (+ `parse_notes`, `notes_cache.json`), `extract.py`, `app.py`. **friend `potatohater8`** (domain knowledge) owns `engine.py` and `calibrate.py` (steps 0-9) and may change the physics, but keeps `evaluate(House) -> Result` and the `Result` fields. Step 10 (`quote_request`, `handover_pdf`) is agreed between the two when P0-c starts. Branches `junwoo/loader` and `engine`, merged into `main` every 1-2 h; `schema.py` changes go straight to `main` and only through Junwoo (`docs/TEAM_GIT.md`). Also on the repo: `cybeuu`, `lukakopse` (invited 2026-10-24). Until the owner pushes, `engine.py` on `main` is the tracer engine; the owner may replace it freely behind the contract (structured fields, `check_result`, baseline compare, tracer fallback, W/m² model seam: see `FLOW.md` §4 and `ENGINE_PLAN.md`). Teammate onboarding: `FLOW.md` (data flow, where to change what).
- [ ] Is pre-written code allowed
- [ ] Engine owner, wording to fix in `engine.py` (the UI already hides both): B-05 path line says "Radiators give 12.0 kW at 55 °C" but 12.0 kW is the 75/65/20 °C rating; `installer_checklist` items carry a "Check on site:" prefix and nested brackets. Best fix: fill the structured `Result` fields instead of sentences.
- [x] Data terms (anonymised, private repo OK; reconfirm), reference format, CSV fields, location granularity, photos in eval data (none)
