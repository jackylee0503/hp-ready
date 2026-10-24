"""pipe_classifier (ML module 1): radiator photo → single-pipe vs two-pipe heating (RadiatorObs).

Contract: CONTRACT.md §1-§3, schema contracts/pipe.schema.json, examples contracts/examples/pipe_output_two_pipe.json,
pipe_output_single_pipe.json, pipe_output_unknown.json.
Called in-process by orchestrator.py as run(request) -> reply. Plain Python, no new dependencies
(Pillow and numpy are already installed). Limit 10 s.
CLI test:  python -m modules.pipe_classifier < request.json
Test set: data/pipe_photos/* with installer-confirmed labels in data/pipe_photos/labels.json
          (06, 11 single-pipe; 05, 10 two-pipe; 07 unknown → pipe_system MUST stay None).

Request: {"file": {"path": "<absolute temp file>", "mime": "image/jpeg" | "image/png" | "image/webp"},
          "hint": {"build_year": 1972 | None}}          # hint is optional context, never copy it into the reply

Main output: pipe_system "two_pipe" | "single_pipe" | None (None = unsure; never a guess),
with confidence["pipe_system"] 0..1 and evidence["pipe_system"] = a short reason.
Photo unusable (blurry, dark, not a radiator …) → pipe_system None, missing {"pipe_system": reason}, retake_tip.

Example replies:
  two-pipe (photo 05):
    {"ok": True, "module": "pipe_classifier", "version": "1-draft", "warnings": [],
     "data": {"pipe_system": "two_pipe", "pipe_reason": None, "panel_type": "22", "radiator_size": None,
              "valve_type": None, "confidence": {"pipe_system": 0.8},
              "evidence": {"pipe_system": "valve at the top, separate return at the bottom, two pipes into the floor"},
              "missing": {}, "retake_tip": None}}
  single-pipe (photo 06):
    {"ok": True, ..., "data": {"pipe_system": "single_pipe", "confidence": {"pipe_system": 0.75},
              "evidence": {"pipe_system": "one pipe along the wall, tapped by a fitting at the radiator"}, ...}}
  unknown (photo 07):
    {"ok": True, ..., "data": {"pipe_system": None, "confidence": {"pipe_system": 0.0},
              "evidence": {"pipe_system": "bathroom valve block, exists for both systems"}, "missing": {}, ...}}
  unusable photo:
    {"ok": True, ..., "data": {"pipe_system": None, "missing": {"pipe_system": "blurry"},
              "retake_tip": "Hold the phone still and tap the pipes to focus, then take it again.", ...}}
"""
from __future__ import annotations

import json
import sys

MODULE = "pipe_classifier"
VERSION = "1-draft"
# TODO(teammate): set to True once run() returns real data. While False the app treats this module as
# "not available" and uses the cache-only fallback (the probe {"probe": True} answers `unsupported`).
IMPLEMENTED = False
MIMES = ("image/jpeg", "image/png", "image/webp")


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
    hint = request.get("hint") or {}            # optional: {"build_year": int | None}
    _ = hint

    # TODO(teammate): open the image at f["path"], classify the pipe system and fill the fields below.
    #   data = {
    #       "pipe_system": None,         # "two_pipe" | "single_pipe" | None (unsure → None; photo 07 must be None)
    #       "pipe_reason": None,         # optional, same as evidence["pipe_system"]
    #       "panel_type": None,          # optional "11" | "22" | "33", only if you can really tell
    #       "radiator_size": None,       # optional "small" | "medium" | "large"
    #       "valve_type": None,          # optional free text
    #       "confidence": {},            # {"pipe_system": 0..1}
    #       "evidence": {},              # {"pipe_system": "short reason, e.g. 'H-block with side bypass port'"}
    #       "missing": {},               # photo unusable: {"pipe_system": "blurry" | "not_visible" | "ambiguous"
    #                                    #                                 | "wrong_object"}
    #       "retake_tip": None,          # one concrete sentence when unusable
    #   }
    #   return ok(data)
    # Can't open the file at all → return fail("unreadable", "...")
    return fail("unsupported", "skeleton: not implemented yet")


if __name__ == "__main__":
    try:
        reply = run(json.loads(sys.stdin.read()))
    except ValueError:
        reply = fail("bad_input", "stdin is not JSON")
    except Exception as e:  # noqa: BLE001
        reply = fail("internal", f"{type(e).__name__}: {e}")
    print(json.dumps(reply, ensure_ascii=False, indent=2))
