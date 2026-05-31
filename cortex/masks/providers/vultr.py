"""
Vultr-hosted mask providers — self-hosted HF models on a GPU box.

Where ``hf.py`` talks to HF's *curated* Inference-Providers router, this talks to **our own**
FastAPI server (``vultr/serve.py``) running on a Vultr GPU instance, which can host arbitrary /
heavier vision models: SAM-style instance segmentation, CLIPSeg text-prompted masks,
Depth-Anything depth, and a heavier segformer. Adding a model = one route on the box + one
``register(...)`` here.

The box is started / destroyed manually (hackathon $100 credit), so availability is gated on a
configured URL **and** a short-TTL-cached ``/health`` ping — these providers grey out in the rail
when the box is down. Config resolves like the HF/Gemini keys: env ``PLUMB_VULTR_URL`` /
``PLUMB_VULTR_TOKEN`` with gitignored ``.vultr_url`` / ``.vultr_token`` repo-root fallbacks.

Projection without a camera matrix stays the documented approximation shared with ``hf.py``:
segment labels map onto parts by vertical band (see ``cortex/masks/banding.py``); depth's grid
maps to a per-part scalar by the same height↔image-row correspondence.
"""

from __future__ import annotations

import json
import os
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlencode

import numpy as np

from ..banding import band_regions, znorm
from ..registry import MaskProvider, register

_URL_FILE = Path(__file__).resolve().parents[3] / ".vultr_url"
_TOKEN_FILE = Path(__file__).resolve().parents[3] / ".vultr_token"
_HEALTH_TTL = 30.0  # seconds — cache the health ping so catalog() (called per rail render) stays cheap
_health_cache: dict = {"t": -1e9, "ok": False, "url": None}


# --- config / availability -------------------------------------------------------------------

def _read_file(p: Path) -> str | None:
    try:
        return p.read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def _vultr_url() -> str | None:
    return os.environ.get("PLUMB_VULTR_URL") or _read_file(_URL_FILE)


def _vultr_token() -> str | None:
    return os.environ.get("PLUMB_VULTR_TOKEN") or _read_file(_TOKEN_FILE)


def _auth_headers(content_type: str | None = None) -> dict:
    h: dict[str, str] = {}
    tok = _vultr_token()
    if tok:
        h["Authorization"] = f"Bearer {tok}"
    if content_type:
        h["Content-Type"] = content_type
    return h


def _health_ok() -> bool:
    """Cached ``GET /health`` against the box (TTL-bounded so ``catalog()`` stays cheap)."""
    url = _vultr_url()
    if not url:
        return False
    now = time.monotonic()
    c = _health_cache
    if c["url"] == url and (now - c["t"]) < _HEALTH_TTL:
        return c["ok"]
    ok = False
    try:
        req = urllib.request.Request(f"{url.rstrip('/')}/health", headers=_auth_headers())
        with urllib.request.urlopen(req, timeout=5) as resp:
            ok = bool(json.loads(resp.read().decode("utf-8")).get("ok"))
    except Exception:
        ok = False
    _health_cache.update(t=now, ok=ok, url=url)
    return ok


def available() -> bool:
    return bool(_vultr_url()) and _health_ok()


# --- network seam (mocked in tests) ----------------------------------------------------------

def _vultr_request(task: str, image_bytes: bytes, params: dict | None = None):
    """POST a PNG (+ optional params as query string) to ``/<task>`` and return parsed JSON."""
    base = _vultr_url()
    if not base:
        raise RuntimeError("vultr url not configured")
    url = f"{base.rstrip('/')}/{task}"
    if params:
        url = f"{url}?{urlencode(params)}"
    req = urllib.request.Request(url, data=image_bytes, headers=_auth_headers("image/png"))
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8"))


# --- compute fns -----------------------------------------------------------------------------

def _labels(segs) -> list[str]:
    return [s.get("label", f"seg_{i}") for i, s in enumerate(segs or [])]


def _segmentation(task: str):
    """A categorical segmentation provider whose box route is ``task``."""
    def compute(asset, images) -> dict:
        segs = _vultr_request(task, images[0])
        return band_regions(asset.parts, _labels(segs))
    return compute


def _text_mask(asset, images) -> dict:
    prompt = str((asset.mask_params or {}).get("prompt", "")).strip()
    segs = _vultr_request("clipseg", images[0], {"prompt": prompt})
    # When the box returns no label, fall back to the prompt itself as the region name.
    labels = [s.get("label", prompt or f"seg_{i}") for i, s in enumerate(segs or [])]
    return band_regions(asset.parts, labels)


def _depth(asset, images) -> dict:
    """Monocular depth grid → per-part scalar by the height↔image-row correspondence.

    The box returns a downsampled depth ``grid`` (rows top→bottom of the render) + ``min``/``max``.
    Image rows map to world height: a part high in the scene reads the top rows. Each part takes
    the mean depth of the row matching its normalised height, giving a ``per_part`` scalar the
    existing scalar renderer shades with the ``viridis`` ramp.
    """
    res = _vultr_request("depth", images[0])
    grid = np.asarray(res.get("grid", []), dtype=float)
    lo, hi = float(res.get("min", 0.0)), float(res.get("max", 1.0))
    per_part: dict[str, float] = {}
    rows = grid.shape[0] if grid.ndim == 2 and grid.size else 0
    for pid, t in znorm(asset.parts):
        if rows:
            row = int(round((1.0 - t) * (rows - 1)))  # top of image (row 0) = top of object
            per_part[pid] = float(grid[row].mean())
        else:
            per_part[pid] = lo
    if not per_part:
        per_part = {"part_00": lo}
    return {"per_part": per_part, "range": [lo, max(hi, lo + 1e-6)], "ramp": "viridis"}


# --- registrations ---------------------------------------------------------------------------

register(MaskProvider("part_segmentation_hq", "Part segmentation (HQ)", "vultr", "physics",
                      "categorical", True, available, _segmentation("segment")))
register(MaskProvider("sam_parts", "SAM parts", "vultr", "physics",
                      "categorical", True, available, _segmentation("sam")))
register(MaskProvider("text_mask", "Text mask", "vultr", "physics",
                      "categorical", True, available, _text_mask))
register(MaskProvider("depth", "Depth", "vultr", "artistic",
                      "scalar", True, available, _depth))
