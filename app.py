"""HP-Ready. Tabs Homeowner / Evaluation / Installer. Layout and copy: docs/design/. The app never computes physics."""
from __future__ import annotations

import re
import urllib.parse
from datetime import date
from functools import reduce
from html import escape as esc
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
.ev-th{font-size:12px;font-weight:500;color:var(--muted);text-align:left;padding:12px 12px;border:none;
       border-bottom:1px solid var(--line);white-space:nowrap;background:transparent}
.ev-td{font-size:14px;color:var(--ink);padding:14px 12px;border:none;border-bottom:1px solid var(--line-soft);
       vertical-align:middle;white-space:nowrap;background:transparent}
.ev-sub{display:block;font-size:12px;color:var(--muted);margin-top:2px}
.ev-card{background:var(--card);border:1px solid var(--line);border-radius:16px;min-width:0}
/* Installer: lead cards (an invisible full-size button sits on top of each card), KPI strip, checks card */
.lead-card{background:transparent;border:1px solid var(--line);border-radius:14px;padding:14px 16px;display:flex;
           flex-direction:column;gap:6px;min-height:44px;color:var(--ink);box-sizing:border-box}
.lead-card.sel{background:#fff;border:1.5px solid var(--ink)}
.stApp [class*="st-key-leadbox_"]{position:relative;gap:0}
.stApp [class*="st-key-leadbtn_"]{position:absolute;inset:0;z-index:2;margin:0}
.stApp [class*="st-key-leadbtn_"] button{width:100%;height:100%;min-height:44px;opacity:0;cursor:pointer}
.stApp [class*="st-key-leadbox_"]:hover .lead-card:not(.sel){border-color:#C9D2DD;background:#FAFBFC}
.stApp [class*="st-key-leadbox_"]:has(button:focus-visible) .lead-card{outline:2px solid var(--ink);outline-offset:2px}
.kpi-strip{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));background:var(--card);
           border:1px solid var(--line);border-radius:16px;overflow:hidden}
.kpi-cell{padding:16px 20px;display:flex;flex-direction:column;gap:4px;border-left:1px solid var(--line-soft);
          margin-left:-1px}
.stApp [class*="st-key-stdchecks_"]{background:var(--card);border:1px solid var(--line);border-radius:16px;
           padding:20px 22px 10px;gap:0}
.stApp [class*="st-key-stdchecks_"] [data-testid="stCheckbox"]{border-top:1px solid var(--line-soft);padding:10px 0}
.stApp [class*="st-key-stdchecks_"] [data-testid="stCheckbox"] p{font-size:14px;color:var(--ink)}
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
    return (f'<div role="img" aria-label="{esc(f"flow temperature {t(p50)}, likely {t(min(vals))} to {t(max(vals))}")}">'
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


def signed_pct(v: float | None, nd: int = 1) -> str:
    """'+19.8 %' / '−9.4 %' with a real minus sign."""
    if v is None:
        return "–"
    return f"{'+' if v > 0 else '−' if v < 0 else '±'}{abs(v):.{nd}f} %"


def pct(p: float | None) -> str:
    return "–" if p is None else f"{round(p * 100)} %"


def flow_span(p10: float | None, p90: float | None) -> str:
    """Likely flow range, en dash, '70+' when the tail runs past the display clip."""
    if p10 is None or p90 is None:
        return "–"
    lo, hi = min(p10, p90), max(p10, p90)
    if lo > 70:
        return ">70 °C"
    return f"{lo:.0f}–{min(hi, 70):.0f}{'+' if hi > 70 else ''} °C"


def clean_text(s: str | None) -> str:
    """Engine prose for display: 'MC' -> 'simulation', '->' -> arrow, ASCII ranges -> en dash. Not escaped."""
    s = (s or "").strip()
    s = re.sub(r"\bthe MC\b", "the simulation", s)
    s = re.sub(r"\bMC\b", "simulation", s)
    s = s.replace("->", "→")
    s = re.sub(r"(\d)-(\d)", r"\1–\2", s)
    s = re.sub(r"\(([+-]?\d+)%\)", lambda m: f"({signed_pct(float(m.group(1)), 0)})", s)
    return s[:1].upper() + s[1:] if s else s


TRUSTED = {"documented area (verdict)": "Documented area", "area × age": "Area × age", "both": "Both",
           "notes": "Notes", "detail (LPG)": "Carrier detail (LPG)", "area × 0.85": "Area × 0.85"}
NEXT_SHORT = {"visit_with_parts": "Short visit, parts", "hold": "Hold until changes", "remote_quote": "Remote quote"}
FUEL_WORD = {"gas": "gas", "lpg": "LPG", "oil": "oil", "district": "district heating", "electric": "electric heating"}


def trusted_label(s: str | None) -> str:
    s = (s or "").strip()
    return TRUSTED.get(s, s[:1].upper() + s[1:])


def bill_chip(h: House) -> str:
    return {"gas": "Gas bill", "oil": "Oil bill", "lpg": "LPG bill"}.get(h.fuel_type or "", "Bill")


def _contradiction_src(h: House, c) -> str:
    srcs = " ".join(c.sources).lower()
    if "notes" in srcs:          # e.g. wood stove (notes + consumption): the note is what raised it
        return "Notes"
    if "consumption" in srcs:
        return bill_chip(h)
    if "rooms" in srcs:
        return "Area vs. room count"
    return "Building data"


def house_flags(h: House, r: Result) -> list[dict]:
    """Issues specific to this house: site flags + installer checklist minus engine.ALWAYS_CHECKS.
    Same count in the Evaluation table and the Installer tab. Each item: {text, src}."""
    always = set(getattr(engine, "ALWAYS_CHECKS", []) or [])
    out = [{"text": clean_text(f), "src": "Site"} for f in r.site_flags]
    contra = list(r.contradictions)
    for item in r.installer_checklist:
        if item in always:
            continue
        if item.startswith("Check on site: "):
            body = item[len("Check on site: "):]
            c = next((c for c in contra if body.startswith(c.what)), None)
            if c is not None:
                contra.remove(c)
                out.append({"text": clean_text(c.what), "src": _contradiction_src(h, c)})
                continue
            body = re.sub(r"\s*\((?:[^()]|\([^()]*\))*\)\s*$", "", body)   # trailing "(trusted…)" bracket
            out.append({"text": clean_text(body), "src": "Notes"})
            continue
        low = item.lower()
        src = ("Not documented" if ("not documented" in low or low.startswith("pipe system unknown"))
               else "Building data" if low.startswith("single-pipe") else "Notes")
        out.append({"text": clean_text(item), "src": src})
    return out

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


@st.cache_data(show_spinner=False)
def radiator_info_raw() -> dict[str, str]:
    """Raw `radiator_info` text per building, only to quote it next to the valve note."""
    out = {}
    try:
        for f in sorted((ROOT / "data").glob("buildings_*.csv")):
            d = pd.read_csv(f)
            if {"building_id", "radiator_info"} <= set(d.columns):
                out.update({str(b): str(v) for b, v in zip(d["building_id"], d["radiator_info"]) if pd.notna(v)})
    except Exception:
        pass
    return out


def _card(inner: str, pad: str = "22px") -> str:
    return f'<div class="ev-card" style="padding:{pad}">{inner}</div>'


def _card_head(title: str, sub: str, right: str = "") -> str:
    r_ = f'<span class="num" style="font-size:13px;color:var(--muted)">{right}</span>' if right else ""
    return ('<div style="padding:18px 22px 8px"><div style="display:flex;justify-content:space-between;'
            f'align-items:baseline;gap:8px"><h3 style="margin:0;font-size:16px;font-weight:600;color:var(--ink)">{title}</h3>{r_}</div>'
            f'<p style="margin:4px 0 0;font-size:13px;color:var(--muted)">{sub}</p></div>')


def _top_color(r: Result) -> tuple[str, float]:
    return max((("green", r.p_green), ("yellow", r.p_yellow), ("red", r.p_red)), key=lambda x: x[1])


def eval_kpis(B, dev) -> str:
    ok = sum(r.best_color == ref["verdict"] for _, ref, r in dev)
    chips_ = []
    for bid, ref, r in dev:
        hit = r.best_color == ref["verdict"]
        chips_.append(pill(r.best_color if hit else "red",
                           f"{bid} {r.best_color.capitalize()} ✓" if hit
                           else f"{bid} {r.best_color.capitalize()} ✗ (ref {ref['verdict'].capitalize()})"))
    c1 = kpi_card("Dev verdicts reproduced", f"{ok} / {len(dev)}",
                  f'<div style="display:flex;gap:8px;flex-wrap:wrap">{"".join(chips_)}</div>')
    try:
        import calibrate
        loo = calibrate.leave_one_out(B)
        k = calibrate.fit(B).k
    except Exception as e:
        loo, k = None, DEFAULT.k
        st.caption(f"Calibration not available ({e}).")
    if loo is not None and len(loo):
        rows = "".join(
            '<div style="display:grid;grid-template-columns:44px minmax(0,1fr) 60px;align-items:center;gap:10px;font-size:12px">'
            f'<span style="color:var(--muted)">{esc(str(b))}</span>{diverging_bar(e)}'
            f'<span class="num" style="text-align:right;font-weight:600;color:var(--ink)">{signed_pct(e)}</span></div>'
            for b, e in zip(loo["building_id"], loo["error_pct"]))
        mae = float(loo["error_pct"].abs().mean())
        c2 = kpi_card("Heat-load error · leave-one-out", f"{mae:.1f} %",
                      f'<div style="display:flex;flex-direction:column;gap:6px">{rows}</div>'
                      '<div style="font-size:12px;color:var(--muted)">Each building predicted without using its own '
                      'reference.</div>', aside="mean absolute")
        lo_k, hi_k = float(loo["k_fit"].min()), float(loo["k_fit"].max())
        c3 = kpi_card("Calibration", f"k = {k:.2f}",
                      '<div style="font-size:13px;color:var(--muted);line-height:1.5">Per-fold fit stays tight: '
                      f'<span class="num" style="color:var(--ink);font-weight:600">{lo_k:.3f} – {hi_k:.3f}</span>. '
                      'Nothing else is fitted to the dev set.</div>', aside="1 tuned number")
    else:
        c2 = kpi_card("Heat-load error · leave-one-out", "–")
        c3 = kpi_card("Calibration", f"k = {k:.2f}", aside="1 tuned number")
    return ('<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:16px">'
            f'{c1}{c2}{c3}</div>')


def eval_table(res, sel: str) -> str:
    legend = "".join(f'<span style="display:flex;align-items:center;gap:6px"><span style="width:10px;height:10px;'
                     f'border-radius:2px;background:var(--bar-{c[0]});display:block"></span>{c.capitalize()}</span>'
                     for c in ("green", "yellow", "red"))
    heads = [("Building", ""), ("Verdict", ""), ("Confidence", "width:180px"), ("Flow temp", ""), ("Heat load", ""),
             ("Flags", "text-align:right"), ("Next step", ""), ("Lead score", "width:120px")]
    th = "".join(f'<th class="ev-th" style="{s}">{n}</th>' for n, s in heads)
    body = []
    for bid, h, ref, r in res:
        if r is None:
            body.append(f'<tr><td class="ev-td"><b>{esc(bid)}</b></td><td class="ev-td" colspan="7">'
                        '<span class="ev-sub">No result</span></td></tr>')
            continue
        is_sel = bid == sel
        tr = ' style="background:#F3F6FA"' if is_sel else ""
        first = ' style="box-shadow:inset 3px 0 0 var(--ink)"' if is_sel else ""
        if ref:
            hit = ref["verdict"] == r.best_color
            refmark = (f'<span style="font-size:12px;color:var(--{"g" if hit else "r"}-tx)">'
                       f'{"✓" if hit else "✗"} ref</span>')
        else:
            refmark = '<span style="font-size:12px;color:var(--muted)">no ref</span>'
        top, p_top = _top_color(r)
        conf = f"{pct(p_top)} {top}" + (" · close call" if top != r.best_color else "")
        fl = r.required_flow_temp_c
        load = r.heat_load_kw.p50
        if ref:
            load_sub = f"ref {ref['heating_load_kw']:.1f} · {pct_diff(load, ref['heating_load_kw'])}"
        else:
            b = r.heat_load_bill_kw.p50
            load_sub = "no bill" if b is None else f"bill {b:.1f} · {pct_diff(load, b)}"
        body.append(
            f'<tr{tr}><td class="ev-td"{first}><b>{esc(bid)}</b><span class="ev-sub">{"dev" if ref else "held-out"}</span></td>'
            f'<td class="ev-td">{pill(r.best_color, r.best_color.capitalize())} {refmark}</td>'
            f'<td class="ev-td">{stacked_bar(r.p_green, r.p_yellow, r.p_red)}<span class="ev-sub num">{conf}</span></td>'
            f'<td class="ev-td num">{t(fl.p50)}<span class="ev-sub">{flow_span(fl.p10, fl.p90)}</span></td>'
            f'<td class="ev-td num">{kw(load)}<span class="ev-sub">{load_sub}</span></td>'
            f'<td class="ev-td num" style="text-align:right">{len(house_flags(h, r))}</td>'
            f'<td class="ev-td">{NEXT_SHORT.get(r.visit_type, "–")}</td>'
            f'<td class="ev-td">{score_bar(r.lead_score)}</td></tr>')
    return ('<div class="ev-card" style="overflow:hidden">'
            '<div style="display:flex;justify-content:space-between;align-items:center;padding:18px 20px 12px;'
            'flex-wrap:wrap;gap:8px"><h2 style="margin:0;font-size:16px;font-weight:600;color:var(--ink)">All buildings</h2>'
            f'<div style="display:flex;gap:14px;font-size:12px;color:var(--muted);align-items:center">{legend}</div></div>'
            '<div style="overflow-x:auto"><table style="width:100%;border-collapse:collapse;min-width:900px;margin:0;'
            f'border:none"><thead><tr>{th}</tr></thead><tbody>{"".join(body)}</tbody></table></div>'
            '<div style="padding:12px 20px;font-size:12px;color:var(--muted);border-top:1px solid var(--line-soft)">'
            'Pick a building below the table to open it.</div></div>')


def _house_line(h: House) -> str:
    parts = [str(h.build_year) if h.build_year else None,
             f"{h.living_area_m2:.0f} m²" if h.living_area_m2 else None,
             FUEL_WORD.get(h.fuel_type or "", h.fuel_type)]
    n = h.radiator_count
    if h.heat_distribution == "underfloor":
        parts.append("underfloor heating")
    elif h.heat_distribution == "mixed":
        parts.append(f"{n} radiators, mixed" if n else "radiators and underfloor")
    elif n:
        parts.append(f"{n} radiators")
    return " · ".join(p for p in parts if p)


_ANNOT = re.compile(r"\s*\(((?:notes|assum)[^()]*)\)\s*$", re.I)


def notes_rows(bid: str, h: House) -> list[tuple[str, str, str]]:
    """(quote html, field, value html) rows for 'Read from the notes'."""
    rows = []
    o = h.notes_obs
    for f, q in (o.evidence.items() if o else []):
        m = _ANNOT.search(q or "")
        note = m.group(1) if m else ""
        quote = _ANNOT.sub("", q or "").strip()
        assumed = bool(m) or (o.confidence.get(f, 1) < 0.7)
        v = getattr(o, f, None)
        if f == "unheated_area_note":
            val = "Yes" if v else "None"
        elif f == "u_values" and v:
            val = human_value(v) + " W/m²K"
        else:
            val = human_value(v)
        val = val[:1].upper() + val[1:]
        tag = (f' <span title="{esc(note or "low confidence")}" style="font-size:12px;color:var(--y-tx);'
               'background:var(--y-bg);padding:2px 8px;border-radius:999px;margin-left:4px;font-weight:500">assumed</span>'
               if assumed else "")
        rows.append((f"“{esc(quote)}”", esc(human_field(f)), f"<b>{esc(val)}</b>{tag}"))
    raw = radiator_info_raw().get(bid, "")
    for n in h.data_notes:
        low = n.lower()
        if "valve" not in low:
            continue
        clause = next((c.strip() for c in raw.split(";") if "valve" in c.lower()), "")
        head, _, rest = n.partition(", ")
        if "valve blocks" in low:
            head, rest = "Valve blocks", n[low.index("valve blocks") + len("valve blocks"):].strip()
        elif "presettable" in low:
            head = "Presettable"
        elif "preset" in low:
            head = "Preset"
        else:
            head = head[:1].upper() + head[1:]
        grey = f' <span style="font-size:12px;color:var(--muted);margin-left:4px">{esc(rest)}</span>' if rest else ""
        rows.append((f"“{esc(clause)}”" if clause else '<span style="font-style:normal">Radiator info</span>',
                     "Valves", f"<b>{esc(head)}</b>{grey}"))
    return rows


def short_check(item: str) -> str:
    s = clean_text(item)
    if "?" in s or len(s) <= 90:
        return s
    head = re.split(r": |\. ", s, maxsplit=1)[0].rstrip(".") + "."
    if "single-pipe" in s.lower() and "single-pipe" not in head.lower():
        head += " Single-pipe loop?"
    return head


def eval_detail(bid: str, h: House, ref: dict | None, r: Result) -> str:
    tag = (pill("none", f"Dev · reference: {ref['verdict'].capitalize()}") if ref
           else pill("none", "Held-out · no reference verdict"))
    head = ('<div style="display:flex;align-items:baseline;gap:14px;flex-wrap:wrap">'
            f'<h2 style="margin:0;font-size:26px;font-weight:700;letter-spacing:-0.01em;color:var(--ink)">{esc(bid)}</h2>'
            f'<div style="font-size:16px;color:var(--ink)">{esc(_house_line(h))}</div>{tag}</div>')

    # left 1: conflicting inputs
    rows = []
    for c in r.contradictions:
        lab, val = ("Trusted", trusted_label(c.trusted)) if c.trusted else ("Status", "Open, installer to check")
        why = f'<span style="font-size:13px;color:var(--muted)">{esc(clean_text(c.why))}</span>' if c.why else ""
        rows.append('<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:8px 16px;'
                    'padding:16px 22px;border-top:1px solid var(--line-soft)">'
                    f'<div style="font-size:14px;line-height:1.5;color:var(--ink)">{esc(clean_text(c.what))}</div>'
                    '<div style="display:flex;flex-direction:column;gap:4px">'
                    f'<span style="font-size:12px;color:var(--muted)">{lab}</span>'
                    f'<span style="font-size:14px;font-weight:600;color:var(--ink)">{esc(val)}</span>{why}</div></div>')
    if not rows:
        rows = ['<div style="padding:14px 22px 18px;border-top:1px solid var(--line-soft);font-size:14px;'
                'color:var(--muted)">No conflicting inputs found.</div>']
    conflicts = ('<div class="ev-card" style="overflow:hidden">'
                 + _card_head("Conflicting inputs", "Where the sources disagreed, and which one the model went with.")
                 + "".join(rows) + "</div>")

    # left 2: read from the notes
    o = h.notes_obs
    nrows = notes_rows(bid, h)
    sub = "What the AI pulled out of free text, field by field."
    if o and o.method == "keywords":
        sub += " Rule-based analysis (no AI available)."
    if nrows:
        tb = "".join('<tr><td class="ev-td" style="padding-left:22px;white-space:normal;color:#3A4A66;font-style:italic">'
                     f'{q}</td><td class="ev-td" style="white-space:normal">{f}</td>'
                     f'<td class="ev-td" style="white-space:normal">{v}</td></tr>' for q, f, v in nrows)
        notes_body = ('<div style="overflow-x:auto"><table style="width:100%;border-collapse:collapse;min-width:480px;'
                      'margin:0;border:none"><thead><tr><th class="ev-th" style="padding-left:22px">Note says</th>'
                      f'<th class="ev-th">Field</th><th class="ev-th">Value</th></tr></thead><tbody>{tb}</tbody></table></div>')
    else:
        notes_body = ('<div style="padding:14px 22px 18px;border-top:1px solid var(--line-soft);font-size:14px;'
                      'color:var(--muted)">Nothing in the notes changed the inputs.</div>')
    notes = '<div class="ev-card" style="overflow:hidden">' + _card_head("Read from the notes", sub) + notes_body + "</div>"

    # right 1: verdict
    title, word = headline(r)
    p_best = {"green": r.p_green, "yellow": r.p_yellow, "red": r.p_red}[r.best_color]
    fl = r.required_flow_temp_c
    approx = "" if fl.p50 is None or fl.p50 > 70 else "≈ "
    bill = r.heat_load_bill_kw.p50
    if r.saving_eur is None:
        cost_big = "–"
    else:
        cost_big = f"{'−' if r.saving_eur > 0 else '+'}€{abs(r.saving_eur):,.0f} / yr"
    cost_note = (f'<div style="font-size:12px;color:var(--muted);grid-column:1/-1">{esc(clean_text(r.cost_note))}</div>'
                 if r.cost_note else "")
    verdict = _card(
        '<div style="display:flex;flex-direction:column;gap:18px">'
        '<div style="display:flex;align-items:center;gap:14px">'
        f'<span style="width:40px;height:40px;border-radius:20px;background:{_FILLED[r.best_color][0]};display:block;flex:none"></span>'
        f'<div><div style="font-size:24px;font-weight:700;line-height:1.1;color:var(--ink)">{esc(title)}</div>'
        f'<div style="font-size:13px;color:var(--muted)">{esc(word)} · {pct(p_best)} of simulations</div></div></div>'
        f'{stacked_bar(r.p_green, r.p_yellow, r.p_red, width="100%", height=10)}'
        '<div style="display:flex;flex-direction:column;gap:10px">'
        '<div style="display:flex;justify-content:space-between;align-items:baseline;gap:8px">'
        '<span style="font-size:13px;color:var(--muted);font-weight:500">Flow temperature, coldest day</span>'
        f'<span class="num" style="font-size:18px;font-weight:700;color:var(--ink)">{approx}{t(fl.p50)}</span></div>'
        f'{flow_scale(fl.p10, fl.p50, fl.p90)}'
        f'<div style="font-size:12px;color:var(--muted)">Grey bar = likely range, {flow_span(fl.p10, fl.p90)}. '
        'Lower is cheaper to run.</div></div>'
        '<div style="display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;border-top:1px solid var(--line-soft);'
        'padding-top:16px">'
        '<div><div style="font-size:12px;color:var(--muted)">Heat load</div>'
        f'<div class="num" style="font-size:18px;font-weight:700;color:var(--ink)">{kw(r.heat_load_kw.p50)}</div>'
        f'<div style="font-size:12px;color:var(--muted)">{"no bill" if bill is None else f"bill says {bill:.1f}"}</div></div>'
        '<div><div style="font-size:12px;color:var(--muted)">Running cost</div>'
        f'<div class="num" style="font-size:18px;font-weight:700;color:var(--ink)">{cost_big}</div>'
        f'<div style="font-size:12px;color:var(--muted)">vs. {FUEL_WORD.get(h.fuel_type or "", "the current heating")} today</div></div>'
        f'{cost_note}</div></div>')

    # right 2: still open
    oc = r.open_checks
    if oc:
        lis = "".join(f"<li>{esc(short_check(c.item))}</li>" for c in oc)
        still = _card('<div style="display:flex;flex-direction:column;gap:12px">'
                      '<div style="display:flex;justify-content:space-between;align-items:baseline">'
                      '<h3 style="margin:0;font-size:16px;font-weight:600;color:var(--ink)">Still open</h3>'
                      f'<span class="num" style="font-size:13px;color:var(--muted)">{len(oc)}</span></div>'
                      '<ol style="margin:0;padding-left:20px;display:flex;flex-direction:column;gap:10px;font-size:14px;'
                      f'line-height:1.45;color:var(--ink)">{lis}</ol></div>', pad="20px 22px")
    else:
        still = ""
    return ('<div style="display:flex;flex-direction:column;gap:18px">' + head
            + '<div style="display:flex;flex-wrap:wrap;gap:20px;align-items:flex-start">'
            f'<div style="flex:999 1 520px;min-width:0;display:flex;flex-direction:column;gap:20px">{conflicts}{notes}</div>'
            f'<div style="flex:1 1 340px;max-width:100%;min-width:0;display:flex;flex-direction:column;gap:16px">{verdict}{still}</div>'
            '</div></div>')


def tab_evaluation():
    B = buildings()
    res = [(bid, h, ref, evaluate(h)) for bid, h, ref in B]
    dev = [(bid, ref, r) for bid, _, ref, r in res if ref and r]
    n_dev = sum(1 for _, _, ref in B if ref)
    n_out = len(B) - n_dev
    st.html('<div style="display:flex;flex-direction:column;gap:6px">'
            '<h1 style="margin:0;padding:0;font-size:26px;font-weight:700;letter-spacing:-0.01em;color:var(--ink)">'
            'How well does it hold up?</h1>'
            f'<p style="margin:0;font-size:15px;color:var(--muted)">{len(B)} buildings. {n_dev} dev case'
            f'{"s" if n_dev != 1 else ""} with a reference verdict and heat load, {n_out} held-out case'
            f'{"s" if n_out != 1 else ""} with only the bill.</p></div>')
    if not any(r for *_, r in res):
        st.info(f"Engine not ready yet ({ENGINE_ERR}). Buildings load fine: {', '.join(b for b, *_ in res)}")
        return
    st.html(eval_kpis(B, dev))

    ids = [b for b, *_ in res]
    table_slot = st.container()
    default = "B-05" if "B-05" in ids else ids[-1]
    try:
        sel = st.segmented_control("Open a building", ids, default=default, key="eval_sel", required=True)
    except TypeError:
        sel = st.segmented_control("Open a building", ids, default=default, key="eval_sel")
    except AttributeError:
        sel = st.radio("Open a building", ids, index=ids.index(default), horizontal=True, key="eval_sel")
    sel = sel or st.session_state.get("eval_last", default)
    st.session_state["eval_last"] = sel
    with table_slot:
        st.html(eval_table(res, sel))

    bid, h, ref, r = next(x for x in res if x[0] == sel)
    if r is None:
        st.info(f"No result for {bid}.")
        return
    st.html(eval_detail(bid, h, ref, r))


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


def request_subject(r: Result) -> str:
    return f"Heat pump: {VISIT.get(r.visit_type, 'quote request')}"


def mailto(subject: str, body: str, to: str = "") -> str:
    return f"mailto:{urllib.parse.quote(to)}?" + urllib.parse.urlencode({"subject": subject, "body": body},
                                                                        quote_via=urllib.parse.quote)


def request_panel(h: House, r: Result, key: str):
    """Homeowner contact form (last step of the Homeowner flow). Stores what was entered for the Installer footer."""
    html('<div class="card" style="border:1.5px solid #14213D"><b>Your request is ready</b><br>'
         '<span class="muted">Just add how to reach you.</span></div>')
    name = st.text_input("Name", key=f"name_{key}")
    contact = st.text_input("E-mail or phone", key=f"contact_{key}")
    plz = st.text_input("Postcode", key=f"plz_{key}")
    if name.strip() or contact.strip() or plz.strip():
        prev = st.session_state.get("request_sent") or {}
        st.session_state["request_sent"] = {"name": name.strip(), "contact": contact.strip(), "postcode": plz.strip(),
                                            "date": prev.get("date") or date.today().strftime("%d %b %Y").lstrip("0")}
    pdf = None
    if engine is not None and hasattr(engine, "handover_pdf"):
        try:
            pdf = engine.handover_pdf(h, r, {"name": name, "contact": contact, "postcode": plz})
        except Exception as e:
            st.caption(f"PDF not available: {e}")
    if pdf:
        st.download_button("PDF for the installer", pdf, file_name="pre-visit-sheet.pdf", mime="application/pdf",
                           type="primary", width="stretch", key=f"pdf_{key}")
    body = (f"Hello,\n\nplease find my pre-visit sheet attached (HP-Ready first estimate: {r.best_color}, "
            f"about {t(r.required_flow_temp_c.p50)}).\n\n{name}\n{contact}\n{plz}")
    st.link_button("Open as e-mail", mailto(request_subject(r), body), width="stretch")
    st.caption("One page any installer reads in a minute. Nothing is stored.")

# ---------------------------------------------------------------- installer


STANDARD_CHECKS = ["Room-by-room heat load (DIN EN 12831)", "Electrical capacity, meter cabinet",
                   "Hydraulics and balancing", "Outdoor unit: position, sound distance, permits"]
_NUM = r"(\d+(?:\.\d+)?)"


def flow_big(v: float | None) -> str:
    return "–" if v is None else ("> 70 °C" if v > 70 else f"≈ {v:.0f} °C")


def visit_pill_text(r: Result) -> str:
    c = r.best_color.capitalize()
    return {"hold": "Hold · not without changes", "visit_with_parts": f"{c} · short visit with parts",
            "remote_quote": f"{c} · remote quote possible"}.get(r.visit_type or "", c)


def installer_meta(h: House) -> str:
    fuel = {"gas": "gas boiler", "lpg": "LPG boiler", "oil": "oil boiler", "district": "district heating",
            "electric": "electric heating"}.get(h.fuel_type or "", h.fuel_type)
    n = h.radiator_count
    if h.heat_distribution == "underfloor":
        rad = "underfloor heating"
    else:
        rad = f"{n} radiator{'s' if n != 1 else ''}" if n else None
    parts = [human_enum(h.building_type) if h.building_type else None, str(h.build_year) if h.build_year else None,
             f"{h.living_area_m2:.0f} m²" if h.living_area_m2 else None, fuel, rad]
    return " · ".join(p for p in parts if p)


def radiator_share(h: House) -> str:
    """Mixed systems: share of the load on the radiator circuit (radiators / rooms), as the engine splits it."""
    if h.heat_distribution != "mixed" or not h.radiator_count or not h.rooms:
        return ""
    share = min(h.radiator_count / h.rooms, 1.0)
    return (f" — the radiator circuit carries {share:.0%} of the load ({h.radiator_count} radiators / "
            f"{h.rooms} rooms)").replace("%", " %")


def what_it_takes(h: House, r: Result) -> list[tuple[str, str]]:
    """(title, body) blocks from r.path_to_yellow. Titles come from what each line says, not from the building."""
    out, letters = [], iter("ABCDEFG")
    for line in r.path_to_yellow or []:
        s = clean_text(line)
        m = re.search(rf"give {_NUM} kW, about {_NUM} kW is needed", s)
        if s.lower().startswith("no change needed") and m:
            have, need = float(m.group(1)), float(m.group(2))
            body = (f"Radiators are rated {have:.1f} kW (at 75 °C); 55 °C needs a rating of about {need:.1f} kW"
                    f"{radiator_share(h)}.")
            if need and (have - need) / need < 0.05:
                body += f" Tight margin ({(have - need) / need:.0%}), so the real radiator sizes decide it.".replace("%", " %")
            out.append(("No radiator changes for 55 °C", body))
            continue
        if s.lower().startswith("nothing to change"):
            out.append(("Nothing to change", clean_text(s.split(":", 1)[-1])))
            continue
        m = re.search(rf"Add about {_NUM} kW radiator output for 55 °C \({_NUM} kW for 60 °C\); today {_NUM} kW", s)
        if m:
            a55, a60, now = (float(x) for x in m.groups())
            tail = (" 60 °C already works with today's radiators." if a60 <= 0
                    else f" About {a60:.1f} kW for 60 °C.")
            out.append((f"Option {next(letters)} · more radiator surface",
                        f"Add about {a55:.1f} kW of rated radiator output for 55 °C.{tail} Today: {now:.1f} kW."))
            continue
        m = re.search(r"cut the heat loss by about (\d+)\s*%", s)
        if m:
            out.append((f"Option {next(letters)} · cut heat loss",
                        f"About −{m.group(1)} % heat loss (insulation or windows) reaches 55 °C with today's radiators."))
            continue
        head, sep, rest = s.partition(": ")
        if sep and len(head) <= 40:
            rest = re.sub(r"\s*\((?:installer to )?check[^()]*\)\s*\.?$", ".", rest).strip()
            out.append((head, clean_text(rest)))
        else:
            out.append((f"Option {next(letters)}", s))
    if r.best_color == "green" and out and out[0][0] in ("No radiator changes for 55 °C", "Nothing to change"):
        return out[:1]
    return out


def bring_rows(h: House, r: Result) -> tuple[list[tuple[str, str]], str]:
    p = r.parts
    note = (p.radiators_note or "").strip()
    rs = p.radiators_to_swap
    if rs is None:
        swap = "n/a (underfloor)" if h.heat_distribution == "underfloor" else "–"
    else:
        lo, mid, hi = rs
        if lo == hi:
            swap = "None" if mid == 0 else (f"All {mid}" if h.radiator_count and mid >= h.radiator_count else str(mid))
        elif mid == 0:
            swap = f"None expected (up to {hi})"
        else:
            swap = f"{mid} ({lo}–{hi})"
        if "may not be enough" in note:
            swap += " — may not be enough"
    rows = [("Radiators to swap", swap),
            ("Thermostatic valves", f"{p.valves} to replace" if p.valves else "None documented"),
            ("Hydraulic balancing", {"needed": "Needed", "check": "Check"}.get(p.balancing or "", "–"))]
    if h.heat_distribution == "underfloor":
        cap = "Underfloor heating; attached radiators: check." if "attached" in note else ""
    else:
        cap = "Radiator sizes unknown — assumed medium." if h.radiator_size is None else ""
    return rows, cap


def installer_summary(h: House, r: Result) -> str:
    fl = r.required_flow_temp_c.p50
    if h.heat_distribution == "underfloor":
        first = "Underfloor heating runs at about 35–40 °C, ideal for a heat pump."
    elif fl is None:
        first = "Flow temperature can't be estimated from the data yet."
    elif fl > 70:
        first = "Needs more than 70 °C flow on the coldest day — well above the ~60 °C a heat pump handles efficiently."
    elif fl > 60:
        first = f"Needs about {fl:.0f} °C flow on the coldest day — above the ~60 °C a heat pump handles efficiently."
    elif fl > 55.5:
        first = f"Needs about {fl:.0f} °C flow on the coldest day — workable, but above the efficient band (up to 55 °C)."
    else:
        first = f"Needs about {fl:.0f} °C flow on the coldest day — inside the efficient band (up to 55 °C)."
    if r.visit_type == "hold" or r.best_color == "red":
        return first + " Workable only with more radiator surface or less heat loss."
    rs = r.parts.radiators_to_swap
    if h.heat_distribution == "underfloor":
        swaps = "No radiator work expected"
    elif rs is None:
        swaps = "Radiator work unclear"
    elif rs[1] == 0 and rs[2] == 0:
        swaps = "No radiator swaps expected"
    elif rs[1] == 0:
        swaps = f"No radiator swaps expected (up to {rs[2]} if they are smaller than assumed)"
    else:
        swaps = f"About {rs[1]} radiator swap{'s' if rs[1] != 1 else ''} expected"
    topics = []
    for c in r.contradictions:
        w, srcs = c.what.lower(), " ".join(c.sources).lower()
        topic = ("the floor area" if "rooms" in srcs else "the bill mismatch" if "consumption" in srcs and "bill" in w
                 else "the extra heat source" if "heat source" in w else "the hot-water setup" if "hot water" in w
                 else "the renovation status" if "renovation" in w else "the fuel (gas or LPG)" if "lpg" in w
                 else "the unused floor" if "unused" in w else None)
        if topic and topic not in topics:
            topics.append(topic)
    if r.visit_type == "remote_quote":
        why = "; a remote quote should do."
    elif topics:
        why = "; the visit is mostly to settle " + (" and ".join(topics[:2])) + "."
    elif h.radiator_size is None and h.heat_distribution != "underfloor":
        why = "; the visit is mostly to measure the radiators."
    else:
        why = "."
    return f"{first} {swaps}{why}"


def lead_card(bid: str, r: Result | None, selected: bool) -> str:
    if r is None:
        right, line = pill("none", "No result", size="11px"), "–"
    else:
        right = pill(r.best_color, r.best_color.capitalize(), size="11px")
        line = f"{kw(r.heat_load_kw.p50)} · {flow_big(r.required_flow_temp_c.p50)} · score {r.lead_score or 0:.2f}"
    return (f'<div class="lead-card{" sel" if selected else ""}">'
            f'<span style="display:flex;justify-content:space-between;align-items:center;gap:8px">'
            f'<b style="font-size:15px">{esc(bid)}</b>{right}</span>'
            f'<span class="num" style="font-size:12px;color:var(--muted)">{esc(line)}</span></div>')


def _sec(title: str, inner: str, right: str = "") -> str:
    r_ = f'<span class="num" style="font-size:13px;color:var(--muted)">{right}</span>' if right else ""
    return ('<section class="ev-card" style="padding:20px 22px;display:flex;flex-direction:column;gap:4px">'
            '<div style="display:flex;justify-content:space-between;align-items:baseline;margin-bottom:6px">'
            f'<h2 style="margin:0;font-size:16px;font-weight:600;color:var(--ink)">{title}</h2>{r_}</div>{inner}</section>')


def installer_body_left(h: House, r: Result) -> str:
    takes = "".join('<div style="display:flex;flex-direction:column;gap:4px;padding-top:12px;margin-top:8px;'
                    'border-top:1px solid var(--line-soft)">'
                    f'<span style="font-size:14px;font-weight:600;color:var(--ink)">{esc(tt)}</span>'
                    f'<span style="font-size:14px;color:#3A4A66;line-height:1.5">{esc(b)}</span></div>'
                    for tt, b in what_it_takes(h, r)) or '<span style="font-size:14px;color:var(--muted)">–</span>'
    rows, cap = bring_rows(h, r)
    bring = "".join('<div style="display:flex;justify-content:space-between;gap:16px;font-size:14px;padding:8px 0;'
                    f'border-top:1px solid var(--line-soft)"><span style="color:var(--muted)">{esc(k)}</span>'
                    f'<span class="num" style="font-weight:600;text-align:right;color:var(--ink)">{esc(v)}</span></div>'
                    for k, v in rows)
    if cap:
        bring += f'<span style="font-size:12px;color:var(--muted);margin-top:6px">{esc(cap)}</span>'
    return ('<div style="display:flex;flex-direction:column;gap:20px">'
            + _sec("What it takes", takes) + _sec("Bring", bring) + "</div>")


def installer_flags(h: House, r: Result) -> list[dict]:
    """house_flags, without repeating what 'What it takes' already says (keep only the check)."""
    out = []
    for f in house_flags(h, r):
        txt = f["text"]
        if "; options:" in txt:
            txt = txt.split("; options:")[0].rstrip(".") + "."
        txt = re.sub(r"(\d) (%|kW|°C)", "\\1\u00a0\\2", txt)      # keep units on the number's line
        out.append({**f, "text": txt[:1].upper() + txt[1:]})
    return out


def installer_flags_html(flags: list[dict]) -> str:
    if not flags:
        inner = ('<div style="font-size:14px;color:var(--muted);padding:12px 0;border-top:1px solid var(--line-soft)">'
                 'Nothing specific to this house.</div>')
    else:
        inner = "".join(
            '<div style="display:grid;grid-template-columns:24px minmax(0,1fr);gap:10px;padding:12px 0;'
            'border-top:1px solid var(--line-soft)">'
            '<span class="num" style="width:24px;height:24px;border-radius:12px;background:var(--line-soft);font-size:12px;'
            f'font-weight:600;display:flex;align-items:center;justify-content:center;color:var(--ink)">{i}</span>'
            '<div style="display:flex;flex-direction:column;gap:6px">'
            f'<span style="font-size:14px;line-height:1.5;color:var(--ink)">{esc(f["text"])}</span>'
            '<span style="font-size:11px;color:#3A4A66;background:var(--line-soft);border-radius:6px;padding:2px 8px;'
            f'align-self:flex-start">{esc(f["src"])}</span></div></div>'
            for i, f in enumerate(flags, 1))
    return _sec("Flags for this house", inner, str(len(flags)))


def kpi_strip(h: House, r: Result, ref: dict | None, rank: int, n: int) -> str:
    load, bill = r.heat_load_kw.p50, r.heat_load_bill_kw.p50
    load_sub = (f"reference {ref['heating_load_kw']:.1f} kW" if ref and ref.get("heating_load_kw") is not None
                else "no bill" if bill is None else f"bill says {bill:.1f} kW")
    fl = r.required_flow_temp_c
    nr = h.radiator_count
    size = f"{h.radiator_size} size" if h.radiator_size else "sizes unknown"
    if h.heat_distribution == "underfloor":
        rad_big = "Underfloor"
        rad_sub = f"{nr} radiator{'s' if nr != 1 else ''} attached" if nr else "no radiators documented"
    else:
        rad_big = str(nr) if nr else "–"
        rad_sub = (("mixed · " if h.heat_distribution == "mixed" else "") + size) if nr else "not documented"
    cells = [("Heat load", kw(load), load_sub), ("Flow temp, coldest day", flow_big(fl.p50), f"likely {flow_span(fl.p10, fl.p90)}"),
             ("Radiators", rad_big, rad_sub),
             ("Lead score", "–" if r.lead_score is None else f"{r.lead_score:.2f}", f"#{rank} of {n}")]
    inner = "".join(
        f'<div class="kpi-cell"><span style="font-size:12px;color:var(--muted)">{a}</span>'
        f'<span class="num" style="font-size:22px;font-weight:700;color:var(--ink)">{esc(b)}</span>'
        f'<span class="num" style="font-size:12px;color:var(--muted)">{esc(c)}</span></div>' for a, b, c in cells)
    return f'<div class="kpi-strip">{inner}</div>'


def sent_card(lead: str, h: House) -> str:
    req = st.session_state.get("request_sent") if lead == "Homeowner house" else None
    if req:
        l1 = " · ".join(x for x in (req.get("name"), req.get("postcode")) if x) or "No name given"
        l2 = " · ".join(x for x in (req.get("contact") or "No contact given", req.get("date")) if x)
    elif X.DEMO_ONLY:
        pc = re.search(r"\((\d\dx+)\)", h.region or "")
        l1 = f"Sample homeowner · {pc.group(1) if pc else '8xxxx'}"
        l2 = f"homeowner@example.com · {date.today().strftime('%d %b %Y').lstrip('0')}"
    else:
        l1, l2 = "Not sent yet", "The homeowner's details appear here once they send the request."
    return ('<section class="ev-card" style="padding:18px 22px;display:flex;justify-content:space-between;'
            'align-items:center;gap:16px;flex-wrap:wrap"><div style="display:flex;flex-direction:column;gap:4px">'
            '<span style="font-size:12px;color:var(--muted)">Sent by the homeowner</span>'
            f'<span style="font-size:15px;font-weight:600;color:var(--ink)">{esc(l1)}</span>'
            f'<span style="font-size:13px;color:var(--muted)">{esc(l2)}</span></div>'
            '<span style="font-size:12px;color:var(--muted);max-width:320px">One page, readable in a minute. '
            'Nothing is stored on our side.</span></section>')


def _lead_key(bid: str) -> str:
    return re.sub(r"\W", "_", bid)


def tab_installer():
    ss = st.session_state
    leads = [(bid, h, ref) for bid, h, ref in buildings()]
    if ss.get("reads"):
        leads.append(("Homeowner house", home_house(), None))
    res = [(bid, h, ref, evaluate(h)) for bid, h, ref in leads]
    if not any(r for *_, r in res):
        st.info(f"Engine not ready yet ({ENGINE_ERR or 'no result'}).")
        return
    res.sort(key=lambda x: (-(x[3].lead_score or 0) if x[3] else 1, x[0]))
    ids = [x[0] for x in res]
    if ss.get("lead") not in ids:
        ss["lead"] = ids[0]
    left, right = st.columns([1, 3.3], gap="large")
    with left:
        st.html('<div style="display:flex;justify-content:space-between;align-items:baseline;padding:0 4px">'
                '<h2 style="margin:0;font-size:14px;font-weight:600;color:var(--ink)">Leads</h2>'
                f'<span style="font-size:12px;color:var(--muted)">{len(ids)} · by lead score</span></div>')
        for bid, _, _, r in res:
            k = _lead_key(bid)
            with st.container(key=f"leadbox_{k}"):
                st.html(lead_card(bid, r, bid == ss["lead"]))
                label = f"{bid}: {r.best_color} · score {r.lead_score or 0:.2f}" if r else bid
                st.button(label, key=f"leadbtn_{k}", on_click=lambda b=bid: ss.update(lead=b), width="stretch")
    rank = ids.index(ss["lead"]) + 1
    bid, h, ref, r = res[rank - 1]
    with right:
        if r is None:
            st.info(f"No result for {bid}.")
            return
        top_l, top_r = st.columns([1, 1], vertical_alignment="top")
        top_l.html('<div style="display:flex;flex-direction:column;gap:10px;min-width:0">'
                   '<div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap">'
                   f'<h1 style="margin:0;padding:0;font-size:30px;font-weight:700;letter-spacing:-0.02em;color:var(--ink)">{esc(bid)}</h1>'
                   f'{pill(r.best_color, visit_pill_text(r), filled=True, size="13px")}</div>'
                   f'<div style="font-size:16px;color:#3A4A66">{esc(installer_meta(h))}</div></div>')
        with top_r.container(horizontal=True, horizontal_alignment="right", key=f"inst_actions_{_lead_key(bid)}"):
            pdf = None
            if engine is not None and hasattr(engine, "handover_pdf"):
                try:
                    pdf = engine.handover_pdf(h, r, {})
                except Exception:
                    pdf = None
            if pdf:
                st.download_button("Download one-pager", pdf, file_name=f"{_lead_key(bid)}-pre-visit.pdf",
                                   mime="application/pdf", key=f"inst_pdf_{_lead_key(bid)}")
            else:   # TODO: enable once engine.handover_pdf exists
                st.button("Download one-pager", disabled=True, key=f"inst_pdf_{_lead_key(bid)}",
                          help="The one-page PDF isn't available in this build yet.")
            req = ss.get("request_sent") if bid == "Homeowner house" else None
            to = (req or {}).get("contact", "")
            greet = f"Hello {req['name']}," if req and req.get("name") else "Hello,"
            body = (f"{greet}\n\nthank you for your request. HP-Ready first estimate: {r.best_color}, about "
                    f"{t(r.required_flow_temp_c.p50)} on the coldest day ({VISIT.get(r.visit_type, '').lower()}).\n\n"
                    "We'll be in touch to arrange the next step.")
            st.link_button("Reply to homeowner", mailto("Re: " + request_subject(r), body, to if "@" in to else ""),
                           type="primary")
        st.html(f'<p style="margin:0;font-size:16px;line-height:1.55;max-width:760px;color:var(--ink)">'
                f'{esc(installer_summary(h, r))}</p>')
        st.html(kpi_strip(h, r, ref, rank, len(ids)))
        c1, c2 = st.columns(2, gap="medium")
        c1.html(installer_body_left(h, r))
        with c2:
            st.html(installer_flags_html(installer_flags(h, r)))
            with st.container(key=f"stdchecks_{_lead_key(bid)}"):
                st.html('<h2 style="margin:0;font-size:16px;font-weight:600;color:var(--ink)">Standard on-site checks</h2>')
                for i, lab in enumerate(STANDARD_CHECKS):
                    st.checkbox(lab, key=f"chk_{_lead_key(bid)}_{i}")
        st.html(sent_card(bid, h))


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
