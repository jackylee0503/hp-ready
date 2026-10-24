"""calculation: House → Result (replaces engine.py evaluate + installer_brief when it works).

Contract: CONTRACT.md §1-§3, schemas contracts/house.schema.json and contracts/result.schema.json,
examples contracts/examples/calc_input_B-04/B-05/form.json → calc_output_B-04/B-05.json (today's engine.py).
Called in-process by orchestrator.py as run(request) -> reply. Plain Python, no new dependencies. Limit 20 s.
Deterministic: use `seed` for the Monte Carlo.
CLI test:  python -m modules.calculation < contracts/examples/calc_input_B-05.json

Request: {"house": House (dict, see contracts/house.schema.json), "n": 500, "seed": 0}

Example of a successful reply:
    {"ok": True, "module": "calculation", "version": "1-draft", "warnings": [],
     "data": <contents of contracts/examples/calc_output_B-05.json>}
Check it: CONTRACT.md §5 (Result.model_validate + schema.check_result).
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

    # TODO(teammate): compute the Result from h. Rules: CLAUDE.md "Engine" (fixed prices and JAZ, 55/60 °C bands,
    #   missing data → yellow "cannot_tell_yet", never red). Fuel precedence: bill raw values (kwh_printed, else
    #   m3 × zustandszahl × brennwert, liters × 10, scaled to 365 days) → annual_fuel_kwh → annual_fuel_liters × 10
    #   → monthly_advance_eur. Tip: `from schema import House, Result; House.model_validate(h)` gives typed access,
    #   and `Result(...).model_dump(mode="json")` gives a valid reply. Fields the UI reads (else it shows "–"):
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
