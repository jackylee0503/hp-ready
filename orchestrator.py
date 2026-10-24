"""Orchestrator: calls the three ML modules through one registry (CONTRACT.md §6). No Streamlit import.

  1 pipe_classifier   radiator photo → RadiatorObs (single_pipe | two_pipe | None)
  2 bill_recognizer   bill photo/PDF → BillObs (raw numbers as printed)
  3 calculation       House → Result (verdict + internal contradictions)

Each module is a Python function `run(request: dict) -> dict` that returns the CONTRACT.md envelope
{"ok", "module", "version", "data" | "error"}. Default implementations live in `modules/`; any entry can be pointed
elsewhere without editing this file:  HP_MODULE_CALCULATION="ml.predict:run"  (also _BILL_RECOGNIZER, _PIPE_CLASSIFIER).

Never raises: every failure becomes an ok=False envelope, and the public helpers fall back to the cached readers
(extract.py, cache only) or return None so app.py falls back to engine.py → engine_tracer.py.
Invariant 1: a fallback never calls the LLM by itself. Only the page-4 "Read it" button (an explicit request) does.

Env switches:
  HP_MODULES=0        no module calls at all (everything uses the fallback path)
  HP_MODULES_ONLY=1   no fallback for the inputs (bill, radiator photo): for testing a teammate's module
  HP_LLM_FALLBACK=1   the input fallback may call the LLM live when the demo cache has no entry (off by default)
"""
from __future__ import annotations

import importlib
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

from schema import BillObs, House, RadiatorObs, Result

ROOT = Path(__file__).parent
# calculation → modules/screening.py (2026-10-24): engine.py + best/worst-case bounds; it hands every request to the
# ML team's modules/calculation.py as soon as that one is implemented (IMPLEMENTED = True), so their switch still works.
REGISTRY = {"bill_recognizer": "modules.bill_recognizer:run",
            "pipe_classifier": "modules.pipe_classifier:run",
            "calculation": "modules.screening:run"}
LIMIT_S = {"pipe_classifier": 10, "bill_recognizer": 15, "calculation": 20}     # CONTRACT.md §1 (warning only)
VERSION = "1-draft"
EXT = {"application/pdf": ".pdf", "image/jpeg": ".jpg", "image/jpg": ".jpg", "image/png": ".png", "image/webp": ".webp"}

LAST: dict[str, dict] = {}       # module -> last envelope (debugging in a REPL)


def _flag(var: str, default: str) -> bool:
    return os.environ.get(var, default).strip().lower() in ("1", "true", "yes", "on")


def modules_enabled() -> bool:
    return _flag("HP_MODULES", "1")


def modules_only() -> bool:
    return _flag("HP_MODULES_ONLY", "0")


def llm_fallback() -> bool:
    """HP_LLM_FALLBACK=1: the input fallback may call the LLM live. Off by default (Invariant 1)."""
    return _flag("HP_LLM_FALLBACK", "0")


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
    # a registered module may hand over to another file in modules/ (screening → calculation): watch them all
    parts.append("modules=" + ",".join(f"{p.name}@{_mtime(p)}" for p in sorted((ROOT / "modules").glob("*.py"))))
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


def _err(env: dict) -> str:
    e = env.get("error") or {}
    return f"{env.get('module')}: {e.get('code')} ({e.get('message')})"


# ---------------------------------------------------------------- inputs


def _fallback_read(data: bytes, mime: str, mission: str) -> tuple[House | None, str]:
    """The input fallback when a module is unavailable or failed. Invariant 1: cache only (samples/cached_extract.json,
    the committed demo reads), never a live LLM call. HP_LLM_FALLBACK=1 lets it call the LLM on a cache miss.
    → (house, "cache") | (house, "llm") | (None, reason)."""
    if modules_only():
        return None, "HP_MODULES_ONLY=1: fallback reader disabled"
    try:
        import extract
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"
    try:
        return extract.extract(data, mime, mission, cache_only=True), "cache"
    except Exception as e:
        why = f"not in the demo cache ({type(e).__name__})"
    if not llm_fallback():
        return None, why
    try:
        return extract.extract(data, mime, mission), "llm"
    except Exception as e:
        return None, f"{why}; LLM fallback: {type(e).__name__}: {e}"


def recognize_bill(data: bytes, mime: str, fuel_hint: str | None = None) -> tuple[House | None, str]:
    """ML module 2. (house, "module") | (house, "cache" | "llm") | (None, reason).
    bill_recognizer → BillObs → House (photo problems come back in its own missing/retake_tip); else the fallback."""
    import extract
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
    h, how = _fallback_read(data, mime, "bill")
    return (h, how) if h is not None else (None, f"{why}; fallback: {how}")


def classify_pipes(data: bytes, mime: str, build_year: int | None = None) -> tuple[House | None, str]:
    """ML module 1. (house, "module") | (house, "cache" | "llm") | (None, reason).
    pipe_classifier → RadiatorObs (pipe_system, optional panel_type/radiator_size, missing/retake_tip) → House."""
    import extract
    why = "pipe_classifier not available"
    if available("pipe_classifier"):
        req = {"hint": {"build_year": build_year}}
        env = _with_file(data, mime, lambda f: run_module("pipe_classifier", {"file": f, **req}))
        if env.get("ok"):
            try:
                return extract.obs_to_house("radiator", RadiatorObs.model_validate(env.get("data") or {})), "module"
            except Exception as e:
                why = f"pipe_classifier: reply does not match RadiatorObs ({type(e).__name__}: {e})"
        else:
            why = _err(env)
    h, how = _fallback_read(data, mime, "radiator")
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


# ---------------------------------------------------------------- contract v2 helpers (any logic; no Streamlit)

BRIEF_FIELDS = ("visit_type", "parts", "installer_checklist", "next_step", "next_photo", "confidence", "lead_score")


def _brief_empty(r: Result, f: str) -> bool:
    v = getattr(r, f)
    if f == "parts":
        return v is None or (v.radiators_to_swap is None and v.valves is None and v.balancing is None
                             and not v.radiators_note)
    if f in ("confidence", "lead_score"):
        return not v
    return v in (None, [], "")


def fill_installer_brief(h: House, r: Result) -> tuple[Result, bool]:
    """Fill the installer fields a logic left empty (visit_type, parts, installer_checklist, next_step, next_photo,
    confidence, lead_score) from the baseline engine.installer_brief (fallback engine_tracer), run on a copy.
    Never overwrites a field the logic filled. → (result, used_baseline). Never raises."""
    try:
        empty = [f for f in BRIEF_FIELDS if _brief_empty(r, f)]
        if not empty or not any(f in empty for f in ("visit_type", "parts", "installer_checklist", "next_step")):
            return r, False
        from schema import Range, quantity
        tmp = r.model_copy(deep=True)
        if "traffic_light" not in r.model_fields_set:      # not in the v2 core: derive it for the baseline brief only
            tmp.traffic_light = "unclear" if r.verdict_basis == "cannot_tell_yet" else r.best_color
        for key, field in (("flow_temp_c", "required_flow_temp_c"), ("heat_load_kw", "heat_load_kw"),
                           ("heat_load_bill_kw", "heat_load_bill_kw")):
            q = quantity(r, key)                # the baseline brief reads the legacy ranges: hand it the logic's numbers
            if getattr(tmp, field).p50 is None and q is not None:
                setattr(tmp, field, Range(p10=q.p10, p50=q.p50, p90=q.p90))
    except Exception:
        return r, False
    for name in ("engine", "engine_tracer"):
        try:
            b = importlib.import_module(name).installer_brief(h, tmp)
            out = r.model_copy(deep=True)
            for f in empty:
                setattr(out, f, getattr(b, f))
            return out, True
        except Exception:
            continue
    return r, False


def baseline(h: House) -> tuple[Result | None, str | None]:
    """The baseline logic: engine.py evaluate + installer_brief (fallback engine_tracer), adapted to contract v2."""
    from schema import BASELINE_INFO, with_core
    err = None
    for name in ("engine", "engine_tracer"):
        try:
            mod = importlib.import_module(name)
            r = mod.evaluate(h)
            if hasattr(mod, "installer_brief"):
                r = mod.installer_brief(h, r)
            if not isinstance(r, Result):
                r = Result.model_validate(r if isinstance(r, dict) else r.model_dump())
            info = BASELINE_INFO if name == "engine" else BASELINE_INFO.model_copy(update={"version": "engine_tracer.py"})
            return with_core(r, info), None
        except Exception as e:
            err = f"{name}: {type(e).__name__}: {e}"
    return None, err


def _q50(r: Result | None, key: str):
    if r is None:
        return None
    from schema import quantity
    q = quantity(r, key)
    if q is None and key.endswith("_eur"):
        return getattr(r, key, None)
    return None if q is None else q.p50


def _err_pct(v, ref):
    return None if v is None or not ref else round((v - ref) / ref * 100, 1)


def compare_logic(buildings) -> list[dict]:
    """A/B for the paper: A = baseline (engine.py), B = the calculation module; one dict per building.
    `buildings` = loader.load_buildings() → [(id, House, reference | None)]. B columns are None when no module is
    available (b_error says why). Keys: building_id, dev, ref_verdict, ref_load_kw, {a,b}_color, {a,b}_p_green,
    {a,b}_flow_c, flow_delta, {a,b}_load_kw, load_delta, {a,b}_load_err_pct (vs reference, dev only),
    {a,b}_hit (verdict == reference, dev only), {a,b}_model, {a,b}_error. Deterministic (seed 0), no Streamlit."""
    rows = []
    use_b = available("calculation")
    for bid, h, ref in buildings:
        a, a_err = baseline(h)
        b, b_err = None, "calculation not available"
        if use_b:
            b, _, b_err = calculate(h)
        ref = ref or {}
        rv, rl = ref.get("verdict"), ref.get("heating_load_kw")
        row = {"building_id": str(bid), "dev": bool(rv or rl), "ref_verdict": rv, "ref_load_kw": rl}
        for tag, r, e in (("a", a, a_err), ("b", b, b_err)):
            row[f"{tag}_color"] = r.best_color if r else None
            row[f"{tag}_p_green"] = round(r.p_green, 3) if r else None
            row[f"{tag}_flow_c"] = _q50(r, "flow_temp_c")
            row[f"{tag}_load_kw"] = _q50(r, "heat_load_kw")
            row[f"{tag}_load_err_pct"] = _err_pct(row[f"{tag}_load_kw"], rl)
            row[f"{tag}_hit"] = (r.best_color == rv) if (r is not None and rv) else None
            row[f"{tag}_model"] = r.model_info.name if r is not None and r.model_info else None
            row[f"{tag}_error"] = None if r is not None else e
        for k, unit in (("flow", "c"), ("load", "kw")):
            va, vb = row[f"a_{k}_{unit}"], row[f"b_{k}_{unit}"]
            row[f"{k}_delta"] = None if va is None or vb is None else round(vb - va, 2)
        rows.append(row)
    return rows


def compare_summary(rows: list[dict]) -> dict:
    """Measured from compare_logic rows: dev verdicts reproduced and mean |heat-load error| vs reference, A and B."""
    out = {"n_dev": sum(1 for r in rows if r["dev"])}
    for tag in ("a", "b"):
        hits = [r[f"{tag}_hit"] for r in rows if r["dev"] and r[f"{tag}_hit"] is not None]
        errs = [abs(r[f"{tag}_load_err_pct"]) for r in rows if r[f"{tag}_load_err_pct"] is not None]
        out[f"{tag}_hits"], out[f"{tag}_n"] = sum(hits), len(hits)
        out[f"{tag}_mae_pct"] = round(sum(errs) / len(errs), 1) if errs else None
    return out


if __name__ == "__main__":                    # python orchestrator.py → status of the three modules
    print("HP_MODULES:", modules_enabled(), "| HP_MODULES_ONLY:", modules_only(), "| HP_LLM_FALLBACK:", llm_fallback())
    for m in REGISTRY:
        env = run_module(m, {"probe": True})
        print(f"{m:17s} {spec(m):38s} available={available(m)!s:5s} probe → ok={env.get('ok')} {env.get('error') or ''}")
