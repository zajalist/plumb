"""
HuggingFace mask provider — the ML source, via HF Inference Providers.

HF retired the old ``api-inference.huggingface.co`` serverless host for the
``router.huggingface.co/hf-inference`` Inference-Providers router; only a curated set of
models is served there. ``part_segmentation`` uses ``segformer`` (image-segmentation,
confirmed served). Token resolves like the Gemini key: env ``HF_TOKEN`` /
``HUGGINGFACEHUB_API_TOKEN`` with a gitignored ``.hf_token`` repo-root fallback.

Per-part projection without a camera matrix is approximate: parts are assigned to a segment
label by vertical band (centroid height → image band). Documented as refine-later.
"""

from __future__ import annotations

import json
import os
import urllib.request
from pathlib import Path

from ..banding import band_regions
from ..registry import MaskProvider, register

SEGMENT_MODEL = os.environ.get("PLUMB_HF_SEGMENT_MODEL", "nvidia/segformer-b0-finetuned-ade-512-512")
_ROUTER = "https://router.huggingface.co/hf-inference/models"
_KEY_FILE = Path(__file__).resolve().parents[3] / ".hf_token"


def _hf_token() -> str | None:
    env = os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACEHUB_API_TOKEN")
    if env:
        return env
    try:
        return _KEY_FILE.read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def available() -> bool:
    return bool(_hf_token())


def _hf_request(model: str, image_bytes: bytes):
    """The mockable network seam — POST an image, return the parsed JSON response."""
    req = urllib.request.Request(
        f"{_ROUTER}/{model}", data=image_bytes,
        headers={"Authorization": f"Bearer {_hf_token()}", "Content-Type": "image/png"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _part_segmentation(asset, images) -> dict:
    segs = _hf_request(SEGMENT_MODEL, images[0])
    labels = [s.get("label", f"seg_{i}") for i, s in enumerate(segs)]
    return band_regions(asset.parts, labels)


register(MaskProvider("part_segmentation", "Part segmentation", "hf", "physics", "categorical",
                      True, available, _part_segmentation))
