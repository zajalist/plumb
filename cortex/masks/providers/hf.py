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

import numpy as np

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


def _znorm(asset):
    """Each part id with its centroid height normalised to [0,1] (bottom→top)."""
    cents = [(p["id"], float(np.asarray(p.get("centroid", [0, 0, 0]), float)[2])) for p in asset.parts]
    if not cents:
        return []
    zs = [z for _, z in cents]
    lo, hi = min(zs), max(zs)
    span = (hi - lo) or 1.0
    return [(pid, (z - lo) / span) for pid, z in cents]


def _part_segmentation(asset, images) -> dict:
    segs = _hf_request(SEGMENT_MODEL, images[0])
    labels = [s.get("label", f"seg_{i}") for i, s in enumerate(segs)] or ["region"]
    palette = ["#34C0AD", "#D9A84C", "#7E8AA0", "#E0694F", "#6E8B7A", "#A088B0", "#B58A5A"]
    ordered = sorted(_znorm(asset), key=lambda kv: kv[1])  # bottom → top
    n = len(labels)
    regions: dict[str, dict] = {}
    for i, (pid, _zn) in enumerate(ordered):
        band = min(n - 1, int(i / max(1, len(ordered)) * n))
        lab = labels[band]
        r = regions.setdefault(lab, {"label": lab, "color": palette[band % len(palette)], "part_ids": []})
        r["part_ids"].append(pid)
    if not regions:
        regions["region"] = {"label": "region", "color": palette[0], "part_ids": []}
    return {"regions": list(regions.values())}


register(MaskProvider("part_segmentation", "Part segmentation", "hf", "physics", "categorical",
                      True, available, _part_segmentation))
