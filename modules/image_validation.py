"""image_validation: says whether a photo is USABLE (sharp, bright, right object), not what it means (ImageCheck).

Contract: CONTRACT.md §1-§3, schema contracts/image_check.schema.json,
examples contracts/examples/image_check_ok.json, image_check_blurry.json.
Called in-process by orchestrator.py as run(request) -> reply. Plain Python, no new dependencies
(Pillow and numpy are already installed). Limit 5 s.
CLI test:  python -m modules.image_validation < request.json

Request: {"file": {"path": "<absolute temp file>", "mime": "image/jpeg" | "image/png" | "image/webp"},
          "expected": "radiator" | "bill" | "exterior"}

Example of a successful reply:
    {"ok": True, "module": "image_validation", "version": "1-draft", "warnings": [],
     "data": {"expected": "radiator", "usable": False, "reason": "blurry",
              "retake_tip": "Hold the phone still and tap the radiator to focus, then take it again.",
              "width_px": 1568, "height_px": 1176, "sharpness": 18.0, "brightness": 0.47, "radiator": None}}
"""
from __future__ import annotations

import json
import sys

MODULE = "image_validation"
VERSION = "1-draft"
# TODO(teammate): set to True once run() returns real data. While False the app treats this module as
# "not available" and skips the photo check (the probe {"probe": True} answers `unsupported`).
IMPLEMENTED = False
EXPECTED = ("radiator", "bill", "exterior")
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
    if request.get("expected") not in EXPECTED:
        return fail("bad_input", "expected must be radiator | bill | exterior")
    if f["mime"] not in MIMES:
        return fail("unsupported", f"mime {f['mime']} not handled")

    # TODO(teammate): open the image at f["path"] and fill the fields below.
    #   data = {
    #       "expected": request["expected"],
    #       "usable": True,              # False → the app shows retake_tip and keeps nothing from this photo
    #       "reason": "ok",              # "ok" | "blurry" | "too_dark" | "too_bright" | "too_small" | "wrong_object"
    #                                    # | "unreadable" | "unsupported_type"
    #       "retake_tip": None,          # one concrete sentence when not usable
    #       "width_px": None,            # int
    #       "height_px": None,           # int
    #       "sharpness": None,           # module-defined (e.g. Laplacian variance); higher = sharper
    #       "brightness": None,          # mean 0..1
    #       "radiator": None,            # optional, only if you can REALLY tell (RadiatorObs):
    #                                    #   {"panel_type": "11"|"22"|"33"|None, "radiator_size": "small"|"medium"|"large"|None,
    #                                    #    "valve_type": None, "pipe_system": "two_pipe"|"single_pipe"|None,
    #                                    #    "pipe_reason": None, "evidence": {}, "confidence": {}, "missing": {},
    #                                    #    "retake_tip": None}
    #                                    #   pipe_system stays None unless sure (organiser photo 07 must stay None).
    #   }
    #   return ok(data)
    return fail("unsupported", "skeleton: not implemented yet")


if __name__ == "__main__":
    try:
        reply = run(json.loads(sys.stdin.read()))
    except ValueError:
        reply = fail("bad_input", "stdin is not JSON")
    except Exception as e:  # noqa: BLE001
        reply = fail("internal", f"{type(e).__name__}: {e}")
    print(json.dumps(reply, ensure_ascii=False, indent=2))
