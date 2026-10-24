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
.stApp, .stApp * {font-family:'Inter',system-ui,sans-serif;}
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


def t_range(rg):
    return "–" if rg.p50 is None else f"{t(rg.p50)} ({t(rg.p10)}–{t(rg.p90)})"


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

# ---------------------------------------------------------------- shared blocks


def rechenweg(r: Result):
    b = r.heat_load_bill_kw
    st.markdown(f"Heating load (size, age): **{kw(r.heat_load_kw.p50)}** ({kw(r.heat_load_kw.p10)}–{kw(r.heat_load_kw.p90)})  \n"
                f"From the bill: {kw(b.p50)} ({kw(b.p10)}–{kw(b.p90)})")
    if r.trace:
        st.dataframe(pd.DataFrame([s.model_dump() for s in r.trace]), hide_index=True, width="stretch")
    for c in r.contradictions:
        st.markdown(f"- **{c.what}** · trusted: {c.trusted}. {c.why}")
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
        st.caption(f"Likely {t(r.required_flow_temp_c.p10)}–{t(r.required_flow_temp_c.p90)}. Lower is cheaper.")
    with st.expander("Running cost" + (f" · save ~{eur(r.saving_eur)}/yr" if r.saving_eur else "")):
        st.markdown(f"Today **{eur(r.cost_now_eur)}** · heat pump **{eur(r.cost_hp_eur)}**")
        if r.cost_note:
            st.caption(r.cost_note)
        st.caption("Challenge prices. Installation and subsidies come with the quote.")
    with st.expander(f"What's still open · {len(r.open_checks)} things"):
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
                st.markdown(f"- {c.what} → trusted **{c.trusted}**: {c.why}")
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
        out.append(f'<span class="chip{" unsure" if unsure else ""}">{fmt.format(v).replace("_", " ")}{"?" if unsure else ""}</span>')
    return "".join(out)


def home_house() -> House:
    ss = st.session_state
    h = reduce(X.merge, [House.model_validate_json(j) for j in ss.reads.values()], House(building_id="Homeowner"))
    conf = House(building_id="Homeowner", **ss.confirmed)
    conf.source = {f: "confirmed" for f in ss.confirmed}
    conf.confidence = {f: 0.9 for f in ss.confirmed}
    return X.merge(h, conf)


def do_read(slot: str, data: bytes, mime: str, mission: str):
    with st.spinner("Reading…"):
        try:
            st.session_state.reads[slot] = X.extract(data, mime, mission).model_dump_json()
        except Exception as e:
            st.warning(f"We couldn't read that ({e}). You can skip this step.")


def read_upload(up, slot: str, mission: str):
    if up is None:
        return
    tag = f"{up.name}:{up.size}"
    if st.session_state.get(f"tag_{slot}") != tag:
        st.session_state[f"tag_{slot}"] = tag
        do_read(slot, up.getvalue(), up.type or "image/jpeg", mission)


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
            if pick != "–" and ss.get("tag_radiator") != pick:
                ss["tag_radiator"] = pick
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
                ss["tag_doc"] = "demo"
                do_read("doc", (ROOT / "assets/demo/bill_demo_gas_2025_photo.jpg").read_bytes(), "image/jpeg", "bill")
            show_read("doc")
            st.caption("Only the numbers are kept.")
            act = nav(3, True)
        elif ss.step == 4:
            st.markdown("## Is this right?")
            st.caption("Tap to fix.")
            for f, label, opts in FIX:
                v = getattr(h, f)
                c1, c2, c3 = st.columns([2, 3, 1])
                c1.markdown(label)
                if opts:
                    choices = ["don't know"] + opts
                    new = c2.selectbox(label, choices, index=choices.index(v) if v in choices else 0,
                                       key=f"fix_{f}", label_visibility="collapsed")
                    new = None if new == "don't know" else new
                else:
                    new = c2.number_input(label, min_value=0, value=int(v or 0), step=1, key=f"fix_{f}",
                                          label_visibility="collapsed", help="0 = don't know")
                    new = None if new == 0 else new
                html(f'<span class="pill">{h.source.get(f, "missing")}</span>', c3)
                if new is not None and new != v:
                    ss.confirmed[f] = new
            asked = 0
            for c in h.conflicts:
                if c["field"] in ss.confirmed or asked >= 2:
                    continue
                (sa, va), (sb, vb) = list(c["values"].items())[:2]
                pick = st.radio(f"Your {sa} says {va}, your {sb} says {vb}. Which one is it?",
                                [va, vb, "don't know"], index=None, key=f"q_{c['field']}")
                if pick not in (None, "don't know"):
                    ss.confirmed[c["field"]] = pick
                asked += 1
            q = engine.next_question(home_house()) if engine is not None and hasattr(engine, "next_question") else None
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
        html('<div class="card"><b>What we know so far</b> <span class="muted">tap to fix</span></div>')
        for f, label, _ in FIX + [("pipe_system", "Pipes", None), ("kwh_printed", "Bill kWh", None)]:
            v = getattr(h, f)
            if v is not None:
                c1, c2 = st.columns([3, 1])
                c1.markdown(f"{label}: **{v}**")
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
