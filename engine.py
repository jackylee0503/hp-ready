"""Physics engine: House → Result (CLAUDE.md "Engine", steps 0-10). Tracer version: spec-faithful, plain.

Chain: fuel → useful heat → bill load (cross-check) · area × age load (primary) → radiators → required flow
temperature → JAZ → cost → traffic light. Uncertainty by a vectorised numpy Monte Carlo over the same chain.
Every number lands in `Result.trace` (the Rechenweg). No LLM here; prices and JAZ only from schema constants.
"""
from __future__ import annotations

import math
from datetime import date

import numpy as np

from schema import (BAND_GREEN_MAX_C, BAND_YELLOW_MAX_C, DEFAULT, FLOW_SPREAD_K, FULL_LOAD_HOURS, GAS_KWH_PER_M3_DEFAULT,
                    JAZ, OIL_KWH_PER_L, PRICE_EUR_KWH, RADIATOR_EXPONENT, RADIATOR_KW, RADIATOR_SIZE_PRIOR,
                    SPECIFIC_LOAD_HINT_W_M2, U_WALL_REF, UNDERFLOOR_FLOW_C, W_PER_M2, W_PER_M2_ORGANISER_BAND,
                    Contradiction, House, NextStep, OpenCheck, Params, Parts, Range, Result, Step)

ROOM_C = 20.0
PIPE_SENTENCE = ("Heating pipe system unclear. A technician should check whether this is a single-pipe system, "
                 "because that can require a higher flow temperature.")
ALWAYS_CHECKS = ["Exact heating load (DIN EN 12831) and room-by-room radiator sizing",
                 "Electrical capacity and meter cabinet",
                 "Hydraulics and hydraulic balancing",
                 "Outdoor-unit position, sound distance and permits"]
COL_NAME = {1: "unrenovated / unknown", 2: "partially renovated", 3: "fully renovated"}
COL_OF = {"unrenovated": 1, "partially": 2, "fully": 3}


def _f(v, nd=1) -> str:
    return "–" if v is None else f"{v:,.{nd}f}"


def color_of(t: float | None) -> str | None:
    if t is None:
        return None
    return "green" if t <= BAND_GREEN_MAX_C else "yellow" if t <= BAND_YELLOW_MAX_C else "red"


def _band(table, year):
    for row in table:
        if year <= row[0]:
            return row
    return table[-1]


# ---------------------------------------------------------------- step 1: fuel → heat

def _days(start: str | None, end: str | None) -> int | None:
    try:
        d = (date.fromisoformat(str(end)[:10]) - date.fromisoformat(str(start)[:10])).days + 1
        return d if d > 0 else None
    except Exception:
        return None


def fuel_type_of(h: House) -> str | None:
    if h.fuel_type:
        return h.fuel_type
    if h.bill_carrier:
        try:
            from loader import fuel_from
            return fuel_from(h.bill_carrier, None)
        except Exception:
            return None
    return None


def fuel_kwh(h: House, p: Params = DEFAULT) -> dict:
    """Yearly fuel in kWh by the agreed precedence → {kwh, lo, hi, how, field, steps}. kwh None = unknown."""
    steps: list[Step] = []
    fuel = fuel_type_of(h)
    out = {"kwh": None, "lo": None, "hi": None, "how": None, "field": None, "steps": steps}
    raw = None
    if h.kwh_printed is not None:
        raw, how, field = h.kwh_printed, "bill, printed kWh", "kwh_printed"
    elif h.m3 is not None:
        if h.zustandszahl is not None and h.brennwert is not None:
            raw, how = h.m3 * h.zustandszahl * h.brennwert, f"bill: {h.m3:,.0f} m³ × Zustandszahl {h.zustandszahl} × Brennwert {h.brennwert}"
        else:
            raw, how = h.m3 * GAS_KWH_PER_M3_DEFAULT, f"bill: {h.m3:,.0f} m³ × {GAS_KWH_PER_M3_DEFAULT:.0f} kWh/m³ (organiser value, factors missing)"
        field = "m3"
    elif h.liters is not None:
        raw, how, field = h.liters * OIL_KWH_PER_L, f"bill: {h.liters:,.0f} L × {OIL_KWH_PER_L:.0f} kWh/L", "liters"
    if raw is not None:
        days = _days(h.period_start, h.period_end)
        if days:
            kwh = raw * 365.0 / days
            how += f", {days}-day period" + ("" if 364 <= days <= 366 else " scaled to 365 days")
        else:
            kwh = raw
            how += ", bill period unknown: taken as one year"
        out.update(kwh=kwh, lo=kwh, hi=kwh, how=how, field=field)
    elif h.certificate_kwh_m2a is not None and (h.certificate_area_m2 or h.living_area_m2):
        if h.certificate_area_m2:
            a_lo = a_hi = a_mid = h.certificate_area_m2
            how = f"certificate {h.certificate_kwh_m2a:.0f} kWh/(m²·a) × A_N {a_mid:.0f} m² (hot water included)"
        else:
            a_mid, a_lo, a_hi = 1.2 * h.living_area_m2, 1.2 * h.living_area_m2, 1.35 * h.living_area_m2
            how = (f"certificate {h.certificate_kwh_m2a:.0f} kWh/(m²·a) × A_N ≈ 1.2-1.35 × living area "
                   "(certificate rule, low confidence, hot water included)")
        out.update(kwh=h.certificate_kwh_m2a * a_mid, lo=h.certificate_kwh_m2a * a_lo,
                   hi=h.certificate_kwh_m2a * a_hi, how=how, field="certificate_kwh_m2a")
    elif h.annual_fuel_kwh is not None:
        out.update(kwh=h.annual_fuel_kwh, lo=h.annual_fuel_kwh, hi=h.annual_fuel_kwh,
                   how="stated yearly use", field="annual_fuel_kwh")
    elif h.annual_fuel_liters is not None:
        k = h.annual_fuel_liters * OIL_KWH_PER_L
        out.update(kwh=k, lo=k, hi=k, how=f"{h.annual_fuel_liters:,.0f} L × {OIL_KWH_PER_L:.0f} kWh/L",
                   field="annual_fuel_liters")
    elif h.monthly_advance_eur is not None and fuel in PRICE_EUR_KWH:
        k = h.monthly_advance_eur * 12 / PRICE_EUR_KWH[fuel]
        out.update(kwh=k, lo=0.7 * k, hi=1.1 * k, field="monthly_advance_eur",
                   how=f"advance payment €{h.monthly_advance_eur:.0f} × 12 / {PRICE_EUR_KWH[fuel]} €/kWh "
                       "(range −30 %..+10 %, low confidence)")
    if out["kwh"] is not None:
        steps.append(Step(label="Fuel per year", value=f"{out['kwh']:,.0f} kWh", assumption=out["how"]))
    else:
        steps.append(Step(label="Fuel per year", value="unknown", assumption="no bill, yearly use or advance payment given"))
    return out


def eta_of(h: House, p: Params, fuel: str | None) -> tuple[float, str]:
    if fuel in ("district", "electric"):
        return 1.0, f"{fuel}: η 1.0"
    if h.boiler_condensing is None:
        return p.eta_default, "organiser default η 0.88 (old boiler loses ~12 %)"
    key = "condensing" if h.boiler_condensing else "non_condensing"
    if fuel == "oil":
        return p.eta_oil[key], f"oil {key.replace('_', '-')} boiler (Hi basis)"
    return p.eta_gas[key], f"{fuel or 'gas'} {key.replace('_', '-')} boiler (Hs basis)"


# ---------------------------------------------------------------- step 2: W/m² column

def renovation_column(h: House) -> dict:
    """→ {col, why, inferred (bool: renovated column chosen from notes/U-values), unknown (bool)}."""
    if h.renovation:
        return {"col": COL_OF[h.renovation], "why": f"renovation stated: {h.renovation}", "inferred": False, "unknown": False}
    o = h.notes_obs
    if h.build_year is not None and o and o.u_values.get("wall") is not None:
        ref = _band(U_WALL_REF, h.build_year)[1]
        if o.u_values["wall"] < 0.7 * ref:
            return {"col": 2, "inferred": True, "unknown": False,
                    "why": f"wall U {o.u_values['wall']} < 0.7 × age reference {ref} W/m²K → partially renovated"}
    if o and o.insulation_measures:
        return {"col": 2, "inferred": True, "unknown": False,
                "why": "notes name insulation work (" + "; ".join(o.insulation_measures[:3]) + ") → partially renovated"}
    if h.walls_insulated or h.roof_insulated:
        return {"col": 2, "inferred": True, "unknown": False, "why": "insulated walls or roof stated → partially renovated"}
    if o and o.insulation_measures == []:
        return {"col": 1, "why": "notes say no additional insulation", "inferred": False, "unknown": False}
    return {"col": 1, "why": "renovation unknown → unrenovated column", "inferred": False, "unknown": True}


# ---------------------------------------------------------------- setup shared by MC, parts, next question

def setup(h: House, p: Params = DEFAULT, col: int | None = None, mix_cols: tuple[int, int] | None = None) -> dict:
    """Everything the chain needs, as plain numbers. No randomness here."""
    s: dict = {"notes": []}
    rc = renovation_column(h)
    s["rc"] = rc
    col = col or rc["col"]
    s["col"] = col
    # W/m²
    if h.build_year is not None:
        row = _band(W_PER_M2, h.build_year)
        s["w_values"] = [row[c] for c in (mix_cols or (col,))]
        s["w_point"] = row[col]
        s["band"] = W_PER_M2_ORGANISER_BAND.get(row[0], "")
    else:
        vals = [row[col] for row in W_PER_M2]
        s["w_values"], s["w_point"], s["band"] = vals, float(np.median(vals)), "year unknown: all age bands"
    # area
    s["area"] = h.living_area_m2
    o = h.notes_obs
    s["unused"] = bool(o and o.unheated_area_note)
    s["af_point"] = p.unused_area_factor[0] if s["unused"] else 1.0
    s["af_range"] = (p.unused_area_factor[1], p.unused_area_factor[2]) if s["unused"] else (1.0, 1.0)
    s["area_widen"] = 1.0                       # set by the rooms-vs-area rule
    # distribution
    dist = h.heat_distribution
    s["dist_assumed"] = None
    if dist is None and (h.radiator_count is not None or h.radiator_size is not None):
        dist, s["dist_assumed"] = "radiators", "radiators (a radiator count or size was given)"
    s["dist"] = dist
    s["dist_missing"] = dist is None
    if dist is None:
        dist = "radiators"                       # physics still runs; verdict is unclear
    s["dist_calc"] = dist
    # radiator count
    if h.radiator_count is not None and h.radiator_count > 0:
        s["count"], s["count_src"] = h.radiator_count, "stated"
    elif h.rooms:
        s["count"], s["count_src"] = max(1, round(h.rooms * 1.3)), f"rooms {h.rooms} × 1.3 (estimated)"
    elif h.living_area_m2:
        s["count"], s["count_src"] = max(1, round(h.living_area_m2 / 18)), f"area {h.living_area_m2:.0f} m² / 18 (estimated)"
    else:
        s["count"], s["count_src"] = None, "unknown"
    s["size"] = h.radiator_size
    s["phi_point"] = RADIATOR_KW[h.radiator_size or "medium"][0]
    # mixed share
    if dist == "mixed":
        if h.rooms and s["count"]:
            sh = min(1.0, s["count"] / h.rooms)
            s["share_point"], s["share_range"] = sh, (sh, sh)
            s["share_src"] = f"{s['count']} radiators / {h.rooms} rooms"
        else:
            s["share_point"], s["share_range"], s["share_src"] = 0.75, (0.5, 1.0), "rooms unknown: 0.75 (MC 0.5-1.0, estimated)"
    else:
        s["share_point"], s["share_range"], s["share_src"] = 1.0, (1.0, 1.0), None
    # pipe system (step 3b)
    if dist in ("radiators", "mixed") and h.pipe_system == "single_pipe":
        s["pen_point"], s["pen_range"] = sum(p.single_pipe_penalty_k) / 2, p.single_pipe_penalty_k
        s["pen_why"] = "single-pipe confirmed: +5..10 K (point +7.5 K, estimated)"
    elif dist in ("radiators", "mixed") and h.pipe_system is None and h.build_year and 1960 <= h.build_year <= 1979:
        s["pen_point"], s["pen_range"] = 0.0, p.unknown_pipe_penalty_k
        s["pen_why"] = "pipe system unknown in a 1960-1979 house (single-pipe was common): MC +0..10 K"
    else:
        s["pen_point"], s["pen_range"], s["pen_why"] = 0.0, (0.0, 0.0), None
    return s


def point_load(s: dict, p: Params) -> float | None:
    if s["area"] is None:
        return None
    return p.k * s["w_point"] * s["area"] * s["af_point"] / 1000.0


def flow_from(load_rad_kw: float, sum_phi_kw: float, penalty: float = 0.0) -> float:
    dt = 50.0 * (load_rad_kw / sum_phi_kw) ** (1.0 / RADIATOR_EXPONENT)
    return ROOM_C + dt + FLOW_SPREAD_K / 2 + penalty


def phi_needed(load_rad_kw: float, t_flow: float, penalty: float = 0.0) -> float | None:
    """ΣΦ_n needed so that the required flow temperature equals t_flow."""
    dt = t_flow - ROOM_C - FLOW_SPREAD_K / 2 - penalty
    if dt <= 0:
        return None
    return load_rad_kw / (dt / 50.0) ** RADIATOR_EXPONENT


# ---------------------------------------------------------------- step 7: Monte Carlo

def monte_carlo(s: dict, p: Params, n: int = 500, seed: int = 0) -> dict | None:
    """Vectorised draws; every variable is drawn every time (fixed order) so runs stay comparable."""
    if s["area"] is None:
        return None
    rng = np.random.default_rng(seed)
    wf = rng.uniform(*p.load_spread, n)
    af = rng.uniform(*s["af_range"], n) if s["af_range"][0] != s["af_range"][1] else np.full(n, s["af_range"][0])
    rng_widen = rng.uniform(1.0, 1.0 if s["area_widen"] <= 1.0 else s["area_widen"], n)
    wpick = rng.integers(0, len(s["w_values"]), n)
    size_u = rng.uniform(0, 1, n)
    phi_u = rng.uniform(0, 1, n)
    jit = rng.uniform(*p.radiator_jitter, n)
    share = rng.uniform(*s["share_range"], n)
    pen = rng.uniform(*s["pen_range"], n)
    ufh = rng.uniform(*UNDERFLOOR_FLOW_C, n)

    w = np.asarray(s["w_values"], dtype=float)[wpick]
    load = p.k * w * wf * s["area"] * af * rng_widen / 1000.0
    if s["dist_calc"] == "underfloor":
        t = ufh
    else:
        if s["size"] is None:
            c1 = RADIATOR_SIZE_PRIOR["small"]
            c2 = c1 + RADIATOR_SIZE_PRIOR["medium"]
            lo = np.where(size_u < c1, RADIATOR_KW["small"][1], np.where(size_u < c2, RADIATOR_KW["medium"][1], RADIATOR_KW["large"][1]))
            hi = np.where(size_u < c1, RADIATOR_KW["small"][2], np.where(size_u < c2, RADIATOR_KW["medium"][2], RADIATOR_KW["large"][2]))
        else:
            lo = np.full(n, RADIATOR_KW[s["size"]][1])
            hi = np.full(n, RADIATOR_KW[s["size"]][2])
        phi = (lo + (hi - lo) * phi_u) * jit
        sum_phi = s["count"] * phi
        t = ROOM_C + 50.0 * (load * share / sum_phi) ** (1.0 / RADIATOR_EXPONENT) + FLOW_SPREAD_K / 2 + pen
    q = lambda a: tuple(float(x) for x in np.percentile(a, [10, 50, 90]))
    return {"t": t, "load": load, "t_q": q(t), "load_q": q(load),
            "p_green": float(np.mean(t <= BAND_GREEN_MAX_C)),
            "p_yellow": float(np.mean((t > BAND_GREEN_MAX_C) & (t <= BAND_YELLOW_MAX_C))),
            "p_red": float(np.mean(t > BAND_YELLOW_MAX_C))}


def _renovation_flips(h: House, p: Params, n: int, seed: int) -> bool:
    """Step 2: renovation unknown → does the colour differ between the unrenovated and partially column?"""
    rc = renovation_column(h)
    if not rc["unknown"] or h.build_year is None or h.living_area_m2 is None:
        return False
    cols = []
    for c in (1, 2):
        s = setup(h, p, col=c)
        if s["count"] is None and s["dist_calc"] != "underfloor":
            return False
        mc = monte_carlo(s, p, n, seed)
        cols.append(color_of(mc["t_q"][1]))
    return cols[0] != cols[1]


# ---------------------------------------------------------------- step 8: next question

def _missing_core(h: House, s: dict) -> list[str]:
    miss = []
    if h.build_year is None:
        miss.append("build_year")
    if h.living_area_m2 is None:
        miss.append("living_area_m2")
    if s["dist_missing"]:
        miss.append("heat_distribution")
    elif s["dist_calc"] != "underfloor" and s["count"] is None:
        miss.append("radiator_count")
    return miss


QUESTIONS = {
    "build_year": "When was the house built? A rough year is fine.",
    "living_area_m2": "About how many m² of living area does the house have?",
    "heat_distribution": "Do you heat with radiators, underfloor heating, or both?",
    "radiator_count": "How many radiators does the house have?",
    "renovation": "Was the house insulated or were windows replaced since it was built?",
    "radiator_size": "How big is your biggest radiator? A photo from the side, pipes in view, tells us.",
    "fuel": "How much gas or oil do you use a year? A bill tells us.",
}


def _next_question(h: House, s: dict, flips: bool) -> str | None:
    miss = _missing_core(h, s)
    if miss:
        return QUESTIONS[miss[0]]
    if flips:
        return QUESTIONS["renovation"]
    if s["dist_calc"] != "underfloor" and h.radiator_size is None:
        return QUESTIONS["radiator_size"]
    if fuel_kwh(h)["kwh"] is None:
        return QUESTIONS["fuel"]
    return None


def next_question(h: House) -> str | None:
    """Step 8 (P0 fixed order): year > area > heating surfaces > renovation flip > radiator size > yearly use."""
    s = setup(h, DEFAULT)
    flips = not _missing_core(h, s) and _renovation_flips(h, DEFAULT, 500, 0)
    return _next_question(h, s, flips)


# ---------------------------------------------------------------- evaluate

def _physics(h: House, p: Params, n: int, seed: int) -> Result:
    r = Result(building_id=h.building_id)
    T: list[Step] = r.trace
    fuel = fuel_type_of(h)

    # ---- step 2 column, flip check
    s0 = setup(h, p)
    missing = _missing_core(h, s0)
    flips = not missing and _renovation_flips(h, p, n, seed)
    s = setup(h, p, mix_cols=(1, 2)) if flips else s0
    rc = s["rc"]

    # ---- step 0 site flags
    if h.listed_building:
        r.site_flags.append("Listed building: check permits for the outdoor unit")
    if h.outdoor_unit_space is False:
        r.site_flags.append("No obvious space for the outdoor unit: find a spot on site")
    if h.flat_level_gas_heating:
        r.site_flags.append("Flat-level gas heating: a central heating circuit is needed")

    # ---- step 1 fuel → heat
    fk = fuel_kwh(h, p)
    eta, eta_why = eta_of(h, p, fuel)
    q_heat = q_space = None
    if fk["kwh"] is not None:
        T.extend(fk["steps"])
        q_heat = fk["kwh"] * eta
        T.append(Step(label="Useful heat Q_heat = fuel × η", value=f"{fk['kwh']:,.0f} × {eta:.2f} = {q_heat:,.0f} kWh",
                      assumption=eta_why))
        o = h.notes_obs
        solar = bool(o and o.solar_thermal_dhw)
        if h.dhw_by_boiler and h.occupants:
            q_dhw = p.dhw_kwh_per_person * h.occupants * (p.solar_dhw_factor if solar else 1.0)
            T.append(Step(label="Hot water Q_dhw", value=f"{q_dhw:,.0f} kWh",
                          assumption=f"{p.dhw_kwh_per_person:.0f} kWh × {h.occupants} people (organiser)"
                                     + (f" × {p.solar_dhw_factor} solar thermal (our assumption)" if solar else "")))
        elif h.dhw_by_boiler and not h.occupants:
            q_dhw = 0.0
            T.append(Step(label="Hot water Q_dhw", value="0 kWh", assumption="number of people unknown: no hot-water deduction"))
        else:
            q_dhw = 0.0
            T.append(Step(label="Hot water Q_dhw", value="0 kWh",
                          assumption="hot water not via the boiler" if h.dhw_by_boiler is False
                          else "hot-water route unknown: no deduction"))
        q_space = max(0.0, q_heat - q_dhw)
        T.append(Step(label="Space heat Q_space = Q_heat − Q_dhw", value=f"{q_space:,.0f} kWh"))
        lo_s = max(0.0, fk["lo"] * eta - q_dhw)
        hi_s = max(0.0, fk["hi"] * eta - q_dhw)
        r.heat_load_bill_kw = Range(p10=round(lo_s / FULL_LOAD_HOURS["high"], 2),
                                    p50=round(q_space / FULL_LOAD_HOURS["mid"], 2),
                                    p90=round(hi_s / FULL_LOAD_HOURS["low"], 2))
    else:
        T.extend(fk["steps"])

    # ---- step 2 area × age
    contradictions: list[Contradiction] = []
    p_load = point_load(s, p)
    if s["area"] is not None:
        heated = s["area"] * s["af_point"]
        T.append(Step(label="Heated area", value=f"{heated:,.0f} m²",
                      assumption=(f"{s['area']:.0f} m² × {s['af_point']} (unused area in the notes, MC 0.7-1.0)"
                                  if s["unused"] else "living area as documented")))
        T.append(Step(label="W/m² (age × renovation)",
                      value=(f"{s['w_point']:.0f} W/m²" if not flips else
                             f"{s['w_values'][0]:.0f} or {s['w_values'][1]:.0f} W/m² (renovation unknown, both used)"),
                      assumption=(f"built {h.build_year or '?'}, {COL_NAME[s['col']]} ({rc['why']}); organiser band "
                                  f"{s['band']}; first estimate, not a DIN EN 12831 calculation")))
        T.append(Step(label="Heating load (point) = k × W/m² × area",
                      value=f"{p.k:.2f} × {s['w_point']:.0f} W/m² × {heated:,.0f} m² = {p_load:.1f} kW",
                      assumption="k is the only calibrated parameter (3 dev buildings)"))
    else:
        T.append(Step(label="Heating load", value="unknown", assumption="living area unknown"))

    # ---- step 2b contradictions (those that widen inputs first)
    o = h.notes_obs
    bill50 = r.heat_load_bill_kw.p50
    w_k = p.k * s["w_point"] / 1000.0
    if h.rooms and h.living_area_m2 and h.living_area_m2 / h.rooms < 10:
        why = (f"{h.rooms} rooms in {h.living_area_m2:.0f} m² is {h.living_area_m2 / h.rooms:.1f} m² per room: "
               "the documented area may not include all heated rooms (basement, attic?)")
        if bill50 is not None and p_load and bill50 > 1.4 * p_load:
            bill_area = bill50 / (w_k * s["af_point"])
            s["area_widen"] = min(2.0, bill_area / s["area"])
            why += f"; the bill points the same way, so the MC widens the area up to {s['area'] * s['area_widen']:.0f} m²"
        contradictions.append(Contradiction(what="Few m² per room for the number of rooms",
                                            sources=["rooms", "floor area"], trusted="documented area (verdict)", why=why))
    if rc["inferred"]:
        contradictions.append(Contradiction(what="No renovation documented, but the notes say otherwise",
                                            sources=["renovation status", "notes"], trusted="notes",
                                            why=rc["why"]))

    mc = monte_carlo(s, p, n, seed)
    if mc:
        lq = mc["load_q"]
        r.heat_load_kw = Range(p10=round(lq[0], 2), p50=round(lq[1], 2), p90=round(lq[2], 2))
        T.append(Step(label="Heating load range (MC p10-p50-p90)", value=f"{lq[0]:.1f} – {lq[1]:.1f} – {lq[2]:.1f} kW",
                      assumption=f"N={n}, seed {seed}: W/m² × U(0.8, 1.2)" + (", unused area U(0.7, 1.0)" if s["unused"] else "")
                                 + (f", area up to × {s['area_widen']:.2f}" if s["area_widen"] > 1 else "")))
        heated_mid = s["area"] * s["af_point"]
        r.specific_load_w_m2 = round(lq[1] * 1000 / heated_mid, 1)
        T.append(Step(label="Specific load", value=f"{r.specific_load_w_m2:.0f} W/m²",
                      assumption=f"hint above {SPECIFIC_LOAD_HINT_W_M2:.0f} W/m² (organiser)"))
        if r.specific_load_w_m2 > SPECIFIC_LOAD_HINT_W_M2:
            r.hints.append("Better windows or insulation may be worth it: the house loses more heat than "
                           f"{SPECIFIC_LOAD_HINT_W_M2:.0f} W per m².")
    if bill50 is not None:
        b = r.heat_load_bill_kw
        T.append(Step(label="Bill-based load = Q_space / full-load hours",
                      value=f"{b.p10:.1f} – {b.p50:.1f} – {b.p90:.1f} kW",
                      assumption="2,100 / 2,000 / 1,800 h (organiser); cross-check only, the verdict uses area × age"))
        if mc:
            lo_c, hi_c = min(b.p10, r.heat_load_kw.p10), max(b.p90, r.heat_load_kw.p90)
            T.append(Step(label="Both methods, combined range", value=f"{lo_c:.1f} – {hi_c:.1f} kW",
                          assumption="shown because both exist (organiser); verdict uses area × age"))

    # remaining contradiction rules
    if bill50 is not None and p_load:
        diff = (bill50 - p_load) / p_load
        if abs(diff) > 0.40:
            if diff < 0 and o and o.extra_source_all_winter:
                cause = "an extra heat source runs all winter, so the bill is too low"
            elif diff < 0 and s["unused"]:
                cause = "part of the house is unused, so the documented area is too high"
            elif diff > 0 and h.rooms and h.living_area_m2 and h.living_area_m2 / h.rooms < 10:
                cause = "many rooms for the area: heated rooms may be missing from the documented area"
            else:
                cause = "habits or a record error (installer to check)" + (", LPG amounts are often recorded wrongly" if fuel == "lpg" else "")
            contradictions.append(Contradiction(
                what=f"Bill says {bill50:.1f} kW, area and age say {p_load:.1f} kW ({diff:+.0%})",
                sources=["consumption", "area × age"], trusted="area × age", why=cause))
    if o and o.extra_source_all_winter:
        contradictions.append(Contradiction(
            what=f"Extra heat source all winter ({(o.extra_heat_source or 'stove').replace('_', ' ')})",
            sources=["notes", "consumption"], trusted="area × age",
            why="the stove covers part of the heat, so the bill is a lower bound only"))
    if s["unused"]:
        contradictions.append(Contradiction(what="Part of the house is unused", sources=["notes", "floor area"],
                                            trusted="area × 0.85",
                                            why=f"notes: \"{o.evidence.get('unheated_area_note', o.unheated_area_note)}\"; "
                                                "heated area × 0.85 (MC 0.7-1.0), radiators kept"))
    if h.dhw_by_boiler and o and o.solar_thermal_dhw:
        contradictions.append(Contradiction(what="Hot water via the boiler, but there is solar thermal",
                                            sources=["data", "notes"], trusted="both",
                                            why="hot-water share halved (our assumption)"
                                                + ("; notes only say a solar system is present" if (o.confidence.get("solar_thermal_dhw") or 1) <= 0.6 else "")))
    if any("lpg" in n_.lower() for n_ in h.data_notes):
        contradictions.append(Contradiction(what="Carrier says gas, detail says LPG", sources=["energy_carrier", "detail"],
                                            trusted="detail (LPG)", why="corrected to LPG; real LPG price may be higher"))
    if h.annual_fuel_kwh and h.annual_fuel_liters:
        lk = h.annual_fuel_liters * OIL_KWH_PER_L
        d = (lk - h.annual_fuel_kwh) / h.annual_fuel_kwh
        if abs(d) > 0.15:
            contradictions.append(Contradiction(what=f"Litres ({lk:,.0f} kWh) and kWh ({h.annual_fuel_kwh:,.0f}) differ by {d:+.0%}",
                                                sources=["litres", "kWh"], trusted="kWh", why="stated kWh used; installer to check"))
    if h.build_year and h.build_year < 1980 and s["dist_calc"] in ("underfloor", "mixed"):
        contradictions.append(Contradiction(what="Old house with underfloor heating", sources=["build year", "heat distribution"],
                                            trusted="both", why="likely a retrofit; logged only"))
    for c in h.conflicts:
        vals = c.get("values", {})
        contradictions.append(Contradiction(
            what=f"{c.get('field', '?').replace('_', ' ')}: " + ", ".join(f"{k} says {v}" for k, v in vals.items()),
            sources=list(vals), trusted=str(c.get("used", "")), why="source priority (which input owners know best)"))

    # ---- step 3 radiators → flow temperature
    t_point = None
    if s["area"] is not None:
        if s["dist_calc"] == "underfloor":
            T.append(Step(label="Underfloor heating", value=f"{UNDERFLOOR_FLOW_C[0]:.0f}-{UNDERFLOOR_FLOW_C[1]:.0f} °C",
                          assumption="large surface, low water temperature; JAZ 4.0"))
            t_point = sum(UNDERFLOOR_FLOW_C) / 2
        elif s["count"]:
            sum_phi = s["count"] * s["phi_point"]
            T.append(Step(label="Radiator output ΣΦ_n (75/65/20 °C)",
                          value=f"{s['count']} × {s['phi_point']} kW = {sum_phi:.1f} kW",
                          assumption=f"count {s['count_src']}; size {h.radiator_size or 'unknown → medium (MC 25/50/25 small/medium/large)'} "
                                     "(Kermi/Buderus EN 442)"))
            if s["dist_calc"] == "mixed":
                T.append(Step(label="Radiator share of the load (mixed)", value=f"{s['share_point']:.2f}",
                              assumption=f"{s['share_src']}; underfloor circuit fine at ~35 °C"))
                r.hints.append("The underfloor circuit is fine at about 35 °C; the radiators set the temperature.")
            p_rad = p_load * s["share_point"]
            t_point = flow_from(p_rad, sum_phi, s["pen_point"])
            dt = t_point - ROOM_C - FLOW_SPREAD_K / 2 - s["pen_point"]
            T.append(Step(label="Required flow temperature (point)",
                          value=f"20 + {dt:.1f} + {FLOW_SPREAD_K / 2:.0f}" + (f" + {s['pen_point']:.1f}" if s["pen_point"] else "")
                                + f" = {t_point:.1f} °C",
                          assumption=f"ΔT = 50 × ({p_rad:.1f} / {sum_phi:.1f})^(1/1.3), spread {FLOW_SPREAD_K:.0f} K"))
        if s["pen_why"]:
            T.append(Step(label="Pipe system", value=f"+{s['pen_range'][0]:.0f}..{s['pen_range'][1]:.0f} K", assumption=s["pen_why"]))
    if mc:
        tq = mc["t_q"]
        r.required_flow_temp_c = Range(p10=round(tq[0], 1), p50=round(tq[1], 1), p90=round(tq[2], 1))
        r.p_green, r.p_yellow, r.p_red = round(mc["p_green"], 3), round(mc["p_yellow"], 3), round(mc["p_red"], 3)
        T.append(Step(label="Flow temperature range (MC p10-p50-p90)", value=f"{tq[0]:.1f} – {tq[1]:.1f} – {tq[2]:.1f} °C",
                      assumption=f"G {r.p_green:.2f} / Y {r.p_yellow:.2f} / R {r.p_red:.2f}; verdict = colour of p50"))
        if h.current_flow_temp_c is not None and tq[1] > h.current_flow_temp_c + 10:
            contradictions.append(Contradiction(
                what=f"We need {tq[1]:.0f} °C, the boiler runs at {h.current_flow_temp_c:.0f} °C",
                sources=["engine", "current flow temperature"], trusted="current flow temperature (the house stays warm)",
                why="radiators may be bigger than assumed, or the house loses less heat; installer to check"))

    # ---- step 6 traffic light
    t50 = r.required_flow_temp_c.p50
    raw = "green" if s["dist_calc"] == "underfloor" and mc else color_of(t50)
    capped_by = None
    color = raw
    if color == "green" and h.pipe_system == "single_pipe" and s["dist_calc"] != "underfloor":
        color, capped_by = "yellow", "pipe"
    if color == "green" and r.site_flags:
        color, capped_by = "yellow", capped_by or "site"
    if capped_by:                                # a capped green cannot be green: move its probability to yellow
        r.p_yellow, r.p_green = round(r.p_yellow + r.p_green, 3), 0.0
    unclear = bool(missing) or flips or mc is None
    if unclear:
        r.best_color, r.traffic_light, r.verdict_basis = "yellow", "unclear", "cannot_tell_yet"
    else:
        r.best_color, r.traffic_light = color, color
        r.verdict_basis = {"green": "likely_suitable", "yellow": "checks_remain", "red": "obstacle"}[color]
    r.boundary = bool(mc) and max(r.p_green, r.p_yellow, r.p_red) < 0.6

    # reason category
    if not unclear:
        if capped_by == "pipe":
            r.reason_category = "pipe_system"
        elif color == "red":
            no_pen = None
            if s["count"] and p_load:
                no_pen = flow_from(p_load * s["share_point"], s["count"] * s["phi_point"], 0.0)
            if s["pen_point"] and no_pen is not None and no_pen <= BAND_YELLOW_MAX_C:
                r.reason_category = "pipe_system"
            elif (r.specific_load_w_m2 or 0) > SPECIFIC_LOAD_HINT_W_M2:
                r.reason_category = "insulation_first"
            else:
                r.reason_category = "temperature"
        elif color == "yellow":
            r.reason_category = "temperature"

    # ---- step 4/5 JAZ and cost
    if mc:
        if s["dist_calc"] == "underfloor":
            r.jaz_bucket = "underfloor"
        else:
            r.jaz_bucket = "le55" if t50 <= BAND_GREEN_MAX_C else "55to60" if t50 <= BAND_YELLOW_MAX_C else "gt60"
        jaz = JAZ.get(r.jaz_bucket, JAZ["55to60"])
        T.append(Step(label="JAZ (seasonal efficiency)", value=f"{jaz}",
                      assumption={"underfloor": "underfloor 4.0", "le55": "radiators ≤55 °C: 3.5",
                                  "55to60": "radiators 55-60 °C: 2.8",
                                  "gt60": "above 60 °C not in the table: 2.8 used as a lower bound"}[r.jaz_bucket]))
    else:
        jaz = None
    notes = []
    if q_heat is not None and jaz:
        r.cost_hp_eur = round(q_heat / jaz * PRICE_EUR_KWH["electricity"], 0)
        if fuel in ("gas", "lpg", "oil"):
            r.cost_now_eur = round(fk["kwh"] * PRICE_EUR_KWH[fuel], 0)
            r.saving_eur = round(r.cost_now_eur - r.cost_hp_eur, 0)
            T.append(Step(label="Cost today", value=f"€{r.cost_now_eur:,.0f}/yr",
                          assumption=f"{fk['kwh']:,.0f} kWh × {PRICE_EUR_KWH[fuel]} €/kWh (challenge price)"))
        else:
            notes.append("Current price not provided for this fuel." if fuel else "Fuel type unknown: today's cost not shown.")
        T.append(Step(label="Cost with heat pump", value=f"€{r.cost_hp_eur:,.0f}/yr",
                      assumption=f"{q_heat:,.0f} kWh / JAZ {jaz} × 0.26 €/kWh"))
        if r.saving_eur is not None:
            T.append(Step(label="Saving", value=f"€{r.saving_eur:,.0f}/yr", assumption="running cost only; installation and subsidies come with the quote"))
        if r.jaz_bucket == "gt60":
            notes.append("At least this much: the real running cost is higher above 60 °C.")
        if fuel == "lpg":
            notes.append("Real LPG price may be higher than the challenge's 0.11 €/kWh.")
        if fk["field"] == "monthly_advance_eur":
            notes.append("From the advance payment only: rough.")
    elif q_heat is None:
        notes.append("No yearly fuel use yet: add a bill or your yearly use to see running costs.")
    r.cost_note = " ".join(notes) or None

    # ---- step 6b path to yellow
    r.path_to_yellow = _path_to_yellow(h, s, r, p_load)

    # ---- reason
    r.contradictions = contradictions
    r.next_question = _next_question(h, s, flips)
    r.reason = _reason(h, s, r, missing, flips, capped_by, t50)

    # ---- step 6c open checks
    r.open_checks = _open_checks(h, s, r, missing, flips)
    if s["dist_calc"] != "underfloor":
        r.hints.append("Myth: you don't need underfloor heating or a full renovation for a heat pump.")
    return r


def _path_to_yellow(h: House, s: dict, r: Result, p_load: float | None) -> list[str]:
    if p_load is None or r.required_flow_temp_c.p50 is None:
        return ["Tell us the year and size first; then we can say what would help."]
    if s["dist_calc"] == "underfloor":
        return ["Nothing to change: underfloor heating already runs at about 35-40 °C."]
    load50 = r.heat_load_kw.p50 or p_load
    p_rad = load50 * s["share_point"]
    sum_phi = (s["count"] or 0) * s["phi_point"]
    out = []
    need55 = phi_needed(p_rad, BAND_GREEN_MAX_C, s["pen_point"])
    need60 = phi_needed(p_rad, BAND_YELLOW_MAX_C, s["pen_point"])
    if need55 is None or sum_phi <= 0:
        return ["Radiator data missing: count and size the radiators first."]
    if need55 <= sum_phi:
        out.append(f"No change needed for 55 °C: the radiators give {sum_phi:.1f} kW, about {need55:.1f} kW is needed.")
    else:
        out.append(f"Add about {need55 - sum_phi:.1f} kW radiator output for 55 °C "
                   f"({max(0.0, need60 - sum_phi):.1f} kW for 60 °C); today {sum_phi:.1f} kW.")
        allowed = sum_phi * ((BAND_GREEN_MAX_C - ROOM_C - FLOW_SPREAD_K / 2 - s["pen_point"]) / 50) ** RADIATOR_EXPONENT
        red = 1 - allowed / p_rad
        out.append(f"Or cut the heat loss by about {red:.0%} (insulation or windows) to reach 55 °C with today's radiators.")
    if h.pipe_system == "single_pipe":
        out.append("Single-pipe loop: larger radiators at the end of the loop, a higher flow temperature, "
                   "or converting parts of the system (installer to check bypasses and balancing).")
    return out


def _reason(h, s, r, missing, flips, capped_by, t50) -> str:
    if missing or t50 is None:
        names = {"build_year": "when the house was built", "living_area_m2": "the living area",
                 "heat_distribution": "whether you have radiators or underfloor heating",
                 "radiator_count": "how many radiators there are"}
        return "We can't tell yet: we don't know " + " and ".join(names[m] for m in missing[:2] or ["living_area_m2"]) + "."
    if flips:
        return ("We can't tell yet: the answer depends on whether the house was insulated or got new windows "
                "since it was built.")
    tt = ">70" if t50 > 70 else f"{t50:.0f}"
    if s["dist_calc"] == "underfloor":
        base = "Underfloor heating runs at about 35-40 °C, ideal for a heat pump."
    else:
        base = f"Your radiators would need about {tt} °C on the coldest days"
    if r.best_color == "green":
        return base if s["dist_calc"] == "underfloor" else base + ", inside the efficient band up to 55 °C."
    if r.best_color == "red":
        return (f"There is an obstacle: {base[0].lower() + base[1:]}, above the 60 °C a heat pump handles well; "
                "bigger radiators or less heat loss would fix it.")
    if capped_by == "pipe":
        return base + ", but a single-pipe system needs an on-site check first."
    if capped_by == "site":
        return (base + ", but " if s["dist_calc"] != "underfloor" else base[:-1] + ", but ") + r.site_flags[0][0].lower() + r.site_flags[0][1:] + "."
    return base + ", workable but above the efficient 55 °C; a technician should check the radiator sizes."


def _open_checks(h, s, r, missing, flips) -> list[OpenCheck]:
    out: list[OpenCheck] = []
    names = {"build_year": "the year the house was built", "living_area_m2": "the living area",
             "heat_distribution": "your heating surfaces (radiators, underfloor or both)",
             "radiator_count": "the number of radiators"}
    for m in missing:
        out.append(OpenCheck(item=f"We don't know {names[m]}; with it the answer gets sharper.", why="core field"))
    if flips:
        out.append(OpenCheck(item="Was the house insulated or were windows replaced since it was built?",
                             why="this decides the colour"))
    for c in r.contradictions:
        if c.sources and c.sources[0] == "consumption":
            out.append(OpenCheck(item="Your bill and your house size disagree: is all heated area included, and is the yearly use right?",
                                 why=c.what))
        elif "per room" in c.what:
            out.append(OpenCheck(item="Is all heated area included in the documented size (basement, attic)?", why=c.what))
        elif "unused" in c.what:
            out.append(OpenCheck(item="Will the unused part of the house be heated again later?", why="it changes the heating load"))
        elif "Extra heat" in c.what:
            out.append(OpenCheck(item="How much does the stove heat in winter?", why="the bill covers only the rest"))
    if s["dist_calc"] != "underfloor":
        if h.radiator_size is None:
            out.append(OpenCheck(item="Radiator types and sizes are not documented: a technician checks them room by room.",
                                 why="radiator size decides the water temperature"))
        elif h.radiator_size == "small":
            out.append(OpenCheck(item="Small radiators: needs checking room by room.", why="organiser guidance"))
        if h.pipe_system is None:
            out.append(OpenCheck(item=PIPE_SENTENCE, why="organiser guidance"))
        elif h.pipe_system == "single_pipe":
            out.append(OpenCheck(item="Single-pipe system: a technician checks the loop (bypasses, balancing, end radiators).",
                                 why="later radiators get cooler water"))
    out = out[:5]
    out.append(OpenCheck(item="Exact heating load, electrical capacity and where the outdoor unit can go.",
                         why="always checked on site"))
    return out


# ---------------------------------------------------------------- step 9/10: installer brief

def _field_conf(h: House, field: str) -> float:
    src = h.source.get(field)
    if src in ("data", "confirmed"):
        return 0.9
    if src in ("text", "photo", "bill", "listing", "notes_llm"):
        return min(0.8, h.confidence.get(field, 0.6))
    if src in ("rule", "prior"):
        return 0.5
    return 0.9 if src is None and getattr(h, field, None) is not None else 0.3


def confidence_of(h: House, r: Result) -> float:
    s = setup(h, DEFAULT)
    vals = [_field_conf(h, "living_area_m2") if h.living_area_m2 is not None else 0.3,
            _field_conf(h, "build_year") if h.build_year is not None else 0.3]
    fk = fuel_kwh(h)
    vals.append(_field_conf(h, fk["field"]) if fk["field"] and fk["field"] != "certificate_kwh_m2a"
                else 0.5 if fk["field"] else 0.3)
    if s["dist_calc"] != "underfloor":
        if h.radiator_count is not None:
            vals.append(_field_conf(h, "radiator_count"))
        else:
            vals.append(0.5 if s["count"] else 0.3)
        vals.append(_field_conf(h, "radiator_size") if h.radiator_size is not None else 0.3)
    c = sum(vals) / len(vals) - 0.1 * len(r.contradictions)
    if r.traffic_light == "unclear":
        c = min(c, 0.5)
    return round(max(0.1, c), 2)


def _parts(h: House, r: Result) -> Parts:
    s = setup(h, DEFAULT)
    parts = Parts(valves=h.valves_to_replace, balancing="check" if h.hydraulic_balanced else "needed")
    if s["dist_calc"] == "underfloor":
        parts.radiators_note = "n/a (underfloor heating)" + ("; attached radiators: check" if h.radiator_count else "")
        return parts
    L = r.heat_load_kw
    if L.p50 is None or not s["count"]:
        parts.radiators_note = "radiator data missing: count and size on site"
        return parts
    sum_phi = s["count"] * s["phi_point"]
    gain = RADIATOR_KW["large"][0] - s["phi_point"]
    n_ = []
    for load in (L.p10, L.p50, L.p90):
        need = phi_needed(load * s["share_point"], BAND_GREEN_MAX_C, s["pen_point"])
        short = (need or 0) - sum_phi
        n_.append(0 if short <= 0 else (-1 if gain <= 0 else math.ceil(short / gain)))
    if gain <= 0:                                # already large: swapping cannot add output
        if n_[1] != 0:
            parts.radiators_note = "radiators are already large and short: swapping is not enough, add radiators or check per room"
            return parts
        parts.radiators_to_swap = (0, 0, 0)
        if n_[2] != 0:
            parts.radiators_note = "already large; if they fall short on site, add radiators or check per room"
        return parts
    if max(n_) > s["count"]:
        parts.radiators_note = "swapping every radiator may not be enough: add radiators or reduce heat loss"
    parts.radiators_to_swap = tuple(min(x, s["count"]) for x in n_)
    if h.radiator_size is None:
        parts.radiators_note = (parts.radiators_note + "; " if parts.radiators_note else "") + "current size unknown, assumed medium"
    return parts


def installer_brief(h: House, r: Result) -> Result:
    """Fills visit_type, confidence, lead_score, parts, installer_checklist, next_step, next_photo. Idempotent."""
    r = r.model_copy(deep=True)
    s = setup(h, DEFAULT)
    r.confidence = confidence_of(h, r)
    r.lead_score = round((r.p_green + r.p_yellow) * r.confidence, 3)
    if r.boundary:
        r.visit_type = "visit_with_parts"
    elif r.best_color == "red" and r.traffic_light != "unclear":
        r.visit_type = "hold"
    elif r.traffic_light == "unclear":
        r.visit_type = "visit_with_parts"
    elif r.best_color == "yellow" or r.contradictions or r.confidence < 0.7:
        r.visit_type = "visit_with_parts"
    else:
        r.visit_type = "remote_quote"
    r.parts = _parts(h, r)

    ck: list[str] = []                           # site flags are shown by the app right above this list
    for c in r.contradictions:
        ck.append(f"Check on site: {c.what} ({c.trusted or 'open'})")
    if s["unused"]:
        ck.append("Radiators/valves on the unused floor")
    if s["dist_calc"] != "underfloor":
        if h.pipe_system is None:
            ck.append("Pipe system unknown: check for a single-pipe loop (one pipe along the skirting, bypass at H-blocks)")
        elif h.pipe_system == "single_pipe":
            ck.append("Single-pipe loop: check bypasses and balancing; options: larger radiators at the end of the loop, "
                      "higher flow temperature, converting parts of the system")
        if h.radiator_size is None:
            ck.append("Radiator types/sizes not documented: measure room by room")
    ck.extend(n_ for n_ in h.data_notes if "lpg" not in n_.lower())
    ck.extend(ALWAYS_CHECKS)
    r.installer_checklist = ck

    if r.traffic_light == "unclear" or (s["dist_calc"] != "underfloor" and h.radiator_size is None):
        r.next_photo = "Your biggest radiator, from the side, pipes in view."
    else:
        r.next_photo = None

    if r.traffic_light == "unclear":
        r.next_step = NextStep(kind="answer_question", label="Answer one more question",
                               detail=(r.next_question or "") + (" · or request a check" if r.next_question else "or request a check"))
    elif r.best_color == "green":
        r.next_step = NextStep(kind="quote", label="Get a quote",
                               detail="a remote quote is likely possible" if r.visit_type == "remote_quote"
                               else "an installer will want a short look first")
    elif r.best_color == "yellow":
        top = [c.item.rstrip(".") for c in r.open_checks[:3]]
        r.next_step = NextStep(kind="site_check", label="Request a short on-site check",
                               detail="they will look at: " + "; ".join(top))
    else:
        r.next_step = NextStep(kind="path_to_yellow", label="See what gets you to yellow",
                               detail="or talk to an installer anyway")
    return r


def evaluate(h: House, p: Params = DEFAULT, n: int = 500, seed: int = 0) -> Result:
    """Point estimate + Monte Carlo, deterministic; returns a complete Result (installer brief included)."""
    return installer_brief(h, _physics(h, p, n, seed))


# ---------------------------------------------------------------- smoke check

def _print(bid: str, h: House, ref, r: Result):
    f = r.required_flow_temp_c
    pt = next((x.value.split("=")[-1].strip() for x in r.trace if x.label.startswith("Required flow temperature (point)")), "–")
    print(f"{bid} {r.best_color:6} {r.verdict_basis:16} point={pt} flow p50={f.p50} ({f.p10}-{f.p90}) "
          f"load={r.heat_load_kw.p50} bill={r.heat_load_bill_kw.p50} G/Y/R={r.p_green:.2f}/{r.p_yellow:.2f}/{r.p_red:.2f} "
          f"visit={r.visit_type} conf={r.confidence} lead={r.lead_score} parts={r.parts.radiators_to_swap} ref={ref}")
    print(f"    reason: {r.reason}")
    for c in r.contradictions:
        print(f"    ! {c.what} → trusted {c.trusted}")


if __name__ == "__main__":
    try:
        from loader import load_buildings
        buildings = load_buildings(use_llm=False)
    except ImportError:
        raise SystemExit("loader.py missing")
    for bid, h, ref in buildings:
        _print(bid, h, ref, evaluate(h))
    r = evaluate(buildings[0][1])
    print("\nRechenweg", buildings[0][0])
    for st_ in r.trace:
        print(f"  {st_.label}: {st_.value}" + (f"  [{st_.assumption}]" if st_.assumption else ""))
    assert evaluate(buildings[0][1]).model_dump() == r.model_dump(), "not deterministic"
    assert installer_brief(buildings[0][1], r).model_dump() == r.model_dump(), "installer_brief not idempotent"
    print("\ndeterministic ✓  idempotent ✓")
