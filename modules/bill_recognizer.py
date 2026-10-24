"""bill_recognizer: reads a gas/oil/LPG bill and returns the raw numbers as printed (BillObs).

Contract: CONTRACT.md §1-§3, schema contracts/bill.schema.json, example contracts/examples/bill_output_demo.json.
Called in-process by orchestrator.py as run(request) -> reply. Plain Python, no new dependencies. Limit 15 s.
CLI test:  python -m modules.bill_recognizer < request.json

Request: {"file": {"path": "<absolute temp file>", "mime": "application/pdf" | "image/jpeg" | "image/png" | "image/webp"},
          "fuel_hint": "gas" | "lpg" | "oil" | null}

Example of a successful reply (assets/demo/bill_demo_gas_2025.pdf):
    {"ok": True, "module": "bill_recognizer", "version": "1-draft", "warnings": [],
     "data": {"bill_carrier": "Erdgas", "kwh_printed": 18002.0, "m3": 1651.0, "zustandszahl": 0.9523,
              "brennwert": 11.45, "liters": None, "period_start": "2025-01-01", "period_end": "2025-12-31",
              "bill_total_eur": 2462.12, "monthly_advance_eur": 205.0,
              "evidence": {"kwh_printed": "Verbrauch 18.002 kWh"}, "confidence": {"kwh_printed": 0.95},
              "missing": {}, "retake_tip": None}}
"""
from __future__ import annotations

import json
import sys

MODULE = "bill_recognizer"
VERSION = "1-draft"
# TODO(teammate): set to True once run() returns real data. While False the app treats this module as
# "not available" and uses the existing Python reader (the probe {"probe": True} answers `unsupported`).
IMPLEMENTED = False
MIMES = ("application/pdf", "image/jpeg", "image/png", "image/webp")


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
    f = request.get("file") or {}
    if not isinstance(f.get("path"), str) or not isinstance(f.get("mime"), str):
        return fail("bad_input", "file.path and file.mime are required")
    if f["mime"] not in MIMES:
        return fail("unsupported", f"mime {f['mime']} not handled")

    # TODO(teammate): read the file at f["path"] (PDF text or image) and fill the fields below.
    #   Raw numbers AS PRINTED. No conversion: don't turn m³ into kWh, don't scale the period to a year.
    #   Unknown = None (never 0 or ""). Numbers are floats, dates ISO "YYYY-MM-DD".
    #   data = {
    #       "bill_carrier": None,          # str as printed, e.g. "Erdgas", "Heizöl", "Flüssiggas"
    #       "kwh_printed": None,           # float, kWh printed for the bill period
    #       "m3": None,                    # float, gas volume m³
    #       "zustandszahl": None,          # float, e.g. 0.9523
    #       "brennwert": None,             # float, kWh/m³, e.g. 11.45
    #       "liters": None,                # float, oil/LPG litres
    #       "period_start": None,          # "YYYY-MM-DD"
    #       "period_end": None,            # "YYYY-MM-DD"
    #       "bill_total_eur": None,        # float, display only
    #       "monthly_advance_eur": None,   # float, new monthly payment (Abschlag)
    #       "evidence": {},                # field -> snippet it came from, e.g. {"kwh_printed": "Verbrauch 18.002 kWh"}
    #       "confidence": {},              # field -> 0..1
    #       "missing": {},                 # field -> "not_visible" | "blurry" | "ambiguous" | "wrong_object"
    #       "retake_tip": None,            # one concrete sentence when something was unreadable
    #   }
    #   return ok(data)
    # Can't read it → return fail("unreadable", "no kWh found")
    return fail("unsupported", "skeleton: not implemented yet")


if __name__ == "__main__":
    try:
        reply = run(json.loads(sys.stdin.read()))
    except ValueError:
        reply = fail("bad_input", "stdin is not JSON")
    except Exception as e:  # noqa: BLE001
        reply = fail("internal", f"{type(e).__name__}: {e}")
    print(json.dumps(reply, ensure_ascii=False, indent=2))
