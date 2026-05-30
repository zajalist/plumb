"""
PLUMB — Frozen Contracts (THE SEAM).

This file is the single agreement between the two halves of the build:

  Person A  ("the Cortex")     -> PRODUCES Verdicts from Diffs against a world of PAPs.
  Person B  ("the Conscience") -> RENDERS Verdicts and drives the agent loop.

RULE: Neither side imports the other's internals. They meet HERE, at the JSON.
If you need to change a schema, both people agree in the same sitting and we
bump SCHEMA_VERSION. Until then these shapes are law.

Schemas mirror PLUMB_master_spec.md §13 (Diff / Verdict), §5.5 (PAP).
"""

from __future__ import annotations

from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field

SCHEMA_VERSION = "0.1.0"


# --------------------------------------------------------------------------- #
# Diff  — the agent's proposal (spec §13)
# --------------------------------------------------------------------------- #
class Transform(BaseModel):
    """Canonical space: Z-up, right-handed, metres, kilograms."""
    pos: list[float] = Field(..., min_length=3, max_length=3)          # [x, y, z] metres
    quat: list[float] = Field([0, 0, 0, 1], min_length=4, max_length=4)  # [x, y, z, w]
    scale: list[float] = Field([1, 1, 1], min_length=3, max_length=3)


class Diff(BaseModel):
    """A proposed change to one object's transform."""
    object: str                      # node id in the world model, e.g. "bronze_figure_03"
    transform: Transform


# --------------------------------------------------------------------------- #
# Verdict — the gate stack as data; the entire UI renders from this (spec §13)
# --------------------------------------------------------------------------- #
class GateName(str, Enum):
    collision = "collision"
    stability = "stability"
    constraints = "constraints"
    reach = "reach"


class FixVector(BaseModel):
    """How to move to fix it. Translate in metres; optional rotation (quat delta)."""
    translate: list[float] = Field([0, 0, 0], min_length=3, max_length=3)
    rotate_quat: Optional[list[float]] = None  # [x, y, z, w] delta, if rotation helps


class GateResult(BaseModel):
    gate: GateName
    ok: Optional[bool] = None          # None when skipped
    skipped: bool = False
    # numeric headline — meaning depends on the gate:
    #   collision -> clearance_m (>=0 ok) or penetration as negative
    #   stability -> margin_m (CoM-over-polygon signed margin)
    #   reach     -> width_m of the tightest passage
    value_m: Optional[float] = None
    fix: Optional[FixVector] = None
    viz: Optional[str] = None          # viz hint, e.g. "com_outside_polygon"
    detail: Optional[str] = None       # human string, e.g. "62cm < 90cm"


class Verdict(BaseModel):
    """What validate_operation() returns. Never a bare 'no' — always why + which way."""
    schema_version: str = SCHEMA_VERSION
    ok: bool
    stopped_at: Optional[GateName] = None   # first hard-fail gate, None if all pass
    gates: list[GateResult]
    soft_cost: float = 0.0                  # accumulated soft-constraint cost


# --------------------------------------------------------------------------- #
# PAP — Physical Asset Profile (spec §5.5). The reusable baked artifact.
# --------------------------------------------------------------------------- #
class Geometry(BaseModel):
    obb: list[float] = []        # oriented bbox half-extents [hx, hy, hz]
    aabb: list[float] = []       # axis-aligned bbox half-extents
    volume_m3: float = 0.0
    convex_parts: int = 0
    watertight: bool = False


class MaterialPart(BaseModel):
    part: str
    mat: str
    conf: float = 0.5


class Semantics(BaseModel):
    cls: str = "unknown"
    up: list[float] = [0, 0, 1]
    front: list[float] = [0, 1, 0]
    materials: list[MaterialPart] = []
    affordances: list[str] = []
    conf: float = 0.5


class Physical(BaseModel):
    mass_kg: float = 1.0
    com: list[float] = [0, 0, 0]            # centre of mass, canonical
    inertia: list[list[float]] = []         # 3x3 tensor about com
    hollow: bool = False
    conf: float = 0.5


class Structural(BaseModel):
    """Experimental priors — NEVER hard-gated (spec §5.4, §17.3)."""
    support_footprint: list[list[float]] = []   # 2D hull of ground-contact points
    max_load_kg_est: Optional[float] = None
    experimental: bool = True


class Provenance(BaseModel):
    auto: bool = True
    edited_fields: list[str] = []
    locked: list[str] = []


class PAP(BaseModel):
    asset_id: str
    bake_version: int = 1
    profile: str = "rigid_prop"
    geometry: Geometry = Geometry()
    semantics: Semantics = Semantics()
    physical: Physical = Physical()
    structural: Structural = Structural()
    rest_states: list[str] = ["upright"]
    regions: list[dict] = []
    provenance: Provenance = Provenance()


# --------------------------------------------------------------------------- #
# MCP tool surface (spec §10.1) — signatures Person A implements, B calls.
# These are the function names the agent loop expects to exist.
# --------------------------------------------------------------------------- #
MCP_TOOLS: dict[str, str] = {
    "sync_scene":          "(selector: str) -> list[node_id]",
    "bake_asset":          "(asset_id: str) -> PAP",
    "get_profile":         "(asset_id: str) -> PAP",
    "check_collision":     "(a: str, b: str | None) -> GateResult",
    "simulate_drop":       "(obj: str, t: float) -> GateResult",   # stability
    "path_clear":          "(start, goal, r: float) -> GateResult",
    "evaluate_constraints":"(obj: str | None) -> GateResult",
    "validate_operation":  "(diff: Diff) -> Verdict",
    "suggest_transform":   "(obj: str, intent: dict) -> Transform",
    "commit":              "(diff: Diff) -> bool",
}
