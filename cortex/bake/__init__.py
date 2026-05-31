"""
cortex/bake/ — the asset bake pipeline.

  geometry.py  (Task 2) — load mesh -> AABB/OBB, volume, watertight, convex parts.
  physical.py  (Task 3) — composition-aware mass / CoM / inertia.
  materials.py          — per-part material masks (guesses) + part detail.
  __init__:bake_asset    (Task 3) — composes geometry + physical into a full PAP.
  __init__:bake_asset_detailed — bake + per-part mask detail for the studio UI.

Geometry is the first stage and the only one Task 2 owns; the convex parts it
produces are consumed by the physical bake, the material guesser, and the
collision gate.
"""

from __future__ import annotations

from contracts import PAP, MaterialPart, Provenance, Semantics
from cortex.bake.geometry import bake_geometry_parts
from cortex.bake.materials import describe_parts, guess_materials
from cortex.bake.physical import bake_physical

__all__ = ["bake_asset", "bake_asset_detailed"]


def _normalize_authored(part_materials: dict | None) -> dict:
    """Index→material map from authored input, accepting int, ``"0"`` or ``"part_00"`` keys."""
    if not part_materials:
        return {}
    out: dict[int, str] = {}
    for key, mat in part_materials.items():
        if isinstance(key, int):
            out[key] = mat
        else:
            s = str(key)
            if s.startswith("part_"):
                s = s[len("part_"):]
            try:
                out[int(s)] = mat
            except ValueError:
                continue
    return out


def _bake(
    asset_id: str,
    mesh_path: str,
    part_materials: dict | None,
    profile: str,
) -> tuple[PAP, list[dict]]:
    """Shared bake: geometry + physical + per-part material masks.

    With authored ``part_materials`` those materials drive physics and lock the
    affected fields (a human/agent signed off). With none, the bake stays a pure
    auto-bake — every part is ``"default"`` for *physics* (mass is honest, not
    guessed) while a low-confidence material *guess* per part seeds the confirm
    loop via ``semantics.materials``. Returns the PAP plus per-part mask detail.
    """
    geometry, parts, _flag = bake_geometry_parts(mesh_path)

    authored = _normalize_authored(part_materials)
    guesses = guess_materials(parts) if not authored else []

    # Physics uses authored materials only; guesses never alter mass until confirmed.
    physical = bake_physical(parts, authored)

    if authored:
        materials = [
            MaterialPart(part=f"part_{i:02d}", mat=mat, conf=1.0)
            for i, mat in sorted(authored.items())
        ]
        shown = {i: (mat, 1.0, "default", True) for i, mat in authored.items()}
        locked = ["physical.mass_kg", "physical.com", "physical.inertia", "semantics.materials"]
        auto = False
    else:
        materials = [MaterialPart(part=g.part, mat=g.mat, conf=g.conf) for g in guesses]
        shown = {i: (g.mat, g.conf, g.source, g.confirmed) for i, g in enumerate(guesses)}
        locked = []
        auto = True

    pap = PAP(
        asset_id=asset_id,
        profile=profile,
        geometry=geometry,
        semantics=Semantics(materials=materials),
        physical=physical,
        provenance=Provenance(auto=auto, edited_fields=[], locked=locked),
    )
    detail = describe_parts(parts, authored, shown)
    return pap, detail


def bake_asset(
    asset_id: str,
    mesh_path: str,
    part_materials: dict | None = None,
    profile: str = "rigid_prop",
) -> PAP:
    """Bake a full :class:`PAP` for an asset: geometry (T2) + physical (T3) + masks.

    Loads and decomposes the mesh once, feeds the same convex parts into the
    physical bake (so geometry and physics agree on the decomposition) and the
    material guesser (so every part carries a semantic mask). ``part_materials``
    maps a part key → material name; authored materials drive physics and are
    recorded in ``provenance.locked`` so a later guess never overwrites a confirmed
    choice. With none, the bake is a pure auto-bake (default-density physics +
    low-confidence per-part guesses).
    """
    return _bake(asset_id, mesh_path, part_materials, profile)[0]


def bake_asset_detailed(
    asset_id: str,
    mesh_path: str,
    part_materials: dict | None = None,
    profile: str = "rigid_prop",
) -> tuple[PAP, list[dict]]:
    """Same as :func:`bake_asset` but also returns the per-part mask detail the
    studio renders (volume fraction, displayed material + confidence, mask colour,
    hollowness). The detail is plain dicts — it lives outside the frozen contract."""
    return _bake(asset_id, mesh_path, part_materials, profile)
