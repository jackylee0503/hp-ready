# JSON contract: UI ↔ modules (draft v2)

## MVP: what `calculation` must return

Only four things (plus the three probabilities). Everything else is optional. `schema.check_result(h, r)` checks only these; the UI works with nothing more.

| Required | Field | Rule |
| --- | --- | --- |
| colour | `best_color` | `"green"` \| `"yellow"` \| `"red"` |
| how sure | `p_green`, `p_yellow`, `p_red` | each 0–1, sum ≈ 1; `p_red ≥ 0.5` ⇒ `best_color` must be `"red"` |
| watts | quantity `heat_load_kw` (kW), or legacy `heat_load_kw: {p10, p50, p90}` | `p50` set; p10 ≤ p50 ≤ p90 |
| temperature | quantity `flow_temp_c` (°C, coldest day), or legacy `required_flow_temp_c: {p10, p50, p90}` | `p50` set; p10 ≤ p50 ≤ p90 |

Heat load and flow temperature are required once the house has area and build year (without them the module may answer yellow "can't tell yet"). Minimal valid reply (`contracts/examples/calc_output_minimal.json` is its `data`):

```json
{"ok": true, "module": "calculation", "version": "0.1", "warnings": [],
 "data": {
  "best_color": "green",
  "p_green": 0.72, "p_yellow": 0.18, "p_red": 0.10,
  "quantities": [
    {"key": "heat_load_kw", "p10": 7.8, "p50": 9.3, "p90": 11.0},
    {"key": "flow_temp_c", "p10": 48.0, "p50": 53.0, "p90": 58.0}
  ]
 }}
```

**Optional extras the UI uses when present** (absent → the section is hidden, never a wall of "–"): `reason` (else the UI writes a neutral one, e.g. "About 53 °C on the coldest day: likely suitable."), `verdict_basis` (else derived from the colour), `open_checks`, `explanations`, `trace`, `model_info`, `contradictions`, `options` / `path_to_yellow`, `radiators`, `flags`, `heat_load_bill_kw`, `specific_load_w_m2`, `jaz_bucket`, `cost_now_eur` / `cost_hp_eur` / `saving_eur` / `cost_note`, `hints`, `site_flags`, any other quantity key (shown under "Other model outputs"), and the installer fields (`visit_type`, `parts`, `installer_checklist`, `next_step`, `next_photo`, `confidence`, `lead_score`; empty ones are filled from the baseline `installer_brief`). `schema.optional_gaps(r)` lists the empty extras (information, not errors).

---

Status: **draft v2** (`schema.CONTRACT_VERSION = "2-draft"`, 2026-10-24). Owner: Junwoo (UI + architecture). Change it only together; bump `x-contract-version`. The **MVP section above is the only requirement**; §0 describes the full v2 result (all of it optional beyond the MVP core) and §1–§6 (v1) are **still accepted** and describe the transport, the inputs and the optional physics extras.

## Pipeline (team split, 2026-10-24 afternoon)

```
Table (House) is filled by:
  1/4 dropdowns + typed integers (homeowner)
  2/4 radiator photo → ML module 1 "pipe_classifier": single-pipe vs two-pipe
  3/4 bill (photo/PDF) → ML module 2 "bill_recognizer": OCR → raw bill numbers
  4/4 optional free text → LLM parser, ONLY on "Read it", fills ONLY fields still empty after 1-3
Then ML module 3 "calculation": finds internal contradictions + produces the Result → result screens
```

| # | Module (default file) | Request | Reply `data` | Schema | Examples |
| --- | --- | --- | --- | --- | --- |
| 1 | `pipe_classifier` (`modules/pipe_classifier.py`) | `{"file": {...}, "hint": {"build_year": int \| null}}` (hint optional) | `RadiatorObs`: `pipe_system` `"two_pipe"` \| `"single_pipe"` \| `null` (unsure), `confidence["pipe_system"]`, `evidence["pipe_system"]` (short reason), optional `panel_type` / `radiator_size`, `missing` / `retake_tip` when the photo is unusable | `contracts/pipe.schema.json` | `pipe_output_two_pipe.json`, `pipe_output_single_pipe.json`, `pipe_output_unknown.json` |
| 2 | `bill_recognizer` (`modules/bill_recognizer.py`) | `{"file": {...}, "fuel_hint": "gas" \| null}` | `BillObs`: OCR or any method; raw numbers as printed; no conversion. Photo problems come back in its own `missing` / `retake_tip` | `contracts/bill.schema.json` | `bill_output_demo.json` |
| 3 | `calculation` (`modules/calculation.py`) | `{"house": House, "n": 500, "seed": 0}` | `Result` (§0), including `contradictions` | `contracts/house.schema.json`, `contracts/result.schema.json` | `calc_input_B-04/B-05/form.json` → `calc_output_B-04/B-05.json` |

**The LLM step (4/4) only fills blanks and never asks.** The page-4 free text is read by the LLM parser (`extract.py`, cached) only when the homeowner presses "Read it" (an explicit request). Its `House` carries `source = "notes_llm"`, the lowest merge rank, so it only fills fields still empty after the form, the photo and the bill. When it disagrees with a filled field, nothing is asked: the disagreement is dropped from `House.conflicts` and shown as one muted note under the "We read" chips, e.g. "Not used (already set): living area 140 m² (form says 150 m²)".

**Contradictions vs conflicts.**
- **Internal contradictions** (cross-field inconsistencies inside one House: bill vs area-age load, wood stove all winter, rooms vs area, LPG detail vs gas carrier, …) are **module 3's job**: `calculation` finds them and returns them in `Result.contradictions` (`{what, sources, trusted, why}`).
- **Input conflicts** (the same field from two sources, e.g. the form says oil, the bill says gas) are asked to the homeowner by the UI **before** the calculation (page 4, at most two questions; form vs bill/photo only). The House arrives with the resolved values; `House.conflicts` (`{field, values: {source: value}, used}`) lists them for context only.

**Fallback rule (Invariant 1): a fallback never calls the LLM by itself.** When module 1 or 2 is unavailable or fails, `orchestrator` falls back to `extract.extract(..., cache_only=True)`: the committed demo reads in `samples/cached_extract.json` keep working, a new photo/bill gives "couldn't read that, you can skip". `HP_LLM_FALLBACK=1` restores the live-LLM fallback on a cache miss. Under "We read" a muted line names the reader: "Read by the module" · "Read from the demo cache" · "Couldn't read". Module 3 falls back to `engine.py`, then `engine_tracer.py` (no LLM anywhere).

## §0 Contract v2 core (any logic)

The `calculation` module (ML module 3) may be physics, a trained model (GBM, GP, …), rules or a hybrid. **Superseded as a requirement by "MVP" at the top**: only colour, probabilities, heat load and flow temperature are checked. The table below is the full v2 result the screens use best; every row beyond the MVP core is now an optional extra.

**Full v2 result** (recommended, no longer checked by `schema.check_result`):

| Field | Meaning | old v2 `check_result` wording (now only the MVP rows are checked) |
| --- | --- | --- |
| `best_color` + `p_green`, `p_yellow`, `p_red` | verdict (`green`/`yellow`/`red`) and colour probabilities summing to 1 | `probabilities sum to X, not 1` |
| `verdict_basis` | `likely_suitable` · `checks_remain` · `cannot_tell_yet` · `obstacle` (obstacle ⇒ red; missing data ⇒ yellow `cannot_tell_yet`, never red) | `verdict_basis obstacle but colour is not red` · `missing data must be yellow, not red` |
| `reason` | one plain sentence for the homeowner | `reason empty` |
| `quantities` | at least one `Quantity` with `p50` (and p10 ≤ p50 ≤ p90) | `no quantity (quantities or legacy ranges)` · `KEY: p10 ≤ p50 ≤ p90 broken` |
| `explanations` **or** `trace` | something that explains the verdict | `nothing explains the verdict (explanations or trace)` |
| `open_checks` | what is still open (`{item, why}`) | `open_checks empty` |
| `model_info` | which logic produced it | `model_info missing` |
| (not green) `options` or `path_to_yellow` | what gets the house to 55 °C | `not green but no options / path_to_yellow` |

The colour/reason/quantity/explanation/open_checks checks apply once the house has area and build year.

**`Quantity`** — any number the logic predicts, with uncertainty: `key` (snake_case id), `label` (empty → from `QUANTITY_KEYS` or the key), `unit`, `p10`, `p50`, `p90`, `note`. Well-known keys (`schema.QUANTITY_KEYS`) are read by name by the screens: `flow_temp_c` (°C, coldest day), `heat_load_kw`, `heat_load_bill_kw`, `specific_load_w_m2`, `cost_now_eur`, `cost_hp_eur`, `saving_eur`. **Any other key** (e.g. `p_ok_hp`) is shown generically under "Other model outputs" (label, median, p10–p90, unit).

**`Explanation`** — how one input moved the result: `feature` (House field or model feature), `value` (as shown to people), `contribution` (signed effect on `target`, in `unit`), `target` (`p_green`, `flow_temp_c`, `log_odds_green`, …), `unit`, `text` (optional sentence). The UI shows the top 6 by |contribution| as signed bars ("Why the model decided this"); without contributions it lists `text`.

**`ModelInfo`** — reproducibility for the paper: `name`, `version`, `kind` (`physics` · `ml` · `hybrid` · `rule` · `other`), `trained_on`, `data_hash`, `seed`, `params`, `metrics` (self-reported, e.g. `{"loo_verdict_acc": 0.67}`). The UI shows "Model: name · version · kind" (Evaluation detail, Installer header) and metrics as **"Reported by the model: …"**, always labelled self-reported. Numbers the app computes itself from predictions vs `reference` (verdicts reproduced, heat-load error, Compare logic) are shown as measured (invariant 8).

**A fuller module reply** (`data` validates as `Result`; the extras beyond the MVP core are optional):

```json
{"ok": true, "module": "calculation", "version": "2-draft", "warnings": [],
 "data": {
  "best_color": "green", "verdict_basis": "likely_suitable",
  "p_green": 0.7, "p_yellow": 0.2, "p_red": 0.1,
  "reason": "The existing radiators should manage at a low flow temperature.",
  "open_checks": [{"item": "Confirm radiator sizes on site", "why": "no photo yet"}],
  "quantities": [
    {"key": "flow_temp_c", "p10": 46.0, "p50": 51.0, "p90": 57.0},
    {"key": "heat_load_kw", "p10": 7.9, "p50": 9.3, "p90": 11.2},
    {"key": "p_ok_hp", "label": "P(heat pump OK)", "p10": 0.62, "p50": 0.74, "p90": 0.83}
  ],
  "explanations": [
    {"feature": "radiator_count", "value": "14", "contribution": 0.21, "target": "p_green"},
    {"feature": "build_year", "value": "band 1979–1994", "contribution": -0.12, "target": "p_green"},
    {"feature": "living_area_m2", "value": "140", "contribution": 0.08, "target": "p_green"}
  ],
  "model_info": {"name": "gbm-test", "version": "0.1", "kind": "ml", "trained_on": "3 dev buildings",
                 "seed": 0, "params": {}, "metrics": {"loo_verdict_acc": 0.67}}
 }}
```

**Optional extras** (the UI uses them when present, shows "–" or falls back when absent): the physics fields `required_flow_temp_c`, `heat_load_kw`, `heat_load_bill_kw` (legacy ranges), `jaz_bucket`, `cost_*`, `contradictions`, `trace`, `options`, `radiators`, `flags`, `always_checks`, `site_flags`, `hints`, and the installer fields `visit_type`, `parts`, `installer_checklist`, `next_step`, `next_photo`, `confidence`, `lead_score`. When a module leaves the installer fields empty, the app fills **only the empty ones** from the baseline `engine.installer_brief` (run on a copy, the module's `flow_temp_c` / `heat_load_kw` handed in) and marks the Installer header "installer brief from baseline" (`orchestrator.fill_installer_brief`).

**Helpers.**
- `schema.with_core(r, default_info)` — v1 → v2 adapter: fills `quantities` from the legacy ranges/cost fields and `model_info` from `default_info` when empty (the app applies it to engine.py results with `BASELINE_INFO`).
- `schema.quantity(r, key)` — the one door the UI reads numbers through: v2 `quantities` first, legacy field as fallback. A model that fills only `quantities` renders everywhere.
- `schema.optional_gaps(r)` — optional fields left empty (information, not errors).
- `orchestrator.compare_logic(buildings) -> list[dict]` — A/B for the paper: baseline (engine.py, A) vs the calculation module (B) per building (colour, p_green, flow and heat-load p50 with Δ, |error| vs reference, verdict hit); `orchestrator.compare_summary(rows)` gives dev verdicts reproduced and mean |heat-load error| for A and B. No Streamlit, callable from a notebook:

```python
import orchestrator as O
from loader import load_buildings
rows = O.compare_logic(load_buildings(use_llm=False)); print(O.compare_summary(rows))
```

The Evaluation tab shows the same table behind the **"Compare logic"** toggle (only when a calculation module is available).

**Try it.** `HP_MODULE_CALCULATION="my_pkg.my_model:run" streamlit run app.py` (the module must be importable from the app folder). Evaluation then shows the module's verdicts ("module calc" chip), "Other model outputs", "Why the model decided this", "Model: …" and "Reported by the model: …"; any contract warning appears as a grey line under the table.

---

The Streamlit app stays the UI. `orchestrator.py` calls three **Python** modules in-process with a JSON-shaped request (a `dict`) and gets a JSON-shaped reply back (decision 2026-10-24: Python only, no Node):

```
1/4 page-1 form ─────────────────────────────────────────┐
2/4 radiator photo ──► pipe_classifier ───────────────────┤
3/4 bill photo/PDF ──► bill_recognizer ───────────────────┼─► House ──► (UI asks input conflicts) ──► calculation ──► Result ──► 3 tabs
4/4 free text ("Read it" only) ──► LLM parser, blanks only┘
```

The JSON shapes are the existing Python models in `schema.py`, exported as JSON Schema (module table: "Pipeline" above).

`file` is always `{"path": "<absolute path to a temp file>", "mime": "application/pdf" | "image/jpeg" | "image/png" | "image/webp"}`. The orchestrator writes the upload to a temp file and deletes it after the call; modules never get base64 or bytes.

## 1. How a module is called

- Convention: a plain function **`run(request: dict) -> dict`**, JSON-compatible in and out (only dicts, lists, str, float, int, bool, None). Plain Python, no new dependencies (numpy, Pillow, pandas are installed; anything else: ask first, it must install on Streamlit Cloud).
- Reply envelope:

```python
{"ok": True,  "module": "bill_recognizer", "version": "1-draft", "data": { ... BillObs ... }, "warnings": []}
{"ok": False, "module": "bill_recognizer", "version": "1-draft", "error": {"code": "unreadable", "message": "no kWh found"}}
```

- `error.code`: `bad_input` (request malformed), `unreadable` (file can't be read), `unsupported` (mime not handled, or the module is still a skeleton), `internal` (bug). The orchestrator adds `missing` (module not importable or switched off).
- **Probe:** `{"probe": True}` must be answered quickly. `ok: True` (data may be `None`) = ready; `error.code == "unsupported"` = not implemented yet, so the app uses its fallback. The skeletons flip this with `IMPLEMENTED = True`.
- Time limits: pipe_classifier 10 s, bill_recognizer 15 s, calculation 20 s. In-process there is no hard kill: a slower call still counts, but the orchestrator adds a warning (`took 21.0 s, over the 20 s limit`) and the UI blocks meanwhile, so stay under it. A raised exception, a reply that is not an envelope, or `data` that doesn't validate against the schema = failure; the UI then shows "couldn't read that, you can skip" (inputs) or falls back to `engine.py`, then `engine_tracer.py` (result), marked on screen.
- No network calls, no storing files, deterministic (`calculation` uses `seed`).
- **CLI for testing:** every module also runs as `python -m modules.<name> < request.json` (reads the request JSON on stdin, prints the reply JSON).

## 2. Field rules (all modules)

1. **Exact field names** from the schema files (snake_case), exact enum values (e.g. `"two_pipe"`, `"partially"`, `"green"`).
2. **Unknown = `None`/`null`.** Never `0`, `""` or a guess. Lists that are "unknown" are `null`; an explicit "none" is `[]`.
3. Numbers are numbers (not `"18.002"`), dates are ISO `YYYY-MM-DD`, units fixed: kWh, m³, litres, €, m², °C, kW.
4. Extra fields are ignored by the UI; don't rely on them.
5. Per-field provenance where the schema has it: `confidence[field]` 0-1, `evidence[field]` = the snippet the value came from (e.g. `"Verbrauch 18.002 kWh"`).

## 3. Module by module

### 1 pipe_classifier → `RadiatorObs`
Radiator photo → single-pipe vs two-pipe heating. Main output `pipe_system`: `"two_pipe"` | `"single_pipe"` | `null` when unsure (never a guess), with `confidence["pipe_system"]` and `evidence["pipe_system"]` (short reason, e.g. "H-block with side bypass port"). Optional `panel_type` (`"11"`/`"22"`/`"33"`) and `radiator_size` only if it can really tell.
- Photo unusable (blurry, dark, not a radiator …): `ok: true`, `pipe_system: null`, `missing: {"pipe_system": "blurry" | "not_visible" | "ambiguous" | "wrong_object"}` and a one-sentence `retake_tip`. There is no separate image check.
- `hint.build_year` (from the form, may be `null`) is context only; never copy it into the reply.
- Test set: `data/pipe_photos/*`, installer-confirmed labels in `data/pipe_photos/labels.json` (06, 11 single-pipe; 05, 10 two-pipe; **07 must stay `null`**). Examples: `contracts/examples/pipe_output_two_pipe.json`, `pipe_output_single_pipe.json`, `pipe_output_unknown.json`.

### 2 bill_recognizer → `BillObs`
OCR or any method; raw numbers as printed; no conversion. Reads a gas/oil/LPG bill (PDF text, photo, screenshot) and returns **raw numbers as printed**: `bill_carrier`, `kwh_printed`, `m3`, `zustandszahl`, `brennwert`, `liters`, `period_start`, `period_end`, `bill_total_eur`, `monthly_advance_eur`, plus `confidence`, `evidence`, `missing` (`not_visible` | `blurry` | `ambiguous` | `wrong_object`), `retake_tip`.
- **No conversion.** Don't turn m³ into kWh or scale the period to a year; `calculation` does that (fuel precedence: bill raw values → `annual_fuel_kwh` → `annual_fuel_liters × 10` → advance payment).
- `fuel_hint` = the fuel the homeowner picked on the form (may be `None`); a hint only, never copy it into the reply.
- Test input: `assets/demo/bill_demo_gas_2025.pdf` and `..._photo.jpg` (expected values in `assets/demo/README.md`: 18,002 kWh, 1,651 m³, Zustandszahl 0.9523, Brennwert 11.450, 2025-01-01 to 2025-12-31, €2,462.12).

- Photo quality problems (blurry, cut off, not a bill) come back in its own `missing` / `retake_tip`; there is no separate image check.

### 3 calculation → `Result`
Input `{"house": House}`. **Owns internal contradictions** (`Result.contradictions`, see "Contradictions vs conflicts" at the top); input conflicts arrive already resolved, listed in `House.conflicts` for context. Output a `Result`; this replaces `engine.py`'s `evaluate` + `installer_brief`. **MVP:** only the core at the top (colour, probabilities, heat load, flow temperature) is required; the list below is the v1 physics shape, still accepted and used when present.
- The UI reads: `best_color`, `verdict_basis`, `boundary`, `reason`, `p_green/p_yellow/p_red`, `required_flow_temp_c`, `heat_load_kw`, `heat_load_bill_kw` (`{p10, p50, p90}`), `jaz_bucket`, `cost_now_eur`, `cost_hp_eur`, `saving_eur`, `contradictions`, `open_checks`, `trace`, `visit_type`, `parts`, `lead_score`, `next_step`, and the **structured** fields `options`, `radiators`, `flags`, `always_checks` (fill numbers and kinds; the UI writes the sentences).
- Rules: CLAUDE.md "Engine" (fixed prices and JAZ, 55/60 °C bands, missing data → yellow `cannot_tell_yet`, never red).
- Check against the Python engine: `contracts/examples/calc_output_B-04.json` / `B-05.json` are today's results for the same inputs.
- Sources: values typed on the page-1 form arrive as `source[field] = "text"` for now (see §4), treat `"text"` and `"form"` the same.

## 4. Page-1 form → `House`
The form fills these `House` fields with `confidence[field] = 0.9`: `build_year`, `living_area_m2`, `building_type`, `renovation`, `heat_distribution`, `fuel_type`, `annual_fuel_kwh` (or `annual_fuel_liters`), `occupants`, `radiator_count`, `radiator_size`, `dhw_by_boiler`, `rooms`. "Don't know" → `null`. Example: `contracts/examples/calc_input_form.json`.
- `source[field]`: the target is `"form"`. Until `extract.merge` (`ORDER`) and `engine._field_conf` know `"form"`, the app sends `"text"` (owner-entered, same merge rank and confidence as the old text step) and only the screens say "form". Switch: `app.py` `FORM_MERGE_SRC`.
- Page 1 (2026-10-24, after team review): **numbers are typed as integers, categories are dropdowns.** Empty = "don't know" = `null`. Fields marked `*` on screen matter most for the answer (`build_year`, `living_area_m2`, `heat_distribution`, `renovation`, `radiator_count`, `radiator_size`); they are still optional. The page says "If you don't know everything, it's okay."

| Field | Input | What arrives in `House` | How to read it |
| --- | --- | --- | --- |
| `build_year` * | typed integer 1800–2026 | exact `int` | exact as typed (owner's memory; may be approximate) |
| `living_area_m2` * | typed integer 10–2,000 m² (step 5) | `float` | as typed |
| `annual_fuel_kwh` | typed integer 0–200,000 kWh/yr (step 500), fuel ≠ oil | `float` | as typed; the bill overrules it |
| `annual_fuel_liters` | typed integer 0–20,000 L/yr (step 100), oil only | `float`; `annual_fuel_kwh` stays `null` | ×10 kWh/L happens in the calculation |
| `occupants`, `rooms`, `radiator_count` * | typed integers (1–20, 1–50, 0–80) | exact `int` | |
| enums (`building_type`, `renovation` *, `heat_distribution` *, `fuel_type`, `radiator_size` *, `dhw_by_boiler`) | dropdown with "Don't know" | exact enum value | `renovation` "partly" → `"partially"` |

- Earlier today page 1 briefly used year **bands** (stored as a representative year with `evidence["build_year"] = "band …"`). The app still understands that evidence; when you see it, treat the year as the band, not an exact year.

- Later steps can overrule form values: the bill wins on fuel and yearly use, the radiator photo on radiator size and pipe system, a confirmed conflict answer on anything (`source[field] = "confirmed"`). The optional free text (page 4, LLM parser, only on "Read it") arrives as `source = "notes_llm"` and only fills fields still empty after the form, photo and bill; its disagreements are **not** in `House.conflicts` and are never asked (muted "Not used (already set)" note instead).
- Organiser buildings (`data/`) and `contracts/examples/calc_input_B-0x.json` carry exact years; `contracts/examples/calc_input_form.json` shows a form house.

## 5. Check your output

```bash
python -m modules.calculation < contracts/examples/calc_input_B-05.json > out.json
python -c "import json; from schema import Result, check_result, House; d=json.load(open('out.json')); r=Result.model_validate(d['data']); h=House.model_validate(json.load(open('contracts/examples/calc_input_B-05.json'))['house']); print(check_result(h, r) or 'OK')"
```

Any JSON Schema validator works too, e.g. `npx ajv-cli validate -s contracts/result.schema.json -d <data-only.json>`.
After a change to `schema.py`: `python schema.py --export-contracts` regenerates `contracts/`.

## 6. Orchestrator and fallbacks (`orchestrator.py`)

**Registry.** `orchestrator.REGISTRY` maps a module name to `"package.module:function"`:

```python
REGISTRY = {"bill_recognizer": "modules.bill_recognizer:run",
            "pipe_classifier": "modules.pipe_classifier:run",
            "calculation": "modules.calculation:run"}
```

Each entry can be overridden without editing our code: `HP_MODULE_<NAME>="pkg.mod:func"` (`HP_MODULE_PIPE_CLASSIFIER`, `HP_MODULE_BILL_RECOGNIZER`, `HP_MODULE_CALCULATION`), e.g. `HP_MODULE_CALCULATION="ml.predict:run" streamlit run app.py`. Imports are lazy and reloaded when the file's mtime changes, so editing a module while Streamlit runs is picked up on the next click (the app's result cache key includes the module file times).

**Call order.**

| Input / output | First | Then | Last |
| --- | --- | --- | --- |
| Radiator photo (step 2) | `pipe_classifier` → `RadiatorObs` → `extract.obs_to_house("radiator")` (`orchestrator.classify_pipes`) | `extract.extract(..., "radiator", cache_only=True)` (demo cache; live LLM only with `HP_LLM_FALLBACK=1`) | "couldn't read that, you can skip" |
| Bill (step 3) | `bill_recognizer` → `BillObs` → `extract.obs_to_house("bill")` (`orchestrator.recognize_bill`, no pre-check) | `extract.extract(..., "bill", cache_only=True)` (same rule) | "couldn't read that, you can skip" |
| Free text (step 4) | LLM parser `extract.extract(..., "house_text")`, only on "Read it" (explicit request; cache first) | keyword reader | – |
| Result (all tabs) | `calculation` | `engine.py` | `engine_tracer.py` |

A module counts as **available** when it imports and its probe reply is not `unsupported` (cached per file time). The skeletons answer `unsupported`, so today the app runs entirely on the fallbacks.

**On screen.** A result from `calculation` gets a small **"module calc"** chip (Evaluation, Installer) and "Computed by the calculation module." under the homeowner answer; the tracer keeps its "tracer" chip; `engine.py` shows nothing. Under "We read" a muted line says "Read by the module", "Read from the demo cache" or "Couldn't read" (with `HP_LLM_FALLBACK=1` also "Read by the AI fallback"). When `calculation` is available but fails for a building, Evaluation prints a grey line: `B-05: calculation module failed (…), showing engine.py`.

**Switches.**
- `HP_MODULES=0`: no module calls at all (the app behaves as before the orchestrator).
- `HP_MODULES_ONLY=1`: no fallback at all for bill and radiator photo (not even the demo cache), so a failing module shows up as "couldn't read that" instead of being hidden.
- `HP_LLM_FALLBACK=1`: the bill/photo fallback may call the LLM live on a cache miss. Off by default (Invariant 1: fallbacks never call the LLM by themselves).

**Test one module from the UI.** Set `IMPLEMENTED = True` in your module (or point the registry at your own function), then `HP_MODULES_ONLY=1 streamlit run app.py` → Homeowner → step 2 (example photo) or step 3 ("Use the demo bill photo"), and check the "Read by the module" line and the chips. For `calculation`: open 📊 Evaluation, every building should carry "module calc"; any grey "calculation module failed" line names the error. From the shell: `python orchestrator.py` prints which modules the app considers available.
