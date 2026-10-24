"""Organiser CSV/JSON → House (+ reference for dev cases).

Numbers by regex, facts from free-text notes by LLM NotesObs (cached in data/notes_cache.json),
keyword fallback with negation only when cache and API are both missing.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tomllib
from pathlib import Path

import pandas as pd

from schema import House, NotesObs

ROOT = Path(__file__).parent
NOTES_CACHE = ROOT / "data" / "notes_cache.json"
MODEL = "claude-sonnet-5-5"

# ---------------------------------------------------------------- LLM plumbing (shared with extract.py)


def _clean_key(v) -> str | None:
    v = str(v or "").strip().strip('"').strip("'").strip()
    return v or None


def api_key_source() -> tuple[str | None, str]:
    """(key, where it was found). Looks in: environment, Streamlit secrets (project or ~/.streamlit), then the
    project's secrets file read leniently (Windows Notepad BOM, a stray .txt ending, KEY=value without quotes)."""
    if _clean_key(os.environ.get("ANTHROPIC_API_KEY")):
        return _clean_key(os.environ["ANTHROPIC_API_KEY"]), "environment variable ANTHROPIC_API_KEY"
    try:
        import streamlit as st
        k = _clean_key(st.secrets.get("ANTHROPIC_API_KEY"))
        if k:
            return k, "Streamlit secrets"
    except Exception:
        pass
    homes = [ROOT / ".streamlit", Path.home() / ".streamlit"]
    for d in homes:
        for name in ("secrets.toml", "secrets.toml.txt"):
            f = d / name
            if not f.exists():
                continue
            txt = f.read_text(encoding="utf-8-sig", errors="replace")
            try:
                k = _clean_key(tomllib.loads(txt).get("ANTHROPIC_API_KEY"))
            except Exception:
                m = re.search(r"ANTHROPIC_API_KEY\s*[=:]\s*(\S+)", txt)
                k = _clean_key(m.group(1)) if m else None
            if k:
                return k, str(f)
    return None, ("no key: put ANTHROPIC_API_KEY = \"sk-ant-...\" in " + str(ROOT / ".streamlit" / "secrets.toml")
                  + " (this file is not in git, every computer needs its own copy)")


def api_key() -> str | None:
    return api_key_source()[0]


def check_key() -> int:
    """python loader.py --check-key: where the key comes from and whether one tiny call works."""
    key, where = api_key_source()
    print("key:", where if key else "NOT FOUND")
    if not key:
        print(where)
        return 1
    print("key looks like:", key[:10] + "…" + key[-4:], f"({len(key)} chars)")
    try:
        import anthropic
        print("anthropic SDK:", anthropic.__version__)
        msg = anthropic.Anthropic(api_key=key, timeout=60, max_retries=0).messages.create(
            model=MODEL, max_tokens=20, messages=[{"role": "user", "content": "Say OK."}])
        print("API call: OK ·", MODEL, "·", "".join(getattr(b, "text", "") for b in msg.content).strip()[:20])
        return 0
    except Exception as e:  # noqa: BLE001
        print("API call FAILED:", type(e).__name__, str(e)[:300])
        return 2


def tool_schema(name: str, model, drop: tuple[str, ...] = ()) -> dict:
    s = model.model_json_schema()
    s.pop("title", None)
    for f in drop:
        s.get("properties", {}).pop(f, None)
    return {"name": name,
            "description": f"Record only what the input states ({model.__name__}). Unknown → null.",
            "input_schema": s}


def llm_tool(content: list, tools: list, system: str, max_tokens: int = 2000) -> tuple[str, dict]:
    """One forced tool call → (tool name, input). Raises on any failure; callers fall back."""
    import anthropic
    key = api_key()
    if not key:
        raise RuntimeError("no API key")
    client = anthropic.Anthropic(api_key=key, timeout=90, max_retries=1)
    # Sonnet 5.5 rejects forced tool_choice (any/tool): use auto and require the call in the prompt.
    # Thinking is always on and counts toward max_tokens, so leave room; low effort is enough for parsing.
    msg = client.messages.create(model=MODEL, max_tokens=max(max_tokens, 8000),
                                 system=system + " Always answer by calling exactly one of the provided tools; "
                                                 "never answer in plain text.",
                                 tools=tools, tool_choice={"type": "auto"},
                                 output_config={"effort": "low"},
                                 messages=[{"role": "user", "content": content}])
    for block in msg.content:
        if block.type == "tool_use":
            return block.name, block.input
    raise RuntimeError("model returned no tool call")


def load_json(p: Path) -> dict:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_json(p: Path, data: dict) -> None:
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        print(f"[cache] could not write {p.name}: {e}")

# ---------------------------------------------------------------- notes → NotesObs

NOTES_SYSTEM = (
    "You are a parser for German home-heating data. Fill only facts the notes state. "
    "Unknown → null. Never infer, never compute, never judge heat-pump suitability. "
    "For every field you fill, put a short verbatim quote in evidence[field] and a confidence 0-1 in confidence[field]. "
    "A negated statement ('No additional insulation', 'without low-e coating', 'No renovation documented') "
    "is not a measure: for insulation, set insulation_measures = [] with its quote only when the notes explicitly "
    "say there is no insulation; 'No renovation documented' / 'No renovation information' means unknown, so leave "
    "insulation_measures null. "
    "u_values keys: windows, wall, roof, floor, basement (W/m²K). "
    "solar_thermal_dhw: true only if the notes say hot water; if they only say 'solar thermal system present', "
    "set true with confidence ≤ 0.6 and say so in the evidence.")

NEG = re.compile(r"\b(no|not|without|kein|keine|keinen|ohne|nicht)\b", re.I)
U_RE = re.compile(r"(windows?|external wall|basement wall|wall|roof|floor slab|floor)\s*"
                  r"(?:approx\.?\s*|ca\.?\s*)?(\d+[.,]\d+)", re.I)
U_KEY = {"window": "windows", "windows": "windows", "external wall": "wall", "wall": "wall",
         "basement wall": "basement", "roof": "roof", "floor slab": "floor", "floor": "floor"}


def u_values(text: str) -> dict[str, float]:
    if not re.search(r"u-?values?|w/\(?m", text or "", re.I):
        return {}
    out: dict[str, float] = {}
    for name, val in U_RE.findall(text):
        k = U_KEY.get(name.lower())
        if k and k not in out:
            out[k] = float(val.replace(",", "."))
    return out


def _sentences(t: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", t or "") if s.strip()]


def keyword_notes(text: str) -> NotesObs:
    o = NotesObs(method="keywords")
    for s in _sentences(text):
        low, neg = s.lower(), bool(NEG.search(s))
        if re.search(r"wood stove|kaminofen|holzofen|fireplace|kamin", low) and not neg:
            o.extra_heat_source, o.evidence["extra_heat_source"], o.confidence["extra_heat_source"] = "wood_stove", s, 0.5
            if re.search(r"all winter|whole winter|ganzen winter", low):
                o.extra_source_all_winter, o.evidence["extra_source_all_winter"] = True, s
                o.confidence["extra_source_all_winter"] = 0.5
        if re.search(r"tiled stove|kachelofen", low) and not neg:
            o.extra_heat_source, o.evidence["extra_heat_source"], o.confidence["extra_heat_source"] = "tiled_stove", s, 0.5
        if re.search(r"solar ?thermal|solarthermie", low) and not neg:
            o.solar_thermal_dhw, o.evidence["solar_thermal_dhw"] = True, s
            o.confidence["solar_thermal_dhw"] = 0.6 if "water" in low or "wasser" in low else 0.4
        if re.search(r"not lived in|unused|unheated|not heated|nicht bewohnt|unbeheizt|leer", low):
            o.unheated_area_note, o.evidence["unheated_area_note"], o.confidence["unheated_area_note"] = s, s, 0.5
        if re.search(r"insulat|dämm", low):
            if neg:
                if o.insulation_measures is None:
                    o.insulation_measures, o.evidence["insulation_measures"] = [], s
            else:
                o.insulation_measures = (o.insulation_measures or []) + [s]
                o.evidence["insulation_measures"] = s
            o.confidence["insulation_measures"] = 0.5
        if re.search(r"glazing|verglas|low-e", low):
            o.glazing, o.evidence["glazing"], o.confidence["glazing"] = s, s, 0.5
        bt = ("semi_detached" if re.search(r"semi-detached|doppelhaus", low) else
              "terraced" if re.search(r"terraced|reihen", low) else
              "apartment" if re.search(r"apartment|wohnung", low) else
              "detached" if re.search(r"detached|einfamilienhaus", low) else None)
        if bt and o.building_type is None:
            o.building_type, o.evidence["building_type"], o.confidence["building_type"] = bt, s, 0.5
    return o


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


_LLM_FAILED: set[str] = set()


def parse_notes(text: str, use_llm: bool = True) -> NotesObs:
    """Cache first, then LLM, then keywords. U-values always by regex on top."""
    text = (text or "").strip()
    if not text:
        return NotesObs(method="keywords")
    cache, key = load_json(NOTES_CACHE), _hash(text)
    obs = None
    if key in cache:
        try:
            obs = NotesObs.model_validate({**cache[key], "method": "cache"})
        except Exception as e:
            print(f"[notes] bad cache entry ignored ({e})")
    if obs is not None:
        pass
    elif use_llm and key not in _LLM_FAILED:
        try:
            _, inp = llm_tool([{"type": "text", "text": f"Notes:\n{text}"}],
                              [tool_schema("record_notes", NotesObs, drop=("method",))], NOTES_SYSTEM)
            obs = NotesObs.model_validate({**inp, "method": "llm"})
            cache[key] = obs.model_dump(exclude={"method"}) | {"text": text}
            save_json(NOTES_CACHE, cache)
        except Exception as e:
            _LLM_FAILED.add(key)
            print(f"[notes] LLM failed ({e}); keyword fallback")
            obs = keyword_notes(text)
    else:
        obs = keyword_notes(text)
    for k, v in u_values(text).items():
        obs.u_values.setdefault(k, v)
    return obs

# ---------------------------------------------------------------- organiser rows → House


def _blank(v) -> bool:
    return v is None or (isinstance(v, float) and pd.isna(v)) or (isinstance(v, str) and not v.strip())


def _int_text(s: str) -> int | None:
    """'4,000' / '4.000' / '18000' → int; anything odd → None."""
    try:
        return int(re.sub(r"[.,](?=\d{3}\b)", "", s.strip().rstrip(".,")))
    except Exception:
        return None


def fuel_from(carrier: str | None, detail: str | None) -> str | None:
    t = re.sub(r"[_-]", " ", f"{carrier or ''} {detail or ''}".lower())
    if re.search(r"lpg|flüssiggas|liquefied", t):
        return "lpg"
    if re.search(r"\boil\b|heizöl|\böl", t):
        return "oil"
    if re.search(r"district|fernwärme", t):
        return "district"
    if re.search(r"electric|strom", t):
        return "electric"
    if "gas" in t:
        return "gas"
    return None


def row_to_house(row: dict, use_llm: bool = True) -> tuple[str, House, dict | None]:
    r = {k: (None if _blank(v) else v) for k, v in row.items()}
    bid = str(r["building_id"])
    h = House(building_id=bid)

    def put(field, val, conf=0.9, src="data"):
        if val is None:
            return
        setattr(h, field, val)
        h.source[field], h.confidence[field] = src, conf

    def get(k, cast):
        try:
            return cast(r[k]) if r.get(k) is not None else None
        except Exception:
            return None

    put("build_year", get("construction_year", int))
    put("living_area_m2", get("floor_area_m2", lambda v: float(round(float(v)))))
    ren = r.get("renovation_status")
    rl = str(ren or "").lower()
    put("renovation", "partially" if re.search(r"partial|teilweise", rl) else
        "fully" if re.search(r"full|komplett|vollständig", rl) else
        "unrenovated" if re.search(r"unrenovated|unsaniert", rl) else None)
    hd = r.get("heat_distribution")
    hl = str(hd or "").lower()
    put("heat_distribution", "underfloor" if re.search(r"underfloor|fußboden", hl) else
        "mixed" if re.search(r"mixed|both", hl) else
        "radiators" if re.search(r"radiator|heizkörper", hl) else None)
    put("annual_fuel_kwh", get("annual_consumption_kwh", float))
    detail = r.get("energy_carrier_detail") or ""
    fuel = fuel_from(r.get("energy_carrier"), detail)
    put("fuel_type", fuel)
    if fuel == "lpg" and (r.get("energy_carrier") or "").lower() == "gas":
        h.data_notes.append("carrier says gas, detail says LPG → lpg")
    m = re.search(r"(\d[\d.,]*)\s*(?:litres|liters|liter|l)\b", detail, re.I)
    if m:
        n = _int_text(m.group(1))
        put("annual_fuel_liters", None if n is None else float(n), 0.8)

    ri = r.get("radiator_info") or ""
    low = ri.lower()
    m = re.search(r"(\d+)\s*radiators?\b(?!\s*valves)", ri, re.I)
    put("radiator_count", int(m.group(1)) if m else None, 0.8)
    m = re.search(r"(\d+)\s*(?:\w+\s+)?valves", ri, re.I)
    put("valves_to_replace", int(m.group(1)) if m else None, 0.8)
    if any(re.search(r"(?<!un)balanced|abgeglichen", c) and not NEG.search(c) for c in re.split(r"[,;.]", low)):
        put("hydraulic_balanced", True, 0.8)
    if "presettable" in low:
        h.data_notes.append("presettable valves, balancing to check")
    elif "preset" in low or "voreingestellt" in low:
        h.data_notes.append("preset valves, balancing to check")
    if "valve block" in low:
        h.data_notes.append("valve blocks say nothing about the pipe system")

    ps = str(r.get("pipe_system") or "").lower()
    put("pipe_system", "two_pipe" if re.search(r"two.?pipe|zweirohr", ps) else
        "single_pipe" if re.search(r"single.?pipe|one.?pipe|einrohr", ps) else None)
    put("current_flow_temp_c", get("flow_temperature_c", float))
    put("occupants", get("persons_in_household", int))
    hw = r.get("hot_water_via_heating")
    hws = str(hw).strip().lower() if hw is not None else ""
    put("dhw_by_boiler", True if hws in ("yes", "ja", "true", "1") else False if hws in ("no", "nein", "false", "0") else None)
    put("rooms", get("rooms", int))
    loc = r.get("location") or ""
    m = re.match(r"\s*(\w+)\s+area", loc, re.I)
    put("region", m.group(1).lower() if m else (loc or None))

    h.notes = r.get("building_notes")
    if h.notes:
        h.notes_obs = parse_notes(h.notes, use_llm)
        if h.notes_obs.building_type and h.building_type is None:
            put("building_type", h.notes_obs.building_type,
                min(0.8, h.notes_obs.confidence.get("building_type", 0.6)), "notes_llm")

    ref = None
    if r.get("reference_heating_load_kw") is not None or r.get("expected_verdict"):
        ref = {"heating_load_kw": r.get("reference_heating_load_kw"), "verdict": r.get("expected_verdict")}
    return bid, h, ref


def _read_set(base: Path, stem: str) -> list[dict]:
    j, c = base / f"{stem}.json", base / f"{stem}.csv"
    try:
        if j.exists():
            d = json.loads(j.read_text(encoding="utf-8"))
            if isinstance(d, dict):
                d = next((v for v in d.values() if isinstance(v, list)), [])
            return [x for x in d if isinstance(x, dict)]
        if c.exists():
            return pd.read_csv(c).to_dict("records")
    except Exception as e:
        print(f"[loader] could not read {stem}: {e}")
    return []


def load_buildings(path: str = "data/", use_llm: bool = True) -> list[tuple[str, House, dict | None]]:
    """Every data/buildings_*.json (CSV only if no JSON), one row per building_id, dev first."""
    base = Path(path) if Path(path).is_absolute() else ROOT / path
    stems = sorted({p.stem for p in base.glob("buildings_*.*") if p.suffix in (".json", ".csv")})
    out, seen = [], set()
    for stem in stems:
        for row in _read_set(base, stem):
            bid = str(row.get("building_id"))
            if bid in seen:
                continue
            seen.add(bid)
            out.append(row_to_house(row, use_llm))
    return out


# ---------------------------------------------------------------- baseline snapshot (engine regression check)

BASELINE = ROOT / "data" / "baseline_results.json"


def _brief_fn():
    """engine.evaluate + installer_brief (lazy import: engine imports loader)."""
    import engine

    def run(h: House):
        r = engine.evaluate(h)
        return engine.installer_brief(h, r) if hasattr(engine, "installer_brief") else r
    return run


def baseline_rows(buildings, evaluate_fn) -> dict:
    """Per building id: the numbers a demo depends on. evaluate_fn(House) -> Result | None (None = skipped)."""
    out = {}
    for bid, h, _ in buildings:
        try:
            r = evaluate_fn(h)
        except Exception as e:
            out[bid] = {"error": f"{type(e).__name__}: {e}"}
            continue
        if r is None:
            continue
        fl = r.required_flow_temp_c
        out[bid] = {"best_color": r.best_color, "verdict_basis": r.verdict_basis,
                    "p_green": round(r.p_green, 3), "p_yellow": round(r.p_yellow, 3), "p_red": round(r.p_red, 3),
                    "flow_p10": fl.p10, "flow_p50": fl.p50, "flow_p90": fl.p90,
                    "load_p50": r.heat_load_kw.p50, "load_bill_p50": r.heat_load_bill_kw.p50,
                    "visit_type": r.visit_type, "lead_score": round(r.lead_score or 0, 3),
                    "flag_count": len(r.contradictions) + len(r.installer_checklist)}
    return out


def _delta(a, b):
    return None if a is None or b is None else b - a


def compare_baseline(current: dict, saved: dict) -> list[dict]:
    """Per building in either set: colour changed?, flow p50 delta (°C), load p50 delta (kW), visit changed?"""
    rows = []
    for bid in sorted(k for k in set(current) | set(saved) if not k.startswith("_")):
        c, s = current.get(bid) or {}, saved.get(bid) or {}
        rows.append({"building_id": bid, "missing": "current" if not c else "saved" if not s else None,
                     "error": c.get("error"),
                     "color_saved": s.get("best_color"), "color_now": c.get("best_color"),
                     "color_changed": bool(c and s) and c.get("best_color") != s.get("best_color"),
                     "flow_saved": s.get("flow_p50"), "flow_now": c.get("flow_p50"),
                     "flow_delta": _delta(s.get("flow_p50"), c.get("flow_p50")),
                     "load_saved": s.get("load_p50"), "load_now": c.get("load_p50"),
                     "load_delta": _delta(s.get("load_p50"), c.get("load_p50")),
                     "visit_saved": s.get("visit_type"), "visit_now": c.get("visit_type"),
                     "visit_changed": bool(c and s) and c.get("visit_type") != s.get("visit_type")})
    return rows


def baseline_moved(row: dict, flow_k: float = 1.0, load_kw: float = 0.3) -> bool:
    """True if a compare row is worth showing: missing/error, colour or visit change, or a big enough shift."""
    return bool(row["missing"] or row["error"] or row["color_changed"] or row["visit_changed"]
                or (row["flow_delta"] is not None and abs(row["flow_delta"]) >= flow_k)
                or (row["load_delta"] is not None and abs(row["load_delta"]) >= load_kw))


def load_baseline(path: Path = BASELINE) -> dict:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_baseline(buildings=None, path: Path = BASELINE) -> dict:
    from datetime import datetime
    from schema import DEFAULT
    buildings = buildings if buildings is not None else load_buildings()
    rows = baseline_rows(buildings, _brief_fn())
    eng = ROOT / "engine.py"
    rows["_meta"] = {"engine_sha256": hashlib.sha256(eng.read_bytes()).hexdigest()[:16] if eng.exists() else None,
                     "date": datetime.now().isoformat(timespec="seconds"), "k": DEFAULT.k}
    save_json(Path(path), rows)
    return rows


def _fmt(v, nd=1):
    return "–" if v is None else f"{v:.{nd}f}"


def print_compare(path: Path = BASELINE) -> list[dict]:
    saved = load_baseline(path)
    if not saved:
        print(f"No baseline at {path}. Run: python loader.py --save-baseline")
        return []
    rows = compare_baseline(baseline_rows(load_buildings(), _brief_fn()), saved)
    m = saved.get("_meta", {})
    print(f"Baseline {m.get('date')} engine {m.get('engine_sha256')} k={m.get('k')}")
    print(f"{'':2} {'id':6} {'colour':18} {'flow p50 °C':22} {'load p50 kW':20} visit")
    for r in rows:
        if r["missing"] or r["error"]:
            print(f"!! {r['building_id']:6} {r['error'] or 'missing in ' + r['missing']}")
            continue
        mark = "!!" if r["color_changed"] else ("~ " if baseline_moved(r) else "  ")
        col = f"{r['color_saved']}->{r['color_now']}" if r["color_changed"] else r["color_now"]
        fd, lo = r["flow_delta"], r["load_delta"]
        fl = f"{_fmt(r['flow_saved'])}->{_fmt(r['flow_now'])} (" + ('–' if fd is None else f'{fd:+.1f}') + ")"
        ld = f"{_fmt(r['load_saved'], 2)}->{_fmt(r['load_now'], 2)} (" + ('–' if lo is None else f'{lo:+.2f}') + ")"
        vis = f"{r['visit_saved']}->{r['visit_now']}" if r["visit_changed"] else str(r["visit_now"])
        print(f"{mark} {r['building_id']:6} {col:18} {fl:22} {ld:20} {vis}")
    n = sum(baseline_moved(r) for r in rows)
    print("No differences." if not n else f"{n} building(s) moved.")
    return rows


if __name__ == "__main__":
    import sys
    use_llm = "--no-llm" not in sys.argv
    if "--save-baseline" in sys.argv:
        rows = save_baseline()
        print(f"Saved {len(rows) - 1} buildings to {BASELINE.relative_to(ROOT)} ({rows['_meta']})")
        sys.exit(0)
    if "--check-key" in sys.argv:
        sys.exit(check_key())
    if "--compare-baseline" in sys.argv:
        print_compare()
        sys.exit(0)
    for bid, h, ref in load_buildings(use_llm=use_llm):
        o = h.notes_obs
        print(f"{bid} {h.build_year} {h.living_area_m2} m² {h.fuel_type} kWh={h.annual_fuel_kwh} L={h.annual_fuel_liters} "
              f"rad={h.radiator_count} valves={h.valves_to_replace} pipe={h.pipe_system} rooms={h.rooms} "
              f"type={h.building_type} ref={ref}")
        print(f"   data_notes={h.data_notes}")
        if o:
            print(f"   notes[{o.method}] extra={o.extra_heat_source}/{o.extra_source_all_winter} solar={o.solar_thermal_dhw} "
                  f"unused={bool(o.unheated_area_note)} insulation={o.insulation_measures} u={o.u_values}")
