"""
cortex/bake/physical.py — the composition-aware physical bake (Task 3).

The headline bake. Given the convex parts from the geometric bake (Task 2) and a
per-part material assignment, compose the rigid-body properties that the gates
actually reason about:

  * **mass**    = Σ ρ·V           (each part's density from its material)
  * **CoM**     = Σ(ρ·V·c)/mass   (density-weighted — NOT the uniform centroid)
  * **inertia** = Σ parallel-axis(I_part, r)   the 3×3 tensor about the composite CoM

The density-weighting is the whole moat: a heavy small part stacked high on a light
wide part pulls the centre of mass *upward*, away from where a naive uniform-density
centroid would put it. That is exactly the "top-heavy" property the stability gate
later trips on. Volume-weighting the inertia/CoM (i.e. ignoring ρ) would silently
ship physics that can't topple — so we never do it.

Hollowness comes from an **interior ray test**: sample points inside the part's
bounding box and cast a ray; a point whose ray crosses the surface an odd number of
times is inside solid material. If most interior samples land in *empty* space the
part is hollow (a shell). The cast is a pure-`numpy` Möller–Trumbore so it works even
where ``trimesh.ray``'s accelerated backend (rtree/embree) is absent — the bake must
degrade gracefully (see plans/cortex-plan.md), never crash, never silently lie.

Canonical space everywhere: Z-up, right-handed, metres, kilograms.
"""

from __future__ import annotations

import numpy as np
import trimesh

from contracts import Physical

# Material → density table (kg/m³). "default" is the catch-all for unknown or
# unassigned parts so the bake always produces *some* honest mass.
MATERIAL_DENSITY: dict[str, float] = {
    # metals
    "aluminum": 2700.0, "aluminum_alloy": 2810.0, "steel": 7850.0, "stainless_steel": 8000.0,
    "cast_iron": 7200.0, "iron": 7870.0, "wrought_iron": 7750.0, "copper": 8960.0, "brass": 8500.0,
    "bronze": 8800.0, "gold": 19300.0, "silver": 10490.0, "lead": 11340.0, "titanium": 4500.0,
    "zinc": 7140.0, "nickel": 8900.0, "tin": 7280.0, "magnesium": 1740.0, "tungsten": 19250.0,
    "chromium": 7190.0, "pewter": 7300.0, "platinum": 21450.0, "rusted_steel": 7600.0,
    # wood
    "wood": 700.0, "oak": 750.0, "pine": 500.0, "balsa": 160.0, "bamboo": 400.0, "plywood": 600.0,
    "mahogany": 700.0, "birch": 670.0, "walnut": 650.0, "cedar": 380.0, "teak": 650.0, "maple": 700.0,
    "ash": 680.0, "beech": 720.0, "spruce": 450.0, "mdf": 750.0, "cork": 240.0, "driftwood": 500.0,
    "ebony": 1100.0, "rosewood": 850.0,
    # stone
    "stone": 2500.0, "granite": 2700.0, "marble": 2700.0, "limestone": 2600.0, "sandstone": 2300.0,
    "slate": 2800.0, "basalt": 3000.0, "quartz": 2650.0, "obsidian": 2600.0, "flint": 2600.0,
    "gneiss": 2700.0, "pumice": 640.0,
    # masonry
    "concrete": 2400.0, "brick": 1900.0, "plaster": 1200.0, "mortar": 2200.0, "terracotta": 2000.0,
    "adobe": 1600.0, "cinderblock": 1350.0, "stucco": 1850.0, "asphalt": 2240.0,
    # glass / ceramic
    "glass": 2500.0, "tempered_glass": 2500.0, "porcelain": 2400.0, "ceramic": 2300.0, "clay": 1900.0,
    "stoneware": 2300.0, "earthenware": 2100.0, "enamel": 2400.0,
    # plastic
    "plastic": 1100.0, "abs": 1050.0, "pvc": 1400.0, "nylon": 1150.0, "polycarbonate": 1200.0,
    "acrylic": 1180.0, "polyethylene": 950.0, "polypropylene": 905.0, "polystyrene": 1040.0,
    "resin": 1200.0, "epoxy": 1150.0, "bakelite": 1300.0, "melamine": 1500.0, "teflon": 2200.0,
    # rubber / foam
    "rubber": 1100.0, "silicone": 1100.0, "neoprene": 1230.0, "foam": 50.0, "eva_foam": 90.0,
    "latex": 920.0, "vinyl": 1300.0, "styrofoam": 30.0,
    # fabric
    "fabric": 300.0, "cotton": 400.0, "wool": 350.0, "leather": 900.0, "felt": 300.0, "canvas": 450.0,
    "denim": 480.0, "silk": 350.0, "burlap": 320.0, "velvet": 400.0, "suede": 850.0,
    # organic
    "paper": 800.0, "cardboard": 700.0, "bone": 1800.0, "ivory": 1850.0, "wax": 900.0, "charcoal": 400.0,
    "horn": 1300.0, "shell": 2700.0, "coral": 1500.0, "chitin": 1300.0, "hide": 950.0,
    # composite
    "carbon_fiber": 1600.0, "fiberglass": 1900.0, "kevlar": 1440.0, "particleboard": 700.0,
    "laminate": 1350.0, "gypsum": 800.0,
    # earth
    "sand": 1600.0, "gravel": 1700.0, "dirt": 1300.0, "soil": 1300.0, "mud": 1800.0, "peat": 400.0,
    # liquid / ice
    "water": 1000.0, "ice": 917.0, "snow": 250.0, "oil": 900.0,
    # precious / gem
    "diamond": 3500.0, "ruby": 4000.0, "sapphire": 4000.0, "emerald": 2760.0, "amber": 1060.0,
    "jade": 3300.0, "amethyst": 2650.0,
    "default": 1000.0,
}

# Interior-ray sampling for the hollowness test.
_HOLLOW_SAMPLES = 400
# Fraction of interior sample points that must read *solid* for the part to count
# as solid. Below this the part is a shell (mostly empty interior) → hollow.
_HOLLOW_SOLID_THRESHOLD = 0.5
# Deterministic RNG seed so the bake is reproducible run-to-run.
_HOLLOW_SEED = 0


def density_for(material: str | None) -> float:
    """Density for a material name, falling back to ``"default"`` when unknown."""
    if material is None:
        return MATERIAL_DENSITY["default"]
    return MATERIAL_DENSITY.get(material, MATERIAL_DENSITY["default"])


def bake_physical(
    parts: list[trimesh.Trimesh],
    part_materials: dict,
) -> Physical:
    """Compose mass / CoM / inertia / hollowness over the convex ``parts``.

    ``part_materials`` maps a part key → material name. The key may be the part's
    integer index (``0, 1, …``) as produced by the geometric bake; any part with no
    entry defaults to material ``"default"``. Returns the frozen :class:`Physical`
    contract object (canonical space, kg / metres).
    """
    if not parts:
        raise ValueError("bake_physical requires at least one convex part")

    masses: list[float] = []
    coms: list[np.ndarray] = []
    inertias: list[np.ndarray] = []

    for index, part in enumerate(parts):
        material = _material_for_part(part_materials, index)
        rho = density_for(material)

        # trimesh computes mass properties at the part's assigned density; setting
        # ``density`` rescales mass and the (about-its-own-CoM) inertia tensor.
        part.density = rho
        masses.append(float(part.mass))
        coms.append(np.asarray(part.center_mass, dtype=float))
        inertias.append(np.asarray(part.moment_inertia, dtype=float))

    total_mass = float(sum(masses))
    if total_mass <= 0:
        raise ValueError("composite mass is non-positive; degenerate parts")

    # Density-weighted centre of mass (mass already folds ρ·V).
    com = np.zeros(3)
    for m, c in zip(masses, coms):
        com += m * c
    com /= total_mass

    inertia = _compose_inertia(masses, coms, inertias, com)

    hollow = _is_hollow(parts)

    return Physical(
        mass_kg=total_mass,
        com=[float(x) for x in com],
        inertia=[[float(v) for v in row] for row in inertia],
        hollow=bool(hollow),
        conf=0.5,
    )


# --------------------------------------------------------------------------- #
# Internals
# --------------------------------------------------------------------------- #
def _material_for_part(part_materials: dict, index: int) -> str:
    """Resolve a part's material name, defaulting to ``"default"``.

    Accepts the part's integer index or its string form as the key so callers can
    pass either ``{0: "bronze"}`` or ``{"0": "bronze"}``.
    """
    if not part_materials:
        return "default"
    if index in part_materials:
        return part_materials[index]
    if str(index) in part_materials:
        return part_materials[str(index)]
    return "default"


def _compose_inertia(
    masses: list[float],
    coms: list[np.ndarray],
    inertias: list[np.ndarray],
    com: np.ndarray,
) -> np.ndarray:
    """Sum part inertias about the composite CoM via the parallel-axis theorem.

    Each part's ``I_part`` is taken about its own CoM. Shifting it to the composite
    CoM adds ``m · (‖r‖² E₃ − r⊗r)`` where ``r`` is the offset between the part CoM
    and the composite CoM. The result is symmetric with a positive diagonal.
    """
    total = np.zeros((3, 3))
    for m, c, ip in zip(masses, coms, inertias):
        r = com - c
        shift = m * (float(np.dot(r, r)) * np.eye(3) - np.outer(r, r))
        total += ip + shift
    # Symmetrise to wipe any floating-point asymmetry from the part tensors.
    return 0.5 * (total + total.T)


def _is_hollow(parts: list[trimesh.Trimesh]) -> bool:
    """True when the parts are mostly empty inside (a shell), via interior rays.

    Sample points inside each watertight part's bounding box and cast a +Z ray;
    odd surface-crossing count ⇒ the point sits in solid material. If the solid
    fraction across all sampled interior points falls below the threshold the asset
    is hollow. Non-watertight parts give no reliable inside/outside test, so a part
    that contributes no usable samples is treated as solid (the conservative read).
    """
    rng = np.random.default_rng(_HOLLOW_SEED)
    solid_hits = 0
    total = 0

    for part in parts:
        if not part.is_watertight:
            # Open surface → parity test is meaningless; skip (counts as solid).
            continue
        triangles = np.asarray(part.triangles, dtype=float)
        if len(triangles) == 0:
            continue
        lo, hi = part.bounds
        span = hi - lo
        # Inset away from the surface so boundary points don't dominate the parity.
        pts = rng.uniform(lo + 0.02 * span, hi - 0.02 * span, size=(_HOLLOW_SAMPLES, 3))
        crossings = _ray_triangle_crossings(pts, np.array([0.0, 0.0, 1.0]), triangles)
        inside = (crossings % 2) == 1
        solid_hits += int(inside.sum())
        total += len(pts)

    if total == 0:
        return False  # nothing testable → don't claim hollow
    return (solid_hits / total) < _HOLLOW_SOLID_THRESHOLD


def _ray_triangle_crossings(
    origins: np.ndarray,
    direction: np.ndarray,
    triangles: np.ndarray,
) -> np.ndarray:
    """Count forward ray/triangle intersections per origin (Möller–Trumbore).

    ``origins`` is ``(N, 3)``; all rays share ``direction``; ``triangles`` is
    ``(M, 3, 3)``. Returns an ``(N,)`` int array of how many triangles each ray
    pierces in the positive direction. Pure ``numpy`` so it needs no accelerated
    ray backend (the env here ships trimesh without rtree/embree).
    """
    eps = 1e-9
    d = direction / np.linalg.norm(direction)

    v0 = triangles[:, 0, :]
    v1 = triangles[:, 1, :]
    v2 = triangles[:, 2, :]
    e1 = v1 - v0
    e2 = v2 - v0

    pvec = np.cross(d, e2)                     # (M, 3)
    det = np.einsum("mj,mj->m", e1, pvec)      # (M,)
    parallel = np.abs(det) <= eps
    inv_det = np.where(parallel, 0.0, 1.0 / np.where(parallel, 1.0, det))

    counts = np.zeros(len(origins), dtype=int)
    for i, o in enumerate(origins):
        tvec = o - v0                          # (M, 3)
        u = np.einsum("mj,mj->m", tvec, pvec) * inv_det
        qvec = np.cross(tvec, e1)              # (M, 3)
        v = np.einsum("j,mj->m", d, qvec) * inv_det
        t = np.einsum("mj,mj->m", e2, qvec) * inv_det
        hit = (
            (~parallel)
            & (u >= -eps)
            & (v >= -eps)
            & (u + v <= 1.0 + eps)
            & (t > eps)
        )
        counts[i] = int(hit.sum())
    return counts
