"""
cortex/bake/materials.py — per-part material masks (the bake's semantic layer).

The geometric bake (CoACD) splits an asset into convex parts; each part is a
**mask**. This module attaches semantics to those masks:

  * ``guess_materials(parts)`` — one honest, deliberately low-confidence material
    *guess* per part, from geometry alone. There is no VLM here, so every guess is
    ``source="default"``: a weak prior meant to *seed* the AI-guess → human-confirm
    → lock loop (``contracts.MaterialGuess`` / ``conscience.confirm``), not to be
    trusted as fact. The human confirms or overrides; only then does it drive mass.
  * ``describe_parts(...)`` — the per-part detail the studio renders as masks
    (volume fraction, the material shown, a distinct mask colour, hollowness). The
    *quantitative* fields (volume, fraction) are measured, never guessed; the mass a
    part contributes uses the material physics actually used (default until a human
    confirms), so the parts always reconcile with ``PAP.physical.mass_kg``.

Plan ref: cortex-plan.md ("VLM/heuristic detect"); spec §5.5 (PAP) / §8.2 (regions).
Honesty rule (project-wide): never silently lie — guesses are labelled low-conf and
never alter physics until confirmed.
"""

from __future__ import annotations

import trimesh

from contracts import MaterialGuess
from cortex.bake.physical import density_for

__all__ = ["guess_materials", "describe_parts", "MASK_PALETTE"]

# Distinct, muted mask colours (one per part, by index) — the *visual* masks.
# Material colour is a separate, semantic swatch chosen by the studio.
MASK_PALETTE: list[str] = [
    "#8E9A60", "#C2A24E", "#7E8A9A", "#C16A4A",
    "#6E8B7A", "#A0879A", "#B58A5A", "#7C8AA0",
    "#9A8C5E", "#5E8A86", "#A07A6A", "#8A9A7C",
]


def part_id(index: int) -> str:
    """Stable id for a part mask, e.g. ``part_00``."""
    return f"part_{index:02d}"


def _features(part: trimesh.Trimesh) -> dict:
    """Geometry-only features for one convex part (all measured, none guessed)."""
    vol = float(abs(part.volume))
    ext = sorted(float(e) for e in part.bounding_box.extents)  # [min, mid, max]
    bbox_vol = (ext[0] * ext[1] * ext[2]) or 1e-9
    return {
        "vol": vol,
        "fill": vol / bbox_vol,                 # 1≈fills its box; low≈thin/shell
        "elong": ext[2] / (ext[0] or 1e-9),     # long/limb-like when >> 1
        "flat": ext[0] / (ext[2] or 1e-9),      # platey/base-like when << 1
        "cz": float(part.center_mass[2]),       # height of the part's centroid
    }


def guess_materials(parts: list[trimesh.Trimesh]) -> list[MaterialGuess]:
    """One honest, low-confidence material guess per convex part (``source="default"``).

    These are weak geometric priors — a thin shell *might* be glass, a broad low
    slab *might* be a stone base — emitted only to seed the confirm loop. They are
    never trusted as fact and never touch physics until a human confirms them.
    """
    feats = [_features(p) for p in parts]
    if not feats:
        return []

    vmax = max(f["vol"] for f in feats) or 1e-9
    zlo = min(f["cz"] for f in feats)
    zspan = (max(f["cz"] for f in feats) - zlo) or 1e-9

    guesses: list[MaterialGuess] = []
    for i, f in enumerate(feats):
        rel_v = f["vol"] / vmax
        rel_z = (f["cz"] - zlo) / zspan          # 0 low … 1 high
        mat, conf = "default", 0.50
        if f["fill"] < 0.30 and f["elong"] < 3.0:
            mat, conf = "glass", 0.40            # thin shell / vessel
        elif f["elong"] > 3.0:
            mat, conf = "wood", 0.36             # beam / limb / handle
        elif rel_v > 0.60 and f["flat"] < 0.45 and rel_z < 0.50:
            mat, conf = "stone", 0.46            # broad, low base / plinth
        elif rel_v < 0.40 and f["fill"] > 0.50 and rel_z > 0.50:
            mat, conf = "bronze", 0.40           # compact detail sitting high
        guesses.append(MaterialGuess(part=part_id(i), mat=mat, conf=conf, source="default"))
    return guesses


def describe_parts(
    parts: list[trimesh.Trimesh],
    physics_materials: dict,
    shown_materials: dict[int, tuple[str, float, str, bool]],
) -> list[dict]:
    """Per-part mask detail for the studio (plain dicts — outside the frozen contract).

    ``physics_materials`` is the index→material map the physical bake actually used
    (empty on an auto-bake ⇒ every part is ``"default"``), so each part's reported
    mass reconciles with ``PAP.physical.mass_kg``. ``shown_materials`` maps a part
    index → ``(material, conf, source, confirmed)`` — the material to *display*
    (authored/confirmed at conf 1.0, else the guess at its low conf).
    """
    masses, vols = [], []
    for i, p in enumerate(parts):
        vol = float(abs(p.volume))
        phys_mat = physics_materials.get(i, physics_materials.get(str(i), "default"))
        vols.append(vol)
        masses.append(vol * density_for(phys_mat))
    total_vol = sum(vols) or 1e-9
    total_mass = sum(masses) or 1e-9

    detail: list[dict] = []
    for i, p in enumerate(parts):
        mat, conf, source, confirmed = shown_materials.get(i, ("default", 0.5, "default", False))
        ext = [float(e) / 2.0 for e in p.bounding_box.extents]
        detail.append({
            "id": part_id(i),
            "idx": i,
            "material": mat,
            "conf": round(float(conf), 2),
            "source": source,
            "confirmed": bool(confirmed),
            "volume_m3": vols[i],
            "vol_frac": vols[i] / total_vol,
            "mass_kg": masses[i],
            "mass_frac": masses[i] / total_mass,
            "hollow": bool(not p.is_watertight),   # open per-part surface ≈ shell
            "centroid": [float(x) for x in p.center_mass],
            "extent": ext,
            "color": MASK_PALETTE[i % len(MASK_PALETTE)],
        })
    return detail
