"""
image_rec.py — Few-shot CLIP prototype classifier for radiator pipe systems.

Two modes in one file:

  Train:     python image_rec.py --train data/pipe_photos
             Expects data/pipe_photos/<class>/*.jpg with class dirs
             single-pipe/, two-pipe/, ambiguous/.
             Builds prototypes.json (mean CLIP embedding per class, computed
             over original + augmented images) and prints a leave-one-out
             accuracy report + margin distribution to calibrate the threshold.

  Inference: python image_rec.py photo1.jpg [photo2.jpg ...] [--json]

Honesty contract:
  - Verdicts: two-pipe | single-pipe | unknown. 'ambiguous' top match or low
    margin -> unknown.
  - This only works if leave-one-out accuracy on your labelled photos is
    decent. If the printed report is poor, few-shot CLIP is not good enough
    for this task — fall back to a vision LLM instead of shipping it.

Install:
    pip install transformers torch pillow numpy

You can use it in other python files like this:
from image_rec import classify_pipes

evidence = classify_pipes([
    "uploads/radiator1.jpg",
    "uploads/radiator2.jpg"
])

print(evidence.verdict)
print(evidence.confidence)
print(evidence.signals)
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
from dataclasses import asdict, dataclass, field
from typing import Any, BinaryIO, Optional, Union

import numpy as np
from PIL import Image, ImageEnhance, ImageOps
from transformers import CLIPModel, CLIPProcessor

# ---------------------------------------------------------------------------
# Labels, thresholds, paths
# ---------------------------------------------------------------------------

TWO_PIPE = "two-pipe"
SINGLE_PIPE = "single-pipe"
AMBIGUOUS = "ambiguous"
UNKNOWN = "unknown"

# Cosine-similarity margins between CLIP image embeddings are SMALL
# (typically 0.01-0.10). Start at 0.02 and calibrate from the --train
# margin report. A margin below this -> unknown (abstain).
MARGIN_THRESHOLD = float(os.environ.get("PIPE_MARGIN_THRESHOLD", "0.02"))

# Softmax temperature used only to map similarities to a 0..1 confidence
# number for display. Does not affect the verdict.
CONFIDENCE_SCALE = 100.0

PROTOTYPES_PATH = os.environ.get("PIPE_PROTOTYPES", "prototypes.json")

# Number of augmented copies per labelled photo during training.
AUGMENT_PER_PHOTO = 12

RANDOM_SEED = 42

# ---------------------------------------------------------------------------
# Result contract (same shape your decision engine already consumes)
# ---------------------------------------------------------------------------


@dataclass
class PipeEvidence:
    verdict: str  # two-pipe | single-pipe | unknown
    confidence: float = 0.0
    per_photo: list[dict[str, Any]] = field(default_factory=list)
    signals: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Model loading (cached; Streamlit reruns must not reload this)
# ---------------------------------------------------------------------------

_model: Optional[CLIPModel] = None
_processor: Optional[CLIPProcessor] = None


def _load() -> tuple[CLIPModel, CLIPProcessor]:
    global _model, _processor
    if _model is None or _processor is None:
        model_id = os.environ.get("CLIP_MODEL", "openai/clip-vit-base-patch32")
        _model = CLIPModel.from_pretrained(model_id)
        _processor = CLIPProcessor.from_pretrained(model_id)
        _model.eval()
    return _model, _processor


# ---------------------------------------------------------------------------
# Image embedding — the heart of few-shot: CLIP image tower only, no text.
# ---------------------------------------------------------------------------

ImageSource = Union[str, os.PathLike[str], BinaryIO, Image.Image]


def _open_image(source: ImageSource) -> Image.Image:
    if isinstance(source, Image.Image):
        image = source.copy()
    else:
        image = Image.open(source)
    image = ImageOps.exif_transpose(image)
    if image.mode != "RGB":
        image = image.convert("RGB")
    return image


def _embed_many(images: list[Image.Image]) -> np.ndarray:
    """Embed a batch of images -> (n, 512) L2-normalised float32 array."""
    import torch

    model, processor = _load()
    inputs = processor(images=images, return_tensors="pt")
    with torch.inference_mode():
        # Call the vision tower + projection directly: get_image_features()
        # returns a ModelOutput instead of a tensor in newer transformers
        # versions, so this path is more stable across versions.
        vision = model.vision_model(pixel_values=inputs["pixel_values"])
        features = model.visual_projection(vision.pooler_output)
    features = features / features.norm(dim=-1, keepdim=True)
    return features.cpu().numpy().astype(np.float32)


def _embed_one(image: Image.Image) -> np.ndarray:
    return _embed_many([image])[0]


# ---------------------------------------------------------------------------
# Augmentation — multiplies a handful of labelled photos into a usable
# training set. Crops matter most: the discriminative signal is local
# (valve blocks, bypass ports, pipe runs), so random crops force the
# prototype to encode parts, not whole-room style.
# ---------------------------------------------------------------------------


def _augmentations(image: Image.Image, n: int, rng: random.Random) -> list[Image.Image]:
    out: list[Image.Image] = []
    width, height = image.size
    min_side = min(width, height)

    for _ in range(n):
        img = image

        # Random resized crop (60%-100% of the image), resized back to 224.
        scale = rng.uniform(0.60, 1.00)
        crop_w = max(64, int(width * scale))
        crop_h = max(64, int(height * scale))
        left = rng.randint(0, width - crop_w)
        top = rng.randint(0, height - crop_h)
        img = img.crop((left, top, left + crop_w, top + crop_h)).resize(
            (224, 224), Image.BILINEAR
        )

        # Horizontal flip (vertical pipes stay vertical; labels are safe).
        if rng.random() < 0.5:
            img = img.transpose(Image.FLIP_LEFT_RIGHT)

        # Small rotation.
        if rng.random() < 0.5:
            img = img.rotate(rng.uniform(-10, 10), resample=Image.BILINEAR)

        # Photometric jitter.
        if rng.random() < 0.7:
            img = ImageEnhance.Brightness(img).enhance(rng.uniform(0.8, 1.2))
        if rng.random() < 0.7:
            img = ImageEnhance.Contrast(img).enhance(rng.uniform(0.8, 1.2))
        if rng.random() < 0.5:
            img = ImageEnhance.Color(img).enhance(rng.uniform(0.6, 1.3))

        out.append(img)
    return out


# ---------------------------------------------------------------------------
# Training: build prototypes + leave-one-out validation in one pass
# ---------------------------------------------------------------------------


def _collect_labels(image_dir: str) -> dict[str, list[str]]:
    """Return {class_name: [image paths]} from <image_dir>/<class>/*.jpg."""
    labels: dict[str, list[str]] = {}
    for class_name in sorted(os.listdir(image_dir)):
        class_path = os.path.join(image_dir, class_name)
        if not os.path.isdir(class_path):
            continue
        files = [
            os.path.join(class_path, f)
            for f in sorted(os.listdir(class_path))
            if f.lower().endswith((".jpg", ".jpeg", ".png", ".webp"))
        ]
        if files:
            labels[class_name] = files
    return labels


def _prototype_from_embeddings(embeddings: np.ndarray) -> np.ndarray:
    """Mean of normalised embeddings, re-normalised -> unit prototype."""
    proto = embeddings.mean(axis=0)
    proto = proto / np.linalg.norm(proto)
    return proto.astype(np.float32)


def train(image_dir: str, out_path: str = PROTOTYPES_PATH) -> dict[str, Any]:
    """
    Build class prototypes from labelled photos, then validate honestly:

      1. Prototypes use originals + AUGMENT_PER_PHOTO augmented copies.
      2. Leave-one-out (LOO): each ORIGINAL photo is classified against
         prototypes rebuilt without that photo (originals only). LOO tells
         you whether few-shot CLIP separates your classes at all.
      3. Prints per-class accuracy, overall accuracy, and the LOO margin
         distribution -> use it to set PIPE_MARGIN_THRESHOLD.
    """
    rng = random.Random(RANDOM_SEED)
    labels = _collect_labels(image_dir)
    if not labels:
        raise SystemExit(f"no labelled images found under {image_dir}")

    print(f"classes found: { {k: len(v) for k, v in labels.items()} }")
    for class_name, files in labels.items():
        if len(files) < 3:
            print(
                f"WARNING: only {len(files)} photos for '{class_name}' — "
                "few-shot needs ~8-10+ per class; results will be shaky"
            )

    # 1) Embed originals (for LOO) and originals+augmentations (for deployment).
    original_embeddings: dict[str, list[np.ndarray]] = {}
    all_embeddings: dict[str, list[np.ndarray]] = {}

    for class_name, files in labels.items():
        original_embeddings[class_name] = []
        all_embeddings[class_name] = []
        for path in files:
            image = _open_image(path)
            orig = _embed_one(image)
            original_embeddings[class_name].append(orig)
            augmented = _augmentations(image, AUGMENT_PER_PHOTO, rng)
            batch = _embed_many([image] + augmented)
            all_embeddings[class_name].extend(list(batch))
        print(
            f"  {class_name}: {len(files)} photos -> "
            f"{len(all_embeddings[class_name])} training embeddings"
        )

    # 2) Prototypes for deployment (originals + augmentations).
    prototypes = {
        class_name: _prototype_from_embeddings(np.stack(embs))
        for class_name, embs in all_embeddings.items()
    }

    # 3) Leave-one-out validation (originals only, photo held out).
    correct = 0
    total = 0
    margins: list[tuple[str, float, str]] = []  # (true class, margin, predicted)
    confusion: dict[str, dict[str, int]] = {}

    for true_class, embs in original_embeddings.items():
        for i, emb in enumerate(embs):
            loo_prototypes = {}
            for class_name, class_embs in original_embeddings.items():
                if class_name == true_class and len(class_embs) > 1:
                    rest = [e for j, e in enumerate(class_embs) if j != i]
                    loo_prototypes[class_name] = _prototype_from_embeddings(
                        np.stack(rest)
                    )
                else:
                    loo_prototypes[class_name] = _prototype_from_embeddings(
                        np.stack(class_embs)
                    )
            sims = {
                cls: float(np.dot(emb, proto))
                for cls, proto in loo_prototypes.items()
            }
            ranked = sorted(sims.items(), key=lambda kv: kv[1], reverse=True)
            predicted, margin = ranked[0][0], ranked[0][1] - ranked[1][1]

            judged = predicted if margin >= MARGIN_THRESHOLD else UNKNOWN
            ok = judged == true_class or (
                judged == UNKNOWN and true_class == AMBIGUOUS
            )
            correct += int(ok)
            total += 1
            margins.append((true_class, margin, judged))
            confusion.setdefault(true_class, {})
            confusion[true_class][judged] = (
                confusion[true_class].get(judged, 0) + 1
            )

    print("\n--- leave-one-out report (originals only) ---")
    for true_class, counts in confusion.items():
        print(f"  true {true_class}: {counts}")
    print(f"  accuracy (unknown counts as correct for 'ambiguous'): "
          f"{correct}/{total} = {correct / max(total, 1):.0%}")

    print("\n--- LOO margins by true class (calibrate PIPE_MARGIN_THRESHOLD here) ---")
    for cls in labels:
        vals = [m for t, m, _ in margins if t == cls]
        if vals:
            print(
                f"  {cls}: min={min(vals):.4f} median="
                f"{sorted(vals)[len(vals) // 2]:.4f} max={max(vals):.4f}"
            )

    # 4) Save prototypes.
    payload = {
        "model": os.environ.get("CLIP_MODEL", "openai/clip-vit-base-patch32"),
        "classes": list(prototypes.keys()),
        "prototypes": {
            cls: [float(x) for x in proto] for cls, proto in prototypes.items()
        },
        "loo_accuracy": correct / max(total, 1),
        "margin_threshold": MARGIN_THRESHOLD,
    }
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh)
    print(f"\nprototypes written to {out_path}")
    return payload


# ---------------------------------------------------------------------------
# Inference
# ---------------------------------------------------------------------------

_prototypes_cache: Optional[dict[str, np.ndarray]] = None


def _load_prototypes(path: str = PROTOTYPES_PATH) -> dict[str, np.ndarray]:
    """Load prototypes.json -> {class: unit vector}. Cached per process."""
    global _prototypes_cache
    if _prototypes_cache is None:
        if not os.path.exists(path):
            raise FileNotFoundError(
                f"{path} not found — run: python image_rec.py --train <dir>"
            )
        with open(path, encoding="utf-8") as fh:
            payload = json.load(fh)
        _prototypes_cache = {
            cls: np.asarray(vec, dtype=np.float32)
            for cls, vec in payload["prototypes"].items()
        }
    return _prototypes_cache


def _score_one(image: Image.Image, prototypes: dict[str, np.ndarray]) -> dict[str, Any]:
    """Cosine similarity of the photo to each class prototype + decision."""
    emb = _embed_one(image)
    sims = {cls: float(np.dot(emb, proto)) for cls, proto in prototypes.items()}

    ranked = sorted(sims.items(), key=lambda kv: kv[1], reverse=True)
    (top_cls, top_sim), (_, second_sim) = ranked[0], ranked[1]
    margin = top_sim - second_sim

    if top_cls == AMBIGUOUS:
        verdict = UNKNOWN
        reason = "top match is the ambiguous class (valve block / cover)"
    elif margin >= MARGIN_THRESHOLD:
        verdict = top_cls
        reason = f"{top_cls} prototype closest (margin {margin:.3f})"
    else:
        verdict = UNKNOWN
        reason = f"margin {margin:.3f} below threshold {MARGIN_THRESHOLD:.3f}"

    # Map similarities to a display confidence. Softmax over scaled sims of
    # the two pipe classes; 'unknown' verdicts get capped at 0.5.
    pipe_classes = [c for c in sims if c in (TWO_PIPE, SINGLE_PIPE)]
    exps = [math.exp(CONFIDENCE_SCALE * sims[c]) for c in pipe_classes]
    denom = sum(exps)
    if verdict in pipe_classes:
        confidence = (
            math.exp(CONFIDENCE_SCALE * sims[verdict]) / denom
            if denom else 0.5
        )
        confidence = min(1.0, max(0.5, confidence))
    else:
        confidence = 0.5 if top_cls == AMBIGUOUS else 0.4

    return {
        "similarities": {k: round(v, 4) for k, v in sims.items()},
        "top_class": top_cls,
        "margin": round(margin, 4),
        "verdict": verdict,
        "confidence": round(confidence, 3),
        "reason": reason,
    }


def classify_pipes(sources: list[ImageSource]) -> PipeEvidence:
    """
    Combine per-photo prototype matches into one verdict.

      * any confident single-pipe hit  -> single-pipe
      * any confident two-pipe hit     -> two-pipe
      * confident hits for BOTH        -> unknown (conflicting evidence)
      * no confident hit              -> unknown (photos not decisive)
    """
    if not sources:
        return PipeEvidence(
            verdict=UNKNOWN,
            confidence=0.0,
            per_photo=[],
            signals=["no photos provided"],
        )

    try:
        prototypes = _load_prototypes()
    except FileNotFoundError as exc:
        return PipeEvidence(
            verdict=UNKNOWN,
            confidence=0.0,
            per_photo=[],
            signals=[f"image classifier not trained: {exc}"],
        )

    per_photo: list[dict[str, Any]] = []
    signals: list[str] = []
    votes: list[str] = []

    for index, source in enumerate(sources, start=1):
        try:
            image = _open_image(source)
            result = _score_one(image, prototypes)
        except Exception as exc:  # a bad photo must never break the flow
            result = {
                "similarities": {},
                "top_class": None,
                "margin": 0.0,
                "verdict": UNKNOWN,
                "confidence": 0.0,
                "reason": f"could not be analysed ({exc})",
            }
            signals.append(f"photo {index}: could not be analysed ({exc})")
        result["photo"] = index
        per_photo.append(result)

        if result["verdict"] in (SINGLE_PIPE, TWO_PIPE):
            votes.append(result["verdict"])
            signals.append(
                f"photo {index}: {result['verdict']} — {result['reason']}"
            )
        else:
            votes.append(UNKNOWN)
            signals.append(f"photo {index}: cannot decide — {result['reason']}")

    n_single = votes.count(SINGLE_PIPE)
    n_two = votes.count(TWO_PIPE)

    if n_single and n_two:
        verdict = UNKNOWN
        confidence = 0.5
        signals.append(
            "photos show conflicting pipe systems — technician must check"
        )
    elif n_single:
        verdict = SINGLE_PIPE
        confidence = max(
            r["confidence"] for r in per_photo if r["verdict"] == SINGLE_PIPE
        )
        signals.append(
            "single-pipe systems can often work with a heat pump, but usually "
            "need a higher flow temperature or larger radiators — "
            "technician check recommended"
        )
    elif n_two:
        verdict = TWO_PIPE
        confidence = max(
            r["confidence"] for r in per_photo if r["verdict"] == TWO_PIPE
        )
        signals.append(
            "photos indicate a two-pipe system; confirm the building-wide "
            "pipe layout before treating it as final"
        )
    else:
        verdict = UNKNOWN
        confidence = 0.4
        signals.append(
            "pipe system unclear from the photos — a technician should check "
            "whether it is a single-pipe system"
        )

    return PipeEvidence(
        verdict=verdict,
        confidence=round(float(confidence), 3),
        per_photo=per_photo,
        signals=signals,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _main() -> None:
    parser = argparse.ArgumentParser(
        description="Few-shot CLIP prototype classifier for pipe systems"
    )
    parser.add_argument("images", nargs="*", help="path(s) to radiator photo(s)")
    parser.add_argument(
        "--train", metavar="DIR",
        help="train prototypes from DIR/<class>/*.jpg and exit",
    )
    parser.add_argument(
        "--save", default=PROTOTYPES_PATH,
        help=f"prototypes output path (default: {PROTOTYPES_PATH})",
    )
    parser.add_argument("--json", action="store_true", help="print full JSON")
    args = parser.parse_args()

    if args.train:
        train(args.train, args.save)
        return

    if not args.images:
        parser.error("provide photo path(s), or --train DIR")

    evidence = classify_pipes(args.images)
    icons = {TWO_PIPE: "🟢", SINGLE_PIPE: "🟠", UNKNOWN: "⚪"}
    print(
        f"\n{icons[evidence.verdict]}  Verdict: {evidence.verdict.upper()}  "
        f"(confidence {evidence.confidence:.0%})\n"
    )
    for signal in evidence.signals:
        print(f"   • {signal}")
    if args.json:
        print("\n" + json.dumps(evidence.to_dict(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    _main()