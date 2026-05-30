"""
PLUMB Cortex — PERSON A's territory. Headless. Produces Verdicts.

Owns: bake pipeline, world model, gates, repair solver, MCP tool surface.
NEVER imports a UI library. Everything here is deterministic and unit-testable.

Build order (each step independently testable against contracts.py):
  1. world.py    — in-memory scene graph of {node_id: (PAP, Transform)}
  2. bake.py     — CoACD geometry bake + composition-aware mass/CoM/inertia -> PAP
  3. gates/      — collision (Coal), stability (quasi-static CoM-over-polygon)
  4. repair.py   — suggest_transform via scipy SLSQP minimising the gate cost
  5. orchestrator.py — validate_operation(diff) -> Verdict (runs gates L->R, halts on hard-fail)
  6. server.py   — FastMCP wrapper exposing MCP_TOOLS

Definition of done for the bet: validate_operation(topple_diff) == VERDICT_TOPPLE
shape, and suggest_transform flips it to a passing Verdict.
"""
