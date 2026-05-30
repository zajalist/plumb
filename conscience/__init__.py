"""
PLUMB Conscience — PERSON B's territory. Renders Verdicts + drives the agent.

Owns: Rerun viz, the Gate Stack UI (renders FROM verdict JSON), the agent/MCP
client loop, and the demo orchestration script.

NEVER reaches into cortex internals — only calls the MCP tools in MCP_TOOLS,
and until those exist, imports from fixtures.py. Same Verdict shape either way.

Build order:
  1. rerun_viz.py — given a Verdict + PAP + Transform, draw: proxy mesh, bbox
                    coloured by status, CoM marker, support polygon, gravity
                    vector, ghost-topple of the rejected candidate, fix arrow.
  2. gate_stack.py — the pill row (grey/green/amber/red) + headline number +
                    expandable drawer with the fix vector. Pure verdict -> UI.
  3. agent_loop.py — sync -> propose diff -> validate_operation -> on fail read
                    diagnostics -> suggest_transform -> re-validate -> commit.
  4. demo.py      — runs DEMO_SEQUENCE end to end for the 4-minute recording.

Definition of done for the bet: feed VERDICT_TOPPLE then VERDICT_REPAIRED and
the screen shows red stability gate + ghost-topple + fix arrow, then all green.
"""
