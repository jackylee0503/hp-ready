"""screening (hybrid candidate for ML module 3 "calculation"): engine.py result + best/worst-case screening bounds.

Origin: the teammate package heat_pump_screening v2.0.0 (2026-10-24), an interval "decision tree" after Fraunhofer ISE
WP-QS im Bestand (2nd ed., 25 Nov 2025) and the UBA room-by-room 55 °C check. Ported to the HP-Ready contract:
  - Its radiator equation is the same EN 442 law as engine.py: with the same inputs it gives the same °C (measured on
    B-01 54.05, B-03 58.21, B-04 72.11 °C). So this module does NOT change any engine number or colour:
    MVP core (colour, p_green/p_yellow/p_red, heat load, flow temperature), costs at the fixed challenge prices,
    contradictions, open checks and the installer brief all come from engine.py (fallback engine_tracer.py).
  - Added (contract v2 optional extras, no schema change): best and worst case over every input corner (endpoint
    bounds, NOT p10-p90), what each radiator size would mean when the size is unknown, the water flow at design load,
    the screening's two extra standard checks, and model_info.
  - Kept out on purpose: its economics (Fraunhofer SPF band, own tariffs, NPV, investment after grants: conflicts
    with the fixed JAZ/price table and Invariant 5), location_data.py (network + API key; CONTRACT §1 "no network"),
    its bill parser (bill_recognizer does this), its photo adapter (pipe_classifier does this), its Streamlit app.
  - Its gating stays: a photo or a data record never "verifies" a pipe system; evidence stays low until an
    installer checks loads, radiators and pipes on site (matches CLAUDE.md step 3b and the always-checks).

Contract: CONTRACT.md "MVP" + §1-§3, request/reply exactly like modules/calculation.py. No new dependencies,
no network, deterministic (`seed` goes to the engine's Monte Carlo), well under the 20 s limit.
Try it:  HP_MODULE_CALCULATION="modules.screening:run" streamlit run app.py
CLI:     python -m modules.screening < contracts/examples/calc_input_B-05.json
A/B:     HP_MODULE_CALCULATION="modules.screening:run" python -c "import orchestrator as O; from loader import
         load_buildings; print(O.compare_summary(O.compare_logic(load_buildings(use_llm=False))))"
"""
from __future__ import annotations

import importlib
import itertools
import json
import sys

from schema import (BAND_GREEN_MAX_C, BAND_YELLOW_MAX_C, DEFAULT, DISPLAY_CLIP_C, RADIATOR_KW, BASELINE_INFO,
                    Explanation, House, ModelInfo, Params, Result, Step, with_core)

MODULE = "calculation"                 # answers in the calculation slot (orchestrator REGISTRY / HP_MODULE_CALCULATION)
VERSION = "screening-1"
IMPLEMENTED = True

ROOM_C = 20.0                          # same indoor temperature as engine.py
RATED_EXCESS_K = 50.0                  # EN 442 rating 75/65/20 °C
EXPONENT = (1.2, 1.4)                  # screening package: radiator exponent band (engine.py uses 1.3)
WATER_DT_K = (5.0, 10.0)               # screening package: flow/return difference band (engine.py uses 8 K)
SIZES = ("small", "medium", "large")
EXTRA_CHECKS = ["Heat-pump output on the coldest days, including defrost (size the unit to the heating load)",
                "Hot-water storage and hygiene (legionella protection)"]
SOURCES = ("Fraunhofer ISE, WP-QS im Bestand, final report, 2nd ed. 25 Nov 2025; "
           "UBA Gebäudecheck: room-by-room 55 °C screening")
INFO = ModelInfo(name="physics baseline + screening bounds", version=f"engine.py + {VERSION}", kind="hybrid",
                 trained_on="engine: 3 organiser dev buildings (one parameter k); screening rules: not trained",
                 seed=0, params={"k": DEFAULT.k, "n": 500, "exponent": list(EXPONENT), "water_dt_k": list(WATER_DT_K),
                                 "load_spread": list(DEFAULT.load_spread), "radiator_jitter": list(DEFAULT.radiator_jitter),
                                 "rules": SOURCES})


def ok(data, warnings=None) -> dict:
    return {"ok": True, "module": MODULE, "version": VERSION, "data": data, "warnings": warnings or []}


def fail(code: str, message: str) -> dict:
    """code: bad_input | unreadable | unsupported | internal"""
    return {"ok": False, "module": MODULE, "version": VERSION, "error": {"code": code, "message": message}}


# ---------------------------------------------------------------- screening math (ported, equations unchanged)

def bounds(load_w: tuple[float, float], rated_w: tuple[float, float], loss_k: tuple[float, float],
           supply_c: float = BAND_GREEN_MAX_C) -> dict:
    """Every corner of the input bands (screening package room_result):
    Q_rad = Q_rated × ((T_supply − loss − ΔT/2 − T_room) / 50)^n      → output at `supply_c`
    T_supply,needed = T_room + 50 × (Q_load / Q_rated)^(1/n) + ΔT/2 + loss
    Monotone in every input, so the corners give the true min and max. Endpoint bounds, not quantiles."""
    caps, need = [], []
    for q_nom, n, dt, drop in itertools.product(rated_w, EXPONENT, WATER_DT_K, loss_k):
        excess = supply_c - drop - dt / 2 - ROOM_C
        caps.append(q_nom * max(excess / RATED_EXCESS_K, 0.0) ** n)
    for q, q_nom, n, dt, drop in itertools.product(load_w, rated_w, EXPONENT, WATER_DT_K, loss_k):
        need.append(ROOM_C + RATED_EXCESS_K * (q / q_nom) ** (1 / n) + dt / 2 + drop)
    ratio = (min(caps) / load_w[1], max(caps) / load_w[0])
    status = ("adequate_in_every_case" if ratio[0] >= 1 else
              "inadequate_in_every_case" if ratio[1] < 1 else "depends_on_inputs")
    return {"flow_c": (min(need), max(need)), "ratio_at_supply": ratio, "status": status, "supply_c": supply_c}


def colour_words(lo: float, hi: float) -> str:
    """Which colours the best/worst case still allows (55/60 °C bands)."""
    g, y = BAND_GREEN_MAX_C, BAND_YELLOW_MAX_C
    if hi <= g:
        return "green in every case"
    if lo > y:
        return "red in every case"
    if lo > g and hi <= y:
        return "yellow in every case"
    if lo > g:
        return "never green"
    if hi <= y:
        return "never red"
    return "any colour"


def span(lo: float, hi: float) -> str:
    if lo > DISPLAY_CLIP_C:
        return f"{DISPLAY_CLIP_C:.0f} °C or more"
    if hi > DISPLAY_CLIP_C:
        return f"{lo:.0f} °C to {DISPLAY_CLIP_C:.0f} °C or more"
    return f"{lo:.0f}–{hi:.0f} °C"


# ---------------------------------------------------------------- House → screening bands (same numbers as engine.py)

def bands(h: House, p: Params = DEFAULT) -> dict | None:
    """The engine's own inputs as [lo, hi] bands. None when the screening can't run (no area, underfloor only,
    no radiator count from any fallback). Renovation unknown → both renovation columns are inside the band."""
    import engine
    rc = engine.renovation_column(h)
    s = engine.setup(h, p, mix_cols=(1, 2)) if rc["unknown"] else engine.setup(h, p)
    if s["area"] is None or s["dist_calc"] == "underfloor" or not s["count"]:
        return None
    if s.get("w_lo") is not None:                       # learned W/m² model with a range
        w_lo, w_hi = min(s["w_lo"]), max(s["w_hi"])
    else:
        w_lo, w_hi = min(s["w_values"]) * p.load_spread[0], max(s["w_values"]) * p.load_spread[1]
    a_lo = s["area"] * s["af_range"][0]
    a_hi = s["area"] * s["af_range"][1] * max(1.0, s["area_widen"])
    total_w = (p.k * w_lo * a_lo, p.k * w_hi * a_hi)    # W, whole house
    share = s["share_range"]                            # mixed: radiator circuit share
    return {"s": s, "total_w": total_w, "rad_load_w": (total_w[0] * share[0], total_w[1] * share[1]),
            "loss_k": tuple(s["pen_range"]), "count": s["count"], "count_src": s["count_src"], "size": s["size"],
            "renovation_both": rc["unknown"]}


def rated_for(count: int, size: str | None, p: Params = DEFAULT) -> tuple[float, float]:
    """ΣΦ_n band in W: count × size range × the engine's ±15 % jitter (unknown size → small low .. large high)."""
    lo = RADIATOR_KW["small" if size is None else size][1]
    hi = RADIATOR_KW["large" if size is None else size][2]
    return count * lo * p.radiator_jitter[0] * 1000.0, count * hi * p.radiator_jitter[1] * 1000.0


def screen(h: House, p: Params = DEFAULT) -> dict:
    """Plain-dict screening for one house (also usable from a notebook). {"applied": False, "why"} when it can't run."""
    b = bands(h, p)
    if b is None:
        why = ("underfloor only: the screening is a radiator method" if h.heat_distribution == "underfloor"
               else "no living area or radiator count to work with")
        return {"applied": False, "why": why}
    out = {"applied": True, "bands": {k: v for k, v in b.items() if k != "s"},
           "all": bounds(b["rad_load_w"], rated_for(b["count"], b["size"], p), b["loss_k"]),
           "at_60": bounds(b["rad_load_w"], rated_for(b["count"], b["size"], p), b["loss_k"], BAND_YELLOW_MAX_C)}
    if b["size"] is None:
        out["by_size"] = {z: bounds(b["rad_load_w"], rated_for(b["count"], z, p), b["loss_k"]) for z in SIZES}
    t = b["total_w"]
    out["water_flow_m3_h"] = (t[0] / 1000 / (1.163 * WATER_DT_K[1]), t[1] / 1000 / (1.163 * WATER_DT_K[0]))
    return out


# ---------------------------------------------------------------- screening → Result extras (no colour, no number changed)

def add_extras(h: House, r: Result, sc: dict) -> Result:
    import engine
    out = r.model_copy(deep=True)
    if not sc.get("applied"):
        out.trace.append(Step(label="Best and worst case (screening)", value="not applied", assumption=sc.get("why")))
        return out
    b, lo_hi = sc["bands"], sc["all"]["flow_c"]
    corners = ["heat load ±20 %" + (" (both renovation columns)" if b["renovation_both"] else ""),
               "radiator output " + (f"for '{b['size']}' radiators" if b["size"] else "small to large"),
               "exponent 1.2–1.4", "flow/return 5–10 K"]
    if b["loss_k"][1] > 0:
        corners.append(f"pipe system +{b['loss_k'][0]:.0f}–{b['loss_k'][1]:.0f} K")
    out.trace.append(Step(label="Best and worst case (screening)",
                          value=f"{span(*lo_hi)} · {colour_words(*lo_hi)}",
                          assumption="every corner of: " + ", ".join(corners)
                                     + "; same EN 442 law as above; bounds, not a p10-p90 range"))
    # A sentence for people only when it settles something ("any colour" says nothing; it stays in the trace).
    if "by_size" in sc:
        parts = [f"{z} {span(*v['flow_c'])} ({colour_words(*v['flow_c'])})" for z, v in sc["by_size"].items()]
        out.trace.append(Step(label="If the radiators are small / medium / large", value=" · ".join(parts),
                              assumption="radiator size not documented; a side photo or a technician settles it"))
        if any(colour_words(*v["flow_c"]) != "any colour" for v in sc["by_size"].values()):
            out.explanations.append(Explanation(
                feature="radiator_size", value="not documented", target="flow_temp_c", unit="°C",
                text="Radiator size decides it. Best and worst case: " + "; ".join(parts) + "."))
    elif colour_words(*lo_hi) != "any colour":
        out.explanations.append(Explanation(
            feature="radiator_size", value=b["size"], target="flow_temp_c", unit="°C",
            text=f"Best and worst case over all inputs: {span(*lo_hi)} ({colour_words(*lo_hi)})."))
    f = sc["water_flow_m3_h"]
    out.trace.append(Step(label="Water flow at design load", value=f"{f[0]:.1f}–{f[1]:.1f} m³/h",
                          assumption="heat load ÷ (1.163 × flow/return 5–10 K); the installer checks pipes and pump"))
    out.trace.append(Step(label="Screening rules", value="evidence low until checked on site",
                          assumption=SOURCES + ". A photo or a record never verifies the pipe system."))
    base = list(r.always_checks) or list(getattr(engine, "ALWAYS_CHECKS", []))
    out.always_checks = base + [c for c in EXTRA_CHECKS if c not in base]
    return out


# ---------------------------------------------------------------- module entry

def _baseline(h: House, n: int, seed: int) -> tuple[Result | None, str | None]:
    """engine.py evaluate + installer_brief (fallback engine_tracer), adapted to contract v2 like orchestrator.baseline."""
    err = None
    for name in ("engine", "engine_tracer"):
        try:
            mod = importlib.import_module(name)
            r = mod.evaluate(h, n=n, seed=seed) if name == "engine" else mod.evaluate(h)
            if hasattr(mod, "installer_brief"):
                r = mod.installer_brief(h, r)
            if not isinstance(r, Result):
                r = Result.model_validate(r if isinstance(r, dict) else r.model_dump())
            return with_core(r, BASELINE_INFO), None
        except Exception as e:  # noqa: BLE001
            err = f"{name}: {type(e).__name__}: {e}"
    return None, err


def run(request: dict) -> dict:
    if not isinstance(request, dict):
        return fail("bad_input", "request must be a JSON object")
    if request.get("probe"):
        return ok(None) if IMPLEMENTED else fail("unsupported", "not enabled")
    raw = request.get("house")
    if not isinstance(raw, dict):
        return fail("bad_input", "house object is required")
    try:
        h = House.model_validate(raw)
    except Exception as e:  # noqa: BLE001
        return fail("bad_input", f"house does not match House ({type(e).__name__})")
    n = request.get("n") if isinstance(request.get("n"), int) else 500
    seed = request.get("seed") if isinstance(request.get("seed"), int) else 0
    r, err = _baseline(h, n, seed)
    if r is None:
        return fail("internal", err or "baseline failed")
    warnings = []
    try:
        r = add_extras(h, r, screen(h))
    except Exception as e:  # noqa: BLE001  (the extra layer never takes the result down)
        warnings.append(f"screening layer skipped: {type(e).__name__}: {e}"[:200])
    r.model_info = INFO.model_copy(update={"seed": seed, "params": {**INFO.params, "n": n}})
    return ok(r.model_dump(mode="json"), warnings)


if __name__ == "__main__":
    try:
        reply = run(json.loads(sys.stdin.read()))
    except ValueError:
        reply = fail("bad_input", "stdin is not JSON")
    except Exception as e:  # noqa: BLE001
        reply = fail("internal", f"{type(e).__name__}: {e}")
    print(json.dumps(reply, ensure_ascii=False, indent=2))
