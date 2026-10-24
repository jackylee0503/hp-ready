"""HP-Ready. Tabs Homeowner / Evaluation (Installer only with HP_SHOW_INSTALLER=1). Layout and copy: docs/design/.
The app never computes physics. It renders any `calculation` result that fills the MVP core (CONTRACT.md "MVP")."""
from __future__ import annotations

import hashlib
import os
import re
import urllib.parse
from datetime import date
from functools import reduce
from html import escape as esc
from pathlib import Path

import pandas as pd
import streamlit as st

import extract as X
import orchestrator as O
from loader import load_buildings
from schema import DEFAULT, House, Range, Result

try:
    from schema import check_result
except ImportError:                          # older schema.py: no contract checker
    def check_result(h, r):
        return []

try:                                         # contract v2 core (CONTRACT.md §0)
    from schema import BASELINE_INFO, quantity, with_core
except ImportError:
    BASELINE_INFO, quantity = None, None

    def with_core(r, default_info=None):
        return r

st.set_page_config(page_title="HP-Ready", page_icon="🔥", layout="wide")

# Browser auto-translation (e.g. Chrome → Korean) rewrites the DOM under React and crashes the app with
# "NotFoundError: Failed to execute 'removeChild' on 'Node'". Mark the page as not translatable.
# components.html runs in a same-origin iframe, so it can set the attribute on the parent page.
try:                                            # never let this guard break the app
    import streamlit.components.v1 as _components
    _components.html("""<script>
try {
  const d = window.parent.document;
  d.documentElement.setAttribute("translate", "no");
  d.documentElement.classList.add("notranslate");
  if (!d.querySelector('meta[name="google"][content="notranslate"]')) {
    const m = d.createElement("meta"); m.name = "google"; m.content = "notranslate"; d.head.appendChild(m);
  }
} catch (e) {}
</script>""", height=0)
except Exception:
    pass

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
/* Wizard progress: 4 bars with step names, current one bold */
.steps{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:6px;margin:4px 0 16px}
.steps .bar{height:5px;border-radius:3px;background:#D5DBE1}
.steps .on .bar{background:#14213D}
.steps span{display:block;font-size:12px;color:var(--muted);margin-top:6px;line-height:1.25}
.steps .cur span{color:var(--ink);font-weight:700}
/* Sidebar "What we know so far": one card, rows inside, readable source pills */
.know{background:#fff;border:1px solid #E2E6EA;border-radius:20px;padding:18px 20px;margin-bottom:12px}
.know-row{display:flex;justify-content:space-between;align-items:center;gap:10px;padding:8px 0;
          border-top:1px solid var(--line-soft);font-size:15px;color:var(--ink)}
.know-row .need{color:#7A5205;font-weight:700}
.know-note{font-size:12px;color:var(--muted);margin-top:8px}
.src{font-size:12px;font-weight:600;color:#15233B;background:#E3E8EF;border:1px solid #C9D2DD;border-radius:999px;
     padding:3px 10px;white-space:nowrap}
/* Page 4: the conflict question box stands out */
.stApp [class*="st-key-conflictbox"]{background:#FFF8E6;border-color:#E6B84A !important}
/* Uploader: hide Streamlit's "Limit 200MB per file" line (homeowner noise) */
[data-testid="stFileUploaderDropzoneInstructions"]{display:none}
/* Evaluation KPI row: 4 across on desktop, 2×2 on tablets, 1 on phones */
.kpi-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:16px}
@media (max-width:1100px){.kpi-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media (max-width:560px){.kpi-grid{grid-template-columns:minmax(0,1fr)}}
/* Answer card call to action: an in-page link to the request form, styled as a button */
a.cta{display:block;text-align:center;padding:10px 16px;border-radius:8px;background:#14213D;color:#fff !important;
      font-weight:600;text-decoration:none !important;margin:8px 0 4px}
a.cta:hover{background:#22345A}
a.cta.secondary{background:#fff;color:#14213D !important;border:1px solid #9AA5B1}
a.cta.secondary:hover{border-color:#14213D}
.stApp [data-testid="stIconMaterial"], .stApp span[data-testid*="Icon"], .stApp span[translate="no"][aria-hidden="true"],
.stApp .material-symbols-rounded {font-family:"Material Symbols Rounded" !important;}
</style>""", unsafe_allow_html=True)


def html(s: str, where=st):
    where.markdown(s, unsafe_allow_html=True)

# ---------------------------------------------------------------- data + engine (cached)


@st.cache_data(show_spinner="Reading the 5 buildings…")
def buildings():
    return load_buildings()


def _tracer():
    """Frozen copy of the original engine (engine_tracer.py), used per building when engine.py fails."""
    try:
        import engine_tracer
        return engine_tracer
    except Exception:
        return None


def _eng_attr(name: str):
    """Optional engine extra (next_question, handover_pdf, ALWAYS_CHECKS): engine.py first, else the tracer."""
    for m in (engine, _tracer()):
        if m is not None and hasattr(m, name):
            return getattr(m, name)
    return None


def _mtime(name: str) -> float:
    try:
        return (ROOT / name).stat().st_mtime
    except OSError:
        return 0.0


def engine_key() -> str:
    """Part of the _run cache key: editing engine.py while the app runs must not serve stale results."""
    return (f"engine.py@{_mtime('engine.py')}|engine_tracer.py@{_mtime('engine_tracer.py')}|import_ok={engine is not None}"
            f"|{O.cache_tag()}")


def _brief(mod, h: House) -> Result:
    r = mod.evaluate(h)
    if hasattr(mod, "installer_brief"):
        r = mod.installer_brief(h, r)
    if not isinstance(r, Result):
        r = Result.model_validate(r if isinstance(r, dict) else r.model_dump())
    return r


@st.cache_data(show_spinner=False)
def _run(house_json: str, eng_key: str) -> dict:
    """{"result": json, "engine": "module"|"main"|"tracer", "error": str|None, "module_error": str|None}.
    The calculation module first (when available, orchestrator.py), then engine.py, then the tracer."""
    h = House.model_validate_json(house_json)
    mod_err = None
    if O.available("calculation"):
        r, _, mod_err = O.calculate(h)
        if r is not None:
            given = sorted(r.model_fields_set)       # what the module actually returned (MVP core may be all)
            brief = False
            try:                                 # installer fields the module left empty → baseline brief (never overwrites)
                r, brief = O.fill_installer_brief(h, r)
            except Exception:
                pass
            return {"result": r.model_dump_json(), "engine": "module", "error": None, "module_error": None,
                    "brief": "baseline" if brief else None, "given": given}
    err = f"import failed ({ENGINE_ERR})" if engine is None else None
    if engine is not None:
        try:
            return {"result": _brief(engine, h).model_dump_json(), "engine": "main", "error": None, "module_error": mod_err}
        except Exception as e:
            err = f"{type(e).__name__}: {e}"
    tr = _tracer()
    if tr is None:
        raise RuntimeError(err or "no engine")
    try:
        return {"result": _brief(tr, h).model_dump_json(), "engine": "tracer", "error": err, "module_error": mod_err}
    except Exception as e2:
        raise RuntimeError(f"{err}; tracer also failed ({type(e2).__name__}: {e2})") from e2


ENGINE_ERRS: dict[str, str] = {}               # building id -> last evaluate error (shown small in Evaluation)
ENGINE_USED: dict[str, dict] = {}              # building id -> {"engine": "module"|"main"|"tracer", "error", "module_error"}


def evaluate(h: House, quiet: bool = False) -> Result | None:
    bid = str(h.building_id)
    try:
        out = _run(h.model_dump_json(), engine_key())
        r = Result.model_validate_json(out["result"])
        if out["engine"] in ("main", "tracer"):        # contract v2: the baseline engines don't fill the core yet
            info = None
            if BASELINE_INFO is not None:
                info = BASELINE_INFO.model_copy(update={"version": "engine_tracer.py"}) if out["engine"] == "tracer" \
                    else BASELINE_INFO
            r = with_core(r, info)
        else:                                          # a module: labels/units for its quantities, no default model_info
            r = mvp_defaults(with_core(r), out.get("given"))
        ENGINE_ERRS.pop(bid, None)
        ENGINE_USED[bid] = {"engine": out["engine"], "error": out["error"], "module_error": out.get("module_error"),
                            "brief": out.get("brief"), "given": out.get("given")}
        return r
    except Exception as e:
        ENGINE_ERRS[bid] = str(e)
        ENGINE_USED.pop(bid, None)
        if not quiet:
            st.caption(f"Engine error for {h.building_id}: {e}")
        return None


VERDICT_WORD = {"green": "likely suitable", "yellow": "workable, some checks remain", "red": "not without changes"}


def neutral_reason(r: Result) -> str:
    """One plain sentence from colour + flow temperature, for a logic that sent no `reason` (MVP core only)."""
    fl = qr(r, "flow_temp_c").p50
    word = VERDICT_WORD.get(r.best_color, "")
    if fl is None:
        return f"{word[:1].upper()}{word[1:]}." if word else ""
    temp = "70 °C or more" if fl > 70 else f"About {fl:.0f} °C"
    return f"{temp} on the coldest day: {word}."


def mvp_defaults(r: Result, given: list | None) -> Result:
    """A module that returned only the MVP core: derive the display-only fields it left out (never overwrites)."""
    if given is None:
        return r
    given = set(given)
    if "verdict_basis" not in given:
        r.verdict_basis = {"green": "likely_suitable", "yellow": "checks_remain"}.get(r.best_color, "checks_remain")
    if "traffic_light" not in given:
        r.traffic_light = r.best_color
    if not r.reason:
        r.reason = neutral_reason(r)
    return r


def given_by_logic(bid, field: str) -> bool:
    """False only when a module produced this building's result and left `field` out (hide that section)."""
    key = "Homeowner" if bid == "Homeowner house" else str(bid)
    u = ENGINE_USED.get(key) or {}
    return u.get("engine") != "module" or u.get("given") is None or field in u["given"]


def show_installer() -> bool:
    """The Installer tab is out of the MVP; HP_SHOW_INSTALLER=1 brings it back (code kept)."""
    return os.environ.get("HP_SHOW_INSTALLER", "0").strip().lower() in ("1", "true", "yes", "on")


def engine_used(bid) -> str | None:
    """"module" | "main" | "tracer" | None: which engine produced this building's result."""
    key = "Homeowner" if bid == "Homeowner house" else str(bid)   # the homeowner house is built with building_id "Homeowner"
    return (ENGINE_USED.get(key) or {}).get("engine")


def on_tracer(bid) -> bool:
    return engine_used(bid) == "tracer"


def on_module(bid) -> bool:
    return engine_used(bid) == "module"


def brief_from_baseline(bid) -> bool:
    """The module left the installer fields empty and the baseline installer_brief filled them."""
    key = "Homeowner" if bid == "Homeowner house" else str(bid)
    return (ENGINE_USED.get(key) or {}).get("brief") == "baseline"


def model_line(r: Result, extra: str = "") -> str:
    """Small muted 'Model: name · version · kind' line from r.model_info (contract v2). '' when nothing to say."""
    mi = r.model_info
    parts = [p for p in ((mi.name, mi.version, mi.kind) if mi is not None else ()) if p]
    if extra:
        parts.append(extra)
    return (f'<div style="font-size:12px;color:var(--muted)">Model: {esc(" · ".join(parts))}</div>' if parts else "")


CHIP_STYLE = ('style="font-size:10px;font-weight:600;color:var(--muted);border:1px solid var(--line);border-radius:999px;'
              'padding:1px 6px;margin-left:6px;vertical-align:middle"')


def tracer_chip(bid) -> str:
    """Tiny muted chip next to a building id: "module calc" (calculation module), "tracer" (frozen engine), nothing for engine.py."""
    if on_module(bid):
        return f'<span title="computed by the calculation module (orchestrator.py)" {CHIP_STYLE}>module calc</span>'
    if not on_tracer(bid):
        return ""
    return ('<span title="engine.py failed for this building; showing the frozen tracer engine" '
            'style="font-size:10px;font-weight:600;color:var(--muted);border:1px solid var(--line);border-radius:999px;'
            'padding:1px 6px;margin-left:6px;vertical-align:middle">tracer</span>')

# ---------------------------------------------------------------- formatting


LEGACY_FIELD = {"flow_temp_c": "required_flow_temp_c", "heat_load_kw": "heat_load_kw",
                "heat_load_bill_kw": "heat_load_bill_kw"}
KNOWN_QUANTITIES = ("flow_temp_c", "heat_load_kw", "heat_load_bill_kw", "specific_load_w_m2", "cost_now_eur",
                    "cost_hp_eur", "saving_eur")         # read by name by the screens; any other key is shown generically


def qr(r: Result, key: str) -> Range:
    """One door for every number the screens show: v2 `quantities` first (schema.quantity), else the legacy field."""
    q = quantity(r, key) if quantity is not None else None
    if q is not None:
        return Range(p10=q.p10, p50=q.p50, p90=q.p90)
    if key in LEGACY_FIELD:
        return getattr(r, LEGACY_FIELD[key])
    return Range(p50=getattr(r, key, None))


def qv(r: Result, key: str) -> float | None:
    return qr(r, key).p50


HOT = "70 °C or more"                            # the one form for the display clip (never ">70", never "≈ >70")


def t(v):
    return "–" if v is None else (HOT if v > 70 else f"{v:.0f} °C")


def about_t(v):
    """'about 54 °C' / '70 °C or more' (no 'about' in front of the clip)."""
    return "–" if v is None else (HOT if v > 70 else f"about {v:.0f} °C")


def fix_text(s: str | None) -> str:
    """Engine prose for the screens: one form for the clip, and the myth hint as 'Myth: … Fact: …'."""
    s = s or ""
    s = re.sub(r"(?:about|≈)\s*>\s*70\s*°C", HOT, s)
    s = re.sub(r">\s*70\s*°C", HOT, s)
    m = re.match(r"^Myth: you don't need (.+?) for a heat pump\.?$", s.strip())
    if m:
        s = f"**Myth:** you need {m.group(1)} for a heat pump.  \n**Fact:** you don't — most radiators work."
    return s


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
    rg = qr(r, 'flow_temp_c')
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


def stacked_bar(pg: float, py: float, pr: float, width: str = "150px", height: int = 8, labels: bool = False) -> str:
    """G/Y/R bar. labels=True: a letter (and % when it fits) inside each segment, so colour isn't the only cue."""
    ink = {"g": "#fff", "y": "#3A2802", "r": "#fff"}

    def lab(c, p):
        if not labels or p < 0.08:
            return ""
        txt = f"{c.upper()} {round(p * 100)}" if p >= 0.22 else c.upper()
        return (f'<span style="font-size:10px;font-weight:700;line-height:{height}px;color:{ink[c]};'
                f'white-space:nowrap;overflow:hidden">{txt}</span>')
    seg = "".join(f'<span style="width:{max(p or 0, 0) * 100:.1f}%;background:var(--bar-{c});display:flex;'
                  f'justify-content:center;overflow:hidden">{lab(c, p or 0)}</span>'
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


def diverging_bar(pct: float | None, half: float = 25, label: str | None = None,
                  colors: tuple[str, str] = ("var(--div-pos)", "var(--div-neg)")) -> str:
    """0-centred bar: + red to the right, − blue to the left; half the track = ±half % (or ±half in any unit)."""
    track = 'position:relative;height:8px;background:var(--line-soft);border-radius:4px;display:block'
    if pct is None:
        return f'<span style="{track}"></span>'
    w = min(abs(pct) / half, 1) * 50 if half else 0
    side = (f"left:50%;background:{colors[0]};border-radius:0 4px 4px 0" if pct >= 0
            else f"right:50%;background:{colors[1]};border-radius:4px 0 0 4px")
    return (f'<span role="img" aria-label="{esc(label) if label is not None else f"{pct:+.1f} %"}" style="{track}">'
            f'<span style="position:absolute;top:0;height:8px;width:{w:.1f}%;{side};display:block"></span></span>')


def qnum(v: float | None) -> str:
    """Generic number for model outputs of unknown scale."""
    if v is None:
        return "–"
    a = abs(v)
    return f"{v:,.0f}" if a >= 100 else f"{v:.1f}" if a >= 10 else f"{v:.2f}".rstrip("0").rstrip(".")


def extra_quantities(r: Result) -> list:
    """v2 quantities the screens don't read by name (model-specific outputs)."""
    return [q for q in r.quantities if q.key not in KNOWN_QUANTITIES]


def other_outputs_html(r: Result) -> str:
    """'Other model outputs' card for quantities the UI doesn't know; '' when there are none (today's engine)."""
    qs = extra_quantities(r)
    if not qs:
        return ""
    rows = "".join(
        '<tr><td class="ev-td" style="padding-left:22px;white-space:normal">'
        f'{esc(q.label or human_field(q.key))}'
        + (f'<span class="ev-sub">{esc(q.note)}</span>' if q.note else "") + '</td>'
        f'<td class="ev-td num" style="font-weight:600">{qnum(q.p50)}</td>'
        f'<td class="ev-td num">{"–" if q.p10 is None or q.p90 is None else f"{qnum(q.p10)}–{qnum(q.p90)}"}</td>'
        f'<td class="ev-td" style="color:var(--muted)">{esc(q.unit or "")}</td></tr>' for q in qs)
    return ('<div class="ev-card" style="overflow:hidden">'
            + _card_head("Other model outputs", "Numbers this model reports that the screens don't use by name.")
            + '<div style="overflow-x:auto"><table style="width:100%;border-collapse:collapse;margin:0;border:none">'
            '<thead><tr><th class="ev-th" style="padding-left:22px">Output</th><th class="ev-th">Median</th>'
            f'<th class="ev-th">Likely range (p10–p90)</th><th class="ev-th">Unit</th></tr></thead><tbody>{rows}</tbody>'
            '</table></div></div>')


def _target_text(target: str, unit: str) -> str:
    tgt = {"p_green": "chance of green", "flow_temp_c": "flow temperature", "heat_load_kw": "heat load"}.get(
        target, target.replace("_", " ")) if target else ""
    return " · ".join(x for x in (f"on {tgt}" if tgt else "", unit) if x)


def explanations_html(r: Result, top: int = 6) -> str:
    """'Why the model decided this': top inputs by |contribution| as signed bars scaled to the largest one;
    plain sentences when no contributions are given; '' when the logic sent no explanations (today's engine)."""
    ex = list(r.explanations)
    if not ex:
        return ""
    signed = [e for e in ex if e.contribution is not None]
    if signed:
        signed = sorted(signed, key=lambda e: -abs(e.contribution))[:top]
        half = max(abs(e.contribution) for e in signed) or 1.0
        body = "".join(
            '<div style="display:grid;grid-template-columns:minmax(0,1.3fr) minmax(90px,1fr) 92px;align-items:center;'
            'gap:12px;padding:10px 22px;border-top:1px solid var(--line-soft)">'
            f'<div style="font-size:14px;color:var(--ink);min-width:0">{esc(human_field(e.feature))}'
            + (f' <span style="color:var(--muted)">· {esc(str(e.value))}</span>' if e.value not in (None, "") else "")
            + (f'<span class="ev-sub">{esc(e.text)}</span>' if e.text else "") + '</div>'
            f'{diverging_bar(e.contribution, half, label=f"{e.contribution:+.3g} {e.unit}".strip(), colors=("var(--ink)", "#8A96A6"))}'
            '<div style="text-align:right"><span class="num" style="font-size:13px;font-weight:600;color:var(--ink)">'
            f'{e.contribution:+.3g}</span><span class="ev-sub">{esc(_target_text(e.target, e.unit))}</span></div></div>'
            for e in signed)
        sub = "Inputs that moved the result most, largest first. Bars are scaled to the largest effect."
    else:
        body = ('<ul style="margin:0;padding:12px 22px 16px 40px;font-size:14px;line-height:1.5;color:var(--ink);'
                'border-top:1px solid var(--line-soft)">'
                + "".join(f"<li>{esc(e.text or human_field(e.feature))}</li>" for e in ex[:top]) + "</ul>")
        sub = "What the model says drove the result."
    return ('<div class="ev-card" style="overflow:hidden">' + _card_head("Why the model decided this", sub)
            + body + "</div>")


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
        return HOT
    if hi > 70:
        return f"{lo:.0f} °C to {HOT}"
    return f"{lo:.0f}–{hi:.0f} °C"


def clean_text(s: str | None) -> str:
    """Engine prose for display: 'MC' -> 'simulation', '->' -> arrow, ASCII ranges -> en dash. Not escaped."""
    s = fix_text((s or "").strip())
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


# Fallback when neither r.always_checks nor engine.ALWAYS_CHECKS exists (engine wording, used to filter the checklist).
DEFAULT_ALWAYS_CHECKS = ["Exact heating load (DIN EN 12831) and room-by-room radiator sizing",
                         "Electrical capacity and meter cabinet", "Hydraulics and hydraulic balancing",
                         "Outdoor-unit position, sound distance and permits"]


def always_checks(r: Result | None) -> list[str]:
    """Checks done at every visit: r.always_checks first, else engine.ALWAYS_CHECKS, else the spec defaults."""
    if r is not None and r.always_checks:
        return list(r.always_checks)
    return list(_eng_attr("ALWAYS_CHECKS") or DEFAULT_ALWAYS_CHECKS)


FLAG_SRC = {"notes": "Notes", "area_rooms": "Area vs. room count", "not_documented": "Not documented",
            "data": "Building data", "site": "Site"}


def house_flags(h: House, r: Result) -> list[dict]:
    """Issues specific to this house. Single entry point for both tabs (same count). Each item: {text, src}.
    Structured r.flags first; else parse site flags + installer checklist minus the always-checks."""
    if r.flags:
        return [{"text": clean_text(f.text),
                 "src": bill_chip(h) if f.src == "bill" else FLAG_SRC.get(f.src, "Building data")} for f in r.flags]
    return _house_flags_from_text(h, r)


def _house_flags_from_text(h: House, r: Result) -> list[dict]:
    """Fallback for engines that do not fill r.flags: parse the English checklist."""
    always = set(always_checks(r))
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


def _band_text(h: House | None, s: str | None) -> str | None:
    """A year chosen as a band is stored as a representative year; show the band, never that year."""
    ev = (h.evidence.get("build_year") or "") if h is not None and h.build_year else ""
    if not s or not ev.startswith("band "):
        return s
    return re.sub(rf"\b{h.build_year}\b", ev[5:], s)


def rechenweg(r: Result, h: House | None = None, full: bool = True):
    """The calculation steps (Invariant 4). full=False: steps only, for the Evaluation detail, which already shows the
    explanations, the other outputs and the contradictions."""
    b = qr(r, 'heat_load_bill_kw')
    st.markdown(f"Heating load (size, age): **{t_range(qr(r, 'heat_load_kw'), kw)}**"
                + (f"  \nFrom the bill: {t_range(b, kw)}" if b.p50 is not None else ""))
    if r.trace:
        rows = [{k: fix_text(_band_text(h, v)) if isinstance(v, str) else v for k, v in s.model_dump().items()}
                for s in r.trace]
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    if full:
        for extra in (explanations_html(r), other_outputs_html(r)):    # contract v2: only when the logic sent them
            if extra:
                st.html(extra)
        for c in r.contradictions:
            st.markdown(f"- **{c.what}**" + (f" · trusted: {c.trusted}." if c.trusted else "") + f" {c.why or ''}")
    st.caption("First estimate, not a DIN EN 12831 calculation. " + " · ".join(f"{k}: {v}" for k, v in TERMS.items()))


def answer_card(h: House, r: Result | None, key: str):
    """Homeowner answer (team decision 2026-10-24: show little). Always: colour + one sentence, G/Y/R chances,
    water temperature, heating load. Collapsed: what's still open (red: what would change it). One button to an
    installer; cost, Rechenweg and hints stay in the Evaluation tab and on the PDF."""
    if r is None:
        st.info(f"Engine not ready yet ({ENGINE_ERR or 'no result'}).")
        return
    title, word = headline(r)
    html(f'<div class="card"><span class="light" style="background:{COL[r.best_color]}"></span>'
         f'<span style="font-size:26px;font-weight:700">{title}</span> <span class="muted">{word}</span>'
         f'<p style="font-size:16px;margin:12px 0 0">{esc(fix_text(r.reason))}</p></div>')
    rg, ld = qr(r, 'flow_temp_c'), qr(r, 'heat_load_kw')
    if r.verdict_basis == "cannot_tell_yet":      # numbers from a missing core field would read like a verdict
        rows = ['<div style="font-size:14px;color:#4A5565">Chances, water temperature and heating load show up '
                'once we know the missing piece above. Use "Change answers" to add it.</div>']
    else:
        rows = ['<div style="font-size:13px;color:#4A5565;margin-bottom:6px">How sure</div>' + prob_bar(r)
            + f'<div style="font-size:14px;margin:6px 0 14px">Green {r.p_green:.0%} · Yellow {r.p_yellow:.0%} · '
              f'Red {r.p_red:.0%}</div>']
    if rg.p50 is not None and r.verdict_basis != "cannot_tell_yet":
        span = f" · likely {flow_span(rg.p10, rg.p90)}" if rg.p10 is not None and rg.p90 is not None else ""
        rows.append(f'<div style="font-size:13px;color:#4A5565" title="{esc(TERMS.get("Vorlauftemperatur", ""))}">'
                    f'Water temperature on the coldest day: <b style="color:#14213D">{esc(about_t(rg.p50))}</b>'
                    f'{esc(span)}</div>' + scale(r))
    if ld.p50 is not None and r.verdict_basis != "cannot_tell_yet":
        rows.append(f'<div style="font-size:13px;color:#4A5565" title="{esc(TERMS["Heizlast"])}">'
                    f'Heating load: <b style="color:#14213D">{esc(t_range(ld, kw))}</b></div>')
    html('<div class="card" style="margin-top:12px">' + "".join(rows) + '</div>')
    takes = what_it_takes(h, r) if r.best_color == "red" else []
    if takes:                                     # Invariant 6: every red carries its path to yellow
        with st.expander("What would change it"):
            for tt, b in takes:
                st.markdown(f"**{tt}**  \n{b}")
            st.caption("Physics only: an installer turns this into parts and a price.")
    if r.open_checks:
        n = len(r.open_checks)
        with st.expander(f"What's still open · {n} thing{'s' if n != 1 else ''}"):
            for i, c in enumerate(r.open_checks, 1):
                st.markdown(f"{i}. {fix_text(c.item)}" + (f" ({fix_text(c.why)})" if c.why else ""))
    req = f"ask_{key}"
    if not st.session_state.get(req):
        st.button("Ask an installer", key=f"askbtn_{key}", type="primary", width="stretch",
                  on_click=lambda: st.session_state.update({req: True}))

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


RED_RISK = 0.30                                  # R % at or above this is shown bold red (Evaluation)


def gyr_text(r: Result) -> str:
    """'G 51 % · Y 18 % · R 31 %' (HTML), red share bold red when it is a real risk."""
    rr = f"R {pct(r.p_red)}"
    if r.p_red >= RED_RISK:
        rr = f'<b style="color:var(--r-tx)">{rr}</b>'
    return f"G {pct(r.p_green)} · Y {pct(r.p_yellow)} · {rr}"


def red_risk_cell(r: Result) -> str:
    """Red-risk column, one style for every row: R % as text (bold red at ≥ 30 % or a red verdict, muted below)
    with a short label under it."""
    sub = "verdict red" if r.best_color == "red" else "real red risk" if r.p_red >= RED_RISK else "low"
    strong = r.best_color == "red" or r.p_red >= RED_RISK
    sty = "font-weight:700;color:var(--r-tx)" if strong else "color:var(--muted)"
    return f'<span class="num" style="{sty}">{pct(r.p_red)}</span><span class="ev-sub">{sub}</span>'


def red_calls_card(res) -> str:
    """KPI: how many buildings are red, and for dev buildings whether 'red or not' matches the reference."""
    got = [(bid, ref, r) for bid, _, ref, r in res if r is not None]
    reds = [bid for bid, _, r in got if r.best_color == "red"]
    risky = [bid for bid, _, r in got if r.best_color != "red" and r.p_red >= RED_RISK]
    dev = [(bid, ref, r) for bid, ref, r in got if ref and ref.get("verdict")]
    match = sum((r.best_color == "red") == (ref["verdict"] == "red") for _, ref, r in dev)
    chips_ = "".join(pill("red", f"{esc(str(b))} Red", filled=True) for b in reds)
    chips_ += "".join(pill("red", f"{esc(str(b))} R {pct(r.p_red)}") for b, _, r in got if b in risky)
    lines = [f'<div style="display:flex;gap:8px;flex-wrap:wrap">{chips_}</div>' if chips_ else ""]
    if dev:
        lines.append(f'<div style="font-size:13px;color:var(--ink)">Dev buildings: red / not red matches the reference '
                     f'<b class="num">{match} / {len(dev)}</b></div>')
    lines.append(f'<div style="font-size:12px;color:var(--muted)">Pale chips: not red, but red risk ≥ {pct(RED_RISK)}.</div>'
                 if risky else "")
    return kpi_card("Red calls", f"{len(reds)} / {len(got)}", "".join(lines), aside="buildings red")


def eval_kpis(B, dev, res=()) -> str:
    ok = sum(r.best_color == ref["verdict"] for _, ref, r in dev)
    chips_ = []
    for bid, ref, r in dev:
        hit = r.best_color == ref["verdict"]
        chips_.append(pill(r.best_color if hit else "red",
                           f"{bid} {r.best_color.capitalize()} ✓" if hit
                           else f"{bid} {r.best_color.capitalize()} ✗ (ref {ref['verdict'].capitalize()})"))
    c1 = kpi_card("Dev verdicts reproduced", f"{ok} / {len(dev)}",
                  f'<div style="display:flex;gap:8px;flex-wrap:wrap">{"".join(chips_)}</div>')
    red = red_calls_card(res)
    info = next((r.model_info for _, _, r in dev if r.model_info is not None), None)
    reported = ""
    if info is not None and info.metrics:                # self-reported (invariant 8): labelled, never mixed with measured
        reported = ('<div style="font-size:13px;color:var(--ink);line-height:1.5">Reported by the model: '
                    + esc(", ".join(f"{k} {qnum(v)}" for k, v in info.metrics.items())) + "</div>"
                    '<div style="font-size:12px;color:var(--muted)">Self-reported by the model, not measured by this app.</div>')
    if any(on_module(bid) for bid, _, _ in dev):       # not the baseline: calibrate.py would measure engine.py, not this
        errs = [(bid, (qv(r, 'heat_load_kw') - ref["heating_load_kw"]) / ref["heating_load_kw"] * 100)
                for bid, ref, r in dev if ref.get("heating_load_kw") and qv(r, 'heat_load_kw') is not None]
        rows = "".join(
            '<div style="display:grid;grid-template-columns:44px minmax(0,1fr) 60px;align-items:center;gap:10px;font-size:12px">'
            f'<span style="color:var(--muted)">{esc(str(b))}</span>{diverging_bar(e)}'
            f'<span class="num" style="text-align:right;font-weight:600;color:var(--ink)">{signed_pct(e)}</span></div>'
            for b, e in errs)
        mae = sum(abs(e) for _, e in errs) / len(errs) if errs else None
        c2 = kpi_card("Heat-load error · vs reference", "–" if mae is None else f"{mae:.1f} %",
                      f'<div style="display:flex;flex-direction:column;gap:6px">{rows}</div>'
                      '<div style="font-size:12px;color:var(--muted)">Measured by this app from the model\'s predictions on '
                      'the dev buildings (not leave-one-out).</div>', aside="mean absolute")
        name = info.name if info is not None and info.name else "Calculation module"
        c3 = kpi_card("Model", esc(name), reported or '<div style="font-size:13px;color:var(--muted)">No metrics reported '
                      'by the model.</div>', aside=esc(info.kind) if info is not None else "")
        return f'<div class="kpi-grid">{c1}{red}{c2}{c3}</div>'
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
                      'Nothing else is fitted to the dev set.</div>' + reported, aside="1 tuned number")
    else:
        c2 = kpi_card("Heat-load error · leave-one-out", "–")
        c3 = kpi_card("Calibration", f"k = {k:.2f}", reported, aside="1 tuned number")
    return f'<div class="kpi-grid">{c1}{red}{c2}{c3}</div>'


def eval_table(res, sel: str) -> str:
    legend = "".join(f'<span style="display:flex;align-items:center;gap:6px"><span style="width:10px;height:10px;'
                     f'border-radius:2px;background:var(--bar-{c[0]});display:block"></span>{c.capitalize()}</span>'
                     for c in ("green", "yellow", "red"))
    inst = show_installer()                      # Next step / Lead score are installer columns (out of the MVP)
    heads = [("Building", ""), ("Verdict", ""), ("Green · Yellow · Red", "width:170px"), ("Red risk", ""),
             ("Flow temp", ""), ("Heat load", ""), ("Flags", "text-align:right")]
    if inst:
        heads += [("Next step", ""), ("Lead score", "width:120px")]
    th = "".join(f'<th class="ev-th" style="{s}">{n}</th>' for n, s in heads)
    body = []
    for bid, h, ref, r in res:
        if r is None:
            body.append(f'<tr><td class="ev-td"><b>{esc(bid)}</b></td><td class="ev-td" colspan="{len(heads) - 1}">'
                        '<span class="ev-sub">No result</span></td></tr>')
            continue
        is_sel = bid == sel
        tr = ' style="background:#F3F6FA"' if is_sel else ""
        first = ' style="box-shadow:inset 3px 0 0 var(--ink)"' if is_sel else ""
        if ref:
            hit = ref["verdict"] == r.best_color
            refmark = (f'<span style="font-size:12px;color:var(--{"g" if hit else "r"}-tx)">'
                       f'{"✓" if hit else "✗"} ref {esc(str(ref["verdict"]))}</span>')
        else:
            refmark = '<span style="font-size:12px;color:var(--muted)">no ref</span>'
        top, _ = _top_color(r)
        close = '<span class="ev-sub">close call</span>' if top != r.best_color or r.boundary else ""
        fl = qr(r, 'flow_temp_c')
        load = qr(r, 'heat_load_kw').p50
        if ref and ref.get("heating_load_kw"):
            load_sub = f"ref {ref['heating_load_kw']:.1f} · {pct_diff(load, ref['heating_load_kw'])}"
        else:
            b = qr(r, 'heat_load_bill_kw').p50
            load_sub = (f"bill {b:.1f} · {pct_diff(load, b)}" if b is not None
                        else "" if on_module(bid) else "no bill")
        row = (
            f'<tr{tr}><td class="ev-td"{first}><b>{esc(bid)}</b>{tracer_chip(bid)}<span class="ev-sub">{"dev" if ref else "held-out"}</span></td>'
            f'<td class="ev-td">{pill(r.best_color, r.best_color.capitalize(), filled=r.best_color == "red")} {refmark}</td>'
            f'<td class="ev-td">{stacked_bar(r.p_green, r.p_yellow, r.p_red, width="150px", height=16, labels=True)}{close}</td>'
            f'<td class="ev-td">{red_risk_cell(r)}</td>'
            f'<td class="ev-td num">{t(fl.p50)}<span class="ev-sub">{flow_span(fl.p10, fl.p90)}</span></td>'
            f'<td class="ev-td num">{kw(load)}<span class="ev-sub">{load_sub}</span></td>'
            f'<td class="ev-td num" style="text-align:right">{len(house_flags(h, r))}</td>')
        if inst:
            row += (f'<td class="ev-td">{NEXT_SHORT.get(r.visit_type, "–")}</td>'
                    f'<td class="ev-td">{score_bar(r.lead_score)}</td>')
        body.append(row + "</tr>")
    return ('<div class="ev-card" style="overflow:hidden">'
            '<div style="display:flex;justify-content:space-between;align-items:center;padding:18px 20px 12px;'
            'flex-wrap:wrap;gap:8px"><h2 style="margin:0;font-size:16px;font-weight:600;color:var(--ink)">All buildings</h2>'
            f'<div style="display:flex;gap:14px;font-size:12px;color:var(--muted);align-items:center">{legend}</div></div>'
            '<div style="overflow-x:auto"><table style="width:100%;border-collapse:collapse;min-width:720px;margin:0;'
            f'border:none"><thead><tr>{th}</tr></thead><tbody>{"".join(body)}</tbody></table></div>'
            '<div style="padding:12px 20px;font-size:12px;color:var(--muted);border-top:1px solid var(--line-soft)">'
            f'Red risk = chance of red; bold red from {pct(RED_RISK)}. Labels in the bar: G green, Y yellow, R red (%). Use “Open” above the table for a building’s details.'
            '</div></div>')


def _house_line(h: House) -> str:
    parts = [_band_text(h, str(h.build_year)) if h.build_year else None,
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
    head = ('<div style="display:flex;flex-direction:column;gap:6px">'
            '<div style="display:flex;align-items:baseline;gap:14px;flex-wrap:wrap">'
            f'<h2 style="margin:0;font-size:26px;font-weight:700;letter-spacing:-0.01em;color:var(--ink)">{esc(bid)}</h2>'
            f'<div style="font-size:16px;color:var(--ink)">{esc(_house_line(h))}</div>{tag}</div>'
            + model_line(r, "installer brief from baseline" if brief_from_baseline(bid) else "") + '</div>')

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
    if not r.contradictions and not given_by_logic(bid, "contradictions"):   # optional extra the logic didn't send
        conflicts = ""

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
    fl = qr(r, 'flow_temp_c')
    approx = "" if fl.p50 is None or fl.p50 > 70 else "≈ "
    bill, load50 = qv(r, 'heat_load_bill_kw'), qv(r, 'heat_load_kw')
    sv = qv(r, 'saving_eur')
    cost_note = (f'<div style="font-size:12px;color:var(--muted);grid-column:1/-1">{esc(clean_text(r.cost_note))}</div>'
                 if r.cost_note else "")
    hp_cost = qv(r, 'cost_hp_eur')
    if r.best_color == "red" or (fl.p50 is not None and fl.p50 > 60):   # no saving headline on red (UI review)
        cost_cell = "" if hp_cost is None else (
            '<div><div style="font-size:12px;color:var(--muted)">Running cost, heat pump</div>'
            f'<div class="num" style="font-size:18px;font-weight:700;color:var(--ink)">€{hp_cost:,.0f} / yr</div>'
            '<div style="font-size:12px;color:var(--muted)">lower bound; above 60 °C it runs expensively</div></div>'
            f'{cost_note}')
    else:
        cost_cell = "" if sv is None else (
            '<div><div style="font-size:12px;color:var(--muted)">Running cost</div>'
            f'<div class="num" style="font-size:18px;font-weight:700;color:var(--ink)">{"−" if sv > 0 else "+"}€{abs(sv):,.0f} / yr</div>'
            f'<div style="font-size:12px;color:var(--muted)">vs. {FUEL_WORD.get(h.fuel_type or "", "the current heating")} today</div></div>'
            f'{cost_note}')
    bill_sub = (f"bill says {bill:.1f}" if bill is not None else "" if on_module(bid) else "no bill")
    if ref and ref.get("heating_load_kw"):
        bill_sub = f"reference {ref['heating_load_kw']:.1f}" + (f" · {bill_sub}" if bill_sub else "")
    of_what = "of simulations" if not on_module(bid) else "probability"
    verdict = _card(
        '<div style="display:flex;flex-direction:column;gap:18px">'
        '<div style="display:flex;align-items:center;gap:14px">'
        f'<span style="width:40px;height:40px;border-radius:20px;background:{_FILLED[r.best_color][0]};display:block;flex:none"></span>'
        f'<div><div style="font-size:24px;font-weight:700;line-height:1.1;color:var(--ink)">{esc(title)}</div>'
        f'<div style="font-size:13px;color:var(--muted)">{esc(word)} · {pct(p_best)} {of_what}</div></div></div>'
        '<div style="display:flex;flex-direction:column;gap:6px">'
        f'{stacked_bar(r.p_green, r.p_yellow, r.p_red, width="100%", height=16, labels=True)}'
        f'<div class="num" style="font-size:13px;color:var(--ink)">{gyr_text(r)}</div></div>'
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
        f'<div class="num" style="font-size:18px;font-weight:700;color:var(--ink)">{kw(load50)}</div>'
        f'<div style="font-size:12px;color:var(--muted)">{esc(bill_sub)}</div></div>'
        f'{cost_cell}</div></div>')

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
            f'<div style="flex:999 1 520px;min-width:0;display:flex;flex-direction:column;gap:20px">{conflicts}{notes}'
            f'{explanations_html(r)}{other_outputs_html(r)}</div>'
            f'<div style="flex:1 1 340px;max-width:100%;min-width:0;display:flex;flex-direction:column;gap:16px">{verdict}{still}</div>'
            '</div></div>')


def contract_lines(res) -> list[str]:
    """One muted line per building whose Result breaks the UI contract (schema.check_result) or whose evaluate raised."""
    out = []
    for bid, h, _, r in res:
        if r is None:
            if bid in ENGINE_ERRS:
                out.append(f"{bid}: no result, engine error ({ENGINE_ERRS[bid][:120]})")
            continue
        try:
            probs = check_result(h, r)
        except Exception as e:
            probs = [f"check_result failed: {e}"]
        if probs:
            out.append(f"{bid}: " + "; ".join(probs))
    return out


def fallback_lines(res) -> list[str]:
    """One muted line per building whose result came from the tracer because engine.py failed."""
    if engine is None and any(on_tracer(bid) for bid, *_ in res):
        return [f"New engine failed to import ({(ENGINE_ERR or '')[:120]}), showing the tracer result for all buildings"]
    return ([f"{bid}: new engine failed ({(ENGINE_USED[str(bid)]['error'] or '')[:120]}), showing the tracer result"
             for bid, *_ in res if on_tracer(bid)]
            + [f"{bid}: calculation module failed ({(ENGINE_USED[str(bid)].get('module_error') or '')[:120]}), showing engine.py"
               for bid, *_ in res if (ENGINE_USED.get(str(bid)) or {}).get("module_error")])


def baseline_section(res):
    """Rows only for buildings that moved against data/baseline_results.json (python loader.py --save-baseline)."""
    try:
        from loader import baseline_moved, baseline_rows, compare_baseline, load_baseline
        saved = load_baseline()
        if not saved:
            return
        by_id = {bid: r for bid, _, _, r in res}
        cur = baseline_rows([(bid, h, ref) for bid, h, ref, _ in res], lambda h: by_id.get(str(h.building_id)))
        rows = [x for x in compare_baseline(cur, saved) if x["building_id"] in by_id and not x["missing"]
                and not x["error"] and baseline_moved(x)]
    except Exception as e:
        st.caption(f"Baseline compare not available ({e}).")
        return
    if not rows:
        return
    lines = []
    for x in rows:
        col = (f"{(x['color_saved'] or '?').capitalize()} → {(x['color_now'] or '?').capitalize()}"
               if x["color_changed"] else (x["color_now"] or "?").capitalize())
        parts = [f"<b>{esc(x['building_id'])}</b> {esc(col)}"]
        if x["flow_delta"] is not None:
            parts.append(f"flow {x['flow_saved']:.1f} → {x['flow_now']:.1f} °C ({x['flow_delta']:+.1f})")
        if x["load_delta"] is not None:
            parts.append(f"load {x['load_saved']:.1f} → {x['load_now']:.1f} kW")
        if x["visit_changed"]:
            parts.append(f"visit {esc(str(x['visit_saved']))} → {esc(str(x['visit_now']))}")
        lines.append(f'<div class="num">{" · ".join(parts)}</div>')
    st.html('<div style="font-size:12px;color:var(--muted);display:flex;flex-direction:column;gap:2px;margin-top:6px">'
            '<div style="font-weight:600">Compared with the saved baseline</div>' + "".join(lines) + '</div>')


@st.cache_data(show_spinner="Running both logics on every building…")
def _compare(eng_key: str) -> list[dict]:
    return O.compare_logic(buildings())


def _ab(a, b, fmt) -> str:
    if a is None and b is None:
        return "–"
    return f"{fmt(a)} → {fmt(b)}"


def _hit(v) -> str:
    return "–" if v is None else ('<span style="color:var(--g-tx)">✓</span>' if v
                                  else '<span style="color:var(--r-tx)">✗</span>')


def compare_html(rows: list[dict], s: dict) -> str:
    """A/B table (A = baseline engine.py, B = calculation module), all numbers measured by the app."""
    def col(c):
        return pill(c, c.capitalize(), size="11px") if c else '<span style="color:var(--muted)">–</span>'

    def num(v, unit=""):
        return "–" if v is None else f"{v:.1f}{unit}"

    def delta(v, unit):
        return "" if v is None else f'<span class="ev-sub">Δ {v:+.1f} {unit}</span>'
    heads = ["Building", "Baseline (A)", "Module (B)", "Flow p50 A → B", "Heat load p50 A → B", "Verdict vs ref A / B"]
    th = "".join(f'<th class="ev-th">{h}</th>' for h in heads)
    body = []
    for x in rows:
        err = ""
        if x["dev"] and (x["a_load_err_pct"] is not None or x["b_load_err_pct"] is not None):
            ea, eb = (("–" if v is None else f"{abs(v):.0f} %") for v in (x["a_load_err_pct"], x["b_load_err_pct"]))
            err = f'<span class="ev-sub">|error| vs ref {x["ref_load_kw"]:.1f} kW: {ea} → {eb}</span>'
        b_cell = (col(x["b_color"]) + f'<span class="ev-sub num">p_green {pct(x["b_p_green"])}</span>' if x["b_color"]
                  else f'<span class="ev-sub">{esc((x["b_error"] or "no result")[:80])}</span>')
        body.append(
            f'<tr><td class="ev-td"><b>{esc(x["building_id"])}</b><span class="ev-sub">'
            f'{"dev · ref " + x["ref_verdict"].capitalize() if x["ref_verdict"] else "held-out"}</span></td>'
            f'<td class="ev-td">{col(x["a_color"])}<span class="ev-sub num">p_green {pct(x["a_p_green"])}</span></td>'
            f'<td class="ev-td">{b_cell}</td>'
            f'<td class="ev-td num">{_ab(x["a_flow_c"], x["b_flow_c"], lambda v: num(v, " °C"))}{delta(x["flow_delta"], "K")}</td>'
            f'<td class="ev-td num">{_ab(x["a_load_kw"], x["b_load_kw"], lambda v: num(v, " kW"))}{delta(x["load_delta"], "kW")}{err}</td>'
            f'<td class="ev-td">{_hit(x["a_hit"])} / {_hit(x["b_hit"])}</td></tr>')

    def mae(v):
        return "–" if v is None else f"{v:.1f} %"
    body.append(
        '<tr style="background:#F3F6FA"><td class="ev-td"><b>Summary</b><span class="ev-sub">dev buildings</span></td>'
        f'<td class="ev-td num" colspan="2">Verdicts reproduced: A {s["a_hits"]} / {s["a_n"] or s["n_dev"]} · '
        f'B {s["b_hits"]} / {s["b_n"] or s["n_dev"]}</td><td class="ev-td"></td>'
        f'<td class="ev-td num" colspan="2">Mean |heat-load error|: A {mae(s["a_mae_pct"])} · B {mae(s["b_mae_pct"])}</td></tr>')
    a_name = next((x["a_model"] for x in rows if x["a_model"]), "baseline")
    b_name = next((x["b_model"] for x in rows if x["b_model"]), "calculation module")
    return ('<div class="ev-card" style="overflow:hidden">'
            + _card_head("Compare logic", f"A = {esc(a_name)} (engine.py) · B = {esc(b_name)}. Same inputs, same seed; "
                         "all numbers measured by this app.")
            + '<div style="overflow-x:auto"><table style="width:100%;border-collapse:collapse;min-width:820px;margin:0;'
            f'border:none"><thead><tr>{th}</tr></thead><tbody>{"".join(body)}</tbody></table></div></div>')


def compare_section():
    """Evaluation toggle 'Compare logic' (paper ablation): baseline vs the calculation module, side by side."""
    if not st.toggle("Compare logic", key="eval_compare",
                     help="Run the baseline (engine.py) and the calculation module on every building, side by side."):
        return
    if not O.available("calculation"):
        st.caption("No calculation module yet — plug one in via `modules/calculation.py` or `HP_MODULE_CALCULATION`.")
        return
    try:
        rows = _compare(engine_key())
        st.html(compare_html(rows, O.compare_summary(rows)))
    except Exception as e:
        st.caption(f"Compare not available ({type(e).__name__}: {e}).")


def tab_evaluation():
    B = buildings()
    res = [(bid, h, ref, evaluate(h, quiet=True)) for bid, h, ref in B]
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
    st.html(eval_kpis(B, dev, res))
    compare_section()

    ids = [b for b, *_ in res]
    default = "B-05" if "B-05" in ids else ids[-1]
    # UI review: the picker sits right above the table, labelled "Open:" (robust; HTML table rows can't be clicked)
    with st.container(horizontal=True, vertical_alignment="center", key="eval_open"):
        st.markdown("**Open:**", width="content")
        try:
            sel = st.segmented_control("Open a building", ids, default=default, key="eval_sel", required=True,
                                       label_visibility="collapsed")
        except TypeError:
            sel = st.segmented_control("Open a building", ids, default=default, key="eval_sel",
                                       label_visibility="collapsed")
        except AttributeError:
            sel = st.radio("Open a building", ids, index=ids.index(default), horizontal=True, key="eval_sel",
                           label_visibility="collapsed")
    sel = sel or st.session_state.get("eval_last", default)
    st.session_state["eval_last"] = sel
    st.html(eval_table(res, sel))
    for line in fallback_lines(res) + contract_lines(res):
        st.caption(line)
    baseline_section(res)

    bid, h, ref, r = next(x for x in res if x[0] == sel)
    if r is None:
        st.info(f"No result for {bid}.")
        return
    st.html(eval_detail(bid, h, ref, r))
    with st.expander("How we got this (calculation steps)"):     # the only place the trace shows since f452039
        rechenweg(r, h, full=False)


CHIPS = [("build_year", "{}"), ("living_area_m2", "{:.0f} m²"), ("building_type", "{}"), ("renovation", "{} renovated"),
         ("heat_distribution", "{}"), ("fuel_type", "{}"), ("annual_fuel_kwh", "{:,.0f} kWh"), ("occupants", "{} people"),
         ("radiator_count", "{} radiators"), ("radiator_size", "{} radiators"), ("pipe_system", "{}"),
         ("kwh_printed", "{:,.0f} kWh on the bill"), ("certificate_kwh_m2a", "{:.0f} kWh/m²a"), ("outdoor_unit_space", "outdoor spot: {}")]


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


# ---- page 1 "Your house" (UI review 2026-10-24: dropdown facts first, photo, bill, optional free text last)
# Merge priority: the form is owner-entered, so it ranks like the old owner text ("text" in extract.ORDER: owner fields
# beat bill/photo, the bill beats it for fuel and use, the photo beats it for radiator size and pipes). extract.merge and
# engine._field_conf don't know "form" yet (they would rank it last / give it 0.3 confidence), so the form House carries
# source "text" internally and the screens show "form" (src_label). Flip FORM_MERGE_SRC to "form" once both know it.
# The optional page-4 free text is read by the LLM parser only on "Read it"; its House carries TEXT_MERGE_SRC
# ("notes_llm": below form, bill and photo in every group), so it only fills fields that are still empty. A
# disagreement between the text and a filled field never becomes a question (home_house drops it from
# House.conflicts); it shows as one muted "Not used (already set): …" note under the text's chips.
FORM_MERGE_SRC = "text"
TEXT_MERGE_SRC = "notes_llm"
DK = "Don't know"
YEAR_BANDS = [  # (label, representative year, first, last): same W/m² row as any year inside, keeps the 1960–78 rule
    ("before 1960", 1950, None, 1959), ("1960–1978", 1970, 1960, 1978), ("1979–1994", 1987, 1979, 1994),
    ("1995–2001", 1998, 1995, 2001), ("2002–2015", 2008, 2002, 2015), ("2016 or later", 2018, 2016, None)]
BAND_YEAR = {b: y for b, y, _, _ in YEAR_BANDS}


def year_band(y) -> str | None:
    try:
        y = int(y)
    except (TypeError, ValueError):
        return None
    return next((b for b, _, lo, hi in YEAR_BANDS if (lo is None or y >= lo) and (hi is None or y <= hi)), None)


NAMES = {"detached": "detached", "semi_detached": "semi-detached", "terraced": "terraced", "apartment": "apartment",
         "unrenovated": "not renovated", "partially": "partly", "fully": "fully",
         "radiators": "radiators", "underfloor": "underfloor", "mixed": "both",
         "gas": "gas", "lpg": "LPG", "oil": "oil", "district": "district heating", "electric": "electric"}
FORM = [  # (field, label, options | NUM (min, max, step, unit), value -> text)
    ("build_year", "Year built", ("num", 1800, 2026, 1, ""), "{}"),
    ("living_area_m2", "Living area", ("num", 10, 2000, 5, "m²"), "{:,} m²"),
    ("building_type", "Building type", ["detached", "semi_detached", "terraced", "apartment"], NAMES),
    ("renovation", "Insulation / renovation", ["unrenovated", "partially", "fully"], NAMES),
    ("heat_distribution", "Heating surfaces", ["radiators", "underfloor", "mixed"], NAMES),
    ("fuel_type", "Fuel", ["gas", "lpg", "oil", "district", "electric"], NAMES),
    ("annual_fuel_kwh", "Yearly use", ("num", 0, 200000, 500, "kWh / year"), "{:,} kWh"),        # fuel isn't oil
    ("annual_fuel_liters", "Yearly use", ("num", 0, 20000, 100, "litres / year"), "{:,} litres"),  # fuel is oil
    ("occupants", "People", ("num", 1, 20, 1, ""), "{}"),
    ("rooms", "Rooms", ("num", 1, 50, 1, ""), "{}"),
    ("radiator_count", "Radiators", ("num", 0, 80, 1, ""), "{}"),
    ("radiator_size", "Radiator size", ["small", "medium", "large"], "{}"),
    ("dhw_by_boiler", "Hot water from the boiler", ["yes", "no"], "{}"),
]
# Page-1 sections, in this order (the form is long; headers make it scannable).
FORM_GROUPS = ["The building", "Heating", "Radiators", "People and rooms"]
GROUP_OF = {"build_year": "The building", "living_area_m2": "The building", "building_type": "The building",
            "renovation": "The building", "heat_distribution": "Heating", "fuel_type": "Heating",
            "annual_fuel_kwh": "Heating", "annual_fuel_liters": "Heating", "dhw_by_boiler": "Heating",
            "radiator_count": "Radiators", "radiator_size": "Radiators",
            "occupants": "People and rooms", "rooms": "People and rooms"}
# Fields that move the colour most (engine: load = area × W/m²(year, renovation); flow temperature from radiators).
IMPORTANT = {"build_year", "living_area_m2", "heat_distribution", "renovation", "radiator_count", "radiator_size"}
FORM_EXAMPLE = {"build_year": 1972, "living_area_m2": 140, "building_type": "terraced", "renovation": "partially",
                "heat_distribution": "radiators", "fuel_type": "gas", "annual_fuel_kwh": 18000, "occupants": 3,
                "radiator_count": 10, "radiator_size": "large", "dhw_by_boiler": "yes"}
DEMO_BILL = "assets/demo/bill_demo_gas_2025_photo.jpg"
# Example houses for page 1 (all fictional: invented names, no addresses). A card fills the form, attaches its radiator
# photo and bill through the same read path as an upload (orchestrator → module or demo cache, never a live LLM call)
# and pre-fills the page-4 text box (read only on "Read it").
EXAMPLES = {
    "weber": {"name": "The Webers' terraced house", "place": "Munich-Pasing", "year": "1972",
              "line": "140 m² · gas · 10 large radiators · photo and bill attached",
              "form": FORM_EXAMPLE, "photo": "05_zweirohr-vermutet_kompakt.jpeg", "bill": DEMO_BILL,
              "text": "assets/demo/house_persona_en.txt"},
    "schneider": {"name": "Haus Schneider", "place": "Detached · Dachau area", "year": "1985",
                  "line": "120 m² · oil 2,000 L · 4 people · bill attached",
                  "form": {"build_year": 1985, "living_area_m2": 120, "building_type": "detached",
                           "renovation": "unrenovated", "heat_distribution": "radiators", "fuel_type": "oil",
                           "annual_fuel_liters": 2000, "occupants": 4},
                  "photo": None, "bill": DEMO_BILL, "text": "assets/demo/house_conflict_en.txt"},
    "farmhouse": {"name": "The old farmhouse", "place": "Upper Bavaria", "year": "year unknown",
                  "line": "about 150 m² · radiators · the rest unknown",
                  "form": {"living_area_m2": 150, "heat_distribution": "radiators"},
                  "photo": None, "bill": None, "text": "assets/demo/house_minimal_en.txt"},
    "newer": {"name": "The Kaya family's house", "place": "Detached · Erding", "year": "2008",
              "line": "160 m² · underfloor heating · gas 12,000 kWh",
              "form": {"build_year": 2008, "living_area_m2": 160, "building_type": "detached",
                       "heat_distribution": "underfloor", "fuel_type": "gas", "annual_fuel_kwh": 12000, "occupants": 4,
                       "dhw_by_boiler": "yes"},
              "photo": None, "bill": None, "text": None},
}
INT_FIELDS = ("build_year", "occupants", "rooms", "radiator_count")
FLOAT_FIELDS = ("living_area_m2", "annual_fuel_kwh", "annual_fuel_liters")
NUM_FIELDS = {f for f, _, o, _ in FORM if isinstance(o, tuple)}


def form_text(f: str, v) -> str:
    """Option → what the owner reads."""
    if v == DK or v is None:
        return DK
    fmt = next((n for x, _, _, n in FORM if x == f), None)
    if isinstance(fmt, dict):
        return fmt.get(v, str(v))
    try:
        return (fmt or "{}").format(v)
    except (ValueError, TypeError):
        return str(v)


def form_rows(fuel) -> list:
    """Page-1 rows; the yearly-use row switches between kWh and litres with the fuel."""
    skip = "annual_fuel_kwh" if fuel == "oil" else "annual_fuel_liters"
    return [row for row in FORM if row[0] != skip]


def src_label(src: str | None) -> str:
    """Display name of a source: the form's internal merge source shows as "form", the free text as "text"."""
    return {FORM_MERGE_SRC: "form", TEXT_MERGE_SRC: "text", "confirmed": "you"}.get(src, src or "")


def value_text(h: House, f: str, v=None, src: str | None = None) -> str:
    """A House value for the screens; a year stored from an old band answer shows the band (years are typed now)."""
    v = getattr(h, f) if v is None else v
    src = src or h.source.get(f)
    if f == "build_year":
        ev = h.evidence.get("build_year", "")
        if ev.startswith("band ") and year_band(v) == ev[5:]:
            return ev[5:]
    if isinstance(v, bool):
        return "yes" if v else "no"
    if f in ("annual_fuel_kwh", "kwh_printed"):
        return f"{v:,.0f} kWh"
    if f == "annual_fuel_liters":
        return f"{v:,.0f} litres"
    if f == "living_area_m2":
        return f"{v:.0f} m²"
    if isinstance(v, str):
        return NAMES.get(v, v).replace("_", " ")
    return str(v)


def form_changed(f: str):
    ss = st.session_state
    v = ss.get(f"pf_{f}")
    if v is None or v == DK:                    # "Don't know" = not answered
        ss.form.pop(f, None)
    else:
        ss.form[f] = v
    ss.confirmed.pop(f, None)                   # a new form answer beats an older conflict answer for that field
    ss.setdefault("conflict_dk", set()).discard(f)
    if f == "fuel_type":                        # yearly use is kWh or litres by fuel: drop the one in the wrong unit
        drop = "annual_fuel_kwh" if v == "oil" else "annual_fuel_liters"
        ss.form.pop(drop, None)
        ss.pop(f"pf_{drop}", None)


def form_fill_example():
    pick_example("weber")


def _clear_inputs():
    """Forget every answer, read and attachment (page-1 'Start empty' and before a new example)."""
    ss = st.session_state
    ss.form, ss.reads, ss.confirmed, ss.readers = {}, {}, {}, {}
    for k in list(ss.keys()):
        if k.startswith(("tag_", "q_")) or k in ("read_fail", "text_unused", "example_reads", "conflict_dk", "use_note"):
            del ss[k]
    for f, *_ in FORM:
        ss[f"pf_{f}"] = None if f in NUM_FIELDS else DK
    ss.house_text_val = ss.house_text_in = ""
    ss.rad_example = "–"
    ss.example = None


def pick_example(key: str | None):
    """Card click (callback): fill page 1, queue the card's photo and bill reads (run in the script body, so the read
    path and its spinner are exactly the upload's) and pre-fill the page-4 text. key None = 'Start empty'."""
    ss = st.session_state
    _clear_inputs()
    ex = EXAMPLES.get(key or "")
    if ex is None:
        return
    ss.form = dict(ex["form"])
    for f, *_ in FORM:
        ss[f"pf_{f}"] = ss.form.get(f, None if f in NUM_FIELDS else DK)
    if ex.get("text"):
        try:
            ss.house_text_val = ss.house_text_in = (ROOT / ex["text"]).read_text(encoding="utf-8").strip()
        except OSError:
            pass
    ss.example = key
    ss.example_reads = key


def run_example_reads():
    """The reads a card queued: the radiator photo and the bill, as if the owner had uploaded them."""
    ss = st.session_state
    ex = EXAMPLES.get(ss.pop("example_reads", None) or "")
    if ex is None:
        return
    if ex.get("photo"):
        ss["tag_radiator_ex"] = ss["rad_example"] = ex["photo"]
        try:
            do_read("radiator", (ROOT / "data/pipe_photos" / ex["photo"]).read_bytes(), "image/jpeg", "radiator")
        except OSError as e:
            ss.setdefault("read_fail", {})["radiator"] = str(e)
    if ex.get("bill"):
        ss["tag_doc_demo"] = ex["bill"]
        try:
            do_read("doc", (ROOT / ex["bill"]).read_bytes(), "image/jpeg", "bill")
        except OSError as e:
            ss.setdefault("read_fail", {})["doc"] = str(e)


def example_gallery():
    """Page 1: 'Try an example house' cards; the chosen one shows as selected, 'Start empty' clears everything."""
    ss = st.session_state
    st.markdown("**Try an example house**")
    cols = st.columns(len(EXAMPLES))
    for col, (key, ex) in zip(cols, EXAMPLES.items()):
        sel = ss.get("example") == key
        with col.container(border=True, key=f"excard_{key}"):
            html('<div style="display:flex;justify-content:space-between;align-items:center;gap:6px">'
                 '<span class="pill">Example</span>'
                 + ('<span class="ok">✓ Selected</span>' if sel else "") + '</div>'
                 f'<div style="font-weight:700;font-size:15px;margin:8px 0 2px;min-height:40px">{esc(ex["name"])}</div>'
                 f'<div class="muted" style="font-size:13px;min-height:36px">{esc(ex["place"])} · {esc(ex["year"])}</div>'
                 f'<div style="font-size:13px;margin-top:6px;min-height:58px">{esc(ex["line"])}</div>')
            st.button("Selected" if sel else "Use this house", key=f"exbtn_{key}", on_click=pick_example, args=(key,),
                      type="primary" if sel else "secondary", width="stretch")
    c1, c2 = st.columns([1, 3])
    c1.button("Start empty", key="exbtn_empty", on_click=pick_example, args=(None,), width="stretch")
    c2.caption("Example houses are made up (names invented, no real addresses). A card fills the form and attaches "
               "its radiator photo and bill, so you can just press Next.")


def form_house() -> House | None:
    """Page-1 answers → House (source FORM_MERGE_SRC, confidence 0.9). None when nothing is filled.
    Integers are typed exactly (empty = don't know); categories come from dropdowns."""
    fm = st.session_state.get("form") or {}
    vals, ev = {}, {}
    for f in INT_FIELDS:
        if fm.get(f) is not None:
            vals[f] = int(fm[f])
    for f in FLOAT_FIELDS:
        if fm.get(f) is not None:
            vals[f] = float(fm[f])
    for f in ("building_type", "renovation", "heat_distribution", "fuel_type", "radiator_size"):
        if fm.get(f) not in (None, DK):
            vals[f] = fm[f]
    if fm.get("dhw_by_boiler") in ("yes", "no"):
        vals["dhw_by_boiler"] = fm["dhw_by_boiler"] == "yes"
    if fm.get("fuel_type") == "oil":            # stale kWh answer from before the fuel switch
        vals.pop("annual_fuel_kwh", None)
    elif "annual_fuel_liters" in vals:
        vals.pop("annual_fuel_liters")
    if not vals:
        return None
    h = House(**vals)
    h.source = {f: FORM_MERGE_SRC for f in vals}
    h.confidence = {f: 0.9 for f in vals}
    h.evidence = ev
    return h


def form_page(h: House):
    ss = st.session_state
    st.markdown("## Your house")
    html('<p style="font-size:16px;margin:0 0 4px">If you don\'t know everything, it\'s okay.</p>'
         '<p class="muted" style="margin:0 0 12px">Fill in what you know and leave the rest empty. '
         '<b>*</b> marks what matters most for the answer.</p>')
    example_gallery()
    rows = sorted(form_rows(ss.form.get("fuel_type")), key=lambda r: FORM_GROUPS.index(GROUP_OF[r[0]]))
    group = None
    for f, label, opts, _ in rows:
        if GROUP_OF[f] != group:                 # small section header: the building · heating · radiators · people
            group = GROUP_OF[f]
            html(f'<div style="font-size:13px;font-weight:600;color:#4A5565;text-transform:uppercase;'
                 f'letter-spacing:.04em;margin:18px 0 4px">{esc(group)}</div>')
        key = f"pf_{f}"
        num = isinstance(opts, tuple)
        if key not in ss:                        # seed once from the stored answers (widget state is dropped off-page)
            ss[key] = ss.form.get(f, None if num else DK)
        c1, c2, c3 = st.columns([2, 3, 1.3])
        c1.markdown(f"{label} **\\***" if f in IMPORTANT else label)
        if num:
            _, lo, hi, step, unit = opts
            c2.number_input(label, min_value=lo, max_value=hi, step=step, value=None, key=key,
                            placeholder=f"Don't know{' · ' + unit if unit else ''}", on_change=form_changed,
                            args=(f,), label_visibility="collapsed")
        else:
            c2.selectbox(label, [DK] + opts, key=key, on_change=form_changed, args=(f,),
                         label_visibility="collapsed", format_func=lambda v, x=f: form_text(x, v))
        src, v = h.source.get(f), getattr(h, f)
        if f in needs_answer(h):
            tag = "⚠ asked on page 4"
        elif v is None or src == FORM_MERGE_SRC:
            tag = ""                             # nothing to say: an empty pill looked like a button
        else:                                    # filled (or overruled) by the bill, photo, text or a conflict answer
            tag = f"{src_label(src)} · {value_text(h, f)}"
        if tag:
            html(f'<span class="src">{esc(tag)}</span>', c3)


def home_house() -> House:
    """Free text first (lowest), then the form over it, then photo and bill reads, then conflict answers."""
    ss = st.session_state
    pieces = [House.model_validate_json(ss.reads[s]) for s in ("text",) if ss.reads.get(s)]
    fh = form_house()
    pieces += [fh] if fh else []
    pieces += [House.model_validate_json(j) for s, j in ss.reads.items() if s != "text"]
    h = reduce(X.merge, pieces, House(building_id="Homeowner"))
    if ss.confirmed:
        conf = House(building_id="Homeowner", **ss.confirmed)
        conf.source = {f: "confirmed" for f in ss.confirmed}
        conf.confidence = {f: 0.9 for f in ss.confirmed}
        h = X.merge(h, conf)
    band = (fh.evidence.get("build_year", "")[5:] if fh else "")
    if band:                                     # an exact year inside the form's band is not a disagreement
        h.conflicts = [c for c in h.conflicts if c["field"] != "build_year"
                       or any(year_band(v) != band for v in c["values"].values())]
    # The page-4 text only fills blanks and never asks: its disagreements leave House.conflicts (no question, no
    # contradiction) and become the muted "Not used (already set)" note under its chips.
    unused = []
    for c in h.conflicts:
        vals = c.get("values") or {}
        if TEXT_MERGE_SRC in vals and c.get("used") != TEXT_MERGE_SRC:
            other = next(((s, v) for s, v in vals.items() if s != TEXT_MERGE_SRC), None)
            if other:
                f = c["field"]
                unused.append(f"{human_field(f).lower()} {value_text(h, f, vals[TEXT_MERGE_SRC], TEXT_MERGE_SRC)} "
                              f"({src_label(other[0])} says {value_text(h, f, other[1], other[0])})")
    h.conflicts = [c for c in h.conflicts if TEXT_MERGE_SRC not in (c.get("values") or {})]
    ss["text_unused"] = unused
    # Litres are an oil unit: once the fuel is settled as something else, a litres answer is not that fuel's use.
    ss["use_note"] = ""
    if ("fuel_type" not in needs_answer(h) and h.fuel_type not in (None, "oil")
            and h.annual_fuel_liters is not None):
        note = (f"The {h.annual_fuel_liters:,.0f} litres from the form are not used: litres are for oil, "
                f"your heating is {FUEL_WORD.get(h.fuel_type, h.fuel_type)}.")
        if h.kwh_printed is not None:
            note += f" Your bill's {h.kwh_printed:,.0f} kWh is used."
        ss["use_note"] = note
        h.annual_fuel_liters = None
        h.source.pop("annual_fuel_liters", None)
    return h


USE_FIELDS = ("fuel_type", "annual_fuel_kwh", "annual_fuel_liters")   # one question settles all three


def open_conflicts(h: House) -> list[dict]:
    """Conflicts the owner has not answered yet (an answer or "don't know" closes one)."""
    ss = st.session_state
    done = set(ss.get("confirmed") or {}) | set(ss.get("conflict_dk") or ())
    return [c for c in h.conflicts if c["field"] not in done]


def needs_answer(h: House) -> set[str]:
    """Fields the screens must not show a value for yet: open conflicts (fuel and yearly use go together)."""
    out = set()
    for c in open_conflicts(h):
        out |= set(USE_FIELDS) if c["field"] in USE_FIELDS else {c["field"]}
    return out


# How an input was read (muted line under "We read"). Fallbacks never call the LLM by themselves (Invariant 1).
READER = {"module": "Read by the module", "cache": "Read from the demo cache",
          "llm": "Read by the AI fallback (HP_LLM_FALLBACK=1)", "failed": "Couldn't read"}


EVIDENCE_NAMES = {"kwh_printed": "Use on the bill", "m3": "Gas volume", "zustandszahl": "Zustandszahl",
                  "brennwert": "Brennwert", "period_start": "Billing period", "period_end": "Billing period",
                  "bill_carrier": "Bill type", "bill_total_eur": "Bill total", "monthly_advance_eur": "Monthly payment",
                  "liters": "Litres on the bill", "certificate_kwh_m2a": "Energy certificate"}


def do_read(slot: str, data: bytes, mime: str, mission: str):
    """Radiator photo → pipe_classifier, bill → bill_recognizer (orchestrator.py; fallback = demo cache only).
    The optional free text goes to the LLM parser (extract.py, cached), only when the owner presses "Read it"."""
    ss = st.session_state
    ss.setdefault("readers", {})
    with st.spinner("Reading…"):
        try:
            if mission == "radiator":
                h, how = O.classify_pipes(data, mime, (ss.get("form") or {}).get("build_year"))
            elif mission in ("bill", "listing"):
                h, how = O.recognize_bill(data, mime, (ss.get("form") or {}).get("fuel_type"))
            else:
                h, how = X.extract(data, mime, mission), "python"
        except Exception as e:                  # orchestrator never raises; belt and braces
            h, how = None, f"{type(e).__name__}: {e}"
        if h is None:                           # drop an older read of this slot: it isn't this file
            ss.reads.pop(slot, None)
            ss.readers[slot] = "failed"
            ss.setdefault("read_fail", {})[slot] = how
            return
        if mission == "house_text":              # below the form, bill and photo: the text only fills gaps
            h.source = {f: TEXT_MERGE_SRC for f in h.source}
        ss.reads[slot], ss.readers[slot] = h.model_dump_json(), how


def read_upload(up, slot: str, mission: str):
    if up is None:
        return
    tag = f"{up.name}:{up.size}"
    if st.session_state.get(f"tag_{slot}_up") != tag:
        st.session_state[f"tag_{slot}_up"] = tag      # before the read, so a failing read isn't retried
        st.session_state.pop(f"tag_{slot}_demo", None)   # an own upload replaces an attached example bill
        do_read(slot, up.getvalue(), up.type or "image/jpeg", mission)


def conflict_picked(f: str, vals: list):
    ss = st.session_state
    i = ss.get(f"q_{f}")
    if i is None:
        return
    if i >= len(vals):                          # "don't know" closes the question; the merge's pick stays
        ss.setdefault("conflict_dk", set()).add(f)
        return
    ss.confirmed[f] = vals[i]


def conflict_reset(f: str):
    """'Change' next to an answered conflict: ask it again."""
    ss = st.session_state
    ss.confirmed.pop(f, None)
    ss.setdefault("conflict_dk", set()).discard(f)
    ss.pop(f"q_{f}", None)


def show_read(slot: str):
    ss = st.session_state
    how = (ss.get("readers") or {}).get(slot)
    j = ss.reads.get(slot)
    if not j:
        if how == "failed":
            st.warning("We couldn't read that. You can skip this step.")
            st.caption(f"{READER['failed']} · {(ss.get('read_fail') or {}).get(slot, '')}")
        return
    h = House.model_validate_json(j)
    found = chips(h)
    if found:
        html('<p class="ok">✓ We read</p>' + found)
    if slot == "text" and ss.get("text_unused"):
        html('<p style="font-size:12px;color:var(--muted);margin:4px 0 0">Not used (already set): '
             + esc("; ".join(ss.text_unused)) + "</p>")
    # Which reader ran (module / demo cache / AI fallback) is internal: not shown to the homeowner (UI review).
    if h.evidence:
        with st.expander("Why?"):
            shown = set()
            for f, q in h.evidence.items():
                lab = EVIDENCE_NAMES.get(f) or human_field(f)
                if (lab, q) in shown or not lab:
                    continue
                shown.add((lab, q))
                st.caption(f"{lab}: {q}")
    if h.retake_tip or h.missing:
        (st.info if found else st.warning)(h.retake_tip or "Some of it was unreadable. One more photo?")


def nav(step: int, can_skip: bool, blocked: bool = False) -> str | None:
    """blocked: forward is disabled (page 4 with an unanswered conflict question)."""
    c1, c2, c3 = st.columns(3)
    act = None
    if step > 1 and c1.button("Back", key=f"back{step}", width="stretch"):
        act = "back"
    if can_skip and c2.button("Skip", key=f"skip{step}", width="stretch", disabled=blocked):
        act = "next"
    if c3.button("Show my answer" if step == 4 else "Next", key=f"next{step}", type="primary", width="stretch",
                 disabled=blocked):
        act = "next"
    if blocked:
        st.caption("Answer the question above first, then we show your answer.")
    return act


def text_changed():
    st.session_state.house_text_val = st.session_state.get("house_text_in", "")


def use_example_text():
    ss = st.session_state
    ss.house_text_val = ss.house_text_in = (ROOT / "assets/demo/house_persona_en.txt").read_text(encoding="utf-8").strip()


def _use_of(src: str) -> str:
    """'2,000 litres a year' / '18,002 kWh a year': the yearly use that came with this source ('' if none)."""
    ss = st.session_state
    if src == FORM_MERGE_SRC:
        fm = ss.get("form") or {}
        if fm.get("annual_fuel_liters") is not None:
            return f"{float(fm['annual_fuel_liters']):,.0f} litres a year"
        if fm.get("annual_fuel_kwh") is not None:
            return f"{float(fm['annual_fuel_kwh']):,.0f} kWh a year"
        return ""
    for j in (ss.get("reads") or {}).values():
        try:
            d = House.model_validate_json(j)
        except Exception:
            continue
        if d.source.get("fuel_type") != src:
            continue
        for f, unit in (("kwh_printed", "kWh"), ("annual_fuel_kwh", "kWh"), ("liters", "litres"), ("m3", "m³")):
            v = getattr(d, f, None)
            if v is not None:
                return f"{v:,.0f} {unit} a year"
    return ""


def conflict_questions(h: House) -> int:
    """Every input conflict (form vs bill/photo), asked before the calculation; answered ones collapse to one line
    with 'Change'. The page-4 text never asks: home_house already dropped its disagreements. Returns how many are
    still open (the answer button stays disabled until 0)."""
    ss, open_n = st.session_state, 0
    dk = ss.setdefault("conflict_dk", set())
    for c in h.conflicts:
        f = c["field"]
        if f in ss.confirmed or f in dk:
            ans = value_text(h, f, ss.confirmed[f], "confirmed") if f in ss.confirmed else \
                f"don't know (we use {value_text(h, f)})"
            c1, c2 = st.columns([4, 1], vertical_alignment="center")
            c1.markdown(f"✓ {human_field(f)}: **{ans}**")
            c2.button("Change", key=f"chg_{f}", on_click=conflict_reset, args=(f,), width="stretch")
            continue
        (sa, va), (sb, vb) = list(c["values"].items())[:2]
        ta, tb = value_text(h, f, va, sa), value_text(h, f, vb, sb)
        if f == "fuel_type":                     # show the unit mismatch with the fuel (litres vs kWh)
            ua, ub = _use_of(sa), _use_of(sb)
            q = (f"Your {src_label(sa)} says **{ta}**{f' ({ua})' if ua else ''}, your {src_label(sb)} says "
                 f"**{tb}**{f' ({ub})' if ub else ''}. Which heating do you have?")
        else:
            q = f"Your {src_label(sa)} says **{ta}**, your {src_label(sb)} says **{tb}**. Which one is it?"
        labels = [ta, tb, "don't know"]
        st.radio(q, [0, 1, 2], format_func=lambda i, lb=labels: lb[i], index=None, key=f"q_{f}",
                 on_change=conflict_picked, args=(f, [va, vb]), horizontal=True)
        open_n += 1
    return open_n


def go_radiator_photo():
    st.session_state.step = 2


def text_page(h: House) -> int:
    """Page 4: the conflict questions (prominent), the engine's next question, the optional free text.
    Returns how many conflict questions are still open."""
    ss = st.session_state
    st.markdown("## Before your answer")
    open_n = 0
    if h.conflicts:
        with st.container(border=True, key="conflictbox"):
            n = len(h.conflicts)
            st.markdown(f"**{'One thing doesn' if n == 1 else f'{n} things don'}'t match.** "
                        "Pick the right one, or \"don't know\".")
            open_n = conflict_questions(h)
            if ss.get("use_note"):
                st.caption(ss.use_note)
    try:
        q = _eng_attr("next_question")(h) if _eng_attr("next_question") else None
    except Exception:
        q = None
    if q and not open_n:
        st.info(q)
        if "radiator" in q.lower() and "photo" in q.lower():   # the question asks for a photo: offer the way there
            st.button("Go to the radiator photo", on_click=go_radiator_photo, key="go_rad")
    elif not h.conflicts:
        html('<p class="ok">✓ No questions for you</p>')
    st.markdown("#### Anything else? (optional)")
    st.caption("Tell us anything the form missed — we only read it, "
               "the numbers come from the form and your bill.")
    st.button("Use the example text", on_click=use_example_text)
    if "house_text_in" not in ss:
        ss.house_text_in = ss.get("house_text_val", "")
    txt = st.text_area("Anything else", key="house_text_in", on_change=text_changed, height=130,
                       label_visibility="collapsed", placeholder="e.g. new windows in 2015, a wood stove in winter…")
    if st.button("Read it", disabled=not txt.strip()):
        data = txt.strip().encode("utf-8")
        tag = hashlib.sha256(data).hexdigest()[:16]
        if ss.get("tag_text") != tag:            # never read the same text twice
            ss["tag_text"] = tag
            do_read("text", data, "text/plain", "house_text")
            st.rerun()
    show_read("text")
    return open_n


@st.cache_data(show_spinner=False)
def bill_example_png() -> bytes | None:
    """The demo bill photo straightened and cropped to its upper half (a clean 'like this' thumbnail, no grey table).
    The photo is the page rotated −3.5° (assets/demo/make_demo_assets.py); None → show the photo as is."""
    try:
        import io

        from PIL import Image, ImageOps
        im = Image.open(ROOT / DEMO_BILL).convert("RGB")
        cx, cy = im.width * 391 / 750, im.height * 501.5 / 1007
        sx, sy = im.width / 750, im.height / 1007
        im = im.rotate(3.5, center=(cx, cy), resample=Image.BICUBIC, fillcolor="white")
        im = im.crop((int(cx - 300 * sx), int(cy - 386 * sy), int(cx + 300 * sx), int(cy + 35 * sy)))
        im = ImageOps.autocontrast(im, cutoff=(0, 8)).point(lambda v: 255 if v > 215 else v)
        im = ImageOps.expand(im, border=14, fill="white")
        buf = io.BytesIO()
        im.save(buf, format="PNG")
        return buf.getvalue()
    except Exception:
        return None


STEPS = ["Your house", "Radiator", "Bill", "Check & answer"]


def progress_html(step: int) -> str:
    """4 bars with the step names under them; the current step bold."""
    cells = "".join(
        f'<div class="step{" on" if i <= step else ""}{" cur" if i == step else ""}"><div class="bar"></div>'
        f'<span>{i}. {esc(name)}</span></div>' for i, name in enumerate(STEPS, 1))
    return f'<div class="steps" role="list" aria-label="Step {step} of 4: {esc(STEPS[step - 1])}">{cells}</div>'


def tab_homeowner():
    ss = st.session_state
    ss.setdefault("step", 1)
    ss.setdefault("reads", {})
    ss.setdefault("confirmed", {})
    ss.setdefault("form", {})
    ss.setdefault("readers", {})
    run_example_reads()                               # a card click queued its photo and bill
    h = home_house()
    left, right = st.columns([3, 2])
    with left:
        if ss.step <= 4:
            html(progress_html(ss.step))
        act = None
        if ss.step == 1:
            form_page(h)
            act = nav(1, False)
        elif ss.step == 2:
            st.markdown("## Your biggest radiator")
            st.caption("From the side, pipes in view.")
            up_col, ex_col = st.columns([3, 2])
            with ex_col:                                 # what a usable photo looks like
                st.image(str(ROOT / "data/pipe_photos/05_zweirohr-vermutet_kompakt.jpeg"), width=200)
                st.caption("Like this: the whole radiator from the side, the valve and both pipes in view.")
            with up_col:
                read_upload(st.file_uploader("Radiator photo", type=["jpg", "jpeg", "png", "webp"], key="up_rad",
                                             label_visibility="collapsed"), "radiator", "radiator")
            photos = sorted(p.name for p in (ROOT / "data/pipe_photos").glob("*.jp*g"))
            if ss.get("rad_example") not in ["–"] + photos:   # seed once (widget state is dropped off-page)
                ss["rad_example"] = ss.get("tag_radiator_ex") if ss.get("tag_radiator_ex") in photos else "–"
            pick = st.selectbox("or use an example photo", ["–"] + photos, key="rad_example")
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
            up_col, ex_col = st.columns([3, 2])
            with ex_col:                                 # what a usable bill looks like (shown once, straightened)
                ex_img = bill_example_png()
                st.image(ex_img if ex_img else str(ROOT / DEMO_BILL), width=220)
                st.caption("Like this: the page with your yearly use in kWh or m³. You can cover your name and address.")
                if ss.get("tag_doc_demo") and ss.reads.get("doc"):
                    html('<p class="ok">✓ Attached: the demo bill</p>')
            with up_col:
                read_upload(st.file_uploader("Bill or listing", type=["jpg", "jpeg", "png", "webp", "pdf"],
                                             key="up_doc", label_visibility="collapsed"), "doc", "bill")
                if st.button("Use the demo bill photo"):
                    ss["tag_doc_demo"] = DEMO_BILL
                    do_read("doc", (ROOT / DEMO_BILL).read_bytes(), "image/jpeg", "bill")
            show_read("doc")
            st.caption("Only the numbers are kept.")
            act = nav(3, True)
        elif ss.step == 4:
            open_n = text_page(home_house())         # a read in this run happened after the first merge
            act = nav(4, True, blocked=open_n > 0)
        else:
            if open_conflicts(h):                    # never compute over an unanswered conflict
                ss.step = 4
                st.rerun()
            if st.button("Change answers"):
                ss.step = 1
                st.rerun()
            r = evaluate(h)
            answer_card(h, r, "home")
            if r is not None and ss.get("ask_home"):
                request_panel(h, r, "home")
        if act == "next":
            ss.step += 1
            st.rerun()
        if act == "back":
            ss.step -= 1
            st.rerun()
    with right:
        h = home_house()                              # reads in this run happened after the first merge
        seen, out = set(), []
        rows = [(f, lb) for f, lb, *_ in FORM] + [("pipe_system", "Pipes"), ("kwh_printed", "Use on the bill")]
        ask = needs_answer(h)
        for f, label in rows:
            v = getattr(h, f)
            if v is None or label in seen:
                continue
            seen.add(label)
            if f in ask:                             # unresolved conflict: no silent winner
                out.append(f'<div class="know-row"><span>{esc(label)}: <span class="need">⚠ Needs your answer</span>'
                           '</span></div>')
                continue
            out.append(f'<div class="know-row"><span>{esc(label)}: <b>{esc(value_text(h, f))}</b></span>'
                       f'<span class="src">{esc(src_label(h.source.get(f)))}</span></div>')
        if not out:
            out.append('<div class="know-row" style="color:var(--muted)">Nothing yet.</div>')
        note = (f'<div class="know-note">{esc(ss.use_note)}</div>' if ss.get("use_note") else "")
        html('<div class="know"><div style="font-weight:700;font-size:16px;margin-bottom:6px">What we know so far</div>'
             + "".join(out) + note + '</div>')


def request_subject(r: Result) -> str:
    return f"Heat pump: {VISIT.get(r.visit_type, 'quote request')}"


def mailto(subject: str, body: str, to: str = "") -> str:
    return f"mailto:{urllib.parse.quote(to)}?" + urllib.parse.urlencode({"subject": subject, "body": body},
                                                                        quote_via=urllib.parse.quote)


def request_panel(h: House, r: Result, key: str):
    """Homeowner contact form (last step of the Homeowner flow). Stores what was entered for the Installer footer."""
    st.subheader("Your request is ready", anchor="request")    # plain heading; the answer card links here
    st.caption("Just add how to reach you.")
    name = st.text_input("Name", key=f"name_{key}")
    contact = st.text_input("E-mail or phone", key=f"contact_{key}")
    plz = st.text_input("Postcode", key=f"plz_{key}")
    if name.strip() or contact.strip() or plz.strip():
        prev = st.session_state.get("request_sent") or {}
        st.session_state["request_sent"] = {"name": name.strip(), "contact": contact.strip(), "postcode": plz.strip(),
                                            "date": prev.get("date") or date.today().strftime("%d %b %Y").lstrip("0")}
    pdf = None
    if _eng_attr("handover_pdf"):
        try:
            pdf = _eng_attr("handover_pdf")(h, r, {"name": name, "contact": contact, "postcode": plz})
        except Exception as e:
            st.caption(f"PDF not available: {e}")
    if pdf:
        st.download_button("PDF for the installer", pdf, file_name="pre-visit-sheet.pdf", mime="application/pdf",
                           type="primary", width="stretch", key=f"pdf_{key}")
    body = (f"Hello,\n\nplease find my pre-visit sheet attached (HP-Ready first estimate: {r.best_color}, "
            f"{about_t(qr(r, 'flow_temp_c').p50)}).\n\n{name}\n{contact}\n{plz}")
    st.link_button("Open as e-mail", mailto(request_subject(r), body), type="primary", width="stretch")
    st.caption("One page any installer reads in a minute. Nothing is stored.")

# ---------------------------------------------------------------- installer


STANDARD_CHECKS = ["Room-by-room heat load (DIN EN 12831)", "Electrical capacity, meter cabinet",
                   "Hydraulics and balancing", "Outdoor unit: position, sound distance, permits"]
_NUM = r"(\d+(?:\.\d+)?)"


def flow_big(v: float | None) -> str:
    return "–" if v is None else (HOT if v > 70 else f"≈ {v:.0f} °C")


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
    parts = [human_enum(h.building_type) if h.building_type else None, _band_text(h, str(h.build_year)) if h.build_year else None,
             f"{h.living_area_m2:.0f} m²" if h.living_area_m2 else None, fuel, rad]
    return " · ".join(p for p in parts if p)


def radiator_share(h: House, r: Result | None = None) -> str:
    """Mixed systems: share of the load on the radiator circuit. r.radiators.share first, else radiators / rooms."""
    rad = r.radiators if r is not None else None
    if rad is not None and rad.share is not None:
        if rad.share >= 1:
            return ""
        n = rad.count or h.radiator_count
        how = f" ({n} radiators / {h.rooms} rooms)" if n and h.rooms else ""
        return f" — the radiator circuit carries {rad.share:.0%} of the load{how}".replace("%", " %")
    if h.heat_distribution != "mixed" or not h.radiator_count or not h.rooms:
        return ""
    share = min(h.radiator_count / h.rooms, 1.0)
    return (f" — the radiator circuit carries {share:.0%} of the load ({h.radiator_count} radiators / "
            f"{h.rooms} rooms)").replace("%", " %")


def no_change_text(h: House, r: Result, have: float, need: float, margin_pct: float | None = None) -> str:
    """'Radiators are rated X kW (at 75 °C); 55 °C needs …' + share phrase + tight-margin phrase."""
    body = (f"Radiators are rated {have:.1f} kW (at 75 °C); 55 °C needs a rating of about {need:.1f} kW"
            f"{radiator_share(h, r)}.")
    if margin_pct is None and need:
        margin_pct = (have - need) / need * 100
    if margin_pct is not None and margin_pct < 5:
        body += f" Tight margin ({margin_pct:.0f} %), so the real radiator sizes decide it."
    return body


def option_block(o, letter: str, rad) -> tuple[str, str] | None:
    """One structured Option -> (title, body). Numbers from the engine, wording here."""
    if o.kind == "radiators" and o.add_rated_kw_55 is not None:
        a60 = o.add_rated_kw_60
        tail = ("" if a60 is None else " 60 °C already works with today's radiators." if a60 <= 0
                else f" About {a60:.1f} kW for 60 °C.")
        now = o.rated_kw_today if o.rated_kw_today is not None else (rad.rated_kw if rad is not None else None)
        today = f" Today: {now:.1f} kW." if now is not None else ""
        return (f"Option {letter} · more radiator surface",
                f"Add about {o.add_rated_kw_55:.1f} kW of rated radiator output for 55 °C.{tail}{today}")
    if o.kind == "insulation" and o.loss_cut_pct is not None:
        return (f"Option {letter} · cut heat loss",
                f"About −{o.loss_cut_pct:.0f} % heat loss (insulation or windows) reaches 55 °C with today's radiators.")
    if o.kind == "pipe_loop":
        return ("Single-pipe loop", clean_text(o.note) or "Larger radiators at the end of the loop, a higher flow "
                "temperature, or converting parts of the system.")
    return None


def what_it_takes_structured(h: House, r: Result) -> list[tuple[str, str]] | None:
    """(title, body) blocks from r.options / r.radiators; None when the engine did not fill them."""
    if not (r.options or r.radiators):
        return None
    rad = r.radiators
    no_change = None
    if (rad is not None and rad.rated_kw is not None and rad.needed_rated_kw_55 is not None
            and rad.rated_kw >= rad.needed_rated_kw_55):
        no_change = ("No radiator changes for 55 °C",
                     no_change_text(h, r, rad.rated_kw, rad.needed_rated_kw_55, rad.margin_pct))
    if r.best_color == "green" and no_change:
        return [no_change]
    out, letters = [], iter("ABCDEFG")
    for o in r.options:
        b = option_block(o, next(letters) if o.kind in ("radiators", "insulation") else "", rad)
        if b:
            out.append(b)
    if not out:
        if no_change:
            return [no_change]
        note = next((clean_text(o.note) for o in r.options if o.note), "")
        if h.heat_distribution == "underfloor":
            return [("Nothing to change", note or "Underfloor heating already runs at about 35–40 °C.")]
        return [("Nothing to change", note)] if note else None
    return ([no_change] if no_change else []) + out


def what_it_takes(h: House, r: Result) -> list[tuple[str, str]]:
    """Structured r.options / r.radiators first; else (title, body) blocks parsed from r.path_to_yellow."""
    structured = what_it_takes_structured(h, r)
    if structured is not None:
        return structured
    out, letters = [], iter("ABCDEFG")
    for line in r.path_to_yellow or []:
        s = clean_text(line)
        m = re.search(rf"give {_NUM} kW, about {_NUM} kW is needed", s)
        if s.lower().startswith("no change needed") and m:
            have, need = float(m.group(1)), float(m.group(2))
            out.append(("No radiator changes for 55 °C", no_change_text(h, r, have, need)))
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
        rad = r.radiators
        if rad is not None and rad.size_assumed:
            cap = f"Radiator sizes unknown — assumed {rad.size_assumed}."
        else:
            cap = "Radiator sizes unknown — assumed medium." if h.radiator_size is None else ""
    return rows, cap


def installer_summary(h: House, r: Result) -> str:
    fl = qr(r, 'flow_temp_c').p50
    if h.heat_distribution == "underfloor":
        first = "Underfloor heating runs at about 35–40 °C, ideal for a heat pump."
    elif fl is None:
        first = "Flow temperature can't be estimated from the data yet."
    elif fl > 70:
        first = f"Needs {HOT} flow on the coldest day — well above the ~60 °C a heat pump handles efficiently."
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
        line = f"{kw(qr(r, 'heat_load_kw').p50)} · {flow_big(qr(r, 'flow_temp_c').p50)} · score {r.lead_score or 0:.2f}"
    return (f'<div class="lead-card{" sel" if selected else ""}">'
            f'<span style="display:flex;justify-content:space-between;align-items:center;gap:8px">'
            f'<b style="font-size:15px">{esc(bid)}{tracer_chip(bid)}</b>{right}</span>'
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
    load, bill = qr(r, 'heat_load_kw').p50, qr(r, 'heat_load_bill_kw').p50
    load_sub = (f"reference {ref['heating_load_kw']:.1f} kW" if ref and ref.get("heating_load_kw") is not None
                else "no bill" if bill is None else f"bill says {bill:.1f} kW")
    fl = qr(r, 'flow_temp_c')
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
                   f'{pill(r.best_color, visit_pill_text(r), filled=True, size="13px")}{tracer_chip(bid)}</div>'
                   f'<div style="font-size:16px;color:#3A4A66">{esc(installer_meta(h))}</div>'
                   + model_line(r, "installer brief from baseline" if brief_from_baseline(bid) else "") + '</div>')
        with top_r.container(horizontal=True, horizontal_alignment="right", key=f"inst_actions_{_lead_key(bid)}"):
            pdf = None
            if _eng_attr("handover_pdf"):
                try:
                    pdf = _eng_attr("handover_pdf")(h, r, {})
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
            body = (f"{greet}\n\nthank you for your request. HP-Ready first estimate: {r.best_color}, "
                    f"{about_t(qr(r, 'flow_temp_c').p50)} on the coldest day ({VISIT.get(r.visit_type, '').lower()}).\n\n"
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
                for i, lab in enumerate(r.always_checks or STANDARD_CHECKS):
                    st.checkbox(lab, key=f"chk_{_lead_key(bid)}_{i}")
        st.html(sent_card(bid, h))


def _build_id() -> str:
    """Short commit of the running code, read from .git without calling git (works on Streamlit Cloud)."""
    try:
        head = (ROOT / ".git" / "HEAD").read_text(encoding="utf-8").strip()
        if head.startswith("ref: "):
            ref = head[5:]
            p = ROOT / ".git" / ref
            if p.exists():
                return p.read_text(encoding="utf-8").strip()[:7]
            packed = (ROOT / ".git" / "packed-refs").read_text(encoding="utf-8")
            return next((ln.split()[0][:7] for ln in packed.splitlines() if ln.endswith(" " + ref)), "?")
        return head[:7]
    except Exception:
        return "?"


top_l, top_r = st.columns([4, 1])
top_l.markdown("### HP-Ready")
X.DEMO_ONLY = top_r.toggle("Demo mode", help="Use cached reads only, no live AI calls.")
if show_installer():                          # HP_SHOW_INSTALLER=1: the Installer tab (out of the MVP) comes back
    t_home, t_eval, t_inst = st.tabs(["Homeowner", "Evaluation", "Installer"])
else:
    (t_home, t_eval), t_inst = st.tabs(["Homeowner", "Evaluation"]), None
with t_home:
    tab_homeowner()
with t_eval:
    tab_evaluation()
    st.caption(f"build {_build_id()}")      # developer info: Evaluation footer only, never on the Homeowner tab
if t_inst is not None:
    with t_inst:
        tab_installer()
