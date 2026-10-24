"""pipe_classifier (ML module 1): radiator photo → single-pipe vs two-pipe heating (RadiatorObs).

Two readers behind one switch, HP_PIPE_BACKEND:
  llm  (default)  Claude vision with the organiser's cue table, the same reader as extract.py's "radiator" mission:
                  committed demo cache first, then one live call. Built like bill_recognizer (decision 2026-10-24).
  clip            the teammate's few-shot CLIP prototypes (image_rec.py + prototypes.json). Needs torch and
                  transformers and the CLIP weights already downloaded; this module never downloads them
                  (CONTRACT §1: no network), so on Streamlit Cloud it answers `unsupported` and the app falls back.
Measure before switching a reader on (Invariant 8):  python -m modules.pipe_classifier --eval [--backend clip]
  scores it on the 5 installer-labelled organiser photos. Rule: 0 wrong, and 07 must stay None (unknown).
  2026-10-24: llm = 3 right, 2 "can't tell" (10, 07), 0 wrong. clip: its own leave-one-out in prototypes.json is
  0.2 (1 of 5, and that one is the single "ambiguous" photo compared with itself), so it stays off.

Contract: CONTRACT.md §1-§3, schema contracts/pipe.schema.json, examples contracts/examples/pipe_output_two_pipe.json,
pipe_output_single_pipe.json, pipe_output_unknown.json.
Called in-process by orchestrator.py as run(request) -> reply. Limit 10 s.
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
    {"ok": True, "module": "pipe_classifier", "version": "1-llm", "warnings": [],
     "data": {"pipe_system": "two_pipe", "pipe_reason": None, "panel_type": "22", "radiator_size": None,
              "valve_type": None, "confidence": {"pipe_system": 0.8},
              "evidence": {"pipe_system": "valve at the top, separate return at the bottom, two pipes into the floor"},
              "missing": {}, "retake_tip": None}}
  unknown (photo 07):
    {"ok": True, ..., "data": {"pipe_system": None, "confidence": {"pipe_system": 0.0},
              "evidence": {"pipe_system": "bathroom valve block, exists for both systems"}, "missing": {}, ...}}
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

MODULE = "pipe_classifier"
VERSION = "1-llm"
IMPLEMENTED = True
MIMES = ("image/jpeg", "image/png", "image/webp")
ROOT = Path(__file__).resolve().parents[1]
CLIP_MODEL = "openai/clip-vit-base-patch32"
LABEL = {"two-pipe": "two_pipe", "single-pipe": "single_pipe"}   # image_rec.py labels → contract enum; else None


def ok(data, warnings=None, version=VERSION) -> dict:
    return {"ok": True, "module": MODULE, "version": version, "data": data, "warnings": warnings or []}


def fail(code: str, message: str) -> dict:
    """code: bad_input | unreadable | unsupported | internal"""
    return {"ok": False, "module": MODULE, "version": VERSION, "error": {"code": code, "message": message}}


def backend() -> str:
    return os.environ.get("HP_PIPE_BACKEND", "llm").strip().lower() or "llm"


# ---------------------------------------------------------------- reader 1: Claude vision (default)

def _llm(path: str, mime: str) -> dict:
    from extract import read_obs             # committed cache first, then one live Claude call
    with open(path, "rb") as fh:
        kind, obs = read_obs(fh.read(), mime, "radiator")
    if kind != "radiator":
        return fail("unsupported", f"this looks like a {kind}, not a radiator")
    return ok(obs.model_dump(mode="json"))


# ---------------------------------------------------------------- reader 2: CLIP few-shot (image_rec.py, off by default)

def clip_ready() -> str | None:
    """None when CLIP can run here without downloading anything, else the reason it can't."""
    for pkg in ("torch", "transformers"):
        if importlib.util.find_spec(pkg) is None:
            return f"{pkg} not installed"
    if not (ROOT / "prototypes.json").exists():
        return "prototypes.json missing (python image_rec.py --train <dir>)"
    try:
        from huggingface_hub import try_to_load_from_cache
        hit = try_to_load_from_cache(os.environ.get("CLIP_MODEL", CLIP_MODEL), "config.json")
        if not isinstance(hit, str):
            return "CLIP weights not downloaded (run python image_rec.py <photo> once while online)"
    except Exception as e:  # noqa: BLE001
        return f"cannot check the CLIP weights ({type(e).__name__})"
    return None


def _clip(path: str) -> dict:
    os.environ.setdefault("HF_HUB_OFFLINE", "1")                       # never download inside a module call
    os.environ.setdefault("PIPE_PROTOTYPES", str(ROOT / "prototypes.json"))
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    import image_rec
    ev = image_rec.classify_pipes([path])
    photo = (ev.per_photo or [{}])[0]
    if str(photo.get("reason", "")).startswith("could not be analysed"):
        return fail("unreadable", photo["reason"])
    value = LABEL.get(ev.verdict)
    if value:
        why = f"closest to the {ev.verdict} example photos (CLIP image match, margin {photo.get('margin', 0):.3f})"
    elif photo.get("top_class") == image_rec.AMBIGUOUS:
        why = "closest to the can't-tell examples (valve block or cover); the photo does not show the system"
    else:
        why = "the photo is not clear enough to tell single-pipe from two-pipe"
    data = {"pipe_system": value, "pipe_reason": why, "confidence": {"pipe_system": ev.confidence if value else 0.0},
            "evidence": {"pipe_system": why}, "missing": {}, "retake_tip": None}
    return ok(data, version="1-clip")


# ---------------------------------------------------------------- entry

def run(request: dict) -> dict:
    if not isinstance(request, dict):
        return fail("bad_input", "request must be a JSON object")
    b = backend()
    if request.get("probe"):
        if not IMPLEMENTED:
            return fail("unsupported", "not enabled")
        if b == "clip":
            why = clip_ready()
            return ok(None) if why is None else fail("unsupported", f"clip: {why}")
        return ok(None)
    f = request.get("file") or {}
    if not isinstance(f.get("path"), str) or not isinstance(f.get("mime"), str):
        return fail("bad_input", "file.path and file.mime are required")
    if f["mime"] not in MIMES:
        return fail("unsupported", f"mime {f['mime']} not handled")
    _ = request.get("hint")                     # context only, never copied into the reply
    try:
        if b == "clip":
            why = clip_ready()
            return fail("unsupported", f"clip: {why}") if why else _clip(f["path"])
        return _llm(f["path"], f["mime"])
    except Exception as e:  # noqa: BLE001  (no key, network, unreadable image, CLIP error …)
        return fail("unreadable", f"{type(e).__name__}: {e}"[:300])


def evaluate(which: str | None = None) -> list[dict]:
    """Score a reader on the 5 installer-labelled organiser photos (Invariant 8). → one row per photo."""
    if which:
        os.environ["HP_PIPE_BACKEND"] = which
    labels = json.loads((ROOT / "data" / "pipe_photos" / "labels.json").read_text(encoding="utf-8"))["photos"]
    want_of = {"single-pipe": "single_pipe", "two-pipe": "two_pipe", "unknown": None}
    rows = []
    for p in labels:
        path = ROOT / "data" / "pipe_photos" / p["file"]
        mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
        rep = run({"file": {"path": str(path), "mime": mime}})
        want = want_of[p["pipe_system"]]
        got = (rep.get("data") or {}).get("pipe_system") if rep.get("ok") else "error"
        outcome = "right" if got == want else "error" if got == "error" else "can't tell" if got is None else "WRONG"
        d = rep.get("data") or {}
        rows.append({"photo": p["file"][:2], "installer": want, "read": got, "outcome": outcome,
                     "why": (d.get("evidence") or {}).get("pipe_system") or d.get("pipe_reason")
                     or (rep.get("error") or {}).get("message")})
    return rows


if __name__ == "__main__":
    if "--eval" in sys.argv:
        which = sys.argv[sys.argv.index("--backend") + 1] if "--backend" in sys.argv else None
        rows = evaluate(which)
        for r in rows:
            print(f"{r['photo']}  installer={str(r['installer']):12} read={str(r['read']):12} {r['outcome']:10} {r['why'] or ''}"[:200])
        n = {k: sum(r["outcome"] == k for r in rows) for k in ("right", "can't tell", "WRONG", "error")}
        seven = next(r for r in rows if r["photo"] == "07")
        unsure = n["can't tell"]
        verdict = "OK to switch on" if n["WRONG"] == 0 and n["error"] == 0 and seven["read"] is None else "keep it off"
        print(f"backend={backend()}  right {n['right']} · can't tell {unsure} · wrong {n['WRONG']} · error {n['error']}"
              f"  → {verdict}")
        sys.exit(0)
    try:
        reply = run(json.loads(sys.stdin.read()))
    except ValueError:
        reply = fail("bad_input", "stdin is not JSON")
    except Exception as e:  # noqa: BLE001
        reply = fail("internal", f"{type(e).__name__}: {e}")
    print(json.dumps(reply, ensure_ascii=False, indent=2))
