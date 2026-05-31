"""
Gemini mask providers — the AI-reasoning source.

Gemini reasons semantically (no geometry), so we bind its output to parts by simple
spatial heuristics: ``fragility`` arrives as top/middle/bottom band scores → mapped to each
part by its height band; ``affordances`` arrive as verb + coarse location → placed as a
labelled marker at a representative part centroid. Reuses ``studio.semantics`` for the
client + key (incl. the ``.gemini_key`` fallback), so availability tracks the same gate the
UI already shows.
"""

from __future__ import annotations

import numpy as np

from ..registry import MaskProvider, register

# the mockable seam (tests monkeypatch this)
try:
    from studio.semantics import gemini_status as _gemini_status
    from studio.semantics import semantic_masks as _semantic_masks
except Exception:  # studio not importable in some contexts → degrade to unavailable
    def _gemini_status() -> dict:
        return {"available": False}

    def _semantic_masks(images, hint=""):
        raise RuntimeError("gemini unavailable")


def available() -> bool:
    try:
        return bool(_gemini_status().get("available"))
    except Exception:
        return False


def _bands(asset):
    """Return (part_id -> 'top'|'middle'|'bottom') by centroid height thirds."""
    cents = [(p["id"], float(np.asarray(p.get("centroid", [0, 0, 0]), float)[2])) for p in asset.parts]
    if not cents:
        return {}
    zs = [z for _, z in cents]
    lo, hi = min(zs), max(zs)
    span = (hi - lo) or 1.0
    out = {}
    for pid, z in cents:
        t = (z - lo) / span
        out[pid] = "bottom" if t < 1 / 3 else ("middle" if t < 2 / 3 else "top")
    return out


def _where_centroid(asset, where: str) -> list:
    cents = [np.asarray(p.get("centroid", [0, 0, 0]), float) for p in asset.parts]
    if not cents:
        return [0.0, 0.0, 0.0]
    C = np.array(cents)
    mean = C.mean(axis=0)
    if where == "top":
        return C[np.argmax(C[:, 2])].tolist()
    if where in ("base", "bottom"):
        return C[np.argmin(C[:, 2])].tolist()
    if where == "side":
        return C[np.argmax(np.abs(C[:, 0] - mean[0]))].tolist()
    return mean.tolist()  # center / unknown


def _fragility(asset, images) -> dict:
    res = _semantic_masks(images, "")
    band_score = {b["band"]: float(b.get("score", 0.0)) for b in res.get("fragility", [])
                  if isinstance(b, dict) and "band" in b}
    bands = _bands(asset)
    vals = {pid: band_score.get(b, 0.0) for pid, b in bands.items()} or {"part_00": 0.0}
    lo, hi = float(min(vals.values())), float(max(vals.values()))
    return {"per_part": vals, "range": [lo, max(hi, lo + 1e-6)], "ramp": "inferno",
            "confidence": res.get("confidence")}


def _affordances(asset, images) -> dict:
    res = _semantic_masks(images, "")
    points = []
    for a in res.get("affordances", []):
        if not isinstance(a, dict):
            continue
        verb = str(a.get("verb", "act"))
        points.append({"pos": _where_centroid(asset, str(a.get("where", "center"))),
                       "label": verb, "kind": "affordance"})
    if not points:
        points.append({"pos": _where_centroid(asset, "center"), "label": "asset", "kind": "affordance"})
    return {"points": points, "confidence": res.get("confidence")}


register(MaskProvider("fragility", "Fragility", "gemini", "physics", "scalar",
                      True, available, _fragility))
register(MaskProvider("affordances", "Affordances", "gemini", "affordance", "markers",
                      True, available, _affordances))
