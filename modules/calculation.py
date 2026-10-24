"""calculation (ML module 3): House → Result (replaces engine.py evaluate + installer_brief when it works).
Owns internal contradictions: Result.contradictions = cross-field inconsistencies it finds (bill vs area-age load,
wood stove all winter, rooms vs area, …). Input conflicts (the same field from two sources, e.g. form says oil, bill
says gas) are not its job: the UI asks the homeowner before calculation, the House arrives with the resolved values,
and House.conflicts lists them for context.

MVP (CONTRACT.md "MVP: what `calculation` must return") — the reply `data` needs ONLY:
    best_color                         "green" | "yellow" | "red"
    p_green, p_yellow, p_red           0..1, sum ≈ 1 (p_red ≥ 0.5 ⇒ best_color "red")
    heat load (watts)                  quantity {"key": "heat_load_kw", "p10", "p50", "p90"} (kW)
                                       or legacy "heat_load_kw": {"p10", "p50", "p90"}
    flow temperature                   quantity {"key": "flow_temp_c", "p10", "p50", "p90"} (°C, coldest day)
                                       or legacy "required_flow_temp_c": {"p10", "p50", "p90"}
Minimal valid `data`: contracts/examples/calc_output_minimal.json. Everything else (reason, verdict_basis,
open_checks, explanations, trace, contradictions, model_info, costs, installer fields, …) is optional: the UI uses it
when present and hides the section otherwise (a missing reason becomes a neutral sentence from colour + temperature).

Contract: CONTRACT.md "MVP" + §1-§3, schemas contracts/house.schema.json and contracts/result.schema.json,
fuller examples contracts/examples/calc_input_B-04/B-05/form.json → calc_output_B-04/B-05.json (today's engine.py).
Called in-process by orchestrator.py as run(request) -> reply. Plain Python, no new dependencies. Limit 20 s.
Deterministic: use `seed` for any sampling.
CLI test:  python -m modules.calculation < contracts/examples/calc_input_B-05.json

Request: {"house": House (dict, see contracts/house.schema.json), "n": 500, "seed": 0}

Example of a successful (minimal) reply:
    {"ok": True, "module": "calculation", "version": "0.1", "warnings": [],
     "data": <contents of contracts/examples/calc_output_minimal.json>}
Check it: CONTRACT.md §5 (Result.model_validate + schema.check_result → [] when the MVP core is fine).
"""
from __future__ import annotations

import json
import sys

MODULE = "calculation"
VERSION = "1-draft"
# TODO(teammate): set to True once run() returns a full Result. While False the app treats this module as
# "not available" and uses engine.py (the probe {"probe": True} answers `unsupported`).
IMPLEMENTED = False


def ok(data, warnings=None) -> dict:
    return {"ok": True, "module": MODULE, "version": VERSION, "data": data, "warnings": warnings or []}


def fail(code: str, message: str) -> dict:
    """code: bad_input | unreadable | unsupported | internal"""
    return {"ok": False, "module": MODULE, "version": VERSION, "error": {"code": code, "message": message}}


def run(request: dict) -> dict:
    if not isinstance(request, dict):
        return fail("bad_input", "request must be a JSON object")
    if request.get("probe"):
        return ok(None) if IMPLEMENTED else fail("unsupported", "skeleton: not implemented yet")
    h = request.get("house")
    if not isinstance(h, dict):
        return fail("bad_input", "house object is required")
    n = request.get("n") if isinstance(request.get("n"), int) else 500
    seed = request.get("seed") if isinstance(request.get("seed"), int) else 0

    # TODO(teammate): compute the MVP core from h first — that alone is a complete reply:
    #   data = {
    #       "best_color": "green",                                   # "green" | "yellow" | "red"
    #       "p_green": 0.72, "p_yellow": 0.18, "p_red": 0.10,        # sum to 1
    #       "quantities": [
    #           {"key": "heat_load_kw", "p10": 7.8, "p50": 9.3, "p90": 11.0},   # kW
    #           {"key": "flow_temp_c", "p10": 48.0, "p50": 53.0, "p90": 58.0},  # °C on the coldest day
    #       ],
    #   }
    #   return ok(data)
    # Rules: CLAUDE.md "Engine" (55/60 °C bands; missing data → yellow, never red). Fuel precedence: bill raw values
    #   (kwh_printed, else m3 × zustandszahl × brennwert, liters × 10, scaled to 365 days) → annual_fuel_kwh →
    #   annual_fuel_liters × 10 → monthly_advance_eur. Tip: `from schema import House, Result; House.model_validate(h)`
    #   gives typed access. Then IMPLEMENTED = True.
    # Optional extras (the UI uses them when present, hides the section otherwise):
    #   data = {
    #       "building_id": h.get("building_id"),
    #       "best_color": "green",           # "green" | "yellow" | "red" (always set)
    #       "traffic_light": "green",        # adds "unclear"
    #       "verdict_basis": "likely_suitable",  # | "checks_remain" | "cannot_tell_yet" | "obstacle"
    #       "boundary": False,               # max colour probability < 0.6
    #       "reason": "",                    # one sentence for the homeowner
    #       "p_green": 0.0, "p_yellow": 0.0, "p_red": 0.0,          # sum to 1
    #       "required_flow_temp_c": {"p10": None, "p50": None, "p90": None},
    #       "heat_load_kw": {"p10": None, "p50": None, "p90": None},
    #       "heat_load_bill_kw": {"p10": None, "p50": None, "p90": None},
    #       "jaz_bucket": None,              # "underfloor" | "le55" | "55to60" | "gt60"
    #       "cost_now_eur": None, "cost_hp_eur": None, "saving_eur": None,
    #       "contradictions": [],            # [{"what", "sources": [...], "trusted", "why"}]
    #       "open_checks": [],               # [{"item", "why"}]
    #       "trace": [],                     # Rechenweg: [{"label", "value", "assumption"}]
    #       "visit_type": None,              # "remote_quote" | "visit_with_parts" | "hold"
    #       "parts": {},                     # see result.schema.json Parts
    #       "confidence": 0.0, "lead_score": 0.0,
    #       "next_step": {"kind": "quote", "label": "", "detail": ""},  # quote | site_check | answer_question | path_to_yellow
    #       "options": [], "radiators": None, "flags": [], "always_checks": [],  # structured: numbers + kinds
    #   }
    #   return ok(data)
    del n, seed
    return fail("unsupported", "skeleton: not implemented yet")


if __name__ == "__main__":
    try:
        reply = run(json.loads(sys.stdin.read()))
    except ValueError:
        reply = fail("bad_input", "stdin is not JSON")
    except Exception as e:  # noqa: BLE001
        reply = fail("internal", f"{type(e).__name__}: {e}")
    print(json.dumps(reply, ensure_ascii=False, indent=2))
