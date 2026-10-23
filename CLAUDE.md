# HP-Ready Triage (WATT THE HACK Munich, nuuEnergy challenge #4)

Build spec for the coding agent. Background, rationale and the decision history live in `docs/DESIGN.md`; the pitch lives in `docs/PITCH.md`; the original Korean plan is `docs/CLAUDE.ko.md` (reference only, this file wins on conflict).

**Talk to the user (Junwoo) in Korean.** He is a first-time hackathon participant with no domain or statistics background. Explain in plain words, do the interpretation yourself, never hand it back to him.

## One line

Before an installer drives out, tell nuuEnergy whether a home is heat-pump ready (green / yellow / red), how sure we are, what contradicts itself in the data, and what the installer should bring.
The LLM only **reads** (free-text notes, later photos). A **physics engine** decides. Unknowns become ranges and probabilities, never invented numbers.

## Core principles (never break)

1. **The LLM is a parser.** It fills schema fields only. No verdicts, recommendations or arithmetic.
2. **Unknown stays empty.** Unsure field = null. Every field carries a confidence (0-1).
3. **`engine.py` decides.** Physics + Monte Carlo, calibrated with one parameter on the 3 dev buildings.
4. **Ask only what matters.** At most one follow-up request: the unknown that moves the verdict most.
5. **Schema is the contract.** Fields are defined once, in `schema.py`.
6. **No made-up numbers.** Prices and JAZ come only from the fixed assumptions below. Never output installation cost or subsidy amounts ("installer quote needed").
7. **Red is earned.** Every red carries a reason category and a "this gets you to yellow" path.

## Situation

- One-day hackathon, 2026-10-24 09:00-19:00, TUM campus. Deliverable: a live browser prototype, the result for the 2 hidden buildings, a live demo (not slides).
- Data: 5 real, anonymised nuuEnergy buildings (CSV + JSON). 3 dev cases (`data/buildings_dev.csv`) carry `reference_heating_load_kw` and `expected_verdict` (green/yellow/red only). 2 hidden cases are judged. **No photos.** Fields are what a homeowner realistically knows; empty = not documented.
- Organiser: **"Some cases are deliberately contradictory."** Finding contradictions scores points (engine step 2b).
- Code quality and tests do not matter. The demo must not break.

## Judging and where we score

| Criterion | Pts | Our answer |
| --- | --- | --- |
| Technical execution & reliability | 25 | Cloud deploy, works without API (notes cache + keyword fallback), deterministic |
| Problem-solution fit & user value | 25 | Installer visit prep sheet, one-sentence homeowner reason, cost range |
| Explainability & uncertainty | 20 | Colour probabilities, p10-p90 ranges, contradictions with "which source we trusted and why", Rechenweg |
| Innovation & smart use of tech | 15 | LLM reads messy notes (with quotes), physics decides |
| Feasibility & scalability | 15 | ~1 API call per building (cached), same function scores any lead CSV, assumptions swap out, Phase 2 calibrates on real visits |

Scoring enum is green/yellow/red only, so always output `best_color`; uncertainty and contradictions are flags next to it.
Show the four key terms with tooltips: Heizlast, Vorlauftemperatur, JAZ, Ein-/Zweirohr.

## Priorities (build strictly in this order)

- **P0-a Scoring path**: `loader.py` → `engine.py` → `calibrate.py` → 📊 Evaluation tab.
  - Text fields (`building_notes`, `radiator_info`, `energy_carrier_detail`): numbers (radiator count, valves, litres, U-values) by regex. Facts (extra heat source, solar thermal, unused area, insulation work, renovation hints) by **LLM `NotesObs` as the main path**, with a quote per fact, cached in `data/notes_cache.json` (5 buildings = 5 calls). Keyword fallback only if cache and API are both missing (show "rule-based analysis").
  - **Monte Carlo is P0**: N=500, seed 0, vectorised numpy (see engine step 7).
  - Evaluation tab: 3 dev buildings vs reference (error %), leave-one-out, the 2 hidden buildings with ranges, plus `lead_score` and visit-type columns.
  - Every result has a **Rechenweg** expander: area × W/m² × k → heating load (consumption-based load shown beside it) → ΣΦ_n → required flow temperature → JAZ → cost, each step with its number and assumption, plus contradictions and which source we trusted.
  - Cut order inside P0-a if late (from the end): Rechenweg detail → leave-one-out table → secondary contradiction rules. Never cut LLM notes or Monte Carlo.
- **P0-b 🔧 Installer visit prep sheet**: built only from engine output (step 9). Building selector = the 5 loaded buildings + the current Homeowner house.
- **P0-c 🏠 Homeowner (dropdowns only)**: inputs → traffic light with probabilities, one-sentence reason, cost, flow-temperature scale (p10-p90 band), one "this would make it more accurate" hint.
- **P1**: bill and radiator photo extraction (per-mission schemas, merge, Demo-mode cache) → entropy-based next question.
- **P2**: CSV upload batch triage (rules only, 0 LLM calls), photo retake loop, Installer polish, exterior photo, degree-day method, log-mean numeric solve, optional photos.
- **Cut**: per-postcode design temperature lookup, fine-grained radiator lookup (3 sizes only).

## Timeline (10 h, adjust to the real deadline)

First thing on the day: get the submission deadline and pitch slot. Build time = deadline − opening/team formation − 1.5 h (freeze + pitch prep). If shorter than 10 h, cut P1 first.

| Time | Work |
| --- | --- |
| 0:00-0:30 | Open the data (CSV and JSON), fix field names, build `notes_cache.json` |
| 0:30-3:00 | P0-a, **secure the 2 hidden-building results here** |
| 3:00-4:00 | P0-b Installer (buffer if P0-a ran late) |
| 4:00-5:00 | P0-c Homeowner (dropdowns) |
| 5:00-7:30 | P1 (cut from the end) |
| 7:30-8:30 | Redeploy check, freeze caches, rehearse the happy path 3× |
| 8:30 | **Code freeze** |
| 8:30-10:00 | Pitch prep and rehearsal |

## Pre-event milestones (agent: check these first every session and tell the user the first open one)

- [x] M0 repo, venv, deps (`C:\dev\hp-ready`, private GitHub, pinned pandas<3, pyarrow<22, pillow<12 because Windows Smart App Control blocks newer wheels)
- [x] M1 eng review applied, radiator rating table sourced (Kermi/Buderus EN 442)
- [x] M1b dev data applied (area-age load, k=1.01, contradiction rules, U-value renovation hint, P0 Monte Carlo → dev 3/3)
- [ ] M2 **API check (required before the event, LLM notes are P0)**: user pastes `ANTHROPIC_API_KEY = "..."` into `.streamlit/secrets.toml` and Cloud Secrets; one real call with `claude-sonnet-5-5` succeeds. If it fails, read the error and check the model ID first.
- [x] M3 Cloud first deploy ("HP-Ready (setup)" shows). Still to do: Secrets with M2, record the URL here: `(fill in)`, **open the URL in an incognito window**; a private-repo app may require login, then switch Sharing to public.
- [ ] M4 demo photos (low priority, P1 only): one bill screenshot with name/address/customer number hidden, one large radiator photo at an angle with pipes, one wrong-object photo. Store in `samples/` (raw files are gitignored).
- [ ] M5 first 30 minutes on the day: deadline and pitch slot, data terms, **whether pre-written code is allowed** (via `/intake`). If not allowed: keep `app.py` as the empty shell, treat k=1.01, tables and rules as research notes, write code on the day, and cut P0-c and P1 first.

## Stack

- Python 3.11, Streamlit, Pydantic, pandas, numpy, Anthropic API. Model `claude-sonnet-5-5`.
- API key: `st.secrets["ANTHROPIC_API_KEY"]`, else environment variable. Never hard-code.
- Deploy: Streamlit Community Cloud (Python 3.11), keep a local fallback and a screen recording. Wake the Cloud app 10 minutes before the pitch.
- Data: `data/` is committed (anonymised, private repo; reconfirm terms on the day). Raw bills/photos in `samples/` are gitignored; commit only redacted copies with `git add -f`.

## Files (create no others)

- `schema.py`: Pydantic `House`, `Result`, `NotesObs`, photo schemas (`BillObs`, `RadiatorObs`, `ExteriorObs`), fixed constants, photo-mission texts.
- `loader.py`: CSV/JSON → `House` (+ reference dict for dev cases). Must run without photos.
- `engine.py`: physics, contradictions, Monte Carlo, traffic light, next question, installer brief.
- `calibrate.py`: fit k on the 3 dev cases (one parameter, geometric mean of log ratios), leave-one-out.
- `extract.py` (P1): photo/bill → `House` via per-mission tool-use schemas; resize to 1568 px JPEG before sending.
- `app.py`: Streamlit, tabs `🏠 Homeowner` / `🔧 Installer` / `📊 Evaluation`.
- `data/buildings_*.csv|json`, `data/notes_cache.json`; `samples/`; `docs/`; `requirements.txt`; `.streamlit/secrets.toml` (gitignored).

## Interface contract

```python
# schema.py
class House(BaseModel):                      # all value fields Optional
    confidence: dict[str, float] = {}       # field -> 0..1
    source: dict[str, str] = {}             # field -> data | dropdown | photo | bill | notes_llm | rule | prior
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

# calibrate.py
def fit(buildings) -> Params
def leave_one_out(buildings) -> pd.DataFrame

# extract.py (P1)
def extract(file_bytes: bytes, mime: str, mission: str) -> House
def merge(base: House, new: House) -> House                                # per-field source priority, confidence only breaks ties
```

`python engine.py` prints the 3 dev cases (expect B-01 green, B-03 yellow) and an example house with its Rechenweg (smoke check).

## Fixed assumptions (given by the challenge, do not change)

| Item | Value |
| --- | --- |
| Heat pump electricity | 0.26 €/kWh |
| Gas | 0.11 €/kWh |
| Heating oil | 1.70 €/L (≈10 kWh/L → 0.17 €/kWh) |
| JAZ underfloor | 4.0 |
| JAZ radiators ≤55 °C | 3.5 |
| JAZ radiators 55-60 °C | 2.8 |
| Radiators >60 °C | not in table → red (action needed) |

Gas heat ≈ 0.11/η ≈ 12.2 ct/kWh at η 0.9; worst HP case 0.26/2.8 ≈ 9.3 ct, so ≤60 °C always saves running cost. Break-even JAZ ≈ 2.1.

## Data mapping (code adapts to the data)

| CSV | House | Notes |
| --- | --- | --- |
| `construction_year` | `build_year` | |
| `floor_area_m2` | `living_area_m2` | rounded |
| `renovation_status` | `renovation` (unrenovated/partially/fully/None) | often empty |
| `heat_distribution` | `heat_distribution` (radiators/underfloor/mixed) | |
| `annual_consumption_kwh` | `annual_fuel_kwh` | |
| `energy_carrier` + `energy_carrier_detail` | `fuel_type` (gas/lpg/oil/district/electric) | "LPG"/"Flüssiggas" → lpg; litres → check against kWh |
| `radiator_info` | `radiator_count`, `valves_to_replace`, `hydraulic_balanced` | regex `(\d+)\s*radiators?`, `(\d+)\s*valves`; "balanced"/"abgeglichen" → True; "preset"/"voreingestellt" only → None + note "preset valves, balancing to check" |
| `pipe_system` | `pipe_system` (two_pipe/single_pipe) | `unknown` → None |
| `flow_temperature_c` | `current_flow_temp_c` | often empty |
| `persons_in_household` | `occupants` | |
| `hot_water_via_heating` | `dhw_by_boiler` | yes/no |
| `rooms` | `rooms` | radiator-count fallback |
| `building_notes` | `notes` + `NotesObs` | LLM facts with quotes, cached |
| `location` | `region` | "Munich area (82xxx)" → munich |
| `reference_heating_load_kw`, `expected_verdict` | reference dict | dev only |

`NotesObs` (facts only, each with a one-line quote `evidence`): `u_values` {windows, wall, roof, floor, basement}, `extra_heat_source` (wood_stove/tiled_stove/heat_pump/none), `extra_source_all_winter`, `solar_thermal_dhw`, `unheated_area_note`, `insulation_measures` (list), `glazing`.

Other `House` fields (dropdowns/photos): `building_type`, `monthly_advance_eur`, `boiler_condensing`, `radiator_size` (small/medium/large), `windows`, `roof_insulated`, `walls_insulated`, site flags `listed_building`, `outdoor_unit_space`, `flat_level_gas_heating`, bill raw values (`kwh_printed`, `m3`, `zustandszahl`, `brennwert`, `liters`, `period_start`, `period_end`).

## Result

- `best_color` (green/yellow/red, always set = colour of the Monte Carlo p50 flow temperature), `traffic_light` (adds `unclear`), `boundary` (max colour probability < 0.6), `reason` (one sentence for the homeowner), `reason_category` (temperature/insulation_first).
- `p_green`, `p_yellow`, `p_red`; `required_flow_temp_c` and `heat_load_kw` as p10/p50/p90; `jaz_bucket`; `cost_now_eur`, `cost_hp_eur`, `saving_eur`.
- `contradictions`: list of {what, sources, trusted, why}; `site_flags`.
- `confidence`, `lead_score`, `visit_type` (remote_quote/visit_with_parts/hold), `parts` {radiators_to_swap: (lo, mid, hi), valves, balancing: needed/check/None}, `installer_checklist`, `next_photo`.

## Engine (`engine.py`)

**0. Site flags are not red reasons.** Listed building, no outdoor-unit space, flat-level gas heating: keep the physics colour, add to `site_flags`, put at the top of the installer checklist, cap green at yellow. Red only if a mentor or the data says it is a hard stop.

**1. Fuel to heat (cost and cross-check).** Bill conversion is done here, never by the LLM: `kwh_printed`, else `m3 × zustandszahl × brennwert`, oil `litres × 10`, scaled to 365 days. Advance payment only: `monthly × 12 / price`, range −30 %..+10 %, low confidence.
`Q_heat = annual_fuel_kwh × η`. Gas bills are upper heating value (Hs): η condensing 0.88 / non-condensing 0.80 / unknown 0.84. Oil (10 kWh/L) is lower value (Hi): 0.95 / 0.85 / 0.9. LPG like gas, note "real LPG price may be higher". District heating and direct electric: η 1.0, current cost "price not provided".
`Q_space = Q_heat − Q_dhw`, `Q_dhw = 600 kWh × occupants` if `dhw_by_boiler`, halved with solar thermal.
`current_flow_temp_c` is shown, not used for the verdict; if our result is >10 K above it, log a contradiction.

**Required flow temperature** = supply water temperature that keeps 20 °C indoors with the existing radiators at the local design outdoor temperature (Auslegungsvorlauftemperatur). 55/60 °C are the challenge's JAZ bands, not our choice.

**2. Heating load (Heizlast): area × age is primary.** Consumption-based load needed 625-2,400 full-load hours across the dev cases, so it cannot be calibrated with one parameter.
`P_load = k × w(age, renovation) × heated_area`

| Built | Unrenovated/unknown W/m² | Partly/fully renovated W/m² |
| --- | --- | --- |
| ≤1977 | 130 | 80 |
| 1978-1994 | 85 | 70 |
| 1995-2001 | 60 | 55 |
| 2002-2015 | 50 | 50 |
| ≥2016 | 35 | 35 |

Source: German trade rules of thumb (BDH/VdZ, Viessmann tables); show "first estimate, not a DIN EN 12831 calculation". Monte Carlo ±20 %.
Use the renovated column when the renovation status is empty but (a) notes name insulation work, or (b) the wall U-value is below 0.7 × the age reference (≤1977 1.0, 1978-94 0.6, 1995-2001 0.5, 2002-15 0.35, ≥2016 0.24 W/m²K, estimated). Log it as a contradiction ("no renovation documented vs better-than-code U-values").
Unused area in the notes: heated area × 0.85 (Monte Carlo 0.7-1.0); keep the radiator count and add "radiators/valves on the unused floor" to the installer checklist.
**k = 1.01** (only calibrated parameter, recompute on the day with `calibrate.py`). Leave-one-out error B-01 +20 %, B-02 −9 %, B-03 −8 %.
Consumption-based load `Q_space / 2000 h` is a cross-check only.

**2b. Contradiction checks** (engine decides; the LLM only supplies facts). Each hit adds {what, sources, trusted, why} and widens that value's range.
- Consumption load vs area-age load differs by more than ±40 % → trust area-age; cause from notes (extra heat source all winter → consumption too low; unused area → area too high; else "habits or record error, installer to check").
- Extra heat source all winter → consumption is a lower bound only.
- Unused area → area × 0.85.
- No renovation recorded but insulation work or better-than-code U-values → renovated column.
- DHW via boiler and solar thermal → halve DHW.
- Carrier gas but detail LPG → correct to lpg.
- Litres and kWh both present and differ by more than ±15 %.
- Our flow temperature >10 K above `current_flow_temp_c`.
- Old building with underfloor heating → likely retrofit, log only.
Dev cases: B-01 (10,000 kWh vs ~11 kW area load, −74 %; gas/LPG; U-values), B-02 (wood stove all winter, solar thermal, −31 % so caught by the wood-stove rule, not the ±40 % rule), B-03 (unused top floor).

**3. Radiator output (DIN EN 442).**
Underfloor → 35-40 °C, JAZ 4.0. Radiators: `Φ = Φ_n × (ΔT/50)^1.3`, Φ_n at 75/65/20 °C.
Approximation: `ΔT_need = 50 × (P_load / ΣΦ_n)^(1/1.3)`, `T_flow = 20 + ΔT_need + spread/2`, spread 8 K. Single-pipe +5..10 K.

| Size | Typical | Φ_n | Monte Carlo |
| --- | --- | --- | --- |
| small | Type 11, 600 × ~800 | 0.7 kW | 0.5-0.9 |
| medium | Type 22, 600 × 800-1000 | 1.5 kW | 1.3-1.7 |
| large | Type 22 600 × 1200 or Type 33 600 × 1000-1200 | 2.2 kW | 2.0-2.7 |

Source: Kermi therm-x2 Type 22 600×800 1,333 W, 600×1000 1,666 W, 600×1200 1,999 W; Type 33 600×1000 2,236 W, 600×1200 2,683 W; Buderus Type 22 600×1000 1,688 W (energiefluss24.de). Small is estimated (one panel ≈ half of Type 22).
Radiator count: data → `rooms × 1.3` → `area / 18`. Unknown size → Monte Carlo draws small/medium/large with 0.25/0.5/0.25 (estimated); point estimate uses medium.
Display clip: above 70 °C show ">70 °C" (red, temperature).
Dev check (k 1.01): point estimate B-01 54.0 °C green ✅, B-03 58.2 °C yellow ✅. Monte Carlo B-01 p50 54.6 °C (G 0.52 / Y 0.20 / R 0.28), B-03 p50 58.8 °C (G 0.33 / Y 0.23 / R 0.44). 3/3 with one parameter.

**4. JAZ band.** Underfloor 4.0 / ≤55 3.5 / 55-60 2.8 / >60 none.

**5. Cost.** `cost_now = annual_fuel_kwh × price`, `cost_hp = Q_heat / JAZ × 0.26`, `saving = cost_now − cost_hp`.

**6. Traffic light.** Green: underfloor or ≤55 °C. Yellow: 55-60 °C (or green capped by site flags). Red: >60 °C. Unclear: area/age or radiator count missing (a count from any fallback counts as present). Red needs more evidence than green: high demand without radiator info → unclear, not red.

**6b. Path to yellow (physics only, no prices).** Radiator output to add: `ΣΦ_n,needed(55 °C) − ΣΦ_n` kW, or heat-loss reduction needed: `1 − P_allowed(55 °C) / P_load`. Do not say which insulation achieves it.

**7. Uncertainty (Monte Carlo, P0).** N=500, seed 0, numpy vectors (no per-sample Pydantic objects), cached with `st.cache_data`. Draw: W/m² × U(0.8, 1.2); radiator size as above × U(0.85, 1.15); unused area × U(0.7, 1.0); contradicted values widened. Output colour probabilities and p10/p50/p90.
`best_color` = colour of the p50 flow temperature (not the most frequent colour: the radiator-size tail pushes the mode toward red, B-03 shows this). Max probability < 0.6 → `boundary`, show the top two colours with probabilities ("uncertain: 🟢/🟡").

**8. Next question.** P0: fixed order of empty fields (radiator size > fuel amount > build year). P1: the unknown whose fixing reduces colour entropy most, divided by effort.

**9. Installer visit prep (`installer_brief`).**
Visit type, first match wins:
0. `boundary` → visit with parts (decide on site)
1. red → hold + path to yellow + keep the lead
2. unclear → visit with parts + one photo request
3. yellow, any contradiction, or green with confidence < 0.7 → visit with parts
4. green, no contradictions, confidence ≥ 0.7 → remote quote

`confidence` = mean of 5 core fields (area, age, fuel amount, radiator count, radiator size); data value 0.9, regex fallback 0.5, dropdown 0.8, missing/unknown 0.3; −0.1 per contradiction; unclear caps at 0.5; floor 0.1. `lead_score = (p_green + p_yellow) × confidence`.
Parts (physics only): radiators to swap ≈ `ceil(ΣΦ_n shortfall at 55 °C / (2.2 − current size))`, unknown size = medium; shortfall ≤ 0 → 0; already large and short → "swapping is not enough, add radiators or check per room"; underfloor → n/a (attached radiators "check"). Range from Monte Carlo. Valves to replace from data. Hydraulic balancing: True → "check", otherwise "needed".
Checklist: one line per contradiction ("check X on site"), site flags, pipe system if unknown, always outdoor-unit position and noise distance, electrical supply, hydraulic balancing.

## Photo inputs (P1)

Missions: (1) bill in any form (photo, PDF, app screenshot) → `BillObs` raw numbers only; (2) largest living-room radiator, at an angle, with pipes → size, type, pipe system; (3) exterior → building type, age range, windows. Optional: underfloor manifold, boiler front, outdoor-unit spot.
`merge` priority: fuel → bill > dropdown; radiator and pipes → photo > dropdown; age, area, occupants → dropdown > photo; else photo > dropdown > prior. LLM confidence only breaks ties within one source.
Retake loop (P2): per-field `missing_reason`, max 2 retries, then fall back to dropdown/prior.

## Screens (`app.py`)

- 📊 Evaluation: 5 buildings; dev cases beside their references; hidden cases with ranges; contradictions; "facts the AI found in the notes + quotes"; `lead_score` and visit type. **Pitch uses this screen.**
- 🔧 Installer: building selector → one prep sheet: visit-type badge, parts list, on-site checklist, load and flow temperature (p10-p90), missing fields.
- 🏠 Homeowner: dropdowns → traffic light (two colours when uncertain) + reason → flow-temperature scale 35-70 °C with p10-p90 band → cost → one improvement hint. P1 adds `st.file_uploader` (rear camera on phones) and `st.camera_input`.
- Demo-mode toggle (P1): use `samples/cached_extract.json` instead of the LLM.

## Working rules

- One Claude session, build order: schema → loader (+ notes cache) → engine → calibrate → Evaluation → installer_brief + Installer → Homeowner → (P1) extract → photo UI. If a teammate joins, split with git worktrees, never two sessions in one folder.
- After each passing `/check`, commit only the files you changed (never `git add -A`). Never work 30 min without a commit; roll back to the last commit if broken.
- `/hp-review` after P0-a, after P0-b and before the freeze. New information on the day goes through `/intake`.
- Keep function signatures; add new functions if needed. Wrap every LLM and file call in try/except, fall back to cache, show it small on screen.
- Streamlit reruns the script on every click: cache `parse_notes` and `extract` by content hash, keep the house in `st.session_state`, never call the API twice for the same input.
- Store extracted numbers only; never keep raw bills, names or addresses.
- One feature at a time, then `streamlit run app.py` on the happy path. Short explanations, straight to code.

## Demo (P0 only, default)

1. 📊 Evaluation: dev accuracy and leave-one-out → the 2 hidden buildings → B-01 contradiction ("bill says 3 kW, area and age say ~11 kW, −74 %, trusting area-age; installer to check habits/LPG") → AI-found facts with quotes (B-02 "A wood stove is used all winter").
2. 🔧 Installer: B-03 → visit with parts: about N radiators, 12 valves, balancing, check the unused top floor.
3. 🏠 Homeowner: persona (1972 terraced house, 140 m², partly renovated, 3 people, gas 18,000 kWh) by dropdowns → probabilities, reason, scale, cost. Empty the build year → unclear + one hint.
4. Rechenweg once; same input twice → same result.
P1 replaces step 3 with bill screenshot → kWh → radiator photo → band narrows; optional live radiator photo, Demo-mode cache if it fails. Backup: screen recording.

## Pitch lines

- "In Germany, the scarcest resource isn't energy. It's the installer's time."
- "The LLM reads. Physics decides. Nothing is made up."
- "Real data contradicts itself. We show which source we trusted and why."
- "We don't cancel site visits. We make them short and precise."
- Phase 2: calibrate on nuuEnergy's real visit outcomes.

## Do not

- Login, database server, test code, refactoring.
- Let the LLM output verdicts, colours or numbers.
- Output prices, installation cost or subsidies beyond the fixed assumptions.
- Generate fake buildings or visits.
- Add features in the last hour (code freeze).

## On-site information protocol (whenever the user pastes something new)

1. Classify: deliverable/judging, data format, reference values, domain fact, constraint (time/team/rules), feedback.
2. Three-line plain summary (in Korean).
3. Conflicts: name the sections of this file it touches, or "no conflict".
4. Minimal edit proposal, changed lines only. Touch principles 1-7 only if the new info demands it.
5. Priority impact on P0/P1/P2/timeline; when time shrinks cut P2, then P1.
6. After the user says "ㅇㅋ", edit this file, add one line to the decision log in `docs/DESIGN.md` (with time), tick open questions.
7. Explain unfamiliar terms in one line using `docs/DESIGN.md` → Domain primer.

Playbook: data file → print all columns, mapping table, adapt `schema.py`; reference = heating load → refit k; reference = flow temperature → refit the radiator table scale; verdict only → keep 55/60 bands, refit the radiator scale; cost/JAZ → check our cost formula matches theirs. Judging/rule notice → update judging table and timeline; "code must be written during the event" → tell the user what exists and wait. Mentor says a domain fact → engine first; a preference → priorities only. Screenshot only → read it, say what is unreadable.

## Open questions

- [ ] Submission deadline and pitch slot
- [ ] **How did nuuEnergy compute the reference heating load?** (rule-of-thumb area/age, U-value DIN 12831, consumption) → first question to the mentor; refit k and the table accordingly
- [ ] JSON format of the hidden data
- [ ] Team roles (team so far: Junwoo `jackylee0503` + `cybeuu`, write access since 2026-10-23; split work with git worktrees, never two sessions in one folder)
- [ ] Is pre-written code allowed
- [x] Data terms (anonymised, private repo OK; reconfirm), reference format, CSV fields, location granularity, photos in eval data (none)
