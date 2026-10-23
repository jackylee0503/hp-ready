# HP-Ready Triage (WATT THE HACK Munich, nuuEnergy challenge #4)

Build spec for the coding agent. The organiser's own pages (mission, technical guardrails, data, single/two-pipe background, deliverables, judging) are in `docs/challenge/`; they win over everything else and this file implements them. Background, rationale and the decision history live in `docs/DESIGN.md`; the pitch lives in `docs/PITCH.md`; the original Korean plan is `docs/CLAUDE.ko.md` (outdated, reference only, this file wins on conflict).

**Talk to the user (Junwoo) in Korean.** He is a first-time hackathon participant with no domain or statistics background. Explain in plain words, do the interpretation yourself, never hand it back to him.

## One line

Give a **homeowner** an honest first answer in under three minutes, from what they already have (energy bill, a few building facts, photos): is the home heat-pump ready (green / yellow / red) with a reason they understand, and **what is still open** that a technician has to check on site. The same result tells nuuEnergy how sure we are, what contradicts itself in the data and what the installer should bring.
The LLM only **reads** (free-text notes, later bills and photos). A **physics engine** decides. Unknowns become ranges and probabilities, never invented numbers.

## Core principles (never break)

1. **The LLM is a parser.** It fills schema fields only. No verdicts, recommendations or arithmetic.
2. **Unknown stays empty.** Unsure field = null. Every field carries a confidence (0-1).
3. **`engine.py` decides.** Physics + Monte Carlo, calibrated with one parameter on the 3 dev buildings.
4. **Ask only what matters.** At most one follow-up request: the unknown that moves the verdict most.
5. **Schema is the contract.** Fields are defined once, in `schema.py`.
6. **No made-up numbers.** Prices and JAZ come only from the fixed assumptions below. Never output installation cost or subsidy amounts ("installer quote needed").
7. **Red is earned.** Red means an obstacle in the data we have (organiser: "insufficient evidence for a positive assessment"), never just missing data; missing data is yellow "can't tell yet". Every red carries a reason category and a "this gets you to yellow" path.

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
- **P0-b 🏠 Homeowner answer card (dropdowns only)**: the organiser's core user. Inputs → traffic light with probabilities, one-sentence reason ("obstacle" or "can't tell yet" spelled out), **"What's still open"** list (`open_checks`, step 6c), cost, flow-temperature scale (p10-p90 band), one "this would make it more accurate" hint. The same card is shown for each of the 5 loaded buildings. Time it: inputs to answer in under 3 minutes.
- **P0-c 🔧 Installer visit prep sheet**: built only from engine output (step 9). Building selector = the 5 loaded buildings + the current Homeowner house. If time runs out, cut P0-c before P0-b.
- **P1**: bill extraction (official bonus: consumption, energy carrier, costs) and radiator photo extraction (per-mission schemas, merge, Demo-mode cache) → entropy-based next question.
- **P2**: outdoor-unit spot from an exterior photo (official bonus "installation-risk detection"), CSV upload batch triage (rules only, 0 LLM calls), photo retake loop, Installer polish, degree-day method, log-mean numeric solve, optional photos.
- **Cut**: per-postcode design temperature lookup, fine-grained radiator lookup (3 sizes only).

## Timeline (10 h, adjust to the real deadline)

First thing on the day: get the submission deadline and pitch slot. Build time = deadline − opening/team formation − 1.5 h (freeze + pitch prep). If shorter than 10 h, cut P1 first.

| Time | Work |
| --- | --- |
| 0:00-0:30 | Data is already in `data/`: check the organiser files did not change on the day, build or refresh `notes_cache.json` |
| 0:30-3:00 | P0-a, **secure the B-04 / B-05 results here** |
| 3:00-4:00 | P0-b Homeowner answer card (buffer if P0-a ran late) |
| 4:00-5:00 | P0-c Installer prep sheet |
| 5:00-7:30 | P1 (cut from the end) |
| 7:30-8:30 | Local run check (+ Cloud link if used), freeze caches, rehearse the happy path 3× and time the homeowner flow (< 3 min) |
| 8:30 | **Code freeze** |
| 8:30-10:00 | Pitch prep and rehearsal |

## Pre-event milestones (agent: check these first every session and tell the user the first open one)

- [x] M0 repo, venv, deps (`C:\dev\hp-ready`, private GitHub, pinned pandas<3, pyarrow<22, pillow<12 because Windows Smart App Control blocks newer wheels)
- [x] M1 eng review applied, radiator rating table sourced (Kermi/Buderus EN 442)
- [x] M1b dev data applied (area-age load, k=1.01, contradiction rules, U-value renovation hint, P0 Monte Carlo → dev 3/3)
- [x] M1c organiser pages and all 5 buildings in the repo (`docs/challenge/`, `data/`), spec aligned to them (2026-10-23 evening, see `docs/DESIGN.md` decision log).
- [x] M2 (done 2026-10-23 22:30, user confirmed the key works) **API check (required before the event, LLM notes are P0)**: user pastes `ANTHROPIC_API_KEY = "..."` into `.streamlit/secrets.toml` (and Cloud Secrets if Cloud is used); one real call with `claude-sonnet-5-5` succeeds. If it fails, read the error and check the model ID first. After M2, `data/notes_cache.json` for all 5 buildings can be built tonight (their notes are public, 5 calls); if pre-written work turns out not to be allowed (M5), rebuild it on the day.
- [x] M3 Cloud first deploy ("HP-Ready (setup)" shows). Now optional (organiser: runs locally in a browser): if used, Secrets with M2, record the URL here: `(fill in)`, open it in an incognito window; a private-repo app may require login, then switch Sharing to public.
- [ ] M4 demo inputs (low priority, P1 only): bill = the public SWM sample bill (link in "Photo inputs") or your own with name/address/customer number hidden; pipe-system test = the 5 labelled organiser photos in `data/pipe_photos/`; still to take: one large radiator photo at an angle with pipes, one wrong-object photo. Own photos go in `samples/` (raw files are gitignored).
- [ ] M5 first 30 minutes on the day: deadline and pitch slot, data terms, **whether pre-written code is allowed** (via `/intake`). If not allowed: keep `app.py` as the empty shell, treat k=1.01, tables and rules as research notes, write code on the day, and cut P0-c and P1 first.

## Stack

- Python 3.11, Streamlit, Pydantic, pandas, numpy, Anthropic API. Model `claude-sonnet-5-5`.
- API key: `st.secrets["ANTHROPIC_API_KEY"]`, else environment variable. Never hard-code.
- Run: locally with `streamlit run app.py` in a standard browser is the primary demo path (organiser: "runs locally in a standard browser"). Streamlit Community Cloud (Python 3.11) is an optional share link and backup; if used, wake it 10 minutes before the pitch. Keep a screen recording.
- Data: `data/` is committed (anonymised, private repo; reconfirm terms on the day). Raw bills/photos in `samples/` are gitignored; commit only redacted copies with `git add -f`.

## Files (create no others)

- `schema.py`: Pydantic `House`, `Result`, `NotesObs`, photo schemas (`BillObs`, `RadiatorObs`, `ExteriorObs`), fixed constants, photo-mission texts.
- `loader.py`: CSV/JSON → `House` (+ reference dict for dev cases). Must run without photos. Every set exists as both CSV and JSON: read the JSON (typed booleans and nulls), CSV only if the JSON is missing, one row per `building_id` (5 buildings, not 10).
- `engine.py`: physics, contradictions, Monte Carlo, traffic light, next question, installer brief.
- `calibrate.py`: fit k on the 3 dev cases (one parameter, geometric mean of log ratios), leave-one-out.
- `extract.py` (P1): photo/bill → `House` via per-mission tool-use schemas; resize to 1568 px JPEG before sending.
- `app.py`: Streamlit, tabs `🏠 Homeowner` / `📊 Evaluation` / `🔧 Installer`.
- `data/buildings_dev.*` and `data/buildings_eval.*` (organiser files, do not edit), `data/notes_cache.json`, `data/pipe_photos/` (organiser photos + `labels.json`); `samples/`; `docs/` (`docs/challenge/` = organiser pages, do not edit); `requirements.txt`; `.streamlit/secrets.toml` (gitignored).

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

Other `House` fields (dropdowns/photos): `building_type`, `monthly_advance_eur`, `boiler_condensing`, `radiator_size` (small/medium/large), `windows`, `roof_insulated`, `walls_insulated`, site flags `listed_building`, `outdoor_unit_space`, `flat_level_gas_heating`, bill raw values (`kwh_printed`, `m3`, `zustandszahl`, `brennwert`, `liters`, `period_start`, `period_end`, `bill_carrier` as printed, `bill_total_eur` for display only).

## Result

- `best_color` (green/yellow/red, always set, rule in step 6), `traffic_light` (adds `unclear`), `verdict_basis` (`likely_suitable` / `checks_remain` / `cannot_tell_yet` / `obstacle`, the organiser's colour meanings), `boundary` (max colour probability < 0.6), `reason` (one sentence for the homeowner), `reason_category` (temperature/insulation_first/pipe_system).
- `open_checks`: list of {item, why} in homeowner words: what we could not tell from the data and what a technician must check on site (step 6c). `hints`: insulation hint above 75 W/m² (step 2), myth-buster line.
- `p_green`, `p_yellow`, `p_red`; `required_flow_temp_c` and `heat_load_kw` as p10/p50/p90; `heat_load_bill_kw` (bill method, low/mid/high over 1,800 / 2,000 / 2,100 full-load hours); `specific_load_w_m2`; `jaz_bucket`; `cost_now_eur`, `cost_hp_eur`, `saving_eur`.
- `contradictions`: list of {what, sources, trusted, why}; `site_flags`.
- `confidence`, `lead_score`, `visit_type` (remote_quote/visit_with_parts/hold), `parts` {radiators_to_swap: (lo, mid, hi), valves, balancing: needed/check/None}, `installer_checklist`, `next_photo`.

## Engine (`engine.py`)

**0. Site flags are not red reasons.** Listed building, no outdoor-unit space, flat-level gas heating: keep the physics colour, add to `site_flags`, put at the top of the installer checklist, cap green at yellow. Red only if a mentor or the data says it is a hard stop.

**1. Fuel to heat (cost and cross-check).** Organiser method (`03_technical_guardrails.md` §1b). Bill conversion is done here, never by the LLM: `kwh_printed`, else `m3 × zustandszahl × brennwert` (either factor missing → `m3 × 10`, organiser value), oil `litres × 10`, scaled to 365 days. Advance payment only: `monthly × 12 / price`, range −30 %..+10 %, low confidence.
`Q_heat = annual_fuel_kwh × η` (useful heat). **η = 0.88 by default** (organiser: the old boiler loses about 12 %), so our numbers stay comparable with every other team. Only when the boiler type is known (dropdown or photo): gas condensing 0.88 / non-condensing 0.80, oil condensing 0.95 / non-condensing 0.85 (Hs/Hi basis, say so in the Rechenweg). LPG like gas, note "real LPG price may be higher". District heating and direct electric: η 1.0, current cost "price not provided".
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
Unused area in the notes: heated area × 0.85 (Monte Carlo 0.7-1.0); keep the radiator count and add "radiators/valves on the unused floor" to the installer checklist.
**k = 1.01** (only calibrated parameter, recompute on the day with `calibrate.py`). Leave-one-out error B-01 +20 %, B-02 −9 %, B-03 −8 %.
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
| 🟡 yellow | (same) | `cannot_tell_yet` | `unclear`: area/age or radiator count missing (a count from any fallback counts as present). Never red. |
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
Checklist: one line per contradiction ("check X on site"), site flags, pipe system if unknown, single-pipe loop checks (step 3b), then always the organiser's technician list (`03_technical_guardrails.md`): exact heating load (DIN EN 12831) and room-by-room radiator sizing, electrical capacity and meter cabinet, hydraulics and balancing, outdoor-unit position, sound distance and permits.

## Photo inputs (P1)

Missions: (1) bill in any form (photo, PDF, app screenshot) → `BillObs` raw numbers only (official bonus: consumption, energy carrier, costs); (2) largest living-room radiator, at an angle, with pipes → size, type, pipe system; (3) exterior → building type, age range, windows, outdoor-unit spot (official bonus, P2). Optional: underfloor manifold, boiler front.
Pipe-system cues for mission 2 (organiser table): one pipe along the wall or skirting, tapped at each radiator → single-pipe; H-block with an extra adjustable side port (bypass) → single-pipe; valve at the top, separate return at the bottom, two separate pipes → two-pipe; H-block without side port → two-pipe likely; one bottom connection or bathroom multiblock → usually unknown. The system belongs to the building, not one radiator. Unsure → `unknown` with a reason, never a guess. Test set: `data/pipe_photos/labels.json` (07 must come back unknown).
Demo bill without privacy risk: the public Stadtwerke München sample bill (annual kWh on page 1), https://www.swm.de/dam/doc/kundenservice/rechnung/musterrechnung-erklaerung.pdf
`merge` priority: fuel → bill > dropdown; radiator and pipes → photo > dropdown; age, area, occupants → dropdown > photo; else photo > dropdown > prior. LLM confidence only breaks ties within one source.
Retake loop (P2): per-field `missing_reason`, max 2 retries, then fall back to dropdown/prior.

## Screens (`app.py`)

- 🏠 Homeowner (first tab): dropdowns → traffic light (two colours when uncertain) + reason, with "obstacle" or "can't tell yet" spelled out → **What's still open** (`open_checks`) → flow-temperature scale 35-70 °C with the p10-p90 band and marks at 45 °C (ideal), 55 °C (efficient), 60 °C (works, costs more) → cost → one improvement hint (plus the insulation hint above 75 W/m²). Where it fits, one myth-buster line: underfloor heating and a full renovation are not required. P1 adds `st.file_uploader` (bill PDF or screenshot, rear camera on phones) and `st.camera_input`.
- 📊 Evaluation: 5 buildings; dev cases beside their references; **B-04 and B-05 with ranges and their answer card** (the deliverable); both heating-load methods side by side; contradictions; "facts the AI found in the notes + quotes"; `lead_score` and visit type. **The pitch shows the evaluation results here.**
- 🔧 Installer: building selector → one prep sheet: visit-type badge, parts list, on-site checklist, load and flow temperature (p10-p90), missing fields.
- Demo-mode toggle (P1): use `samples/cached_extract.json` instead of the LLM.

## Working rules

- One Claude session, build order: schema → loader (+ notes cache) → engine → calibrate → Evaluation → Homeowner answer card → installer_brief + Installer → (P1) extract → photo UI. If a teammate joins, split with git worktrees, never two sessions in one folder.
- After each passing `/check`, commit only the files you changed (never `git add -A`). Never work 30 min without a commit; roll back to the last commit if broken.
- `/hp-review` after P0-a, after P0-b and before the freeze. New information on the day goes through `/intake`.
- Keep function signatures; add new functions if needed. Wrap every LLM and file call in try/except, fall back to cache, show it small on screen.
- Streamlit reruns the script on every click: cache `parse_notes` and `extract` by content hash, keep the house in `st.session_state`, never call the API twice for the same input.
- Store extracted numbers only; never keep raw bills, names or addresses.
- One feature at a time, then `streamlit run app.py` on the happy path. Short explanations, straight to code.

## Demo (P0 only, default)

1. 🏠 Homeowner: the homeowner's question first. Persona (1972 terraced house, 140 m², partly renovated, 3 people, gas 18,000 kWh) by dropdowns, well under 3 minutes → colour with probabilities, reason, what's still open, scale, cost. Empty the build year → yellow "can't tell yet" + one hint (missing data is not red).
2. 📊 Evaluation: dev accuracy and leave-one-out → **B-04 and B-05 results** → B-05 contradiction (125 m² but 14 rooms and a bill +76 % above the area-age load; we trust area-age, widen the range and ask "is all heated area included?") → B-01 contradiction (bill ~2.4 kW vs area and age ~11 kW, −78 %; trusting area-age; installer to check habits/LPG) → AI-found facts with quotes (B-02 "A wood stove is used all winter").
3. 🔧 Installer: B-04 → single-pipe, red with a path to yellow and the loop checks; or B-03 → visit with parts: about N radiators, 12 valves, balancing, check the unused top floor.
4. Rechenweg once; same input twice → same result.
P1 replaces the dropdown part of step 1 with bill screenshot → kWh → radiator photo → band narrows; optional live radiator photo, Demo-mode cache if it fails. Backup: screen recording.

## Pitch lines

- "'Would a heat pump even work in my home?' Today only a technician's visit answers that. We answer it in under three minutes, and we say what we can't tell."
- "Missing data isn't a no. We say 'can't tell yet' and name the one thing that would settle it."
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
- [x] Evaluation data format: same fields as dev without the two reference columns; inputs are public in `data/buildings_eval.*`
- [ ] Deliverables page says "3 evaluation buildings", the data and the one-pager say 2 → ask on the day, plan for 2
- [ ] Does the jury compare the heating load (kW) for B-04/B-05 as well as the colour? (their hidden "reference values" include both) → decides how big the load range is on screen
- [ ] Team roles (team so far: Junwoo `jackylee0503` + `cybeuu`, write access since 2026-10-23; split work with git worktrees, never two sessions in one folder)
- [ ] Is pre-written code allowed
- [x] Data terms (anonymised, private repo OK; reconfirm), reference format, CSV fields, location granularity, photos in eval data (none)
