"""
Vertical-band projection — map ordered 2D segment labels onto 3D parts.

Image-based segmentation providers (the HF router; the Vultr-hosted segformer / SAM / CLIPSeg
models) return 2D segment labels with no camera matrix to back-project onto the mesh. The shared
approximation, used by every such provider: order the parts bottom→top by centroid height, split
that ordering into N bands (N = number of labels), and assign each band's parts to the matching
label. Documented as refine-later in the mask system spec.
"""

from __future__ import annotations

import numpy as np

# Distinct, legible region colours reused across categorical segmentation masks.
DEFAULT_PALETTE = ["#34C0AD", "#D9A84C", "#7E8AA0", "#E0694F", "#6E8B7A", "#A088B0", "#B58A5A"]


def znorm(parts) -> list[tuple[str, float]]:
    """Each part id with its centroid height normalised to [0,1] (bottom→top)."""
    cents = [(p["id"], float(np.asarray(p.get("centroid", [0, 0, 0]), float)[2])) for p in parts]
    if not cents:
        return []
    zs = [z for _, z in cents]
    lo, hi = min(zs), max(zs)
    span = (hi - lo) or 1.0
    return [(pid, (z - lo) / span) for pid, z in cents]


def band_regions(parts, labels, palette: list[str] | None = None) -> dict:
    """Project ordered segment ``labels`` onto ``parts`` by vertical band.

    Returns the categorical-mask ``data`` shape: ``{"regions": [{label, color, part_ids}, ...]}``.
    Empty/duplicate labels collapse to the same region; an empty label list degrades to a single
    ``"region"`` covering everything.
    """
    palette = palette or DEFAULT_PALETTE
    labels = list(labels) or ["region"]
    ordered = sorted(znorm(parts), key=lambda kv: kv[1])  # bottom → top
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
