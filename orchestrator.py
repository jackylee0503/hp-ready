"""Orchestrator: calls the three input/result modules through one registry (CONTRACT.md §6). No Streamlit import.

Each module is a Python function `run(request: dict) -> dict` that returns the CONTRACT.md envelope
{"ok", "module", "version", "data" | "error"}. Default implementations live in `modules/`; any entry can be pointed
elsewhere without editing this file:  HP_MODULE_CALCULATION="ml.predict:run"  (also _BILL_RECOGNIZER, _IMAGE_VALIDATION).

Never raises: every failure becomes an ok=False envelope, and the public helpers fall back to the Python readers
(extract.py) or return None so app.py falls back to engine.py → engine_tracer.py.

Env switches:
  HP_MODULES=0       no module calls at all (everything uses the existing Python path)
  HP_MODULES_ONLY=1  no fallback for the inputs (bill, radiator photo): for testing a teammate's module
"""
from __future__ import annotations

import importlib
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

from schema import BillObs, House, ImageCheck, RadiatorObs, Result

ROOT = Path(__file__).parent
REGISTRY = {"bill_recognizer": "modules.bill_recognizer:run",
            "image_validation": "modules.image_validation:run",
            "calculation": "modules.calculation:run"}
LIMIT_S = {"image_validation": 5, "bill_recognizer": 15, "calculation": 20}     # CONTRACT.md §1 (warning only)
VERSION = "1-draft"
EXT = {"application/pdf": ".pdf", "image/jpeg": ".jpg", "image/jpg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
# ImageCheck.reason → House.missing reason (schema MissingReason)
MISSING_OF = {"blurry": "blurry", "wrong_object": "wrong_object", "too_dark": "not_visible", "too_bright": "not_visible",
              "too_small": "not_visible", "unreadable": "not_visible", "unsupported_type": "not_visible"}
RETAKE_DEFAULT = {"blurry": "Hold the phone still and tap to focus, then take it again.",
                  "too_dark": "Turn on the light or move closer to a window, then take it again.",
                  "too_bright": "Avoid direct sunlight or flash on it, then take it again.",
                  "too_small": "Move closer so it fills most of the picture.",
                  "wrong_object": "That doesn't look like the right thing. Please take a photo of it again.",
                  "unreadable": "We couldn't open that file. Try a JPG or PNG photo.",
                  "unsupported_type": "Please send a JPG, PNG or PDF."}

LAST: dict[str, dict] = {}       # module -> last envelope (debugging in a REPL)


def _flag(var: str, default: str) -> bool:
    return os.environ.get(var, default).strip().lower() in ("1", "true", "yes", "on")


def modules_enabled() -> bool:
    return _flag("HP_MODULES", "1")


def modules_only() -> bool:
    return _flag("HP_MODULES_ONLY", "0")


def spec(name: str) -> str:
    """"pkg.mod:func" for a module name; env var HP_MODULE_<NAME> overrides the registry."""
    return os.environ.get(f"HP_MODULE_{name.upper()}") or REGISTRY.get(name, "")


def _mtime(p) -> float:
    try:
        return Path(p).stat().st_mtime
    except (OSError, TypeError):
        return 0.0


_LOADED: dict[str, float] = {}   # python module name -> mtime when (re)loaded


def _resolve(name: str):
    """→ (callable, file path). Lazy import; reload when the file changed since the last call. Raises on failure."""
    s = spec(name)
    if ":" not in s:
        raise ImportError(f"no registry entry for {name!r} (got {s!r})")
    mod_name, func = s.split(":", 1)
    if mod_name in sys.modules:
        mod = sys.modules[mod_name]
        f = getattr(mod, "__file__", None)
        if f and _mtime(f) != _LOADED.get(mod_name):
            importlib.invalidate_caches()
            mod = importlib.reload(mod)
    else:
        importlib.invalidate_caches()
        mod = importlib.import_module(mod_name)
    f = getattr(mod, "__file__", None)
    _LOADED[mod_name] = _mtime(f)
    fn = getattr(mod, func, None)
    if not callable(fn):
        raise ImportError(f"{mod_name} has no callable {func}")
    return fn, f


def _fail(name: str, code: str, message: str) -> dict:
    return {"ok": False, "module": name, "version": VERSION, "error": {"code": code, "message": str(message)[:500]}}


def run_module(name: str, request: dict) -> dict:
    """Call the registered run(request) in-process → envelope dict. Never raises.
    Failure codes added here: missing (disabled / not importable), internal (exception or bad envelope)."""
    if not modules_enabled():
        return _fail(name, "missing", "modules disabled (HP_MODULES=0)")
    try:
        fn, _ = _resolve(name)
    except Exception as e:
        return _fail(name, "missing", f"import failed: {type(e).__name__}: {e}")
    t0 = time.perf_counter()
    try:
        env = fn(request)
    except Exception as e:
        return _fail(name, "internal", f"{type(e).__name__}: {e}")
    dt = time.perf_counter() - t0
    if not isinstance(env, dict) or not isinstance(env.get("ok"), bool):
        return _fail(name, "internal", f"reply is not an envelope ({type(env).__name__})")
    env = dict(env)
    if not env["ok"] and not isinstance(env.get("error"), dict):
        env["error"] = {"code": "internal", "message": "ok=false without error"}
    env.setdefault("module", name)
    env["warnings"] = list(env.get("warnings") or [])
    env["elapsed_s"] = round(dt, 3)
    if dt > LIMIT_S.get(name, 20):
        env["warnings"].append(f"took {dt:.1f} s, over the {LIMIT_S.get(name, 20)} s limit (CONTRACT.md §1)")
    LAST[name] = env
    return env


_AVAIL: dict[tuple, bool] = {}


def available(name: str) -> bool:
    """Importable and does not answer the probe {"probe": true} with `unsupported` (= skeleton). Cached per mtime."""
    if not modules_enabled():
        return False
    try:
        _, f = _resolve(name)
    except Exception:
        return False
    key = (name, spec(name), _mtime(f))
    if key not in _AVAIL:
        env = run_module(name, {"probe": True})
        code = (env.get("error") or {}).get("code")
        _AVAIL[key] = bool(env.get("ok")) or code in ("bad_input", "unreadable")   # replied sensibly = implemented
    return _AVAIL[key]


def cache_tag() -> str:
    """Part of app.py's result cache key: editing a module (or the switches) must not serve stale results."""
    parts = []
    for n in REGISTRY:
        s = spec(n)
        mod = sys.modules.get(s.split(":")[0])
        f = getattr(mod, "__file__", None) if mod else None
        if not f:                                # not imported yet: guess the file from the dotted name
            f = ROOT / (s.split(":")[0].replace(".", "/") + ".py")
        parts.append(f"{n}={s}@{_mtime(f)}")
    return "|".join(parts) + f"|on={modules_enabled()}|only={modules_only()}"


def _with_file(data: bytes, mime: str, fn):
    """Write the upload to a temp file, call fn({"path", "mime"}), always delete it."""
    d = tempfile.mkdtemp(prefix="hpready-")
    try:
        p = Path(d) / ("upload" + EXT.get(mime, ".bin"))
        p.write_bytes(data)
        return fn({"path": str(p), "mime": mime})
    finally:
        shutil.rmtree(d, ignore_errors=True)


def _is_image(data: bytes, mime: str) -> bool:
    return (mime or "").startswith("image/") and data[:4] != b"%PDF"


def _err(env: dict) -> str:
    e = env.get("error") or {}
    return f"{env.get('module')}: {e.get('code')} ({e.get('message')})"


# ---------------------------------------------------------------- inputs


def validate_image(data: bytes, mime: str, expected: str) -> ImageCheck | None:
    """image_validation → ImageCheck. None when the module is unavailable or failed (caller just skips the check)."""
    if not available("image_validation"):
        return None
    env = _with_file(data, mime, lambda f: run_module("image_validation", {"file": f, "expected": expected}))
    if not env.get("ok"):
        return None
    try:
        return ImageCheck.model_validate({"expected": expected, **(env.get("data") or {})})
    except Exception:
        return None


def unusable_house(chk: ImageCheck, field: str) -> House:
    h = House()
    h.missing = {field: MISSING_OF.get(chk.reason, "not_visible")}
    h.retake_tip = chk.retake_tip or RETAKE_DEFAULT.get(chk.reason, "Please take the photo again.")
    return h


def _python_read(data: bytes, mime: str, mission: str) -> tuple[House | None, str]:
    if modules_only():
        return None, "HP_MODULES_ONLY=1: fallback reader disabled"
    try:
        import extract
        return extract.extract(data, mime, mission), "python"
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


def recognize_bill(data: bytes, mime: str, fuel_hint: str | None = None) -> tuple[House | None, str]:
    """(house, "module") | (house, "python") | (None, reason).
    Image → image_validation first; then bill_recognizer → BillObs → House; else extract.py (cache/LLM path)."""
    import extract
    if _is_image(data, mime):
        chk = validate_image(data, mime, "bill")
        if chk is not None and not chk.usable:
            return unusable_house(chk, "kwh_printed"), "module"
    why = "bill_recognizer not available"
    if available("bill_recognizer"):
        env = _with_file(data, mime, lambda f: run_module("bill_recognizer", {"file": f, "fuel_hint": fuel_hint}))
        if env.get("ok"):
            try:
                return extract.obs_to_house("bill", BillObs.model_validate(env.get("data") or {})), "module"
            except Exception as e:
                why = f"bill_recognizer: reply does not match BillObs ({type(e).__name__}: {e})"
        else:
            why = _err(env)
    h, how = _python_read(data, mime, "bill")
    return (h, how) if h is not None else (None, f"{why}; fallback: {how}")


def check_radiator_photo(data: bytes, mime: str) -> tuple[House | None, str]:
    """(house, "module") | (house, "python") | (None, reason). image_validation first; its `radiator` reading if any."""
    import extract
    chk = validate_image(data, mime, "radiator") if _is_image(data, mime) else None
    why = "image_validation not available"
    if chk is not None:
        if not chk.usable:
            return unusable_house(chk, "radiator_size"), "module"
        if chk.radiator is not None:
            try:
                return extract.obs_to_house("radiator", RadiatorObs.model_validate(chk.radiator.model_dump())), "module"
            except Exception as e:
                why = f"image_validation: bad radiator reading ({e})"
        else:
            why = "photo usable, image_validation gave no radiator reading"
    h, how = _python_read(data, mime, "radiator")
    return (h, how) if h is not None else (None, f"{why}; fallback: {how}")


# ---------------------------------------------------------------- result


def calculate(h: House, n: int = 500, seed: int = 0) -> tuple[Result | None, str, str | None]:
    """calculation → Result. (result, "module", None) or (None, "module", error); the app then uses engine.py."""
    if not available("calculation"):
        return None, "module", "calculation not available"
    env = run_module("calculation", {"house": h.model_dump(mode="json"), "n": n, "seed": seed})
    if not env.get("ok"):
        return None, "module", _err(env)
    try:
        return Result.model_validate(env.get("data")), "module", None
    except Exception as e:
        return None, "module", f"calculation: reply does not match Result ({type(e).__name__}: {str(e)[:200]})"


if __name__ == "__main__":                    # python orchestrator.py → status of the three modules
    print("HP_MODULES:", modules_enabled(), "| HP_MODULES_ONLY:", modules_only())
    for m in REGISTRY:
        env = run_module(m, {"probe": True})
        print(f"{m:17s} {spec(m):38s} available={available(m)!s:5s} probe → ok={env.get('ok')} {env.get('error') or ''}")
