"""Wizard inputs → House via one forced tool call per mission. The LLM reads; the engine converts."""
from __future__ import annotations

import base64
import hashlib
import io
import re
from pathlib import Path

import loader                  # loader.llm_tool looked up at call time (one place to stub it)
from loader import fuel_from, keyword_notes, load_json, save_json, tool_schema
from schema import (MISSION_MODELS, BillObs, ExteriorObs, House, HouseTextObs, ListingObs,
                    RadiatorObs)

ROOT = Path(__file__).parent
CACHE = ROOT / "samples" / "cached_extract.json"
DEMO_ONLY = False          # app toggle: cached reads only, no live calls
SOURCE = {"house_text": "text", "exterior": "photo", "radiator": "photo", "bill": "bill", "listing": "listing"}
MISSING_OK = {"not_visible", "blurry", "ambiguous", "wrong_object"}
LLM_CAP = 0.8              # CLAUDE.md step 9: LLM confidence capped at 0.8

SYSTEM = (
    "You are a parser for a heat-pump readiness tool. Read the input and call exactly one tool. "
    "Report only what the input states or clearly shows. Unknown or unsure → null. Never guess, never compute, "
    "never convert units, never judge suitability. For every field you fill, put a short verbatim quote or a "
    "short image note in evidence[field] and a confidence 0-1 in confidence[field].")
HINT = {
    "house_text": (
        "Mission: a homeowner's description of their house. yearly_use_value and yearly_use_unit exactly as written "
        "(e.g. 18000 and 'kWh', 2500 and 'l', 150 and 'EUR/month'). radiator_size 'large' only if the words say big or "
        "large, confidence ≤ 0.5, and copy the words into radiator_size_words. renovation 'partially' if some insulation "
        "or window work is named, 'unrenovated' only if stated. Never guess a year from words like 'old'. "
        "Also fill notes (NotesObs) from the same text."),
    "exterior": (
        "Mission: a photo of a house from outside. era_from/era_to always with confidence ≤ 0.4. "
        "outdoor_unit_space true only if a free spot next to the wall is visible, false if clearly none. "
        "Not a house or unreadable → missing {field: wrong_object|blurry} and a short retake_tip."),
    "radiator": (
        "Mission: a photo of a radiator with its pipes. Pipe-system cues: one pipe along the wall or skirting, tapped at "
        "each radiator → single_pipe; H-block with an extra adjustable side port (bypass) → single_pipe; valve at the "
        "top, separate return at the bottom, two separate pipes → two_pipe; H-block without side port → two_pipe with "
        "confidence ≤ 0.6; one bottom connection or a bathroom multiblock → null. Two connections or a valve block alone "
        "say nothing. Unsure → pipe_system null and say why in pipe_reason. Not a radiator or unreadable → missing and "
        "a short retake_tip."),
    "bill": (
        "Mission: an energy bill, or a property listing / energy certificate. Call record_bill for a bill, "
        "record_listing for a listing or certificate. Bill: raw numbers as printed (kWh, m³, Zustandszahl, Brennwert, "
        "litres, period as ISO dates, total €, monthly advance). Listing: certificate kWh/(m²·a) and its area as printed."),
}
HINT["listing"] = HINT["bill"]
TOOL_KIND = {"record_house": "house_text", "record_exterior": "exterior", "record_radiator": "radiator",
             "record_bill": "bill", "record_listing": "listing"}


def _media_block(data: bytes, mime: str) -> dict:
    if mime.endswith("pdf") or data[:4] == b"%PDF":
        return {"type": "document",
                "source": {"type": "base64", "media_type": "application/pdf", "data": base64.b64encode(data).decode()}}
    from PIL import Image, ImageOps
    im = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("RGB")
    im.thumbnail((1568, 1568))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=85)
    return {"type": "image",
            "source": {"type": "base64", "media_type": "image/jpeg", "data": base64.b64encode(buf.getvalue()).decode()}}


def _num(s: str) -> float | None:
    try:
        return float(re.sub(r"[.,](?=\d{3}\b)", "", s).replace(",", "."))
    except (ValueError, TypeError):
        return None


WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "zwei": 2, "drei": 3, "vier": 4, "fünf": 5,
         "zweit": 2, "dritt": 3, "viert": 4, "fünft": 5}
_FAILED: set[str] = set()       # keys whose live call failed this process: a down API is not retried


def keyword_house(text: str) -> HouseTextObs:
    """Fallback for the text step when cache and API are both missing."""
    o, low = HouseTextObs(), text.lower()

    def put(f, v, quote):
        if v is not None:
            setattr(o, f, v)
            o.evidence[f], o.confidence[f] = quote, 0.5
    m = (re.search(r"(?:baujahr|built|from|von|aus|construction)\D{0,15}?\b(1[89]\d\d|20[0-2]\d)\b", low)
         or re.search(r"\b(1[89]\d\d|20[0-2]\d)\b(?!\s*(?:l|kwh|m|qm|€|eur|liter))", low))
    put("build_year", int(m.group(1)) if m else None, m and m.group(0))
    m = re.search(r"(\d[\d.,]*)\s*(m²|m2|qm|sqm|square met)", low)
    v = _num(m.group(1)) if m else None
    put("living_area_m2", v, m and m.group(0))
    m = re.search(r"(\d[\d.,]*)\s*kwh", low)
    v = _num(m.group(1)) if m else None
    if v is not None:
        put("yearly_use_value", v, m.group(0))
        o.yearly_use_unit = "kWh"
    m = re.search(r"(\d+)\s*(radiators|heizkörper)", low)
    put("radiator_count", int(m.group(1)) if m else None, m and m.group(0))
    m = (re.search(r"(\d+)\s*(?:people|persons|personen|leute)", low) or re.search(r"(\d+|\w+) of us", low)
         or re.search(r"zu (zweit|dritt|viert|fünft)", low))
    if m:
        g = m.group(1)
        put("occupants", int(g) if g.isdigit() else WORDS.get(g), m.group(0))
    fuel = None
    for sent in re.split(r"[.;,\n]", low):
        if re.search(r"heizung|heating|boiler|kessel|ofen", sent):
            fuel = fuel_from(None, sent)
            if fuel:
                break
    fuel = fuel or fuel_from(None, low)
    put("fuel_type", fuel, fuel)
    rad, ufh = bool(re.search(r"radiator|heizkörper", low)), bool(re.search(r"underfloor|fußboden", low))
    put("heat_distribution", "mixed" if rad and ufh else "radiators" if rad else "underfloor" if ufh else None,
        "radiators/underfloor")
    o.notes = keyword_notes(text)
    if o.notes.building_type:
        put("building_type", o.notes.building_type, o.notes.evidence.get("building_type"))
    if o.notes.insulation_measures or re.search(r"new windows|neue fenster", low):
        put("renovation", "partially", o.notes.evidence.get("insulation_measures") or "new windows")
    return o


def read_obs(data: bytes, mime: str, mission: str, cache_only: bool = False):
    """→ (kind, obs). 'bill' may come back as 'listing'. Cache → LLM → keywords (text only).
    cache_only=True (orchestrator fallbacks, Invariant 1): never call the LLM; not cached → raises."""
    key = hashlib.sha256(mission.encode() + data).hexdigest()[:20]
    cache = load_json(CACHE)
    if key in cache:
        try:
            kind = cache[key]["kind"]
            return kind, MISSION_MODELS[kind].model_validate(cache[key]["obs"])
        except Exception:
            pass                                  # bad cache entry: go live
    try:
        if DEMO_ONLY or cache_only:
            raise RuntimeError("cache only: not in cache")
        if mission == "house_text":
            if key in _FAILED:
                raise RuntimeError("live call failed earlier")
            tools = [tool_schema("record_house", HouseTextObs)]
            content = [{"type": "text", "text": HINT[mission] + "\n\nText:\n" + data.decode("utf-8", "replace")}]
        elif mission in ("bill", "listing"):
            tools = [tool_schema("record_bill", BillObs), tool_schema("record_listing", ListingObs)]
            content = [_media_block(data, mime), {"type": "text", "text": HINT["bill"]}]
        else:
            tools = [tool_schema(f"record_{mission}", MISSION_MODELS[mission])]
            content = [_media_block(data, mime), {"type": "text", "text": HINT[mission]}]
        name, inp = loader.llm_tool(content, tools, SYSTEM)
        kind = TOOL_KIND.get(name, mission)
        if isinstance(inp, dict) and isinstance(inp.get("missing"), dict):
            inp = {**inp, "missing": {k: v for k, v in inp["missing"].items() if v in MISSING_OK}}
        obs = MISSION_MODELS[kind].model_validate(inp)
    except Exception as e:
        if mission != "house_text":
            raise RuntimeError(f"could not read the {mission}: {e}") from e
        _FAILED.add(key)
        return "house_text", keyword_house(data.decode("utf-8", "replace"))   # not cached
    cache[key] = {"kind": kind, "obs": obs.model_dump()}
    save_json(CACHE, cache)
    return kind, obs


def obs_to_house(kind: str, obs) -> House:
    src, h = SOURCE[kind], House()
    d = obs.model_dump()
    conf, ev = d.get("confidence", {}), d.get("evidence", {})

    def put(field, val, of=None, cap=LLM_CAP):
        if val is None:
            return
        of = of or field
        setattr(h, field, val)
        h.source[field], h.confidence[field] = src, min(cap, conf.get(of, 0.6))
        if ev.get(of):
            h.evidence[field] = ev[of]

    if kind == "house_text":
        for f in ("build_year", "living_area_m2", "building_type", "renovation", "heat_distribution", "fuel_type",
                  "occupants", "radiator_count", "radiator_size", "boiler_condensing"):
            put(f, d[f])
        u, v = (obs.yearly_use_unit or "").lower().replace("³", "3"), obs.yearly_use_value
        if v is not None:
            monthly = ("eur" in u or "€" in u) and bool(re.search(r"month|monat|mtl", u))
            field = ("annual_fuel_kwh" if "kwh" in u else "monthly_advance_eur" if monthly
                     else "m3" if "m3" in u else "annual_fuel_liters" if u.startswith("l") else None)
            if field:
                put(field, v, "yearly_use_value")
        if obs.radiator_size_words and "radiator_size" in h.evidence:
            h.evidence["radiator_size"] = obs.radiator_size_words
        h.notes_obs = obs.notes
    elif kind == "exterior":
        for f in ("building_type", "windows", "outdoor_unit_space"):
            put(f, d[f])
        put("walls_insulated", d["facade_insulation_visible"], "facade_insulation_visible")
        if d["era_from"] and d["era_to"]:      # rough era stays evidence only, never a year
            h.evidence["build_year_photo"] = f"photo looks like {d['era_from']}-{d['era_to']}"
    elif kind == "radiator":
        put("radiator_size", d["radiator_size"])
        put("pipe_system", d["pipe_system"])
        if d["pipe_reason"]:
            h.evidence["pipe_system"] = d["pipe_reason"]
        if d["panel_type"]:
            h.evidence["radiator_panel_type"] = f"Type {d['panel_type']}"
    elif kind == "bill":
        for f in ("kwh_printed", "m3", "zustandszahl", "brennwert", "liters", "period_start", "period_end",
                  "bill_carrier", "bill_total_eur", "monthly_advance_eur"):
            put(f, d[f])
        put("fuel_type", fuel_from(d["bill_carrier"], None), "bill_carrier")   # raw values stay raw: engine step 1
    elif kind == "listing":
        for f in ("build_year", "living_area_m2", "rooms", "building_type", "fuel_type", "certificate_kwh_m2a",
                  "certificate_area_m2"):
            put(f, d[f])
        if obs.modernisation_notes:
            put("renovation", "partially", "modernisation_notes", cap=0.5)
            h.evidence["renovation"] = "; ".join(obs.modernisation_notes)
    h.missing = dict(d.get("missing", {}))
    h.retake_tip = d.get("retake_tip")
    return h


def extract(file_bytes: bytes, mime: str, mission: str, cache_only: bool = False) -> House:
    kind, obs = read_obs(file_bytes, mime, mission, cache_only=cache_only)
    return obs_to_house(kind, obs)


# ---------------------------------------------------------------- merge (CLAUDE.md "Which source wins")

ORDER = {
    "owner": ["confirmed", "data", "text", "listing", "bill", "photo", "notes_llm", "rule", "prior"],
    "device": ["confirmed", "data", "photo", "text", "listing", "bill", "notes_llm", "rule", "prior"],
    "use": ["confirmed", "data", "bill", "listing", "text", "photo", "notes_llm", "rule", "prior"],
}
GROUP = {**{f: "owner" for f in ("build_year", "living_area_m2", "occupants", "rooms", "building_type",
                                  "renovation", "radiator_count", "heat_distribution")},
         **{f: "use" for f in ("annual_fuel_kwh", "annual_fuel_liters", "fuel_type", "monthly_advance_eur", "m3",
                                "kwh_printed", "liters")}}
SKIP = {"building_id", "confidence", "source", "evidence", "missing", "conflicts", "data_notes", "notes",
        "notes_obs", "retake_tip"}


def _same(a, b) -> bool:
    if isinstance(a, bool) or isinstance(b, bool):
        return a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        if isinstance(a, int) and isinstance(b, int):   # years, people, rooms, counts: exact
            return a == b
        return abs(a - b) <= 0.05 * max(abs(a), abs(b), 1)
    return a == b


def merge(base: House, new: House) -> House:
    """Per-field source priority; LLM confidence only breaks ties within one source. Logs disagreements."""
    out = base.model_copy(deep=True)

    def take(f):
        setattr(out, f, getattr(new, f))
        out.source[f] = new.source.get(f, "prior")
        out.confidence[f] = new.confidence.get(f, 0.5)
        if f in new.evidence:
            out.evidence[f] = new.evidence[f]

    for f in House.model_fields:
        if f in SKIP or getattr(new, f) is None:
            continue
        ov, nv = getattr(out, f), getattr(new, f)
        if ov is None:
            take(f)
            continue
        order = ORDER[GROUP.get(f, "device")]
        os_, ns = out.source.get(f, "prior"), new.source.get(f, "prior")
        ri, rj = order.index(ns) if ns in order else len(order), order.index(os_) if os_ in order else len(order)
        new_wins = ri < rj or (ri == rj and new.confidence.get(f, 0) > out.confidence.get(f, 0))
        if not _same(ov, nv) and ns != os_:
            out.conflicts = [c for c in out.conflicts if c["field"] != f] + [
                {"field": f, "values": {os_: ov, ns: nv}, "used": ns if new_wins else os_}]
        if new_wins:
            take(f)
    out.evidence.update({k: v for k, v in new.evidence.items() if k not in out.evidence})
    if new.notes_obs and not out.notes_obs:
        out.notes_obs = new.notes_obs
    out.missing.update(new.missing)
    out.retake_tip = new.retake_tip or out.retake_tip
    out.data_notes = out.data_notes + [n for n in new.data_notes if n not in out.data_notes]
    return out
