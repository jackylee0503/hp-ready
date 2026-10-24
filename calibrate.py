"""Fit k on the dev buildings (one parameter, geometric mean of log ratios) + leave-one-out."""
from __future__ import annotations

import math

import pandas as pd

from engine import point_load, setup
from schema import DEFAULT, Params

K1 = DEFAULT.model_copy(update={"k": 1.0})


def _dev(buildings):
    """(id, load at k = 1 in kW, reference kW) for every building with a reference load and core data."""
    out = []
    for bid, h, ref in buildings:
        if not ref or ref.get("heating_load_kw") is None:
            continue
        load = point_load(setup(h, K1), K1)
        if load:
            out.append((bid, load, float(ref["heating_load_kw"])))
    return out


def _k(rows) -> float:
    return math.exp(sum(math.log(ref / load) for _, load, ref in rows) / len(rows)) if rows else DEFAULT.k


def fit(buildings) -> Params:
    return DEFAULT.model_copy(update={"k": round(_k(_dev(buildings)), 4)})


def leave_one_out(buildings) -> pd.DataFrame:
    rows = _dev(buildings)
    out = []
    for i, (bid, load, ref) in enumerate(rows):
        k = _k(rows[:i] + rows[i + 1:])
        pred = k * load
        out.append({"building_id": bid, "error_pct": round((pred - ref) / ref * 100, 1),
                    "k_fit": round(k, 3), "pred_kw": round(pred, 2), "ref_kw": ref})
    return pd.DataFrame(out, columns=["building_id", "error_pct", "k_fit", "pred_kw", "ref_kw"])


if __name__ == "__main__":
    from loader import load_buildings
    b = load_buildings(use_llm=False)
    print("k =", fit(b).k)
    print(leave_one_out(b).to_string(index=False))
