# JSON contract: UI ↔ modules (draft v2)

Status: **draft v2** (`schema.CONTRACT_VERSION = "2-draft"`, 2026-10-24). Owner: Junwoo (UI + architecture). Change it only together; bump `x-contract-version`. §0 is the contract any decision logic must meet; §1–§6 (v1) are **still accepted** and describe the transport, the inputs and the optional physics extras.

## §0 Contract v2 core (any logic)

The `calculation` module may be physics, a trained model (GBM, GP, …), rules or a hybrid. The app renders **any** `Result` that fills the core below; everything else is optional.

**Required core** (`schema.check_result(h, r)` returns no warnings):

| Field | Meaning | `check_result` wording when broken |
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

**Minimal valid module reply** (`data` validates as `Result`, `check_result` → `[]`):

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
page-1 form ────────────────────────────────────────────────┐
bill upload ──► image_validation ──► bill_recognizer ────────┼─► House ──► calculation ──► Result ──► 3 tabs
radiator photo ──► image_validation ─────────────────────────┘
```

The JSON shapes are the existing Python models in `schema.py`, exported as JSON Schema:

| Module (default) | Request | Reply `data` | Schema | Examples |
| --- | --- | --- | --- | --- |
| `modules/bill_recognizer.py` | `{"file": {...}, "fuel_hint": "gas" \| null}` | `BillObs` | `contracts/bill.schema.json` | `contracts/examples/bill_output_demo.json` |
| `modules/image_validation.py` | `{"file": {...}, "expected": "radiator" \| "bill" \| "exterior"}` | `ImageCheck` | `contracts/image_check.schema.json` | `image_check_ok.json`, `image_check_blurry.json` |
| `modules/calculation.py` | `{"house": House, "n": 500, "seed": 0}` | `Result` | `contracts/house.schema.json`, `contracts/result.schema.json` | `calc_input_B-04/B-05/form.json` → `calc_output_B-04/B-05.json` |

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
- Time limits: image_validation 5 s, bill_recognizer 15 s, calculation 20 s. In-process there is no hard kill: a slower call still counts, but the orchestrator adds a warning (`took 21.0 s, over the 20 s limit`) and the UI blocks meanwhile, so stay under it. A raised exception, a reply that is not an envelope, or `data` that doesn't validate against the schema = failure; the UI then shows "couldn't read that, you can skip" (inputs) or falls back to `engine.py`, then `engine_tracer.py` (result), marked on screen.
- No network calls, no storing files, deterministic (`calculation` uses `seed`).
- **CLI for testing:** every module also runs as `python -m modules.<name> < request.json` (reads the request JSON on stdin, prints the reply JSON).

## 2. Field rules (all modules)

1. **Exact field names** from the schema files (snake_case), exact enum values (e.g. `"two_pipe"`, `"partially"`, `"green"`).
2. **Unknown = `None`/`null`.** Never `0`, `""` or a guess. Lists that are "unknown" are `null`; an explicit "none" is `[]`.
3. Numbers are numbers (not `"18.002"`), dates are ISO `YYYY-MM-DD`, units fixed: kWh, m³, litres, €, m², °C, kW.
4. Extra fields are ignored by the UI; don't rely on them.
5. Per-field provenance where the schema has it: `confidence[field]` 0-1, `evidence[field]` = the snippet the value came from (e.g. `"Verbrauch 18.002 kWh"`).

## 3. Module by module

### bill_recognizer → `BillObs`
Reads a gas/oil/LPG bill (PDF text, photo, screenshot) and returns **raw numbers as printed**: `bill_carrier`, `kwh_printed`, `m3`, `zustandszahl`, `brennwert`, `liters`, `period_start`, `period_end`, `bill_total_eur`, `monthly_advance_eur`, plus `confidence`, `evidence`, `missing` (`not_visible` | `blurry` | `ambiguous` | `wrong_object`), `retake_tip`.
- **No conversion.** Don't turn m³ into kWh or scale the period to a year; `calculation` does that (fuel precedence: bill raw values → `annual_fuel_kwh` → `annual_fuel_liters × 10` → advance payment).
- `fuel_hint` = the fuel the homeowner picked on the form (may be `None`); a hint only, never copy it into the reply.
- Test input: `assets/demo/bill_demo_gas_2025.pdf` and `..._photo.jpg` (expected values in `assets/demo/README.md`: 18,002 kWh, 1,651 m³, Zustandszahl 0.9523, Brennwert 11.450, 2025-01-01 to 2025-12-31, €2,462.12).

### image_validation → `ImageCheck`
Says whether a photo is **usable**, not what it means: `usable`, `reason` (`ok` | `blurry` | `too_dark` | `too_bright` | `too_small` | `wrong_object` | `unreadable` | `unsupported_type`), `retake_tip` (one concrete sentence), `width_px`, `height_px`, `sharpness`, `brightness`.
- Optional `radiator` (`RadiatorObs`: `panel_type`, `radiator_size`, `pipe_system`, …) only if the module can really tell; `pipe_system` stays `null` unless sure (organiser photo `07` must stay `null`).
- Test inputs: `data/pipe_photos/*` (labels in `labels.json`), plus any blurred/dark photo.

### calculation → `Result`
Input `{"house": House}`. Output a `Result`; this replaces `engine.py`'s `evaluate` + `installer_brief`. **v2:** only the §0 core is required; the list below is the v1 physics shape, still accepted and used when present.
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

- Later steps can overrule form values: the bill wins on fuel and yearly use, the radiator photo on radiator size and pipe system, a confirmed conflict answer on anything (`source[field] = "confirmed"`). The optional free text (page 4, LLM parser, only on demand) arrives as `source = "notes_llm"` and only fills fields the form left empty; disagreements are listed in `House.conflicts`.
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
            "image_validation": "modules.image_validation:run",
            "calculation": "modules.calculation:run"}
```

Each entry can be overridden without editing our code: `HP_MODULE_<NAME>="pkg.mod:func"`, e.g. `HP_MODULE_CALCULATION="ml.predict:run" streamlit run app.py`. Imports are lazy and reloaded when the file's mtime changes, so editing a module while Streamlit runs is picked up on the next click (the app's result cache key includes the module file times).

**Call order.**

| Input / output | First | Then | Last |
| --- | --- | --- | --- |
| Bill (step 3) | `image_validation` (photos only; unusable → retake tip, stop) → `bill_recognizer` → `BillObs` → `extract.obs_to_house("bill")` | `extract.extract(..., "bill")` (cache / LLM, being phased out) | "couldn't read that, you can skip" |
| Radiator photo (step 2) | `image_validation` (unusable → retake tip; `radiator` reading if present) | `extract.extract(..., "radiator")` | "couldn't read that, you can skip" |
| Result (all tabs) | `calculation` | `engine.py` | `engine_tracer.py` |

A module counts as **available** when it imports and its probe reply is not `unsupported` (cached per file time). The skeletons answer `unsupported`, so today the app runs entirely on the fallbacks.

**On screen.** A result from `calculation` gets a small **"module calc"** chip (Evaluation, Installer) and "Computed by the calculation module." under the homeowner answer; the tracer keeps its "tracer" chip; `engine.py` shows nothing. Under "We read" a muted line says "Read by the module" or "Read by the fallback reader". When `calculation` is available but fails for a building, Evaluation prints a grey line: `B-05: calculation module failed (…), showing engine.py`.

**Switches.**
- `HP_MODULES=0`: no module calls at all (the app behaves as before the orchestrator).
- `HP_MODULES_ONLY=1`: no Python fallback for bill and radiator photo, so a failing module shows up as "couldn't read that" instead of being hidden.

**Test one module from the UI.** Set `IMPLEMENTED = True` in your module (or point the registry at your own function), then `HP_MODULES_ONLY=1 streamlit run app.py` → Homeowner → step 2 (example photo) or step 3 ("Use the demo bill photo"), and check the "Read by the module" line and the chips. For `calculation`: open 📊 Evaluation, every building should carry "module calc"; any grey "calculation module failed" line names the error. From the shell: `python orchestrator.py` prints which modules the app considers available.
