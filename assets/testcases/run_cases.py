"""Feed each test house's expected_house straight into the engine (no API needed) and compare with `expected`.

Run from the repo root:  python assets/testcases/run_cases.py
This checks the decision logic only. The readers (text parser, radiator photo, exterior photo) are checked by hand
against `expected_reads` in cases.json, by uploading the same inputs in the app.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from schema import House, NotesObs  # noqa: E402

try:
    import engine
except Exception as e:  # noqa: BLE001
    print("engine.py failed to import, using engine_tracer:", e)
    import engine_tracer as engine

HERE = Path(__file__).parent


def build(hd: dict, case_id: str) -> House:
    hd = dict(hd)
    notes = hd.pop("notes_obs", None)
    h = House(building_id=case_id, **hd)
    if notes:
        h.notes_obs = NotesObs(**notes)
    return h


def main() -> int:
    cases = json.loads((HERE / "cases.json").read_text(encoding="utf-8"))["cases"]
    fails = 0
    for c in cases:
        h = build(c["expected_house"], c["id"])
        r = engine.evaluate(h)
        want = c["expected"]["colour_any_of"]
        ok = r.best_color in want
        fails += not ok
        fl = r.required_flow_temp_c
        ld = r.heat_load_kw
        print(f"{'PASS' if ok else 'FAIL'} {c['id']} {c['title']}")
        print(f"     colour {r.best_color} ({r.verdict_basis})  want {'/'.join(want)}  "
              f"G/Y/R {r.p_green:.2f}/{r.p_yellow:.2f}/{r.p_red:.2f}")
        if fl:
            print(f"     flow p50 {fl.p50:.1f} °C ({fl.p10:.1f}-{fl.p90:.1f})", end="")
        if ld:
            print(f"   load p50 {ld.p50:.1f} kW", end="")
        print()
        print(f"     reason: {r.reason}")
        for x in r.contradictions:
            print(f"     ! {x.what} → trusted {x.trusted}")
        for s in r.site_flags:
            print(f"     ⚑ {s}")
        print(f"     open checks: {len(r.open_checks)} · must: {'; '.join(c['expected']['must'])}")
    print(f"\n{len(cases) - fails}/{len(cases)} colours as expected")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
