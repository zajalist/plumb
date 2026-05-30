"""
Fake verdicts + PAPs so Person B is NEVER blocked on Person A.

The demo beat — topple-and-repair — is fully expressible here as a sequence of
two verdicts: a FAIL (figure topples) and, after suggest_transform, a PASS.

Person B renders the entire demo from these until the real cortex lands, then
swaps `from fixtures import ...` for real MCP calls. Same shapes either way.
"""

from contracts import (
    FixVector,
    GateName,
    GateResult,
    PAP,
    Physical,
    Semantics,
    Geometry,
    Transform,
    Verdict,
)

# The hero asset: top-heavy bronze figure (spec running example "The Gallery").
BRONZE_FIGURE = PAP(
    asset_id="bronze_figure_03",
    profile="rigid_prop",
    geometry=Geometry(obb=[0.15, 0.15, 0.75], volume_m3=0.031, convex_parts=9, watertight=True),
    semantics=Semantics(cls="statue", up=[0, 0, 1], front=[0, 1, 0],
                        materials=[{"part": "body", "mat": "bronze", "conf": 0.82}], conf=0.8),
    physical=Physical(mass_kg=48.0, com=[0.0, 0.04, 0.71], hollow=False, conf=0.7),
    rest_states=["upright", "fell"],
)

# THE MOMENT (spec §15 step 5): placed too close to the pedestal edge -> topples.
VERDICT_TOPPLE = Verdict(
    ok=False,
    stopped_at=GateName.stability,
    gates=[
        GateResult(gate=GateName.collision, ok=True, value_m=0.042),
        GateResult(
            gate=GateName.stability, ok=False, value_m=-0.07,
            fix=FixVector(translate=[0.06, 0.0, 0.0]),
            viz="com_outside_polygon", detail="CoM 7cm outside support polygon",
        ),
        GateResult(gate=GateName.constraints, skipped=True),
        GateResult(gate=GateName.reach, skipped=True),
    ],
    soft_cost=1.84,
)

# After suggest_transform nudges +6cm toward centre -> all green (spec §15 step 6-7).
VERDICT_REPAIRED = Verdict(
    ok=True,
    stopped_at=None,
    gates=[
        GateResult(gate=GateName.collision, ok=True, value_m=0.051),
        GateResult(gate=GateName.stability, ok=True, value_m=0.018, detail="CoM 1.8cm inside polygon"),
        GateResult(gate=GateName.constraints, ok=True, value_m=0.0),
        GateResult(gate=GateName.reach, ok=True, value_m=0.94, detail="walkway 94cm >= 90cm"),
    ],
    soft_cost=0.12,
)

# The transform suggest_transform would return to get from topple -> repaired.
SUGGESTED_FIX = Transform(pos=[0.06, 0.0, 0.40], quat=[0, 0, 0, 1])

# Convenience: the demo as an ordered script of (label, verdict).
DEMO_SEQUENCE = [
    ("placed by vibes", VERDICT_TOPPLE),
    ("after suggest_transform", VERDICT_REPAIRED),
]
