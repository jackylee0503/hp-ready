# Engine Lane Implementation Plan (owner: potatohater8)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `engine.py` + `calibrate.py`: take a `House`, return a fully filled `Result` (traffic light, probabilities, ranges, contradictions, open checks, installer prep), deterministic, calibrated with one parameter `k` on the 3 dev buildings.

**Architecture:** One physics chain per house (CLAUDE.md "Engine", steps 0-9): fuel → heat, area × age heating load, radiator output → required flow temperature, JAZ and cost, traffic light. Uncertainty by a vectorised numpy Monte Carlo (N=500, seed 0) over the same chain. Every step appends a `Step` to `Result.trace` (the Rechenweg shown in the app).

**Tech Stack:** Python 3.11, numpy, pandas, Pydantic models from `schema.py`.

**Read first:** `CLAUDE.md` sections "Invariants", "Current implementation", "Fixed assumptions", "Result", "Engine" (the spec this plan implements), `docs/TEAM_GIT.md` (git), `schema.py` (all types and constants). Organiser rules: `docs/challenge/03_technical_guardrails.md`, `05_single_vs_two_pipe.md`.

**You own:** `engine.py`, `calibrate.py`. **Don't edit** `schema.py` (field names are frozen; ask Junwoo for new fields), `loader.py`, `extract.py`, `app.py`. You may change the physics if you know better, but keep the function signatures and fill the `Result` fields listed in Task 12.

**Project rules:** no test files (verify with `python engine.py`), no new code files, commit only your files (`git add engine.py calibrate.py`), never `git add -A`, commit small and often on branch `engine`, merge into `main` every 1-2 hours (`docs/TEAM_GIT.md`). No made-up numbers: prices and JAZ only from `schema.py` constants; never output installation cost or subsidies.

---

## Contract

```python
# engine.py
def evaluate(h: House, p: Params = DEFAULT, n: int = 500, seed: int = 0) -> Result   # deterministic
def installer_brief(h: House, r: Result) -> Result      # fills visit_type, parts, installer_checklist, lead_score, next_step
def next_question(h: House) -> str | None               # P0: fixed order

# calibrate.py
def fit(buildings) -> Params                            # buildings = loader.load_buildings()
def leave_one_out(buildings) -> pd.DataFrame            # columns: building_id, error_pct (+ anything else)
```

`buildings` is a list of `(building_id, House, reference)`; `reference` is `{"heating_load_kw": float, "verdict": "green"|"yellow"|"red"}` for B-01..B-03 and `None` for B-04, B-05.

**Inputs you can rely on (`House`):** `build_year`, `living_area_m2`, `renovation` (None = unknown), `heat_distribution`, `rooms`, `occupants`, `fuel_type`, `dhw_by_boiler`, `radiator_count`, `radiator_size` (None = unknown), `valves_to_replace`, `hydraulic_balanced`, `pipe_system` (None = unknown), `current_flow_temp_c`, `boiler_condensing`, site flags, `notes_obs` (`extra_heat_source`, `extra_source_all_winter`, `solar_thermal_dhw`, `unheated_area_note`, `insulation_measures` (`[]` = explicitly none), `u_values` dict), `data_notes`, `conflicts`, plus `source` / `confidence` per field.

**Fuel precedence (agreed, step 1):** bill raw values when any is present (`kwh_printed`, else `m3 × zustandszahl × brennwert` (either factor missing → `m3 × 10`), oil `liters × 10`, scaled to 365 days with `period_start`/`period_end`) → `annual_fuel_kwh` → `annual_fuel_liters × 10` → `monthly_advance_eur × 12 / price` (range −30 %..+10 %, low confidence). `annual_*` only ever hold per-year values.

**Expected numbers (k = 1.01, η 0.88, DHW 1,000 kWh/person; use these to check yourself):**

| | W/m² column | Area-age load | Bill load (Q_space / 2,000 h) | Bill vs area | Colour |
| --- | --- | --- | --- | --- | --- |
| B-01 2001, 195 m², LPG 10,000 kWh, 4 people, 14 radiators | 55 (partially: wall U 0.21 < 0.7 × 0.5) | 10.8 kW | 2.4 kW | −78 % → flag | green (point 54.0 °C; MC p50 54.6, G .52 / Y .20 / R .28) |
| B-02 2005, 180 m², gas 15,500, underfloor, wood stove, solar | 50 | 9.1 kW | 6.1 kW | −33 % (wood-stove rule) | green (underfloor) |
| B-03 1970, 200 m², oil 40,000, partially, 15 radiators, top floor unused | 80, area × 0.85 | 13.7 kW | 16.6 kW | +21 %, no flag | yellow (point 58.2 °C; MC p50 58.8, G .33 / Y .23 / R .44) |
| B-04 1987, 160 m², oil 25,000, 12 radiators, single-pipe | 85 | 13.7 kW | 9.5 kW | −31 % | never green (single-pipe cap) |
| B-05 2006, 125 m², gas 27,000, mixed (8 radiators, 14 rooms), solar | 50 | 6.3 kW | 11.1 kW | +76 % → flag; 14 rooms in 125 m² | from the radiator circuit |

References: B-01 9.6 kW green, B-02 9.7 kW green, B-03 14.5 kW yellow. Leave-one-out errors about +20 % / −9 % / −8 %.

---

### Task 0: Stub on `main` (first 30 minutes)

**Files:** Create `engine.py`, `calibrate.py`

- [ ] **Step 1: Set up**

```bash
git clone https://github.com/jackylee0503/hp-ready.git && cd hp-ready
python -m venv .venv
.venv\Scripts\activate            # Mac/Linux: source .venv/bin/activate
pip install -r requirements.txt
```

- [ ] **Step 2: Write the stub `engine.py`**

```python
"""Physics engine: House → Result (CLAUDE.md "Engine"). Owner: potatohater8."""
from __future__ import annotations

from schema import DEFAULT, House, Params, Result, Step


def evaluate(h: House, p: Params = DEFAULT, n: int = 500, seed: int = 0) -> Result:
    return Result(building_id=h.building_id, reason="Engine stub: no physics yet.",
                  trace=[Step(label="stub", value="–", assumption="engine not built yet")])


def installer_brief(h: House, r: Result) -> Result:
    return r


def next_question(h: House) -> str | None:
    return None


def _print(bid: str, h: House, ref, r: Result):
    f = r.required_flow_temp_c
    print(f"{bid} {r.best_color:6} {r.verdict_basis:16} flow p50={f.p50} ({f.p10}-{f.p90}) "
          f"load={r.heat_load_kw.p50} bill={r.heat_load_bill_kw.p50} G/Y/R={r.p_green:.2f}/{r.p_yellow:.2f}/{r.p_red:.2f} "
          f"ref={ref}")
    for c in r.contradictions:
        print(f"    ! {c.what} → trusted {c.trusted}")


if __name__ == "__main__":
    try:
        from loader import load_buildings
        buildings = load_buildings(use_llm=False)
    except ImportError:
        raise SystemExit("loader.py is not on main yet: git pull origin main (Junwoo pushes it in the first hour)")
    for bid, h, ref in buildings:
        _print(bid, h, ref, evaluate(h))
    r = evaluate(buildings[0][1])
    print("\nRechenweg", buildings[0][0])
    for s in r.trace:
        print(f"  {s.label}: {s.value}" + (f"  [{s.assumption}]" if s.assumption else ""))
    assert evaluate(buildings[0][1]).model_dump() == r.model_dump(), "not deterministic"
```

- [ ] **Step 3: Write the stub `calibrate.py`**

```python
"""Fit k on the 3 dev buildings (one parameter, geometric mean of log ratios) + leave-one-out. Owner: potatohater8."""
from __future__ import annotations

import pandas as pd

from schema import DEFAULT, Params


def fit(buildings) -> Params:
    return DEFAULT


def leave_one_out(buildings) -> pd.DataFrame:
    return pd.DataFrame(columns=["building_id", "error_pct"])


if __name__ == "__main__":
    from loader import load_buildings
    b = load_buildings(use_llm=False)
    print("k =", fit(b).k)
    print(leave_one_out(b))
```

- [ ] **Step 4: Push the stub to `main`, then branch**

```bash
python -c "from engine import evaluate; from schema import House; print(evaluate(House(building_id='x')).reason)"
git add engine.py calibrate.py
git commit -m "engine: stub evaluate/installer_brief/next_question, calibrate stub"
git push
git switch -c engine
git push -u origin engine
```

Expected: `Engine stub: no physics yet.` and the push succeeds. Tell Junwoo "stub on main".

---

### Task 1: Fuel to heat (step 1)

**Files:** Modify `engine.py`

- [ ] **Step 1: Implement `fuel_kwh(h, p) -> (kwh, low, high, note)`** with the precedence above; `period_days` from ISO dates, scale to 365.
- [ ] **Step 2: Implement η**: default `p.eta_default` (0.88); only when `boiler_condensing` is known: gas/LPG `p.eta_gas`, oil `p.eta_oil`; district/electric η 1.0 and current cost "price not provided".
- [ ] **Step 3: `Q_heat = fuel × η`, `Q_dhw = p.dhw_kwh_per_person × occupants` if `dhw_by_boiler`, × `p.solar_dhw_factor` when `notes_obs.solar_thermal_dhw`; `Q_space = Q_heat − Q_dhw`.**
- [ ] **Step 4: `heat_load_bill_kw` = Range(p10 = Q_space / 2100, p50 = Q_space / 2000, p90 = Q_space / 1800)** (`schema.FULL_LOAD_HOURS`). Add a `Step` for each number with its assumption.
- [ ] **Step 5: Verify:** `python engine.py` → bill load B-01 2.4, B-02 6.1, B-03 16.6, B-04 9.5, B-05 11.1 kW.
- [ ] **Step 6: Commit** `git add engine.py && git commit -m "engine: fuel to heat, bill-based load" && git push`

### Task 2: Heating load, area × age (step 2)

- [ ] **Step 1: `w_per_m2(year, column)`** from `schema.W_PER_M2` (`column` 1 = unrenovated/unknown, 2 = partially, 3 = fully).
- [ ] **Step 2: Column choice:** `renovation` if given; empty but `notes_obs.insulation_measures` non-empty, or wall U-value < 0.7 × `schema.U_WALL_REF` → partially, and log a contradiction ("no renovation documented vs better-than-code U-values / insulation work").
- [ ] **Step 3: Unknown renovation:** compute the colour with the unrenovated and the partially column; same colour → keep unrenovated; different → `verdict_basis = cannot_tell_yet` (yellow) and `next_question` = "Was the house insulated or were windows replaced since it was built?".
- [ ] **Step 4: Unused area** (`notes_obs.unheated_area_note`): heated area × `p.unused_area_factor[0]`; checklist line "radiators/valves on the unused floor".
- [ ] **Step 5: `P_load = p.k × w × heated_area`; `specific_load_w_m2`; above `SPECIFIC_LOAD_HINT_W_M2` → `hints` "better windows or insulation may be worth it".** Trace shows the organiser band (`W_PER_M2_ORGANISER_BAND`) and "first estimate, not a DIN EN 12831 calculation".
- [ ] **Step 6: Verify:** loads 10.8 / 9.1 / 13.7 / 13.7 / 6.3 kW. **Commit.**

### Task 3: Radiators → required flow temperature (steps 3, 3b)

- [ ] **Step 1: Underfloor** → 35-40 °C (`UNDERFLOOR_FLOW_C`), JAZ 4.0.
- [ ] **Step 2: Radiators:** count = `radiator_count` → `rooms × 1.3` → `area / 18`; ΣΦ_n = count × `RADIATOR_KW[size][0]` (unknown size → medium for the point estimate); `ΔT = 50 × (P_load / ΣΦ_n)^(1/1.3)`; `T_flow = 20 + ΔT + FLOW_SPREAD_K / 2`.
- [ ] **Step 3: Mixed:** radiator share = `radiator_count / rooms` (cap 1.0; rooms unknown → 0.75); `T_flow` from `P_load × share`; hint "underfloor circuit fine at ~35 °C".
- [ ] **Step 4: Pipe system:** single-pipe +7.5 K point (MC U(5, 10)), green capped at yellow, `reason_category = pipe_system`; unknown and built 1960-1979 → MC penalty U(0, 10); radiator buildings always get the organiser sentence in `open_checks`.
- [ ] **Step 5: Verify:** point estimate B-01 ≈ 54.0 °C, B-03 ≈ 58.2 °C. **Commit.**

### Task 4: JAZ and cost (steps 4, 5)

- [ ] **Step 1:** `jaz_bucket` ∈ `underfloor` / `le55` / `55to60` / `gt60` (the schema rejects anything else); JAZ from `schema.JAZ`.
- [ ] **Step 2:** `cost_now = fuel × PRICE_EUR_KWH[fuel_type]`; `cost_hp = Q_heat / JAZ × 0.26`; `saving = cost_now − cost_hp`; above 60 °C use JAZ 2.8 and `cost_note` "at least this much, the real running cost is higher"; LPG note "real LPG price may be higher"; district/electric: `cost_now` None, note "price not provided".
- [ ] **Step 3: Verify** B-03 cost is positive saving; **commit.**

### Task 5: Traffic light (step 6)

- [ ] **Step 1:** green ≤ 55 °C or underfloor; yellow 55-60 or capped (site flags, single-pipe); red > 60 with core data present; `unclear` (area/age or radiator count missing) → yellow `cannot_tell_yet`, never red.
- [ ] **Step 2:** `verdict_basis`, `traffic_light`, `best_color`, and a one-sentence `reason` that says "there is an obstacle: …" or "we can't tell yet: …" when it applies.
- [ ] **Step 3: Verify** B-01 green, B-02 green, B-03 yellow, B-04 not green; **commit.**

### Task 6: Monte Carlo (step 7) — never cut

- [ ] **Step 1:** `rng = np.random.default_rng(seed)`, N = `n`, numpy vectors only (no Pydantic objects per sample). Draws: W/m² × U(0.8, 1.2); radiator size from `RADIATOR_SIZE_PRIOR` when unknown, Φ_n uniform within its `RADIATOR_KW` low-high, × U(0.85, 1.15); unused area U(0.7, 1.0); single-pipe U(5, 10) K; unknown pipe 1960-79 U(0, 10) K; mixed share U(0.5, 1.0) when rooms unknown; contradicted values widened (B-05: area up to the bill-implied area, cap 2×).
- [ ] **Step 2:** p10/p50/p90 for `required_flow_temp_c` and `heat_load_kw`; `p_green/p_yellow/p_red`; `best_color` = colour of the **p50** (not the mode), then caps; `boundary` = max probability < 0.6.
- [ ] **Step 3: Verify** B-01 p50 ≈ 54.6 (G .52 / Y .20 / R .28), B-03 p50 ≈ 58.8 (G .33 / Y .23 / R .44); same input twice → identical `Result`. **Commit and merge into `main`** (`docs/TEAM_GIT.md`, "Merging"). **Target 2:30 into the day: this secures the B-04 / B-05 results.**

### Task 7: `calibrate.py`

- [ ] **Step 1: `fit`:** `k = exp(mean(log(reference_load / load_at_k1)))` over the dev buildings (one parameter).
- [ ] **Step 2: `leave_one_out`:** for each dev building, fit on the other two, predict it, `error_pct = (pred − ref) / ref × 100`; columns `building_id`, `error_pct`, `k_fit`, `pred_kw`, `ref_kw`.
- [ ] **Step 3: Verify** `python calibrate.py` → k ≈ 1.01, errors ≈ +20 / −9 / −8. **Commit.**

### Task 8: Contradictions (step 2b)

- [ ] Each hit appends `Contradiction(what, sources, trusted, why)` and widens that value's range. Rules in CLAUDE.md step 2b (±40 % bill vs area-age, rooms vs area < 10 m²/room, extra heat source all winter, unused area, U-value renovation, solar DHW, gas vs LPG detail, litres vs kWh ±15 %, flow > 10 K above `current_flow_temp_c`, old house + underfloor). Also turn each `House.conflicts` entry into one contradiction ("text says oil, bill says gas → used bill").
- [ ] **Verify** flags on B-01 (−78 %, LPG, U-values), B-02 (wood stove), B-03 (unused floor), B-05 (+76 %, 14 rooms); none on B-04 except single-pipe items. **Commit.**

### Task 9: Path to yellow, open checks, next question (steps 6b, 6c, 8)

- [ ] `path_to_yellow`: radiator output to add `ΣΦ_n,needed(55 °C) − ΣΦ_n` kW, or heat-loss reduction `1 − P_allowed(55 °C) / P_load`; single-pipe loop options; no prices.
- [ ] `open_checks` (homeowner words, ≤ 6, most decisive first) and `next_question` (year > area > heating surfaces > renovation flip > radiator size > yearly use).
- [ ] **Commit.**

### Task 10: Installer brief (steps 0, 9)

- [ ] `installer_brief`: `visit_type` (first match: boundary → visit_with_parts; red → hold; unclear → visit_with_parts; yellow / contradiction / green with confidence < 0.7 → visit_with_parts; else remote_quote), `confidence` (5 core fields, rules in step 9), `lead_score = (p_green + p_yellow) × confidence`, `parts`, `installer_checklist`, `next_step` (step 10 table: kind + label + detail), site flags at the top.
- [ ] **Verify** B-04 hold, B-03 visit_with_parts with 12 valves. **Commit and merge into `main`.**

### Task 11: Rechenweg

- [ ] Every number above has a `Step(label, value, assumption)` in `trace`, in order: area × W/m² × k → load (bill load beside it) → ΣΦ_n → flow temperature → JAZ → cost. **Commit.**

### Task 12: Handoff check with Junwoo

The app reads these `Result` fields; none may stay empty for a building with core data: `best_color`, `verdict_basis`, `boundary`, `reason`, `p_green/p_yellow/p_red`, `required_flow_temp_c`, `heat_load_kw`, `heat_load_bill_kw`, `jaz_bucket`, `cost_now_eur`, `cost_hp_eur`, `saving_eur`, `contradictions`, `open_checks`, `hints`, `trace`, `visit_type`, `parts`, `installer_checklist`, `path_to_yellow`, `lead_score`, `next_step`.

- [ ] Run `streamlit run app.py` on `main` → Evaluation tab shows 5 rows, no "–" in those columns.

## Structured output and safety nets

**Structured fields.** Fill numbers and kinds; the app writes the sentences (all in `schema.py`):
`options` (list of `Option`: kind `radiators` / `insulation` / `pipe_loop` / `none`, `add_rated_kw_55/60`, `rated_kw_today`, `loss_cut_pct`), `radiators` (`RadiatorSummary`: count, `size_assumed`, `rated_kw`, `needed_rated_kw_55/60`, `share`, `margin_pct`), `flags` (list of `Flag`: one sentence `text`, `src`, `kind`; no "Check on site:" prefix, never an always-check), `always_checks` (checks done at every visit). Empty → the app falls back to the text fields.

**Contract check.** `schema.check_result(h, r)` returns a list of problems (empty = fine). The Evaluation tab prints them as small grey lines.

**Safety nets while you swap the engine.**
- `engine_tracer.py` is a frozen copy of the original engine. If your `engine.py` fails to import or raises for a building, the app shows the tracer result for that building with a "tracer" chip and a grey line saying why. Don't edit it. Fix the error it names.
- `data/baseline_results.json` is a snapshot of colour, probabilities, flow p10/p50/p90, load, visit type and lead score per building.
  - `python loader.py --compare-baseline`: see what moved (`!!` = colour changed). The Evaluation tab shows the same when a colour changes, flow p50 moves ≥ 1 °C or load ≥ 0.3 kW.
  - `python loader.py --save-baseline`: save a new snapshot, only after a change you meant to make.
- Routine after each engine change: `--compare-baseline` → explain every `!!` → no `check_result` lines in Evaluation → save the baseline only if the change was intended.

## Plugging in a learned W/m² model

The W/m² table (step 2) can be replaced by a trained model without touching the rest of the engine or the app.

- **Hook:** `engine.set_w_model(fn, name="...")` or `HP_W_MODEL="module:function"`. `set_w_model(None)` goes back to the table. No model → results byte-for-byte as before.
- **Input:** `engine.features(h, col)` → dict; the key list is in its docstring (year, area, renovation + asked column, building type, distribution, fuel type and yearly kWh, occupants, rooms, region, wall/roof/window U-values, insulation-measure count, unheated-area and extra-heat-source flags). Unknown stays `None`; never fill with 0 or a mean inside the engine: the model must handle missing values itself.
- **Output:** `{"w": float, "lo"?: float, "hi"?: float, "why"?: str}`, W per m² of *heated* area (the engine applies k and the unused-area factor). With `lo`/`hi`, the Monte Carlo draws U(lo, hi) instead of w × U(0.8, 1.2). `why` goes into the Rechenweg ("learned model <name>: <why>; organiser band …").
- **Fallback:** exception, NaN/inf, w ≤ 0 or an invalid lo/hi → the table for that house, the Rechenweg says "model … failed, table used", one warning per message. The app never breaks.
- **Check:** `HP_W_MODEL=mymod:predict python loader.py --compare-baseline` (explain every `!!`), `python calibrate.py` (k is refit on top of the model; report the leave-one-out errors next to the table's +19.8 / −9.4 / −7.9 %). `engine:example_table_model` returns the table ±20 % and must reproduce today's colours.
- **Honesty rules:** train only on real data (e.g. public German building typology such as IWU/TABULA, energy-certificate statistics), never on generated or synthetic buildings and never on the 2 hidden buildings; 3 dev buildings are for checking, not training. Keep None as None. Always report leave-one-out next to the table baseline; if the model does not beat the table, keep the table.

**Cut order if late (from the end):** Task 11 detail → secondary contradiction rules in Task 8 → Task 9 wording. Never cut Task 6 (Monte Carlo).
**Not in this plan:** step 10 `quote_request` / `handover_pdf` (who writes them is agreed with Junwoo when P0-c starts).
