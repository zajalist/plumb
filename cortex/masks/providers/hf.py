"""
HuggingFace Inference API mask providers — the true-ML half of the source.

No local torch/transformers: these POST a rendered view to the HF Inference API and turn
the response into a per-part mask. The single network seam is ``_hf_request`` (mocked in
tests). Token resolves like the Gemini key: env ``HF_TOKEN`` / ``HUGGINGFACEHUB_API_TOKEN``
with a gitignored ``.hf_token`` repo-root fallback. Unavailable (no token) → the rail
greys the row out, exactly like the Gemini gate.

Per-part projection without a camera matrix is approximate: we sample the 2D model output
by the part's vertical band (centroid height → image row). Documented as refine-later in
the spec; the *shape* of the integration is what matters here.
"""

from __future__ import annotations

import io
import json
import os
import urllib.request
from pathlib import Path

import numpy as np

from ..registry import MaskProvider, register

SALIENCY_MODEL = os.environ.get("PLUMB_HF_SALIENCY_MODEL", "Intel/dpt-hybrid-midas")
SEGMENT_MODEL = os.environ.get("PLUMB_HF_SEGMENT_MODEL", "nvidia/segformer-b0-finetuned-ade-512-512")
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


def _post(model: str, image_bytes: bytes) -> bytes:
    req = urllib.request.Request(
        f"https://api-inference.huggingface.co/models/{model}",
        data=image_bytes,
        headers={"Authorization": f"Bearer {_hf_token()}", "Content-Type": "application/octet-stream"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read()


def _hf_request(kind: str, image_bytes: bytes):
    """The mockable seam. Returns a HxW float map (saliency) or list[{label,score}] (segments)."""
    if kind == "saliency":
        from PIL import Image
        raw = _post(SALIENCY_MODEL, image_bytes)
        img = Image.open(io.BytesIO(raw)).convert("L")
        arr = np.asarray(img, dtype=np.float32)
        return arr
    if kind == "segments":
        raw = _post(SEGMENT_MODEL, image_bytes)
        return json.loads(raw.decode("utf-8"))
    raise ValueError(kind)


def _znorm(asset) -> list[tuple[str, float]]:
    """Each part id with its centroid height normalised to [0,1] (bottom→top)."""
    cents = [(p["id"], float(np.asarray(p.get("centroid", [0, 0, 0]), float)[2])) for p in asset.parts]
    if not cents:
        return []
    zs = [z for _, z in cents]
    lo, hi = min(zs), max(zs)
    span = (hi - lo) or 1.0
    return [(pid, (z - lo) / span) for pid, z in cents]


def _saliency(asset, images) -> dict:
    smap = _hf_request("saliency", images[0])
    smap = (smap - smap.min()) / ((smap.max() - smap.min()) or 1.0)
    h = smap.shape[0]
    vals = {}
    for pid, zn in _znorm(asset):
        row = int(round((1.0 - zn) * (h - 1)))           # top of image = high z
        vals[pid] = float(smap[row].mean())
    if not vals:
        vals = {"part_00": 0.0}
    lo, hi = float(min(vals.values())), float(max(vals.values()))
    return {"per_part": vals, "range": [lo, hi], "ramp": "magma"}


def _part_segmentation(asset, images) -> dict:
    segs = _hf_request("segments", images[0])
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


register(MaskProvider("saliency", "Saliency", "hf", "artistic", "scalar",
                      True, available, _saliency))
register(MaskProvider("part_segmentation", "Part segmentation", "hf", "physics", "categorical",
                      True, available, _part_segmentation))
