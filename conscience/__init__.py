"""
PLUMB Conscience — FaraDuMatin's territory (Person B). Renders Verdicts + drives the agent.

Owns: Rerun viz, the Gate Stack UI (renders FROM verdict JSON), the agent/MCP
client loop, and the demo orchestration script.

NEVER reaches into cortex internals — only calls the MCP tools in MCP_TOOLS,
and until those exist, imports from fixtures.py. Same Verdict shape either way.

Build order (logic first, frontend deferred):
  1. rerun_viz.py — given a Verdict + PAP + Transform, draw: proxy mesh, bbox
                    coloured by status, CoM marker, support polygon, gravity
                    vector, ghost-topple of the rejected candidate, fix arrow,
                    explicit ViewCoordinates (catch handedness/winding flips).
  2. agent_loop.py — sync -> propose diff -> validate_operation -> on fail read
                    diagnostics -> suggest_transform -> re-validate -> commit.
                    Scripted driver first; real LLM MCP client as a Sunday upgrade.
  3. wdf/         — FULL round-trip: serializer + parser; prove load(save(s)) == s.
  4. ue5/         — Remote Control HTTP bridge (sync_scene GET / commit PUT,
                    snapshot-hash concurrency guard) + adapter.py (negate-X
                    coordinate transform with GOLDEN round-trip tests — the §17.5 proof).
  5. confirm_panel — render MaterialGuess[], human approve/edit -> lock
                    (prebaked default + live settings toggle).
  6. demo.py      — runs DEMO_SEQUENCE end to end for the 4-minute recording.
  --- DEFERRED until logic is done ---
  7. gate_stack.py / status graph — the pill row + read-only node graph, both
                    rendered purely from the Verdict JSON.

Definition of done for the bet: feed VERDICT_TOPPLE then VERDICT_REPAIRED and
the screen shows red stability gate + ghost-topple + fix arrow, then all green.
"""
