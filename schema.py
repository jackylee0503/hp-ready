"""The contract. Every field is defined here once (CLAUDE.md principle 5).

Inputs: loader / extract fill `House`. Output: engine fills `Result`.
The LLM only fills *Obs models (raw values + evidence quote + confidence), never Result.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

# ---------------------------------------------------------------- enums

Color = Literal["green", "yellow", "red"]
TrafficLight = Literal["green", "yellow", "red", "unclear"]
VerdictBasis = Literal["likely_suitable", "checks_remain", "cannot_tell_yet", "obstacle"]
ReasonCategory = Literal["temperature", "insulation_first", "pipe_system"]
Renovation = Literal["unrenovated", "partially", "fully"]
HeatDistribution = Literal["radiators", "underfloor", "mixed"]
FuelType = Literal["gas", "lpg", "oil", "district", "electric"]
PipeSystem = Literal["two_pipe", "single_pipe"]  # unknown = None
RadiatorSize = Literal["small", "medium", "large"]
BuildingType = Literal["detached", "semi_detached", "terraced", "apartment"]
ExtraHeat = Literal["wood_stove", "tiled_stove", "heat_pump", "none"]
VisitType = Literal["remote_quote", "visit_with_parts", "hold"]
JazBucket = Literal["underfloor", "le55", "55to60", "gt60"]
Source = Literal["data", "text", "photo", "bill", "listing", "confirmed",
                 "notes_llm", "rule", "prior", "form"]          # form = page-1 form (owner-entered)
MissingReason = Literal["not_visible", "blurry", "ambiguous", "wrong_object"]
Mission = Literal["house_text", "exterior", "radiator", "bill", "listing"]

# ---------------------------------------------------------------- fixed assumptions (challenge, do not change)

PRICE_EUR_KWH = {"electricity": 0.26, "gas": 0.11, "lpg": 0.11, "oil": 0.17}
OIL_EUR_L = 1.70
OIL_KWH_PER_L = 10.0
GAS_KWH_PER_M3_DEFAULT = 10.0          # organiser value when Zustandszahl/Brennwert missing
JAZ = {"underfloor": 4.0, "le55": 3.5, "55to60": 2.8}   # >60: none (cost shown at 2.8 as lower bound)
BAND_GREEN_MAX_C = 55.0
BAND_YELLOW_MAX_C = 60.0
DISPLAY_CLIP_C = 70.0

# Heating load W/m² by age band: (max_year, unrenovated, partially, fully) — engine step 2
W_PER_M2 = [
    (1978, 130, 80, 50),
    (1994, 85, 70, 50),
    (2001, 80, 55, 50),
    (2015, 50, 50, 50),
    (9999, 35, 35, 35),
]
# Organiser guardrail bands shown beside the value in the Rechenweg
W_PER_M2_ORGANISER_BAND = {
    1978: "unrenovated before 1979: 120-180 · renovated: 40-60",
    1994: "1980s-1990s: 80-120 · renovated: 40-60",
    2001: "1980s-1990s: 80-120 · renovated: 40-60",
    2015: "built 2002+: 40-60",
    9999: "low-energy / new build: 15-40",
}
# Wall U-value reference by age band (estimated); below 0.7 × this → partially renovated
U_WALL_REF = [(1978, 1.0), (1994, 0.6), (2001, 0.5), (2015, 0.35), (9999, 0.24)]

# Radiator Φ_n at 75/65/20 °C in kW: point, Monte Carlo low, high (Kermi/Buderus EN 442)
RADIATOR_KW = {"small": (0.7, 0.5, 0.9), "medium": (1.5, 1.3, 1.7), "large": (2.2, 2.0, 2.7)}
RADIATOR_SIZE_PRIOR = {"small": 0.25, "medium": 0.5, "large": 0.25}   # estimated
RADIATOR_EXPONENT = 1.3
FLOW_SPREAD_K = 8.0
UNDERFLOOR_FLOW_C = (35.0, 40.0)

FULL_LOAD_HOURS = {"low": 1800, "mid": 2000, "high": 2100}   # organiser
DHW_KWH_PER_PERSON = 1000.0                                   # organiser
SPECIFIC_LOAD_HINT_W_M2 = 75.0                                # organiser threshold

# ---------------------------------------------------------------- LLM observations (parser output only)


class NotesObs(BaseModel):
    """Facts from free-text notes. `evidence[field]` = one-line quote, `confidence[field]` = 0..1."""
    u_values: dict[str, float] = {}           # windows, wall, roof, floor, basement (W/m²K)
    extra_heat_source: Optional[ExtraHeat] = None
    extra_source_all_winter: Optional[bool] = None
    solar_thermal_dhw: Optional[bool] = None
    unheated_area_note: Optional[str] = None
    insulation_measures: Optional[list[str]] = None   # [] = explicitly "no insulation" (with quote)
    glazing: Optional[str] = None
    building_type: Optional[BuildingType] = None
    evidence: dict[str, str] = {}
    confidence: dict[str, float] = {}
    method: Literal["llm", "cache", "keywords"] = "keywords"


class HouseTextObs(BaseModel):
    """Mission house_text (wizard 1/4). Raw values as written; units are not converted."""
    build_year: Optional[int] = None
    living_area_m2: Optional[float] = None
    building_type: Optional[BuildingType] = None
    renovation: Optional[Renovation] = None
    renovation_hints: list[str] = []
    heat_distribution: Optional[HeatDistribution] = None
    fuel_type: Optional[FuelType] = None
    yearly_use_value: Optional[float] = None
    yearly_use_unit: Optional[str] = None      # "kWh", "l", "m3", "EUR/month" as written
    occupants: Optional[int] = None
    radiator_count: Optional[int] = None
    radiator_size_words: Optional[str] = None  # e.g. "the big flat ones"
    radiator_size: Optional[RadiatorSize] = None
    boiler_condensing: Optional[bool] = None
    notes: NotesObs = NotesObs()
    evidence: dict[str, str] = {}
    confidence: dict[str, float] = {}


class ExteriorObs(BaseModel):
    building_type: Optional[BuildingType] = None
    era_from: Optional[int] = None
    era_to: Optional[int] = None               # always low confidence
    windows: Optional[str] = None
    facade_insulation_visible: Optional[bool] = None
    outdoor_unit_space: Optional[bool] = None
    outdoor_unit_note: Optional[str] = None
    evidence: dict[str, str] = {}
    confidence: dict[str, float] = {}
    missing: dict[str, MissingReason] = {}
    retake_tip: Optional[str] = None


class RadiatorObs(BaseModel):
    panel_type: Optional[Literal["11", "22", "33"]] = None
    radiator_size: Optional[RadiatorSize] = None
    valve_type: Optional[str] = None
    pipe_system: Optional[PipeSystem] = None   # None = unknown, never a guess
    pipe_reason: Optional[str] = None
    evidence: dict[str, str] = {}
    confidence: dict[str, float] = {}
    missing: dict[str, MissingReason] = {}
    retake_tip: Optional[str] = None


class BillObs(BaseModel):
    """Raw numbers only; m³ → kWh happens in the engine."""
    bill_carrier: Optional[str] = None         # as printed
    kwh_printed: Optional[float] = None
    m3: Optional[float] = None
    zustandszahl: Optional[float] = None
    brennwert: Optional[float] = None
    liters: Optional[float] = None
    period_start: Optional[str] = None         # ISO date
    period_end: Optional[str] = None
    bill_total_eur: Optional[float] = None     # display only
    monthly_advance_eur: Optional[float] = None
    evidence: dict[str, str] = {}
    confidence: dict[str, float] = {}
    missing: dict[str, MissingReason] = {}
    retake_tip: Optional[str] = None


class ListingObs(BaseModel):
    build_year: Optional[int] = None
    living_area_m2: Optional[float] = None
    rooms: Optional[int] = None
    building_type: Optional[BuildingType] = None
    fuel_type: Optional[FuelType] = None
    certificate_type: Optional[Literal["verbrauch", "bedarf"]] = None
    certificate_kwh_m2a: Optional[float] = None
    certificate_area_m2: Optional[float] = None   # A_N if printed
    modernisation_notes: list[str] = []
    evidence: dict[str, str] = {}
    confidence: dict[str, float] = {}


MISSION_MODELS = {"house_text": HouseTextObs, "exterior": ExteriorObs,
                  "radiator": RadiatorObs, "bill": BillObs, "listing": ListingObs}


class ImageCheck(BaseModel):
    """Output of image-validation.js (CONTRACT.md). Says whether a photo is usable, never what it means."""
    expected: Literal["radiator", "bill", "exterior"]
    usable: bool
    reason: Literal["ok", "blurry", "too_dark", "too_bright", "too_small", "wrong_object",
                    "unreadable", "unsupported_type"] = "ok"
    retake_tip: Optional[str] = None           # one concrete sentence when not usable
    width_px: Optional[int] = None
    height_px: Optional[int] = None
    sharpness: Optional[float] = None          # module-defined (e.g. Laplacian variance); higher = sharper
    brightness: Optional[float] = None         # mean 0..1
    radiator: Optional[RadiatorObs] = None     # optional: what the module could tell about a radiator photo

MISSION_TEXTS = {
    "house_text": ("Tell us about your house", "Year, size, heating. Whatever you know."),
    "exterior": ("Photo of the outside", "Optional. Rough is fine."),
    "radiator": ("Your biggest radiator", "From the side, pipes in view."),
    "bill": ("Bill or listing?", "Optional. Photo, PDF or screenshot."),
    "listing": ("Bill or listing?", "Optional. Photo, PDF or screenshot."),
}

# ---------------------------------------------------------------- House (engine input)


class House(BaseModel):
    """All value fields Optional: unknown stays None (principle 2)."""
    building_id: Optional[str] = None
    # core
    build_year: Optional[int] = None
    living_area_m2: Optional[float] = None
    renovation: Optional[Renovation] = None
    heat_distribution: Optional[HeatDistribution] = None
    building_type: Optional[BuildingType] = None
    region: Optional[str] = None
    rooms: Optional[int] = None
    occupants: Optional[int] = None
    # energy. Fuel precedence for the engine (step 1): bill raw values below → annual_fuel_kwh
    # → annual_fuel_liters × 10 → monthly_advance_eur. annual_* hold only values stated per year (data, text).
    fuel_type: Optional[FuelType] = None
    annual_fuel_kwh: Optional[float] = None    # stated per year; never a bill's printed kWh
    annual_fuel_liters: Optional[float] = None # stated per year (oil)
    monthly_advance_eur: Optional[float] = None
    boiler_condensing: Optional[bool] = None
    dhw_by_boiler: Optional[bool] = None
    current_flow_temp_c: Optional[float] = None
    # distribution
    radiator_count: Optional[int] = None
    radiator_size: Optional[RadiatorSize] = None
    valves_to_replace: Optional[int] = None
    hydraulic_balanced: Optional[bool] = None
    pipe_system: Optional[PipeSystem] = None
    # envelope
    windows: Optional[str] = None
    roof_insulated: Optional[bool] = None
    walls_insulated: Optional[bool] = None
    # site flags (never red reasons)
    listed_building: Optional[bool] = None
    outdoor_unit_space: Optional[bool] = None
    flat_level_gas_heating: Optional[bool] = None
    # bill raw values, as printed for the bill period; the engine converts and scales to 365 days
    kwh_printed: Optional[float] = None
    m3: Optional[float] = None
    zustandszahl: Optional[float] = None
    brennwert: Optional[float] = None
    liters: Optional[float] = None
    period_start: Optional[str] = None
    period_end: Optional[str] = None
    bill_carrier: Optional[str] = None
    bill_total_eur: Optional[float] = None
    # listing / certificate
    certificate_kwh_m2a: Optional[float] = None
    certificate_area_m2: Optional[float] = None
    # free text
    notes: Optional[str] = None
    notes_obs: Optional[NotesObs] = None
    data_notes: list[str] = []                 # loader remarks, e.g. "preset valves, balancing to check"
    # provenance
    confidence: dict[str, float] = {}          # field -> 0..1
    source: dict[str, Source] = {}             # field -> where it came from
    evidence: dict[str, str] = {}              # field -> quote / image note
    missing: dict[str, MissingReason] = {}
    retake_tip: Optional[str] = None           # one concrete tip when a photo was unreadable
    conflicts: list[dict] = []                 # {field, values: {source: value}, used: source} from merge


# ---------------------------------------------------------------- Params (engine knobs)


class Params(BaseModel):
    k: float = 1.01                            # only calibrated value
    eta_default: float = 0.88                  # organiser: old boiler loses ~12 %
    eta_gas: dict[str, float] = {"condensing": 0.88, "non_condensing": 0.80}
    eta_oil: dict[str, float] = {"condensing": 0.95, "non_condensing": 0.85}
    dhw_kwh_per_person: float = DHW_KWH_PER_PERSON
    solar_dhw_factor: float = 0.5              # our assumption
    single_pipe_penalty_k: tuple[float, float] = (5.0, 10.0)
    unknown_pipe_penalty_k: tuple[float, float] = (0.0, 10.0)   # only built 1960-1979
    unused_area_factor: tuple[float, float, float] = (0.85, 0.7, 1.0)   # point, low, high
    load_spread: tuple[float, float] = (0.8, 1.2)
    radiator_jitter: tuple[float, float] = (0.85, 1.15)


DEFAULT = Params()

# ---------------------------------------------------------------- Result (engine output)


class Step(BaseModel):
    label: str
    value: str
    assumption: Optional[str] = None


class Range(BaseModel):
    p10: Optional[float] = None
    p50: Optional[float] = None
    p90: Optional[float] = None


class Contradiction(BaseModel):
    what: str
    sources: list[str] = []
    trusted: str = ""
    why: str = ""


class OpenCheck(BaseModel):
    item: str
    why: str = ""


class Parts(BaseModel):
    radiators_to_swap: Optional[tuple[int, int, int]] = None   # lo, mid, hi
    radiators_note: Optional[str] = None
    valves: Optional[int] = None
    balancing: Optional[Literal["needed", "check"]] = None


class NextStep(BaseModel):
    kind: Literal["quote", "site_check", "answer_question", "path_to_yellow"]
    label: str
    detail: str = ""


# Structured fields (2026-10-24): the engine fills numbers and kinds, the app writes the sentences.
# Optional for now: the app falls back to parsing the text fields above while they are empty.

class Option(BaseModel):
    """One way to reach 55 °C (step 6b). Numbers only; the app phrases it."""
    kind: Literal["radiators", "insulation", "pipe_loop", "none"]
    add_rated_kw_55: Optional[float] = None    # extra rated radiator output (75/65/20) needed for 55 °C
    add_rated_kw_60: Optional[float] = None
    rated_kw_today: Optional[float] = None
    loss_cut_pct: Optional[float] = None       # heat-loss reduction that reaches 55 °C with today's radiators
    note: str = ""                             # short extra in engine words, may stay empty


class RadiatorSummary(BaseModel):
    count: Optional[int] = None
    size_assumed: Optional[RadiatorSize] = None    # set when the size was not documented
    rated_kw: Optional[float] = None               # ΣΦ_n at 75/65/20 °C
    needed_rated_kw_55: Optional[float] = None     # ΣΦ_n needed to manage at 55 °C
    needed_rated_kw_60: Optional[float] = None
    share: Optional[float] = None                  # fraction of the load on the radiator circuit (mixed systems)
    margin_pct: Optional[float] = None             # (rated − needed_55) / needed_55 × 100


FlagSource = Literal["notes", "bill", "area_rooms", "not_documented", "data", "site"]
FlagKind = Literal["contradiction", "pipe", "radiators", "valves", "unused_area", "site", "other"]


class Flag(BaseModel):
    """A house-specific issue for the installer (never one of the always-checks)."""
    text: str                                  # one sentence, no "Check on site:" prefix
    src: FlagSource
    kind: FlagKind = "other"


class Result(BaseModel):
    building_id: Optional[str] = None
    # verdict
    best_color: Color = "yellow"
    traffic_light: TrafficLight = "unclear"
    verdict_basis: VerdictBasis = "cannot_tell_yet"
    boundary: bool = False
    reason: str = ""
    reason_category: Optional[ReasonCategory] = None
    p_green: float = 0.0
    p_yellow: float = 0.0
    p_red: float = 0.0
    # physics
    required_flow_temp_c: Range = Range()
    heat_load_kw: Range = Range()
    heat_load_bill_kw: Range = Range()          # low / mid / high over 2100 / 2000 / 1800 h
    specific_load_w_m2: Optional[float] = None
    jaz_bucket: Optional[JazBucket] = None
    path_to_yellow: list[str] = []
    # cost (fixed challenge prices only)
    cost_now_eur: Optional[float] = None
    cost_hp_eur: Optional[float] = None
    saving_eur: Optional[float] = None
    cost_note: Optional[str] = None
    # explain
    contradictions: list[Contradiction] = []
    site_flags: list[str] = []
    open_checks: list[OpenCheck] = []
    hints: list[str] = []
    next_question: Optional[str] = None
    trace: list[Step] = []
    # installer
    confidence: float = 0.0
    lead_score: float = 0.0
    visit_type: Optional[VisitType] = None
    parts: Parts = Parts()
    installer_checklist: list[str] = []
    next_photo: Optional[str] = None
    next_step: Optional[NextStep] = None
    # structured (preferred by the app when filled)
    options: list[Option] = []
    radiators: Optional[RadiatorSummary] = None
    flags: list[Flag] = []
    always_checks: list[str] = []


# ---------------------------------------------------------------- contract check

UI_FIELDS = ("reason", "required_flow_temp_c", "heat_load_kw", "open_checks", "trace", "visit_type", "next_step")


def check_result(h: "House", r: Result) -> list[str]:
    """Problems that would show as '–' or nonsense on screen. Empty list = fine. Never raises."""
    out: list[str] = []
    try:
        core = h.living_area_m2 is not None and h.build_year is not None
        s = r.p_green + r.p_yellow + r.p_red
        if core and abs(s - 1.0) > 0.02:
            out.append(f"probabilities sum to {s:.2f}, not 1")
        for name in ("required_flow_temp_c", "heat_load_kw", "heat_load_bill_kw"):
            rg = getattr(r, name)
            vals = [v for v in (rg.p10, rg.p50, rg.p90) if v is not None]
            if vals != sorted(vals):
                out.append(f"{name}: p10 ≤ p50 ≤ p90 broken ({rg.p10}, {rg.p50}, {rg.p90})")
        if core:
            for name in UI_FIELDS:
                v = getattr(r, name)
                if v in (None, "", []) or (isinstance(v, Range) and v.p50 is None):
                    out.append(f"{name} empty")
        if r.verdict_basis == "obstacle" and r.best_color != "red":
            out.append("verdict_basis obstacle but colour is not red")
        if r.best_color == "red" and r.verdict_basis == "cannot_tell_yet":
            out.append("missing data must be yellow, not red")
        if r.best_color != "green" and core and not (r.options or r.path_to_yellow):
            out.append("not green but no options / path_to_yellow")
        for f in r.flags:
            if f.text.lower().startswith("check on site"):
                out.append(f"flag text has a 'Check on site' prefix: {f.text[:40]}")
    except Exception as e:                      # the checker itself must never break the app
        out.append(f"check_result failed: {e}")
    return out


# ---------------------------------------------------------------- JSON contract for the JS modules (CONTRACT.md)

CONTRACT_VERSION = "1-draft"
CONTRACT_MODELS = {"house": House, "result": Result, "bill": BillObs, "image_check": ImageCheck}


def export_contracts(out_dir: str = "contracts") -> list[str]:
    """Write contracts/<name>.schema.json from the Pydantic models and contracts/examples/*.json
    from real data (current engine, cached reads). Re-run after any schema change."""
    import json
    from pathlib import Path
    root = Path(__file__).parent / out_dir
    (root / "examples").mkdir(parents=True, exist_ok=True)
    written = []

    def dump(path, obj):
        path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        written.append(str(path.relative_to(root.parent)))

    for name, model in CONTRACT_MODELS.items():
        s = model.model_json_schema()
        s["$id"] = f"hp-ready/{name}.schema.json"
        s["x-contract-version"] = CONTRACT_VERSION
        dump(root / f"{name}.schema.json", s)

    from loader import load_buildings                       # examples from real data, no API calls
    import engine
    for bid, h, _ in load_buildings():
        if bid in ("B-04", "B-05"):
            r = engine.installer_brief(h, engine.evaluate(h))
            dump(root / "examples" / f"calc_input_{bid}.json", {"house": h.model_dump(mode="json")})
            dump(root / "examples" / f"calc_output_{bid}.json", r.model_dump(mode="json"))
    form = House(building_id="form-example", build_year=1972, living_area_m2=140.0, building_type="terraced",
                 renovation="partially", heat_distribution="radiators", fuel_type="gas", annual_fuel_kwh=18000.0,
                 occupants=3, radiator_count=10, radiator_size="large", dhw_by_boiler=True)
    for f in ("build_year", "living_area_m2", "building_type", "renovation", "heat_distribution", "fuel_type",
              "annual_fuel_kwh", "occupants", "radiator_count", "radiator_size", "dhw_by_boiler"):
        form.source[f], form.confidence[f] = "form", 0.9
    dump(root / "examples" / "calc_input_form.json", {"house": form.model_dump(mode="json")})
    dump(root / "examples" / "bill_output_demo.json", BillObs(
        bill_carrier="Erdgas", kwh_printed=18002.0, m3=1651.0, zustandszahl=0.9523, brennwert=11.45,
        period_start="2025-01-01", period_end="2025-12-31", bill_total_eur=2462.12, monthly_advance_eur=205.0,
        evidence={"kwh_printed": "Verbrauch 18.002 kWh"}, confidence={"kwh_printed": 0.95}).model_dump(mode="json"))
    dump(root / "examples" / "image_check_ok.json", ImageCheck(
        expected="radiator", usable=True, width_px=1568, height_px=1176, sharpness=412.0, brightness=0.52
    ).model_dump(mode="json"))
    dump(root / "examples" / "image_check_blurry.json", ImageCheck(
        expected="radiator", usable=False, reason="blurry", width_px=1568, height_px=1176, sharpness=18.0,
        brightness=0.47, retake_tip="Hold the phone still and tap the radiator to focus, then take it again."
    ).model_dump(mode="json"))
    return written


if __name__ == "__main__":
    import sys
    if "--export-contracts" in sys.argv:
        for p in export_contracts():
            print("wrote", p)
