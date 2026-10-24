# JSON contract: UI ↔ modules (draft v1)

Status: **draft v1** (2026-10-24). Owner: Junwoo (UI + architecture). Change it only together; bump `x-contract-version`.

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
Input `{"house": House}`. Output a full `Result`; this replaces `engine.py`'s `evaluate` + `installer_brief`.
- The UI reads: `best_color`, `verdict_basis`, `boundary`, `reason`, `p_green/p_yellow/p_red`, `required_flow_temp_c`, `heat_load_kw`, `heat_load_bill_kw` (`{p10, p50, p90}`), `jaz_bucket`, `cost_now_eur`, `cost_hp_eur`, `saving_eur`, `contradictions`, `open_checks`, `trace`, `visit_type`, `parts`, `lead_score`, `next_step`, and the **structured** fields `options`, `radiators`, `flags`, `always_checks` (fill numbers and kinds; the UI writes the sentences).
- Rules: CLAUDE.md "Engine" (fixed prices and JAZ, 55/60 °C bands, missing data → yellow `cannot_tell_yet`, never red).
- Check against the Python engine: `contracts/examples/calc_output_B-04.json` / `B-05.json` are today's results for the same inputs.
- Sources: values typed on the page-1 form arrive as `source[field] = "text"` for now (see §4), treat `"text"` and `"form"` the same.

## 4. Page-1 form → `House`
The form fills these `House` fields with `confidence[field] = 0.9`: `build_year`, `living_area_m2`, `building_type`, `renovation`, `heat_distribution`, `fuel_type`, `annual_fuel_kwh` (or `annual_fuel_liters`), `occupants`, `radiator_count`, `radiator_size`, `dhw_by_boiler`, `rooms`. "Don't know" → `null`. Example: `contracts/examples/calc_input_form.json`.
- `source[field]`: the target is `"form"`. Until `extract.merge` (`ORDER`) and `engine._field_conf` know `"form"`, the app sends `"text"` (owner-entered, same merge rank and confidence as the old text step) and only the screens say "form". Switch: `app.py` `FORM_MERGE_SRC`.

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
