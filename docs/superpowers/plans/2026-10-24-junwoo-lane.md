# Junwoo Lane (LLM I/O, schema, app) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn every input (organiser CSV/JSON, homeowner text, bill, radiator and exterior photos) into a `House`, hand it to the friend's `engine.evaluate`, and show the returned `Result` in the three Streamlit tabs drawn in `docs/design/`.

**Architecture:** `loader.py` maps the 5 organiser buildings to `House` (regex for numbers, LLM `NotesObs` for facts, cached in `data/notes_cache.json`, keyword fallback with negation). `extract.py` runs one forced tool call per wizard mission, caches by content hash in `samples/cached_extract.json`, converts the observation to a `House` with sources, and `merge` combines houses by per-field source priority while logging conflicts. `app.py` only renders: it never computes physics, it calls `engine.evaluate` / `engine.installer_brief` (owned by `potatohater8`) behind try/except so the UI runs before the engine exists.

**Tech Stack:** Python 3.11.9, Streamlit 1.66, Pydantic 2.14, anthropic 0.x SDK (model `claude-sonnet-5-5`), pandas, Pillow.

**Project rules that override the skill defaults:** no test files (CLAUDE.md "Do not: test code"), so every task is verified with an exact `python -c` / `python file.py` command and its expected output; create no code files beyond CLAUDE.md "Files"; commit only named files, never `git add -A`; talk to Junwoo in Korean.

**Contract with the engine owner (`potatohater8`):** `engine.evaluate(h: House, p=DEFAULT, n=500, seed=0) -> Result`, `engine.installer_brief(h, r) -> Result`, optional `engine.next_question(h) -> str | None`, optional `engine.handover_pdf(h, r, contact) -> bytes`, `calibrate.leave_one_out(buildings) -> DataFrame` with columns `building_id`, `error_pct`. Fuel input for the engine: `annual_fuel_kwh` if present, else the raw bill fields (`kwh_printed`, `m3`, `zustandszahl`, `brennwert`, `liters`/`annual_fuel_liters`, `monthly_advance_eur`) which the engine converts (step 1). `House.conflicts` lists source disagreements the engine may turn into contradictions.

---

## File map

| File | Responsibility | Status |
| --- | --- | --- |
| `schema.py` | Contract. Task 0 adds `House.conflicts`, `House.retake_tip`. | modify |
| `loader.py` | Organiser data → `House`; shared LLM helpers (`api_key`, `llm_tool`, `tool_schema`); `parse_notes`, `keyword_notes`, `u_values`. | create |
| `data/notes_cache.json` | `NotesObs` per notes-text hash, committed so the demo runs offline. | create (generated) |
| `extract.py` | Wizard missions → `House`; `read_obs`, `obs_to_house`, `keyword_house`, `extract`, `merge`. | create |
| `samples/cached_extract.json` | Mission reads of the demo inputs, committed (JSON is not gitignored). | create (generated) |
| `.streamlit/config.toml` | Theme tokens. | create |
| `app.py` | Tabs Homeowner / Evaluation / Installer. | replace the setup shell |

---

### Task 0: Sync and extend the schema

**Files:**
- Modify: `schema.py` (class `House`, block `# provenance`)

- [ ] **Step 1: Pull the friend's work first**

Run: `git pull --rebase`
Expected: `Already up to date.` or a fast-forward. If `engine.py` arrived, note it; nothing else changes in this task.

- [ ] **Step 2: Add two provenance fields to `House`**

In `schema.py`, replace

```python
    missing: dict[str, MissingReason] = {}


# ---------------------------------------------------------------- Params (engine knobs)
```

with

```python
    missing: dict[str, MissingReason] = {}
    retake_tip: Optional[str] = None           # one concrete tip when a photo was unreadable
    conflicts: list[dict] = []                 # {field, values: {source: value}, used: source} from merge


# ---------------------------------------------------------------- Params (engine knobs)
```

- [ ] **Step 3: Verify**

Run: `.venv/Scripts/python.exe -c "from schema import House; h=House(); print(h.conflicts, h.retake_tip)"`
Expected: `[] None`

- [ ] **Step 4: Commit and push (the friend builds against this)**

```bash
git add schema.py
git commit -m "schema: House.conflicts and retake_tip for merge and photo retakes"
git push
```

---

### Task 1: `loader.py` — organiser rows to `House` (no LLM yet)

**Files:**
- Create: `loader.py`

- [ ] **Step 1: Write `loader.py` with LLM helpers, regex mapping and keyword notes**

```python
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


def api_key() -> str | None:
    if os.environ.get("ANTHROPIC_API_KEY"):
        return os.environ["ANTHROPIC_API_KEY"]
    try:
        return tomllib.loads((ROOT / ".streamlit" / "secrets.toml").read_text(encoding="utf-8")).get("ANTHROPIC_API_KEY")
    except Exception:
        return None


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
    client = anthropic.Anthropic(api_key=key, timeout=60, max_retries=1)
    msg = client.messages.create(model=MODEL, max_tokens=max_tokens, system=system, tools=tools,
                                 tool_choice={"type": "any"},
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
    "is not a measure: for insulation, set insulation_measures = [] with its quote. "
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


def parse_notes(text: str, use_llm: bool = True) -> NotesObs:
    """Cache first, then LLM, then keywords. U-values always by regex on top."""
    text = (text or "").strip()
    if not text:
        return NotesObs(method="keywords")
    cache, key = load_json(NOTES_CACHE), _hash(text)
    if key in cache:
        obs = NotesObs.model_validate({**cache[key], "method": "cache"})
    elif use_llm:
        try:
            _, inp = llm_tool([{"type": "text", "text": f"Notes:\n{text}"}],
                              [tool_schema("record_notes", NotesObs, drop=("method",))], NOTES_SYSTEM)
            obs = NotesObs.model_validate({**inp, "method": "llm"})
            cache[key] = obs.model_dump(exclude={"method"}) | {"text": text}
            save_json(NOTES_CACHE, cache)
        except Exception as e:
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


def _int_text(s: str) -> int:
    """'4,000' / '4.000' / '18000' → int."""
    return int(re.sub(r"[.,](?=\d{3}\b)", "", s))


def fuel_from(carrier: str | None, detail: str | None) -> str | None:
    t = f"{carrier or ''} {detail or ''}".lower()
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
        return cast(r[k]) if r.get(k) is not None else None

    put("build_year", get("construction_year", int))
    put("living_area_m2", get("floor_area_m2", lambda v: float(round(float(v)))))
    ren = r.get("renovation_status")
    put("renovation", ren if ren in ("unrenovated", "partially", "fully") else None)
    hd = r.get("heat_distribution")
    put("heat_distribution", hd if hd in ("radiators", "underfloor", "mixed") else None)
    put("annual_fuel_kwh", get("annual_consumption_kwh", float))
    detail = r.get("energy_carrier_detail") or ""
    fuel = fuel_from(r.get("energy_carrier"), detail)
    put("fuel_type", fuel)
    if fuel == "lpg" and (r.get("energy_carrier") or "").lower() == "gas":
        h.data_notes.append("carrier says gas, detail says LPG → lpg")
    m = re.search(r"(\d[\d.,]*)\s*(?:litres|liters|liter|l)\b", detail, re.I)
    if m:
        put("annual_fuel_liters", float(_int_text(m.group(1))), 0.8)

    ri = r.get("radiator_info") or ""
    low = ri.lower()
    m = re.search(r"(\d+)\s*radiators?\b", ri, re.I)
    put("radiator_count", int(m.group(1)) if m else None, 0.8)
    m = re.search(r"(\d+)\s*valves", ri, re.I)
    put("valves_to_replace", int(m.group(1)) if m else None, 0.8)
    if re.search(r"(?<!un)balanced|abgeglichen", low) and not re.search(r"not balanced|nicht abgeglichen", low):
        put("hydraulic_balanced", True, 0.8)
    if "presettable" in low:
        h.data_notes.append("presettable valves, balancing to check")
    elif "preset" in low or "voreingestellt" in low:
        h.data_notes.append("preset valves, balancing to check")
    if "valve block" in low:
        h.data_notes.append("valve blocks say nothing about the pipe system")

    put("pipe_system", {"two-pipe": "two_pipe", "single-pipe": "single_pipe"}.get((r.get("pipe_system") or "").lower()))
    put("current_flow_temp_c", get("flow_temperature_c", float))
    put("occupants", get("persons_in_household", int))
    hw = r.get("hot_water_via_heating")
    put("dhw_by_boiler", None if hw is None else hw in (True, 1, "yes", "true", "True"))
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
    if j.exists():
        return json.loads(j.read_text(encoding="utf-8"))
    if c.exists():
        return pd.read_csv(c).to_dict("records")
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


if __name__ == "__main__":
    import sys
    use_llm = "--no-llm" not in sys.argv
    for bid, h, ref in load_buildings(use_llm=use_llm):
        o = h.notes_obs
        print(f"{bid} {h.build_year} {h.living_area_m2} m² {h.fuel_type} kWh={h.annual_fuel_kwh} L={h.annual_fuel_liters} "
              f"rad={h.radiator_count} valves={h.valves_to_replace} pipe={h.pipe_system} rooms={h.rooms} "
              f"type={h.building_type} ref={ref}")
        print(f"   data_notes={h.data_notes}")
        if o:
            print(f"   notes[{o.method}] extra={o.extra_heat_source}/{o.extra_source_all_winter} solar={o.solar_thermal_dhw} "
                  f"unused={bool(o.unheated_area_note)} insulation={o.insulation_measures} u={o.u_values}")
```

- [ ] **Step 2: Verify the mapping without the LLM**

Run: `.venv/Scripts/python.exe loader.py --no-llm`
Expected (key values; wording of notes may differ):
- `B-01 2001 195.0 m² lpg kWh=10000.0 L=None rad=14 valves=None pipe=None` and `data_notes=['carrier says gas, detail says LPG → lpg', 'preset valves, balancing to check']`, `u={'windows': 1.1, 'wall': 0.21, 'basement': 0.35, 'roof': 0.24, 'floor': 0.35}`
- `B-02 ... underfloor` row: `rad=1`, `notes[keywords] extra=wood_stove/True solar=True`
- `B-03 1970 200.0 m² oil kWh=40000.0 L=4000.0 rad=15 valves=12 pipe=two_pipe rooms=11`, `unused=True`, insulation list with the cavity-wall sentence
- `B-04 1987 160.0 m² oil kWh=25000.0 L=2500.0 rad=12 pipe=single_pipe type=semi_detached`, `data_notes` has "valve blocks …"
- `B-05 2006 125.0 m² gas kWh=27000.0 rad=8 pipe=None rooms=14`, `insulation=[]`, `data_notes=['presettable valves, balancing to check']`

If any value is off, fix the regex in `row_to_house` / `keyword_notes` before moving on.

- [ ] **Step 3: Commit**

```bash
git add loader.py
git commit -m "loader: organiser rows to House, regex numbers, keyword notes with negation"
```

---

### Task 2: Notes cache with the LLM (5 API calls)

**Files:**
- Create: `data/notes_cache.json` (generated)

- [ ] **Step 1: Build the cache**

Run: `.venv/Scripts/python.exe loader.py`
Expected: five `notes[llm]` lines, no `[notes] LLM failed`. B-02 `extra=wood_stove/True`, B-03 `unused=True`, B-05 `insulation=[]`, B-04 `type=semi_detached`.
If it prints `LLM failed (…model…)`: the model ID is wrong; read the error, check `MODEL` in `loader.py` against CLAUDE.md "Stack".

- [ ] **Step 2: Confirm the second run is offline**

Run: `.venv/Scripts/python.exe loader.py`
Expected: five `notes[cache]` lines with the same facts.

- [ ] **Step 3: Read the quotes once by eye**

Run: `.venv/Scripts/python.exe -c "import json;[print(v['evidence']) for v in json.load(open('data/notes_cache.json',encoding='utf-8')).values()]"`
Expected: every quote is a substring of the original notes (no paraphrase). If one is paraphrased, delete that entry from the file and rerun Step 1.

- [ ] **Step 4: Commit**

```bash
git add data/notes_cache.json
git commit -m "notes cache: LLM NotesObs for the 5 buildings"
git push
```

---

### Task 3: `extract.py` — one mission to `House`

**Files:**
- Create: `extract.py`

- [ ] **Step 1: Write `extract.py`**

```python
"""Wizard inputs → House via one forced tool call per mission. The LLM reads; the engine converts."""
from __future__ import annotations

import base64
import hashlib
import io
import re
from pathlib import Path

from loader import fuel_from, keyword_notes, llm_tool, load_json, save_json, tool_schema
from schema import (MISSION_MODELS, BillObs, ExteriorObs, House, HouseTextObs, ListingObs,
                    RadiatorObs)

ROOT = Path(__file__).parent
CACHE = ROOT / "samples" / "cached_extract.json"
DEMO_ONLY = False          # app toggle: cached reads only, no live calls
SOURCE = {"house_text": "text", "exterior": "photo", "radiator": "photo", "bill": "bill", "listing": "listing"}
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
    if mime == "application/pdf":
        return {"type": "document",
                "source": {"type": "base64", "media_type": "application/pdf", "data": base64.b64encode(data).decode()}}
    from PIL import Image, ImageOps
    im = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("RGB")
    im.thumbnail((1568, 1568))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=85)
    return {"type": "image",
            "source": {"type": "base64", "media_type": "image/jpeg", "data": base64.b64encode(buf.getvalue()).decode()}}


def _num(s: str) -> float:
    return float(re.sub(r"[.,](?=\d{3}\b)", "", s).replace(",", "."))


WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "zwei": 2, "drei": 3, "vier": 4, "fünf": 5}


def keyword_house(text: str) -> HouseTextObs:
    """Fallback for the text step when cache and API are both missing."""
    o, low = HouseTextObs(), text.lower()

    def put(f, v, quote):
        if v is not None:
            setattr(o, f, v)
            o.evidence[f], o.confidence[f] = quote, 0.5
    m = re.search(r"\b(1[89]\d\d|20[0-2]\d)\b", text)
    put("build_year", int(m.group(1)) if m else None, m and m.group(0))
    m = re.search(r"(\d[\d.,]*)\s*(m²|m2|qm|sqm|square met)", low)
    put("living_area_m2", _num(m.group(1)) if m else None, m and m.group(0))
    m = re.search(r"(\d[\d.,]*)\s*kwh", low)
    if m:
        put("yearly_use_value", _num(m.group(1)), m.group(0))
        o.yearly_use_unit = "kWh"
    m = re.search(r"(\d+)\s*(radiators|heizkörper)", low)
    put("radiator_count", int(m.group(1)) if m else None, m and m.group(0))
    m = re.search(r"(\d+)\s*(people|persons|personen)|(\w+) of us|zu (\w+)", low)
    if m:
        n = m.group(1) or WORDS.get(m.group(3) or "") or WORDS.get((m.group(4) or "").replace("dritt", "drei"))
        put("occupants", int(n) if n else None, m.group(0))
    fuel = fuel_from(None, low)
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


def read_obs(data: bytes, mime: str, mission: str):
    """→ (kind, obs). 'bill' may come back as 'listing'. Cache → LLM → keywords (text only)."""
    key = hashlib.sha256(mission.encode() + data).hexdigest()[:20]
    cache = load_json(CACHE)
    if key in cache:
        kind = cache[key]["kind"]
        return kind, MISSION_MODELS[kind].model_validate(cache[key]["obs"])
    if mission == "house_text":
        tools = [tool_schema("record_house", HouseTextObs)]
        content = [{"type": "text", "text": HINT[mission] + "\n\nText:\n" + data.decode("utf-8", "replace")}]
    elif mission in ("bill", "listing"):
        tools = [tool_schema("record_bill", BillObs), tool_schema("record_listing", ListingObs)]
        content = [_media_block(data, mime), {"type": "text", "text": HINT["bill"]}]
    else:
        tools = [tool_schema(f"record_{mission}", MISSION_MODELS[mission])]
        content = [_media_block(data, mime), {"type": "text", "text": HINT[mission]}]
    try:
        if DEMO_ONLY:
            raise RuntimeError("demo mode: not in cache")
        name, inp = llm_tool(content, tools, SYSTEM)
        kind = TOOL_KIND.get(name, mission)
        obs = MISSION_MODELS[kind].model_validate(inp)
    except Exception as e:
        if mission != "house_text":
            raise RuntimeError(f"could not read the {mission}: {e}") from e
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
            field = ("annual_fuel_kwh" if "kwh" in u else "monthly_advance_eur" if ("eur" in u or "€" in u)
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
        if d["era_from"] and d["era_to"]:      # rough era only fills an empty year (merge: text wins)
            put("build_year", (d["era_from"] + d["era_to"]) // 2, "era_from", cap=0.3)
            h.evidence["build_year"] = f"photo looks like {d['era_from']}-{d['era_to']}"
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
        put("fuel_type", fuel_from(d["bill_carrier"], None), "bill_carrier")
        put("annual_fuel_kwh", d["kwh_printed"], "kwh_printed")   # raw printed value; engine scales the period
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


def extract(file_bytes: bytes, mime: str, mission: str) -> House:
    kind, obs = read_obs(file_bytes, mime, mission)
    return obs_to_house(kind, obs)
```

- [ ] **Step 2: Verify the text mission (live call, then cached)**

Run: `.venv/Scripts/python.exe -c "import extract as X;h=X.extract(open('assets/demo/house_persona_en.txt','rb').read(),'text/plain','house_text');print(h.build_year,h.living_area_m2,h.building_type,h.renovation,h.fuel_type,h.annual_fuel_kwh,h.occupants,h.radiator_count,h.radiator_size,h.source)"`
Expected: `1972 140.0 terraced partially gas 18000.0 3 10 large {…'text'…}` (radiator_size may be `large` or `None`; confidence of it ≤ 0.5).

- [ ] **Step 3: Verify the bill (PDF) and a radiator photo**

Run: `.venv/Scripts/python.exe -c "import extract as X;b=X.extract(open('assets/demo/bill_demo_gas_2025.pdf','rb').read(),'application/pdf','bill');print(b.kwh_printed,b.m3,b.zustandszahl,b.brennwert,b.fuel_type,b.period_start,b.period_end,b.bill_total_eur)"`
Expected: `18002.0 1651.0 0.9523 11.45 gas 2025-01-01 2025-12-31 2462.12`

Run: `.venv/Scripts/python.exe -c "import extract as X;[print(f, X.extract(open('data/pipe_photos/'+f,'rb').read(),'image/jpeg','radiator').pipe_system) for f in ('05_zweirohr-vermutet_kompakt.jpeg','07_unklar_bad-multiblock.jpeg')]"`
Expected: `05… two_pipe` and `07… None` (07 must stay unknown). If 07 comes back with a value, tighten `HINT['radiator']` and delete its entry from `samples/cached_extract.json` before rerunning.

- [ ] **Step 4: Verify the keyword fallback**

Run: `.venv/Scripts/python.exe -c "import extract as X;o=X.keyword_house(open('assets/demo/house_persona_en.txt',encoding='utf-8').read());print(o.build_year,o.living_area_m2,o.yearly_use_value,o.radiator_count,o.occupants,o.fuel_type,o.renovation)"`
Expected: `1972 140.0 18000.0 10 3 gas partially`

- [ ] **Step 5: Commit**

```bash
git add extract.py samples/cached_extract.json
git commit -m "extract: per-mission tool calls with cache and text fallback"
```

---

### Task 4: `merge` — source priority and conflicts

**Files:**
- Modify: `extract.py` (append at the end)

- [ ] **Step 1: Append `merge` to `extract.py`**

```python
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
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool):
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
```

- [ ] **Step 2: Verify bill beats text on use, text beats photo on year, and the oil/gas conflict is logged**

Run:
```bash
.venv/Scripts/python.exe -c "
import extract as X
t=X.extract(open('assets/demo/house_conflict_en.txt','rb').read(),'text/plain','house_text')
b=X.extract(open('assets/demo/bill_demo_gas_2025.pdf','rb').read(),'application/pdf','bill')
m=X.merge(X.merge(X.House(), t), b)
print(m.fuel_type, m.source['fuel_type'], m.build_year, m.source['build_year'])
print(m.conflicts)"
```
Expected: `gas bill 1985 text` and a conflict `{'field': 'fuel_type', 'values': {'text': 'oil', 'bill': 'gas'}, 'used': 'bill'}` (a second conflict on `annual_fuel_kwh` only if the text gave a number).

- [ ] **Step 3: Commit**

```bash
git add extract.py samples/cached_extract.json
git commit -m "extract: merge by source priority with conflict log"
git push
```

---

### Task 5: Demo cache for every demo input

**Files:**
- Modify: `samples/cached_extract.json` (generated)

- [ ] **Step 1: Read every demo input once**

Run:
```bash
.venv/Scripts/python.exe -c "
import extract as X, glob
jobs=[(p,'text/plain','house_text') for p in glob.glob('assets/demo/house_*.txt')]
jobs+=[('assets/demo/bill_demo_gas_2025.pdf','application/pdf','bill'),('assets/demo/bill_demo_gas_2025_photo.jpg','image/jpeg','bill'),('assets/demo/listing_demo_reihenhaus_1994.png','image/png','bill')]
jobs+=[(p,'image/jpeg','radiator') for p in glob.glob('data/pipe_photos/*.jp*g')]
for p,mime,m in jobs:
    try: k,o=X.read_obs(open(p,'rb').read(),mime,m); print('ok',k,p)
    except Exception as e: print('FAIL',p,e)"
```
Expected: 12 `ok` lines; the listing PNG prints `ok listing …`.

- [ ] **Step 2: Check the listing and the photo bill**

Run: `.venv/Scripts/python.exe -c "import extract as X;h=X.extract(open('assets/demo/listing_demo_reihenhaus_1994.png','rb').read(),'image/png','bill');print(h.build_year,h.living_area_m2,h.rooms,h.certificate_kwh_m2a,h.renovation);b=X.extract(open('assets/demo/bill_demo_gas_2025_photo.jpg','rb').read(),'image/jpeg','bill');print(b.kwh_printed,b.m3)"`
Expected: `1994 128.0 5 128.0 partially` and `18002.0 1651.0`

- [ ] **Step 3: Commit**

```bash
git add samples/cached_extract.json
git commit -m "demo cache: all demo inputs and organiser radiator photos"
git push
```

---

### Task 6: App skeleton, theme and the Evaluation tab

**Files:**
- Create: `.streamlit/config.toml`
- Replace: `app.py`

- [ ] **Step 1: Theme**

`.streamlit/config.toml`:

```toml
[theme]
primaryColor = "#14213D"
backgroundColor = "#F3F5F7"
secondaryBackgroundColor = "#FFFFFF"
textColor = "#14213D"
font = "sans serif"
```

- [ ] **Step 2: Write `app.py` (shared helpers, answer card, Evaluation; Homeowner and Installer filled in Tasks 7-8)**

```python
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


def tab_homeowner():
    st.info("Homeowner wizard: Task 7.")


def tab_installer():
    st.info("Installer sheet: Task 8.")


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
```

- [ ] **Step 3: Run it**

Run: `.venv/Scripts/streamlit.exe run app.py`
Expected without `engine.py`: Evaluation shows "Engine not ready yet … B-01, B-02, B-03, B-04, B-05", the details selector works, the AI quotes for B-02 show "A wood stove is used all winter". With the friend's stub or engine: the table has 5 rows and the answer card renders for the selected building. No red exception box in either case.

- [ ] **Step 4: Commit**

```bash
git add app.py .streamlit/config.toml
git commit -m "app: theme, answer card, Evaluation tab"
git push
```

---

### Task 7: Homeowner wizard (4 steps + answer)

**Files:**
- Modify: `app.py` (replace `def tab_homeowner(): …` stub)

- [ ] **Step 1: Replace the `tab_homeowner` stub with the wizard**

Replace

```python
def tab_homeowner():
    st.info("Homeowner wizard: Task 7.")
```

with

```python
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
```

- [ ] **Step 2: Run the happy path**

Run: `.venv/Scripts/streamlit.exe run app.py`, then in the Homeowner tab: "Use the example text" → "Read it" (chips: 1972 · 140 m² · terraced · partially renovated · gas · 18,000 kWh · 3 people · 10 radiators) → Next → pick `05_zweirohr-vermutet_kompakt.jpeg` (chip two pipe) → Next → "Use the demo bill photo" (chip 18,002 kWh printed) → Next → step 4 rows show sources text / photo / bill and "✓ No questions for you" → "Show my answer".
Expected: answer card (or "Engine not ready yet" without the engine), request panel with three fields and "Open as e-mail". Time the flow: under 3 minutes with Demo mode on.

- [ ] **Step 3: Run the two edge cases**

Restart the app (fresh session). Type the text of `assets/demo/house_conflict_en.txt`, skip the radiator, use the demo bill.
Expected at step 4: one question "Your text says oil, your bill says gas. Which one is it?".
Fresh session with `assets/demo/house_minimal_en.txt`: step 4 shows "Built" with pill `missing`; with the engine the answer is "Yellow · Can't tell yet".

- [ ] **Step 4: Commit**

```bash
git add app.py
git commit -m "app: homeowner wizard, step-4 confirmations, request panel"
git push
```

---

### Task 8: Installer tab

**Files:**
- Modify: `app.py` (replace `def tab_installer(): …` stub)

- [ ] **Step 1: Replace the stub**

Replace

```python
def tab_installer():
    st.info("Installer sheet: Task 8.")
```

with

```python
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
```

- [ ] **Step 2: Run**

Run: `.venv/Scripts/streamlit.exe run app.py` → Installer tab → B-04, then B-03.
Expected with the engine: B-04 badge "Hold: not without changes", single-pipe items in "Check on site"; B-03 "Short visit with parts", valves 12, unused top floor in the checklist. Without the engine: "Engine not ready yet".

- [ ] **Step 3: Commit**

```bash
git add app.py
git commit -m "app: installer prep sheet"
git push
```

---

### Task 9: Smoke check and handoff

- [ ] **Step 1: Run `/check`** (CLAUDE.md slash command) and report the result to Junwoo in Korean.

- [ ] **Step 2: Tell `potatohater8` what the UI reads**, so nothing renders empty: `Result.reason`, `p_*`, `required_flow_temp_c`, `heat_load_kw`, `heat_load_bill_kw`, `open_checks`, `contradictions`, `trace`, `next_step`, `visit_type`, `parts`, `installer_checklist`, `path_to_yellow`, `lead_score`, and `calibrate.leave_one_out(...)` columns `building_id`, `error_pct`.

---

## Self-review notes

- Spec coverage: loader mapping table rows (all CSV columns) → Task 1; notes LLM main path + quotes + cache + negation-aware fallback → Tasks 1-2; missions house_text / exterior / radiator / bill / listing with retake tip → Task 3; source priority + conflicts → Task 4; Demo-mode cache → Tasks 5-6; Evaluation tab (tiles, table, details, AI quotes, B-04/B-05 answer cards) → Task 6; wizard, step-4 questions (≤ 2), answer card rows, next-step button, request panel (mailto, PDF via engine) → Task 7; Installer tab → Task 8. Engine steps 0-10 physics are out of scope (owner `potatohater8`).
- Not covered here on purpose: `handover_pdf` itself (step 10, agreed later), CSV batch upload (P2), entropy question (P1).
- Names checked across tasks: `X.extract`, `X.merge`, `X.read_obs`, `X.DEMO_ONLY`, `House.conflicts`, `House.retake_tip`, `home_house`, `request_panel`, `answer_card`, `rechenweg`, `VISIT`, `COL`.
