# JSON contract: UI ↔ JS modules (draft v1)

Status: **draft v1** (2026-10-24). Owner: Junwoo (UI + architecture). Change it only together; bump `x-contract-version`.

The Streamlit app (Python) stays the UI. A Python orchestrator calls three JS modules with JSON and gets JSON back:

```
page-1 form ─────────────────────────────────────────────┐
bill upload ──► image-validation.js ──► bill-recognizer.js ┼─► House ──► calculation.js ──► Result ──► 3 tabs
radiator photo ──► image-validation.js ───────────────────┘
```

The JSON shapes are the existing Python models in `schema.py`, exported as JSON Schema:

| Module | Request | Reply `data` | Schema | Examples |
| --- | --- | --- | --- | --- |
| `js/bill-recognizer.js` | `{"file": {...}, "fuel_hint": "gas" \| null}` | `BillObs` | `contracts/bill.schema.json` | `contracts/examples/bill_output_demo.json` |
| `js/image-validation.js` | `{"file": {...}, "expected": "radiator" \| "bill" \| "exterior"}` | `ImageCheck` | `contracts/image_check.schema.json` | `image_check_ok.json`, `image_check_blurry.json` |
| `js/calculation.js` | `{"house": House, "n": 500, "seed": 0}` | `Result` | `contracts/house.schema.json`, `contracts/result.schema.json` | `calc_input_B-04/B-05/form.json` → `calc_output_B-04/B-05.json` |

`file` is always `{"path": "<absolute path to a temp file>", "mime": "application/pdf" | "image/jpeg" | "image/png" | "image/webp"}`. The orchestrator writes the upload to disk; modules never get base64.

## 1. How a module is called

- Command: `node js/<module>.js` with the **request JSON on stdin**. Print **exactly one reply JSON on stdout**; logs go to stderr.
- Also export it for JS-side reuse: `module.exports = { run }` where `run(request) -> reply` (may be async).
- Reply envelope:

```json
{"ok": true,  "module": "bill-recognizer", "version": "1-draft", "data": { /* BillObs */ }, "warnings": []}
{"ok": false, "module": "bill-recognizer", "version": "1-draft", "error": {"code": "unreadable", "message": "no kWh found"}}
```

- `error.code`: `bad_input` (request malformed), `unreadable` (file can't be read), `unsupported` (mime not handled), `internal` (bug).
- Time limits: image-validation 5 s, bill-recognizer 15 s, calculation 20 s. Slower, a non-JSON stdout, or a non-zero exit = failure; the UI then shows "couldn't read that, you can skip" (inputs) or falls back to the Python engine (`engine.py`, then `engine_tracer.py`) for the result, marked on screen.
- No network calls, no storing files, deterministic (`calculation.js` uses `seed`).

## 2. Field rules (all modules)

1. **Exact field names** from the schema files (snake_case), exact enum values (e.g. `"two_pipe"`, `"partially"`, `"green"`).
2. **Unknown = `null`.** Never `0`, `""` or a guess. Lists that are "unknown" are `null`; an explicit "none" is `[]`.
3. Numbers are JSON numbers (not `"18.002"`), dates are ISO `YYYY-MM-DD`, units fixed: kWh, m³, litres, €, m², °C, kW.
4. Extra fields are ignored by the UI; don't rely on them.
5. Per-field provenance where the schema has it: `confidence[field]` 0-1, `evidence[field]` = the snippet the value came from (e.g. `"Verbrauch 18.002 kWh"`).

## 3. Module by module

### bill-recognizer.js → `BillObs`
Reads a gas/oil/LPG bill (PDF text, photo, screenshot) and returns **raw numbers as printed**: `bill_carrier`, `kwh_printed`, `m3`, `zustandszahl`, `brennwert`, `liters`, `period_start`, `period_end`, `bill_total_eur`, `monthly_advance_eur`, plus `confidence`, `evidence`, `missing` (`not_visible` | `blurry` | `ambiguous` | `wrong_object`), `retake_tip`.
- **No conversion.** Don't turn m³ into kWh or scale the period to a year; `calculation.js` does that (fuel precedence: bill raw values → `annual_fuel_kwh` → `annual_fuel_liters × 10` → advance payment).
- Test input: `assets/demo/bill_demo_gas_2025.pdf` and `..._photo.jpg` (expected values in `assets/demo/README.md`: 18,002 kWh, 1,651 m³, Zustandszahl 0.9523, Brennwert 11.450, 2025-01-01 to 2025-12-31, €2,462.12).

### image-validation.js → `ImageCheck`
Says whether a photo is **usable**, not what it means: `usable`, `reason` (`ok` | `blurry` | `too_dark` | `too_bright` | `too_small` | `wrong_object` | `unreadable` | `unsupported_type`), `retake_tip` (one concrete sentence), `width_px`, `height_px`, `sharpness`, `brightness`.
- Optional `radiator` (`RadiatorObs`: `panel_type`, `radiator_size`, `pipe_system`, …) only if the module can really tell; `pipe_system` stays `null` unless sure (organiser photo `07` must stay `null`).
- Test inputs: `data/pipe_photos/*` (labels in `labels.json`), plus any blurred/dark photo.

### calculation.js → `Result`
Input `{"house": House}`. Output a full `Result`; this replaces `engine.py`'s `evaluate` + `installer_brief`.
- The UI reads: `best_color`, `verdict_basis`, `boundary`, `reason`, `p_green/p_yellow/p_red`, `required_flow_temp_c`, `heat_load_kw`, `heat_load_bill_kw` (`{p10, p50, p90}`), `jaz_bucket`, `cost_now_eur`, `cost_hp_eur`, `saving_eur`, `contradictions`, `open_checks`, `trace`, `visit_type`, `parts`, `lead_score`, `next_step`, and the **structured** fields `options`, `radiators`, `flags`, `always_checks` (fill numbers and kinds; the UI writes the sentences).
- Rules: CLAUDE.md "Engine" (fixed prices and JAZ, 55/60 °C bands, missing data → yellow `cannot_tell_yet`, never red).
- Check against the Python engine: `contracts/examples/calc_output_B-04.json` / `B-05.json` are today's results for the same inputs.

## 4. Page-1 form → `House`
The form fills these `House` fields with `source[field] = "form"`, `confidence[field] = 0.9`: `build_year`, `living_area_m2`, `building_type`, `renovation`, `heat_distribution`, `fuel_type`, `annual_fuel_kwh` (or `annual_fuel_liters`), `occupants`, `radiator_count`, `radiator_size`, `dhw_by_boiler`, `rooms`. "Don't know" → `null`. Example: `contracts/examples/calc_input_form.json`.

## 5. Check your output

```bash
node js/calculation.js < contracts/examples/calc_input_B-05.json > out.json
python -c "import json; from schema import Result, check_result, House; d=json.load(open('out.json')); r=Result.model_validate(d['data']); h=House.model_validate(json.load(open('contracts/examples/calc_input_B-05.json'))['house']); print(check_result(h, r) or 'OK')"
```

Any JSON Schema validator works too, e.g. `npx ajv-cli validate -s contracts/result.schema.json -d <data-only.json>`.
After a change to `schema.py`: `python schema.py --export-contracts` regenerates `contracts/`.
