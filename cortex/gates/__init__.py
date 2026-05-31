"""
cortex/gates/ — the gate stack. Each gate is a pure cost function over world state
that returns a frozen ``GateResult``: a signed numeric headline, an ``ok`` verdict,
and (on failure) a ``fix`` vector. The orchestrator (Task 9) runs them left→right.

  stability.py  (Task 4) — CoM-over-support-polygon margin (THE BET).
"""
