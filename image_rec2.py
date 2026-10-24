"""
site_checks.py — Zero-shot panel / house checks built on image_rec.py.

  elecCtrlPanelImgCheck(photos) -> panel-open | panel-closed-or-unsure
  houseSpaceImgCheck(photos)    -> suitable | likely-not-suitable | unknown

No training: each class is defined by text descriptions (prompts).
Reuses the CLIP model, image opening and image embedding from image_rec.py.

    from site_checks import elecCtrlPanelImgCheck, houseSpaceImgCheck
    panel = elecCtrlPanelImgCheck(["uploads/panel.jpg"])
    house = houseSpaceImgCheck("uploads/house.jpg")

CLI:
    python site_checks.py panel photo.jpg [--json]
    python site_checks.py house photo.jpg [--json]
"""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from typing import Any

import numpy as np

from image_rec import (
    CONFIDENCE_SCALE,
    UNKNOWN,
    ImageSource,
    PipeEvidence,
    _embed_one,
    _load,
    _open_image,
)

PANEL_OPEN = "panel-open"
PANEL_CLOSED = "panel-closed-or-unsure"
HOUSE_SUITABLE = "suitable"
HOUSE_NOT_SUITABLE = "likely-not-suitable"


@dataclass(frozen=True)
class Task:
    name: str
    prompts: dict[str, list[str]]   # verdict -> text descriptions
    min_prob: float                 # probability needed to commit to a verdict
    low_confidence_verdict: str     # answer when no class reaches min_prob


PANEL_TASK = Task(
    name="panel",
    prompts={
        PANEL_OPEN: [
            "a photo of an open electrical panel with the cover removed, showing circuit breakers and wiring inside",
            "a photo of the inside of a fuse box with the door open",
            "an electrical distribution board with open door and visible breakers",
        ],
        PANEL_CLOSED: [
            "a photo of a closed electrical panel cabinet with the door shut",
            "a photo of a metal fuse box cover on a wall",
            "a photo of a wall or room, no electrical panel interior visible",
        ],
    },
    min_prob=float(os.environ.get("PANEL_MIN_PROB", "0.65")),
    # Safe fallback: if we can't clearly see the insides, treat as not open.
    low_confidence_verdict=PANEL_CLOSED,
)

HOUSE_TASK = Task(
    name="house",
    prompts={
        HOUSE_SUITABLE: [
            "a photo of a house with a large lawn and lots of open garden space",
            "a detached house surrounded by a big yard with plenty of free space",
            "an aerial view of a house with a spacious garden",
        ],
        HOUSE_NOT_SUITABLE: [
            "a photo of a house with a very small yard or no garden",
            "a terraced house directly on the street with no outdoor space",
            "a house tightly surrounded by other buildings with hardly any free space",
        ],
    },
    min_prob=float(os.environ.get("HOUSE_MIN_PROB", "0.65")),
    low_confidence_verdict=UNKNOWN,  # no safe side: abstain rather than guess
)

# ---------------------------------------------------------------------------
# Text prototypes (computed once per task, cached)
# ---------------------------------------------------------------------------

_text_cache: dict[str, dict[str, np.ndarray]] = {}


def _text_prototypes(task: Task) -> dict[str, np.ndarray]:
    """Mean of the normalised prompt embeddings per verdict -> unit vectors."""
    if task.name in _text_cache:
        return _text_cache[task.name]

    import torch

    model, processor = _load()  # same model/processor as image_rec.py
    out: dict[str, np.ndarray] = {}
    for verdict, prompts in task.prompts.items():
        inputs = processor(text=prompts, return_tensors="pt", padding=True)
        with torch.inference_mode():
            text = model.text_model(
                input_ids=inputs["input_ids"],
                attention_mask=inputs["attention_mask"],
            )
            feats = model.text_projection(text.pooler_output)
        feats = feats / feats.norm(dim=-1, keepdim=True)
        proto = feats.mean(dim=0)
        proto = proto / proto.norm()
        out[verdict] = proto.cpu().numpy().astype(np.float32)
    _text_cache[task.name] = out
    return out


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


def _score(image, task: Task) -> dict[str, Any]:
    protos = _text_prototypes(task)
    emb = _embed_one(image)  # image_rec's embedding, L2-normalised
    sims = {v: float(np.dot(emb, p)) for v, p in protos.items()}

    logits = np.array([CONFIDENCE_SCALE * s for s in sims.values()])
    probs = np.exp(logits - logits.max())
    probs /= probs.sum()
    prob_by_verdict = dict(zip(sims.keys(), probs.tolist()))

    top = max(prob_by_verdict, key=prob_by_verdict.get)
    top_p = prob_by_verdict[top]

    if top_p >= task.min_prob:
        verdict, confidence = top, top_p
        reason = f"{top} matched description (p={top_p:.2f})"
    else:
        verdict, confidence = task.low_confidence_verdict, 0.5
        reason = f"no class reached p={task.min_prob:.2f} (best {top}: {top_p:.2f})"

    return {
        "probabilities": {k: round(v, 3) for k, v in prob_by_verdict.items()},
        "verdict": verdict,
        "confidence": round(float(confidence), 3),
        "reason": reason,
    }


def _run_task(task: Task, sources) -> tuple[list[dict[str, Any]], list[str]]:
    if not isinstance(sources, (list, tuple)):
        sources = [sources]

    per_photo: list[dict[str, Any]] = []
    signals: list[str] = []
    for index, source in enumerate(sources, start=1):
        try:
            result = _score(_open_image(source), task)
        except Exception as exc:  # a bad photo must never break the flow
            result = {
                "probabilities": {},
                "verdict": UNKNOWN,
                "confidence": 0.0,
                "reason": f"could not be analysed ({exc})",
            }
        result["photo"] = index
        per_photo.append(result)
        signals.append(f"photo {index}: {result['verdict']} — {result['reason']}")
    return per_photo, signals


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------


def elecCtrlPanelImgCheck(sources: ImageSource | list[ImageSource]) -> PipeEvidence:
    """Open (insides visible) vs closed/unsure. One confident 'open' photo wins."""
    if not sources:
        return PipeEvidence(PANEL_CLOSED, 0.0, [], ["no photos provided"])

    per_photo, signals = _run_task(PANEL_TASK, sources)
    open_hits = [r for r in per_photo if r["verdict"] == PANEL_OPEN]

    if open_hits:
        verdict = PANEL_OPEN
        confidence = max(r["confidence"] for r in open_hits)
        signals.append("control panel interior is visible")
    else:
        verdict = PANEL_CLOSED
        confidence = max(r["confidence"] for r in per_photo)
        signals.append("interior not clearly visible — ask for a photo with the panel open")
    return PipeEvidence(verdict, round(float(confidence), 3), per_photo, signals)


def houseSpaceImgCheck(sources: ImageSource | list[ImageSource]) -> PipeEvidence:
    """Lots of space vs not much. Conflicting / non-decisive photos -> unknown."""
    if not sources:
        return PipeEvidence(UNKNOWN, 0.0, [], ["no photos provided"])

    per_photo, signals = _run_task(HOUSE_TASK, sources)
    verdicts = [r["verdict"] for r in per_photo]
    ok, no = verdicts.count(HOUSE_SUITABLE), verdicts.count(HOUSE_NOT_SUITABLE)

    if ok and no:
        verdict, confidence = UNKNOWN, 0.5
        signals.append("photos give conflicting impressions of the available space")
    elif ok:
        verdict = HOUSE_SUITABLE
        confidence = max(r["confidence"] for r in per_photo if r["verdict"] == HOUSE_SUITABLE)
        signals.append("plenty of outdoor space visible — appears suitable")
    elif no:
        verdict = HOUSE_NOT_SUITABLE
        confidence = max(r["confidence"] for r in per_photo if r["verdict"] == HOUSE_NOT_SUITABLE)
        signals.append("limited outdoor space visible — a technician should confirm")
    else:
        verdict, confidence = UNKNOWN, 0.4
        signals.append("available space unclear from the photo")
    return PipeEvidence(verdict, round(float(confidence), 3), per_photo, signals)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _main() -> None:
    parser = argparse.ArgumentParser(description="Zero-shot panel / house photo checks")
    parser.add_argument("task", choices=["panel", "house"])
    parser.add_argument("images", nargs="+")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    fn = elecCtrlPanelImgCheck if args.task == "panel" else houseSpaceImgCheck
    evidence = fn(args.images)
    print(f"\nVerdict: {evidence.verdict.upper()} (confidence {evidence.confidence:.0%})\n")
    for s in evidence.signals:
        print(f"   • {s}")
    if args.json:
        print("\n" + json.dumps(evidence.to_dict(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    _main()