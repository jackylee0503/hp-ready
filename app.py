"""HP-Ready. Tabs Homeowner / Evaluation / Installer. Layout and copy: docs/design/. The app never computes physics."""
from __future__ import annotations

import urllib.parse
from functools import reduce
from pathlib import Path

import pandas as pd
import streamlit as st

import extract as X
from loader import load_buildings
from schema import DEFAULT, House, Result

st.set_page_config(page_title="HP-Ready", page_icon="🔥", layout="wide")

try:
    import engine
    ENGINE_ERR = None
except Exception as e:                       # engine.py is potatohater8's; the UI must run without it
    engine, ENGINE_ERR = None, str(e)

ROOT = Path(__file__).parent
COL = {"green": "#1E7A46", "yellow": "#F2B705", "red": "#B42318"}
VISIT = {"remote_quote": "Remote quote possible", "visit_with_parts": "Short visit with parts",
         "hold": "Hold: not without changes"}
TERMS = {"Heizlast": "Heating load: the heat the house loses on the coldest design day, in kW.",
         "Vorlauftemperatur": "Flow temperature: how hot the water going into the radiators must be.",
         "JAZ": "Seasonal efficiency: kWh of heat per kWh of electricity over a year.",
         "Ein-/Zweirohr": "Single- or two-pipe: in a single-pipe loop later radiators get cooler water."}

st.markdown("""<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
:root{--bg:#F1F4F7;--ink:#15233B;--muted:#5B6676;--line:#DDE3EA;--line-soft:#EDF1F5;--card:#FFFFFF;
      --g-bg:#E3F1E7;--g-tx:#17652F;--y-bg:#FBF0D5;--y-tx:#7A5205;--r-bg:#FBE4E1;--r-tx:#A1261A;
      --g-fill:#2F7D4A;--y-fill:#F3D58A;--y-fill-tx:#4A3203;--r-fill:#A1261A;
      --bar-g:#3E9E62;--bar-y:#E6B84A;--bar-r:#8E2A1E;--div-pos:#C2412D;--div-neg:#3D6FB6}
.stApp, .stApp *:not([data-testid*="Icon"]):not([translate="no"]) {font-family:'Inter',system-ui,sans-serif;}
.num{font-variant-numeric:tabular-nums}
.chip{display:inline-block;font-size:14px;font-weight:600;padding:6px 10px;border-radius:999px;background:#fff;
      border:1px solid #E2E6EA;margin:0 6px 6px 0;color:#14213D}
.chip.unsure{background:transparent;border:1.5px dashed #9AA5B1;color:#4A5565}
.pill{font-size:11px;font-weight:600;color:#4A5565;background:#EEF1F4;border-radius:999px;padding:3px 7px}
.card{background:#fff;border:1px solid #E2E6EA;border-radius:20px;padding:22px 20px;margin-bottom:12px}
.light{display:inline-block;width:44px;height:44px;border-radius:50%;vertical-align:middle;margin-right:12px}
.muted{color:#4A5565;font-size:14px}
.ok{color:#1E5E37;font-weight:600;font-size:13px}
.bars{display:grid;grid-template-columns:repeat(4,1fr);gap:6px;margin:4px 0 16px}
.bars div{height:5px;border-radius:3px;background:#D5DBE1}
.bars div.on{background:#14213D}
/* Material icons (Streamlit 1.66: span data-testid=stIconMaterial or st*Icon*, aria-hidden, translate=no) keep their font */
.stApp [data-testid="stIconMaterial"], .stApp span[data-testid*="Icon"], .stApp span[translate="no"][aria-hidden="true"],
.stApp .material-symbols-rounded {font-family:"Material Symbols Rounded" !important;}
</style>""", unsafe_allow_html=True)


def html(s: str, where=st):
    where.markdown(s, unsafe_allow_html=True)

# ---------------------------------------------------------------- data + engine (cached)


@st.cache_data(show_spinner="Reading the 5 buildings…")
def buildings():
    return load_buildings()


@st.cache_data(show_spinner=False)
def _run(house_json: str) -> str:
    h = House.model_validate_json(house_json)
    r = engine.evaluate(h)
    if hasattr(engine, "installer_brief"):
        r = engine.installer_brief(h, r)
    return r.model_dump_json()


def evaluate(h: House) -> Result | None:
    if engine is None:
        return None
    try:
        return Result.model_validate_json(_run(h.model_dump_json()))
    except Exception as e:
        st.caption(f"Engine error for {h.building_id}: {e}")
        return None

# ---------------------------------------------------------------- formatting


def t(v):
    return "–" if v is None else (">70 °C" if v > 70 else f"{v:.0f} °C")


def t_range(rg, fmt=None):
    fmt = fmt or t
    if rg.p50 is None:
        return "–"
    return fmt(rg.p50) + (f" ({fmt(rg.p10)}–{fmt(rg.p90)})" if rg.p10 is not None and rg.p90 is not None else "")


def kw(v):
    return "–" if v is None else f"{v:.1f} kW"


def eur(v):
    return "–" if v is None else f"€{v:,.0f}"


def headline(r: Result) -> tuple[str, str]:
    if r.best_color == "green":
        return ("Green, just" if r.boundary else "Green"), "Likely suitable"
    if r.best_color == "red":
        return "Red", "Not without changes"
    return "Yellow", ("Can't tell yet" if r.verdict_basis == "cannot_tell_yet" else "Some checks remain")


def prob_bar(r: Result) -> str:
    parts = "".join(f'<div style="width:{p * 100:.1f}%;background:{COL[c]}"></div>'
                    for c, p in (("green", r.p_green), ("yellow", r.p_yellow), ("red", r.p_red)))
    return (f'<div role="img" aria-label="green {r.p_green:.0%}, yellow {r.p_yellow:.0%}, red {r.p_red:.0%}" '
            f'style="display:flex;height:10px;border-radius:5px;overflow:hidden">{parts}</div>')


def scale(r: Result) -> str:
    rg = r.required_flow_temp_c
    if rg.p50 is None:
        return ""

    def pos(v):
        return max(0.0, min(100.0, (v - 35) / 35 * 100))
    lo, hi, mid = pos(rg.p10 if rg.p10 is not None else rg.p50), pos(rg.p90 if rg.p90 is not None else rg.p50), pos(rg.p50)
    lo, hi = min(lo, hi), max(lo, hi)
    marks = "".join(
        f'<div style="position:absolute;left:{pos(v)}%;top:36px;width:1.5px;height:8px;background:#6B7684"></div>'
        f'<p style="position:absolute;left:{pos(v)}%;top:46px;margin:0;transform:translateX(-50%);font-size:12px;'
        f'color:#4A5565;text-align:center;line-height:1.25">{v}<br>{w}</p>'
        for v, w in ((45, "ideal"), (55, "efficient"), (60, "pricier")))
    return (f'<div style="position:relative;height:84px" role="img" aria-label="likely {t(rg.p10)} to {t(rg.p90)}">'
            '<div style="position:absolute;left:0;right:0;top:22px;height:10px;border-radius:5px;background:#E6EAEE"></div>'
            f'<div style="position:absolute;left:{lo}%;width:{max(hi - lo, 1)}%;top:22px;height:10px;border-radius:5px;'
            f'background:#A9D6B9;box-shadow:inset 0 0 0 1.5px {COL[r.best_color]}"></div>'
            f'<div style="position:absolute;left:{mid}%;top:14px;width:3px;height:26px;margin-left:-1.5px;'
            'border-radius:2px;background:#14213D"></div>'
            '<p style="position:absolute;left:0;top:46px;margin:0;font-size:12px;color:#4A5565">35</p>'
            '<p style="position:absolute;right:0;top:46px;margin:0;font-size:12px;color:#4A5565">70 °C</p>'
            f'{marks}</div>')

# ---------------------------------------------------------------- ui components
# Pure HTML-string helpers shared by Evaluation and Installer (render with st.html or html()). Display only.

_SOFT = {"green": ("var(--g-bg)", "var(--g-tx)"), "yellow": ("var(--y-bg)", "var(--y-tx)"),
         "red": ("var(--r-bg)", "var(--r-tx)")}
_FILLED = {"green": ("var(--g-fill)", "#FFFFFF"), "yellow": ("var(--y-fill)", "var(--y-fill-tx)"),
           "red": ("var(--r-fill)", "#FFFFFF")}
FIELD_NAMES = {"insulation_measures": "Insulation", "solar_thermal_dhw": "Solar thermal for hot water",
               "extra_heat_source": "Extra heat source", "extra_source_all_winter": "Used all winter",
               "unheated_area_note": "Unused area", "u_values": "U-values", "glazing": "Glazing",
               "building_type": "Building type", "build_year": "Build year", "living_area_m2": "Living area",
               "annual_fuel_kwh": "Yearly fuel use", "fuel_type": "Fuel", "radiator_count": "Radiators",
               "radiator_size": "Radiator size", "pipe_system": "Pipe system", "heat_distribution": "Heat distribution",
               "valves_to_replace": "Valves to replace", "hydraulic_balanced": "Hydraulic balancing",
               "dhw_by_boiler": "Hot water via boiler", "current_flow_temp_c": "Current flow temperature",
               "occupants": "Occupants", "renovation": "Renovation"}
ENUM_NAMES = {"semi_detached": "Semi-detached", "terraced": "Terraced", "detached": "Detached", "two_pipe": "Two-pipe", "single_pipe": "Single-pipe",
              "remote_quote": "Remote quote", "visit_with_parts": "Short visit with parts", "hold": "Hold until changes",
              "wood_stove": "Wood stove", "tiled_stove": "Tiled stove", "heat_pump": "Heat pump", "lpg": "LPG",
              "partially": "Partly renovated", "fully": "Fully renovated", "unrenovated": "Not renovated",
              "insulation_first": "Insulation first", "notes_llm": "Notes (AI)", "none": "None"}


def pill(color: str, text: str, filled: bool = False, size: str = "12px") -> str:
    """Soft (default) or filled colour pill; unknown colour -> neutral outline."""
    pad = "6px 12px" if filled else "4px 10px"
    if color in _SOFT:
        bg, fg = (_FILLED if filled else _SOFT)[color]
        sty = f"background:{bg};color:{fg}"
    else:
        sty = "background:transparent;border:1px solid #C9D2DD;color:var(--muted)"
    return (f'<span style="display:inline-block;font-size:{size};padding:{pad};border-radius:999px;'
            f'font-weight:600;white-space:nowrap;{sty}">{text}</span>')


def stacked_bar(pg: float, py: float, pr: float, width: str = "150px", height: int = 8) -> str:
    seg = "".join(f'<span style="width:{max(p or 0, 0) * 100:.1f}%;background:var(--bar-{c});display:block"></span>'
                  for c, p in (("g", pg), ("y", py), ("r", pr)))
    return (f'<span role="img" aria-label="green {pg or 0:.0%}, yellow {py or 0:.0%}, red {pr or 0:.0%}" '
            f'style="display:flex;height:{height}px;border-radius:{height / 2:g}px;overflow:hidden;width:{width};'
            f'background:var(--line-soft)">{seg}</span>')


def kpi_card(label: str, big: str, sub_html: str = "", aside: str = "") -> str:
    """Evaluation KPI card. Text wraps, never truncates. `aside` = small muted text beside the big number."""
    side = f'<div style="font-size:13px;color:var(--muted)">{aside}</div>' if aside else ""
    return ('<div style="background:var(--card);border:1px solid var(--line);border-radius:16px;padding:22px 24px;'
            'display:flex;flex-direction:column;gap:12px;min-width:0;overflow-wrap:anywhere">'
            f'<div style="font-size:13px;color:var(--muted);font-weight:500">{label}</div>'
            '<div style="display:flex;align-items:baseline;gap:10px;flex-wrap:wrap">'
            f'<div class="num" style="font-size:40px;font-weight:700;letter-spacing:-0.02em;line-height:1;'
            f'color:var(--ink)">{big}</div>{side}</div>{sub_html}</div>')


def diverging_bar(pct: float | None, half: float = 25) -> str:
    """0-centred bar: + red to the right, − blue to the left; half the track = ±half %."""
    track = 'position:relative;height:8px;background:var(--line-soft);border-radius:4px;display:block'
    if pct is None:
        return f'<span style="{track}"></span>'
    w = min(abs(pct) / half, 1) * 50
    side = ("left:50%;background:var(--div-pos);border-radius:0 4px 4px 0" if pct >= 0
            else "right:50%;background:var(--div-neg);border-radius:4px 0 0 4px")
    return (f'<span role="img" aria-label="{pct:+.1f} %" style="{track}">'
            f'<span style="position:absolute;top:0;height:8px;width:{w:.1f}%;{side};display:block"></span></span>')


def score_bar(score: float | None) -> str:
    s = max(0.0, min(1.0, score or 0.0))
    val = "–" if score is None else f"{score:.2f}"
    return ('<span style="display:flex;align-items:center;gap:8px"><span style="width:70px;height:6px;'
            'background:var(--line-soft);border-radius:3px;display:block;overflow:hidden">'
            f'<span style="width:{s * 100:.0f}%;height:6px;background:var(--ink);display:block"></span></span>'
            f'<span class="num" style="font-size:13px">{val}</span></span>')


def flow_scale(p10: float | None, p50: float | None, p90: float | None, lo_t: float = 35, hi_t: float = 75) -> str:
    """35–75 °C scale: 4 coloured bands, grey likely-range bar above, navy p50 marker, labels in a grid below."""
    if p50 is None and p10 is None and p90 is None:
        return ""
    span = hi_t - lo_t

    def pos(v):
        return max(0.0, min(100.0, (v - lo_t) / span * 100))
    bands = [(45, "#2F7D4A", "ideal ≤45"), (55, "#7CC293", "efficient ≤55"), (60, "#E6B84A", "≤60"),
             (hi_t, "#E9C9C3", "pricier above")]
    widths, prev = [], lo_t
    for edge, _, _ in bands:
        widths.append((edge - prev) / span * 100)
        prev = edge
    segs = "".join(f'<span style="width:{w:.2f}%;background:{c};display:block"></span>' for w, (_, c, _) in zip(widths, bands))
    cols = " ".join(f"{w:.2f}fr" for w in widths)
    labels = "".join(f'<span style="text-align:{"right" if i == 3 else "left"}">{lab}</span>'
                     for i, (_, _, lab) in enumerate(bands))
    vals = [v for v in (p10, p90) if v is not None] or [p50]
    a, b = pos(min(vals)), pos(max(vals))
    rng = (f'<span style="position:absolute;left:{a:.2f}%;width:{max(b - a, 1):.2f}%;top:0;height:6px;border-radius:3px;'
           'background:#C9D2DD;display:block"></span>')
    mark = ("" if p50 is None else
            f'<span style="position:absolute;left:{pos(p50):.2f}%;top:8px;width:3px;height:22px;margin-left:-1px;'
            'background:var(--ink);border-radius:2px;display:block"></span>')
    return (f'<div role="img" aria-label="flow temperature {t(p50)}, likely {t(min(vals))} to {t(max(vals))}">'
            f'<div style="position:relative;height:34px">{rng}<span style="position:absolute;left:0;right:0;top:14px;'
            f'height:10px;display:flex;border-radius:5px;overflow:hidden">{segs}</span>{mark}</div>'
            f'<div style="display:grid;grid-template-columns:{cols};font-size:11px;color:var(--muted);margin-top:4px">'
            f'{labels}</div></div>')


def human_enum(v) -> str:
    s = str(v)
    if s in ENUM_NAMES:
        return ENUM_NAMES[s]
    return s.replace("_", " ").capitalize() if s.replace("_", "").isalnum() and s.islower() else s


def human_field(name: str) -> str:
    return FIELD_NAMES.get(name, name.replace("_", " ").capitalize())


def human_value(v) -> str:
    if v is None or v == "" or (isinstance(v, (list, tuple, set, dict)) and not v):
        return "None"
    if isinstance(v, bool):
        return "Yes" if v else "No"
    if isinstance(v, float):
        return f"{v:,.0f}" if abs(v) >= 100 else f"{v:.2f}".rstrip("0").rstrip(".")
    if isinstance(v, (list, tuple, set)):
        return ", ".join(human_value(x) for x in v)
    if isinstance(v, dict):
        return ", ".join(f"{human_field(k)} {human_value(x)}" for k, x in v.items() if x is not None) or "None"
    return human_enum(v)


def fmt_range(lo, hi, unit: str = "") -> str:
    u = f" {unit}" if unit else ""
    if lo is None and hi is None:
        return "–"
    if lo is None or hi is None or round(lo, 1) == round(hi, 1):
        return f"{round(lo if hi is None else hi, 1):g}{u}"
    lo, hi = min(lo, hi), max(lo, hi)
    return f"{round(lo, 1):g}–{round(hi, 1):g}{u}"


def pct_diff(a, b) -> str:
    """(a − b) / b as a signed rounded % with a real minus sign, e.g. '+16 %', '−4 %'."""
    if a is None or not b:
        return "–"
    d = round((a - b) / b * 100)
    return f"{'+' if d > 0 else '−' if d < 0 else '±'}{abs(d)} %"

# ---------------------------------------------------------------- shared blocks


def rechenweg(r: Result):
    b = r.heat_load_bill_kw
    st.markdown(f"Heating load (size, age): **{t_range(r.heat_load_kw, kw)}**  \n"
                f"From the bill: {t_range(b, kw)}")
    if r.trace:
        st.dataframe(pd.DataFrame([s.model_dump() for s in r.trace]), hide_index=True, width="stretch")
    for c in r.contradictions:
        st.markdown(f"- **{c.what}**" + (f" · trusted: {c.trusted}." if c.trusted else "") + f" {c.why or ''}")
    st.caption("First estimate, not a DIN EN 12831 calculation. " + " · ".join(f"{k}: {v}" for k, v in TERMS.items()))


def answer_card(h: House, r: Result | None, key: str):
    if r is None:
        st.info(f"Engine not ready yet ({ENGINE_ERR or 'no result'}).")
        return
    title, word = headline(r)
    html(f'<div class="card"><span class="light" style="background:{COL[r.best_color]}"></span>'
         f'<span style="font-size:26px;font-weight:700">{title}</span> <span class="muted">{word}</span>'
         f'<p style="font-size:16px;margin:12px 0 0">{r.reason}</p></div>')
    top = max((("green", r.p_green), ("yellow", r.p_yellow), ("red", r.p_red)), key=lambda x: x[1])
    with st.expander(f"How sure · {top[1]:.0%} {top[0]}"):
        html(prob_bar(r))
        st.caption(f"Green {r.p_green:.0%} · Yellow {r.p_yellow:.0%} · Red {r.p_red:.0%}")
    with st.expander(f"Water temperature · ≈ {t(r.required_flow_temp_c.p50)}"):
        html(scale(r))
        rg = r.required_flow_temp_c
        st.caption((f"Likely {t(rg.p10)}–{t(rg.p90)}. " if rg.p10 is not None and rg.p90 is not None else "")
                   + "Lower is cheaper.")
    with st.expander("Running cost" + (f" · save ~{eur(r.saving_eur)}/yr" if r.saving_eur and r.saving_eur > 0 else "")):
        st.markdown(f"Today **{eur(r.cost_now_eur)}** · heat pump **{eur(r.cost_hp_eur)}**")
        if r.cost_note:
            st.caption(r.cost_note)
        st.caption("Challenge prices. Installation and subsidies come with the quote.")
    if r.open_checks:
        n = len(r.open_checks)
        with st.expander(f"What's still open · {n} thing{'s' if n != 1 else ''}"):
            for i, c in enumerate(r.open_checks, 1):
                st.markdown(f"{i}. {c.item}" + (f" ({c.why})" if c.why else ""))
    with st.expander("How we got this"):
        rechenweg(r)
    for hint in r.hints:
        st.caption(hint)
    if r.next_step:
        st.button(r.next_step.label, key=f"next_{key}", type="primary", width="stretch")
        if r.next_step.detail:
            st.caption(r.next_step.detail)

# ---------------------------------------------------------------- tabs


def tab_evaluation():
    B = buildings()
    res = [(bid, h, ref, evaluate(h)) for bid, h, ref in B]
    dev = [(ref, r) for _, _, ref, r in res if ref and r]
    c1, c2, c3 = st.columns(3)
    c1.metric("Dev verdicts reproduced", f"{sum(r.best_color == ref['verdict'] for ref, r in dev)} / {len(dev)}")
    loo = None
    try:
        import calibrate
        loo = calibrate.leave_one_out(B)
        c2.metric("Load error, leave-one-out", " · ".join(f"{e:+.0f} %" for e in loo["error_pct"]))
    except Exception:
        c2.metric("Load error, leave-one-out", "–")
    c3.metric("Calibrated numbers", f"1 (k = {DEFAULT.k:.2f})")

    rows = []
    for bid, h, ref, r in res:
        if r is None:
            continue
        mark = (" ✓" if ref["verdict"] == r.best_color else " ✗") if ref else ""
        rows.append({"Building": bid, "Set": "dev" if ref else "eval", "Verdict": r.best_color.capitalize() + mark,
                     "How sure": f"G {r.p_green:.0%} · Y {r.p_yellow:.0%} · R {r.p_red:.0%}",
                     "Water temp.": t_range(r.required_flow_temp_c),
                     "Heating load": f"{kw(r.heat_load_kw.p50)} · " + (f"ref {ref['heating_load_kw']} kW" if ref
                                                                        else f"bill {kw(r.heat_load_bill_kw.p50)}"),
                     "Flags": len(r.contradictions) + len(r.site_flags),
                     "Visit": VISIT.get(r.visit_type, "–"), "Lead score": round(r.lead_score, 2)})
    if rows:
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    else:
        st.info(f"Engine not ready yet ({ENGINE_ERR}). Buildings load fine: {', '.join(b for b, *_ in res)}")
    if loo is not None:
        with st.expander("Leave-one-out table"):
            st.dataframe(loo, hide_index=True, width="stretch")

    sel = st.selectbox("Details", [b for b, *_ in res], index=len(res) - 1)
    bid, h, ref, r = next(x for x in res if x[0] == sel)
    st.subheader(f"{bid} · {h.build_year} · {h.living_area_m2 or 0:.0f} m² · {h.fuel_type} · "
                 f"{h.radiator_count or '?'} radiators · {h.heat_distribution}")
    left, right = st.columns([3, 2])
    with left:
        if r:
            st.markdown("**Contradictions · which source we trusted**")
            for c in r.contradictions or []:
                st.markdown(f"- {c.what}" + (f" → trusted **{c.trusted}**" if c.trusted else "") + (f": {c.why}" if c.why else ""))
            if not r.contradictions:
                st.caption("None found.")
        o = h.notes_obs
        st.markdown("**What the AI read in the notes**" + (" (rule-based analysis)" if o and o.method == "keywords" else ""))
        for f, q in (o.evidence.items() if o else []):
            st.markdown(f"> \"{q}\"  \n→ {f.replace('_', ' ')}: {getattr(o, f, '')}")
        for n in h.data_notes:
            st.caption(n)
    with right:
        answer_card(h, r, f"eval_{bid}")


CHIPS = [("build_year", "{}"), ("living_area_m2", "{:.0f} m²"), ("building_type", "{}"), ("renovation", "{} renovated"),
         ("heat_distribution", "{}"), ("fuel_type", "{}"), ("annual_fuel_kwh", "{:,.0f} kWh"), ("occupants", "{} people"),
         ("radiator_count", "{} radiators"), ("radiator_size", "{} radiators"), ("pipe_system", "{}"),
         ("kwh_printed", "{:,.0f} kWh printed"), ("certificate_kwh_m2a", "{:.0f} kWh/m²a"), ("outdoor_unit_space", "outdoor spot: {}")]
FIX = [("build_year", "Built", None), ("living_area_m2", "Living area (m²)", None),
       ("heat_distribution", "Heating surfaces", ["radiators", "underfloor", "mixed"]),
       ("renovation", "Insulation / renovation", ["unrenovated", "partially", "fully"]),
       ("fuel_type", "Heating fuel", ["gas", "lpg", "oil", "district", "electric"]),
       ("annual_fuel_kwh", "Yearly use (kWh)", None), ("occupants", "People", None),
       ("radiator_count", "Radiators", None), ("radiator_size", "Radiator size", ["small", "medium", "large"])]


def chips(h: House) -> str:
    out = []
    for f, fmt in CHIPS:
        v = getattr(h, f)
        if v is None:
            continue
        unsure = h.confidence.get(f, 1) < 0.5
        text = ({"unrenovated": "not renovated", "partially": "partly renovated", "fully": "fully renovated"}.get(v, v)
                if f == "renovation" else fmt.format(v).replace("_", " "))
        out.append(f'<span class="chip{" unsure" if unsure else ""}">{text}{"?" if unsure else ""}</span>')
    return "".join(out)


def home_house() -> House:
    ss = st.session_state
    h = reduce(X.merge, [House.model_validate_json(j) for j in ss.reads.values()], House(building_id="Homeowner"))
    conf = House(building_id="Homeowner", **ss.confirmed)
    conf.source = {f: "confirmed" for f in ss.confirmed}
    conf.confidence = {f: 0.9 for f in ss.confirmed}
    h = X.merge(h, conf)
    for f in ss.get("cleared", set()):          # "don't know" in step 4 wipes what was read
        setattr(h, f, None)
        h.source.pop(f, None)
        h.confidence.pop(f, None)
    return h


def do_read(slot: str, data: bytes, mime: str, mission: str):
    ss = st.session_state
    with st.spinner("Reading…"):
        try:
            ss.reads[slot] = X.extract(data, mime, mission).model_dump_json()
        except Exception as e:
            st.warning(f"We couldn't read that ({e}). You can skip this step.")
            return
    for f, *_ in FIX:                           # unconfirmed step-4 fields reseed from the new read
        if f not in ss.get("confirmed", {}):
            ss.pop(f"fix_{f}", None)


def read_upload(up, slot: str, mission: str):
    if up is None:
        return
    tag = f"{up.name}:{up.size}"
    if st.session_state.get(f"tag_{slot}_up") != tag:
        st.session_state[f"tag_{slot}_up"] = tag      # before the read, so a failing read isn't retried
        do_read(slot, up.getvalue(), up.type or "image/jpeg", mission)


FLOAT_FIELDS = ("living_area_m2", "annual_fuel_kwh")


def fix_changed(f: str):
    ss = st.session_state
    v = ss.get(f"fix_{f}")
    if v is None or v == "don't know" or v == 0:   # empty (or 0) = don't know
        ss.confirmed.pop(f, None)
        ss.cleared.add(f)
    else:
        ss.confirmed[f] = v
        ss.cleared.discard(f)


def conflict_picked(f: str, vals: list):
    ss = st.session_state
    i = ss.get(f"q_{f}")
    if i is None or i >= len(vals):             # "don't know" or nothing
        return
    v = vals[i]
    ss.confirmed[f] = v
    ss.cleared.discard(f)
    fix = {x: o for x, _, o in FIX}
    if f not in fix:
        return
    if fix[f]:
        ss[f"fix_{f}"] = v if v in fix[f] else "don't know"
    else:
        try:
            ss[f"fix_{f}"] = float(v) if f in FLOAT_FIELDS else int(v)
        except (TypeError, ValueError):
            ss.pop(f"fix_{f}", None)


def show_read(slot: str):
    j = st.session_state.reads.get(slot)
    if not j:
        return
    h = House.model_validate_json(j)
    html('<p class="ok">✓ We read</p>' + chips(h))
    if h.evidence:
        with st.expander("Why?"):
            for f, q in h.evidence.items():
                st.caption(f"{f.replace('_', ' ')}: {q}")
    if h.retake_tip or h.missing:
        st.info(h.retake_tip or "Some of it was unreadable. One more photo?")


def nav(step: int, can_skip: bool) -> str | None:
    c1, c2, c3 = st.columns(3)
    act = None
    if step > 1 and c1.button("Back", key=f"back{step}", width="stretch"):
        act = "back"
    if can_skip and c2.button("Skip", key=f"skip{step}", width="stretch"):
        act = "next"
    if c3.button("Show my answer" if step == 4 else "Next", key=f"next{step}", type="primary", width="stretch"):
        act = "next"
    return act


def tab_homeowner():
    ss = st.session_state
    ss.setdefault("step", 1)
    ss.setdefault("reads", {})
    ss.setdefault("confirmed", {})
    ss.setdefault("cleared", set())
    h = home_house()
    left, right = st.columns([3, 2])
    with left:
        if ss.step <= 4:
            html('<div class="bars">' + "".join(f'<div class="{"on" if i <= ss.step else ""}"></div>' for i in range(1, 5))
                 + f'</div><span class="muted">{ss.step} of 4</span>')
        act = None
        if ss.step == 1:
            st.markdown("## Tell us about your house")
            st.caption("Year, size, heating. Whatever you know.")
            demo = (ROOT / "assets/demo/house_persona_en.txt").read_text(encoding="utf-8").strip()
            st.button("Use the example text", on_click=lambda: ss.update(house_text=demo))
            txt = st.text_area("Your house", key="house_text", placeholder=demo, height=130)
            if st.button("Read it", disabled=not txt.strip()):
                do_read("house_text", txt.strip().encode("utf-8"), "text/plain", "house_text")
            show_read("house_text")
            read_upload(st.file_uploader("Photo of the outside · optional", type=["jpg", "jpeg", "png", "webp"],
                                         key="up_ext"), "exterior", "exterior")
            show_read("exterior")
            act = nav(1, False)
            if act == "next" and txt.strip() and "house_text" not in ss.reads:
                do_read("house_text", txt.strip().encode("utf-8"), "text/plain", "house_text")
        elif ss.step == 2:
            st.markdown("## Your biggest radiator")
            st.caption("From the side, pipes in view.")
            read_upload(st.file_uploader("Radiator photo", type=["jpg", "jpeg", "png", "webp"], key="up_rad"),
                        "radiator", "radiator")
            photos = sorted(p.name for p in (ROOT / "data/pipe_photos").glob("*.jp*g"))
            pick = st.selectbox("or use an example photo", ["–"] + photos)
            if pick != "–" and ss.get("tag_radiator_ex") != pick:
                ss["tag_radiator_ex"] = pick
                do_read("radiator", (ROOT / "data/pipe_photos" / pick).read_bytes(), "image/jpeg", "radiator")
            if pick != "–":
                st.image(str(ROOT / "data/pipe_photos" / pick), width=320)
            show_read("radiator")
            act = nav(2, True)
        elif ss.step == 3:
            st.markdown("## Bill or listing?")
            st.caption("Optional. Photo, PDF or screenshot.")
            read_upload(st.file_uploader("Bill or listing", type=["jpg", "jpeg", "png", "webp", "pdf"], key="up_doc"),
                        "doc", "bill")
            if st.button("Use the demo bill photo"):
                ss["tag_doc_demo"] = "demo"
                do_read("doc", (ROOT / "assets/demo/bill_demo_gas_2025_photo.jpg").read_bytes(), "image/jpeg", "bill")
            show_read("doc")
            st.caption("Only the numbers are kept.")
            act = nav(3, True)
        elif ss.step == 4:
            st.markdown("## Is this right?")
            st.caption("Tap to fix.")
            for f, label, opts in FIX:                # `confirmed` is written only by on_change callbacks
                v, key = getattr(h, f), f"fix_{f}"
                c1, c2, c3 = st.columns([2, 3, 1])
                c1.markdown(label)
                if opts:
                    choices = ["don't know"] + opts
                    if key not in ss:
                        ss[key] = v if v in choices else "don't know"
                    c2.selectbox(label, choices, key=key, label_visibility="collapsed", on_change=fix_changed, args=(f,))
                elif f in FLOAT_FIELDS:
                    if key not in ss:
                        ss[key] = None if v is None else float(v)
                    c2.number_input(label, min_value=0.0, value=None, step=1.0 if f == "living_area_m2" else 100.0, format="%.0f",
                                    key=key, label_visibility="collapsed", help="empty = don't know",
                                    on_change=fix_changed, args=(f,))
                else:
                    if key not in ss:
                        ss[key] = None if v is None else int(v)
                    c2.number_input(label, min_value=0, value=None, step=1, key=key, label_visibility="collapsed",
                                    help="empty = don't know", on_change=fix_changed, args=(f,))
                html(f'<span class="pill">{h.source.get(f, "missing")}</span>', c3)
            asked = 0
            for c in h.conflicts:
                if c["field"] in ss.confirmed or asked >= 2:
                    continue
                (sa, va), (sb, vb) = list(c["values"].items())[:2]
                labels = [str(va), str(vb), "don't know"]
                st.radio(f"Your {sa} says {va}, your {sb} says {vb}. Which one is it?", [0, 1, 2],
                         format_func=lambda i, lb=labels: lb[i], index=None, key=f"q_{c['field']}",
                         on_change=conflict_picked, args=(c["field"], [va, vb]))
                asked += 1
            try:
                q = engine.next_question(home_house()) if engine is not None and hasattr(engine, "next_question") else None
            except Exception:
                q = None
            if q and asked < 2:
                st.info(q)
            elif not asked:
                html('<p class="ok">✓ No questions for you</p>')
            act = nav(4, False)
        else:
            if st.button("Change answers"):
                ss.step = 4
                st.rerun()
            r = evaluate(h)
            answer_card(h, r, "home")
            if r is not None:
                request_panel(h, r, "home")
        if act == "next":
            ss.step += 1
            st.rerun()
        if act == "back":
            ss.step -= 1
            st.rerun()
    with right:
        h = home_house()                              # reads in this run happened after the first merge
        html('<div class="card"><b>What we know so far</b> <span class="muted">tap to fix</span></div>')
        fmts = {**dict(CHIPS), "renovation": "{}", "radiator_count": "{}", "radiator_size": "{}", "occupants": "{}",
                "kwh_printed": "{:,.0f} kWh"}
        for f, label, _ in FIX + [("pipe_system", "Pipes", None), ("kwh_printed", "Bill kWh", None)]:
            v = getattr(h, f)
            if v is not None:
                try:
                    s = fmts.get(f, "{}").format(v)
                except (ValueError, TypeError):
                    s = str(v)
                c1, c2 = st.columns([3, 1])
                c1.markdown(f"{label}: **{s.replace('_', ' ')}**")
                html(f'<span class="pill">{h.source.get(f, "")}</span>', c2)


def request_panel(h: House, r: Result, key: str):
    html('<div class="card" style="border:1.5px solid #14213D"><b>Your request is ready</b><br>'
         '<span class="muted">Just add how to reach you.</span></div>')
    name = st.text_input("Name", key=f"name_{key}")
    contact = st.text_input("E-mail or phone", key=f"contact_{key}")
    plz = st.text_input("Postcode", key=f"plz_{key}")
    pdf = None
    if engine is not None and hasattr(engine, "handover_pdf"):
        try:
            pdf = engine.handover_pdf(h, r, {"name": name, "contact": contact, "postcode": plz})
        except Exception as e:
            st.caption(f"PDF not available: {e}")
    if pdf:
        st.download_button("PDF for the installer", pdf, file_name="pre-visit-sheet.pdf", mime="application/pdf",
                           type="primary", width="stretch", key=f"pdf_{key}")
    subject = f"Heat pump: {VISIT.get(r.visit_type, 'quote request')}"
    body = (f"Hello,\n\nplease find my pre-visit sheet attached (HP-Ready first estimate: {r.best_color}, "
            f"about {t(r.required_flow_temp_c.p50)}).\n\n{name}\n{contact}\n{plz}")
    st.link_button("Open as e-mail", "mailto:?" + urllib.parse.urlencode({"subject": subject, "body": body},
                                                                          quote_via=urllib.parse.quote), width="stretch")
    st.caption("One page any installer reads in a minute. Nothing is stored.")


def tab_installer():
    opts = {bid: h for bid, h, _ in buildings()}
    if st.session_state.get("reads"):
        opts["Homeowner house"] = home_house()
    left, right = st.columns([1, 3])
    sel = left.radio("Leads", list(opts), index=len(opts) - 1)
    h = opts[sel]
    r = evaluate(h)
    with right:
        if r is None:
            st.info(f"Engine not ready yet ({ENGINE_ERR or 'no result'}).")
            return
        st.markdown(f"### {sel} · {h.building_type or ''} {h.build_year or ''} · {h.living_area_m2 or 0:.0f} m² · {h.fuel_type or ''}")
        html(f'<span class="chip" style="background:{COL[r.best_color]};color:{"#14213D" if r.best_color == "yellow" else "#fff"}">'
             f'{VISIT.get(r.visit_type, "–")}</span>')
        st.markdown(r.reason)
        html(f'<span class="chip">Load {kw(r.heat_load_kw.p50)} (bill {kw(r.heat_load_bill_kw.p50)})</span>'
             f'<span class="chip">Water {t_range(r.required_flow_temp_c)}</span>'
             f'<span class="chip">{h.radiator_count or "?"} radiators, size {h.radiator_size or "unknown"}</span>')
        c1, c2, c3 = st.columns(3)
        with c1:
            st.markdown("**Path to yellow**")
            for p in r.path_to_yellow or ["–"]:
                st.markdown(f"- {p}")
        with c2:
            st.markdown("**Bring**")
            rs = r.parts.radiators_to_swap
            st.markdown(f"- Radiators to swap: {f'{rs[1]} ({rs[0]}–{rs[2]})' if rs else '–'}")
            if r.parts.radiators_note:
                st.caption(r.parts.radiators_note)
            st.markdown(f"- Valves: {r.parts.valves if r.parts.valves is not None else 'none documented'}")
            st.markdown(f"- Hydraulic balancing: {r.parts.balancing or '–'}")
        with c3:
            st.markdown("**Check on site**")
            for c in r.site_flags + r.installer_checklist:
                st.markdown(f"- {c}")
        missing = [f for f in ("build_year", "living_area_m2", "annual_fuel_kwh", "radiator_count", "radiator_size")
                   if getattr(h, f) is None]
        if missing:
            st.caption("Missing: " + ", ".join(m.replace("_", " ") for m in missing))
        with st.expander("How we got this"):
            rechenweg(r)
        request_panel(h, r, f"inst_{sel}")


top_l, top_r = st.columns([4, 1])
top_l.markdown("### HP-Ready")
X.DEMO_ONLY = top_r.toggle("Demo mode", help="Use cached reads only, no live AI calls.")
t_home, t_eval, t_inst = st.tabs(["Homeowner", "Evaluation", "Installer"])
with t_home:
    tab_homeowner()
with t_eval:
    tab_evaluation()
with t_inst:
    tab_installer()
