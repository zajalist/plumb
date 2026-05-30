"""
INTEGRATION VERIFIER — the proof the Conscience works end to end, HEADLESS.

This is the whole-conscience smoke test: it runs the 4-minute demo beat on the
fixtures-backed `FakeCortex` (no MCP, no Unreal, no GPU, no viewer) and proves the
three load-bearing guarantees the conscience is built to deliver:

  1. THE BEAT RUNS.   `demo.run_demo(FakeCortex(), out=<.rrd>)` drives the agent loop
     over the Gallery scene and renders every verdict into a Rerun recording. We assert
     it produces a NON-EMPTY `.rrd` and that the episode ENDS ON GREEN (`ok is True`)
     after a topple -> repair sequence — exactly the demo story (red bbox + ghost +
     fix arrow, then all green).

  2. THE LANGUAGE IS REAL.   `demo.export_wdf(...)` emits portable `.wdf` text, and we
     assert `wdf.loads(export)` round-trips: `loads(dumps(doc)) == doc` for the very
     document the demo exports. Round-trip identity is the proof `.wdf` is a genuine
     language artifact, not a one-way print.

  3. THE SEAM HOLDS.   No module under `conscience/` imports `cortex`. The conscience
     RENDERS truth; it never computes physics. We grep the package for real
     `import cortex` / `from cortex ...` statements (ignoring the legitimate identifier
     `cortex_client` and the prose mentions in docstrings) and assert there are none.

Pure consumer of the contract end to end: everything is read out of
`Verdict` / `PAP` / `Transform`; the only seam to the cortex is `contracts.py` +
`fixtures.py` (via `FakeCortex`). The day Person A's real `McpCortex` lands, swapping
it in is the only line that changes — and this very test is what proves the swap is safe.
"""

from __future__ import annotations

import ast
import os
import re
import sys
from pathlib import Path

import pytest

from conscience import demo
from conscience.cortex_client import FakeCortex
from conscience.wdf import dumps, loads
from tests.helpers import tmp_path

# The package under test (absolute, so the grep is independent of cwd / rootdir).
_CONSCIENCE_PKG = Path(__file__).resolve().parent.parent / "conscience"


# =========================================================================== #
# 1. THE BEAT RUNS — non-empty .rrd + a final GREEN verdict after topple->repair.
# =========================================================================== #
def test_run_demo_produces_a_nonempty_rrd():
    """The headless recording is actually written and has bytes in it."""
    out = tmp_path(".rrd")
    result = demo.run_demo(FakeCortex(), out=out)
    assert result.out == out
    assert os.path.exists(out), "run_demo must write the .rrd recording to disk"
    assert os.path.getsize(out) > 0, "the .rrd recording must be non-empty (real frames)"


def test_run_demo_ends_on_a_green_verdict():
    """The episode settles repaired: the final verdict's `ok` is True."""
    result = demo.run_demo(FakeCortex(), out=tmp_path(".rrd"))
    assert result.final_verdict is not None
    assert result.final_verdict.ok is True, "the demo must end on GREEN (ok=True)"
    assert result.steps[-1].verdict.ok is True
    # ...and the green attempt is the one that committed (commit-once, only-green).
    assert result.steps[-1].committed is True


def test_run_demo_is_a_topple_then_repair_sequence():
    """
    The beat is exactly the demo story: a first attempt that FAILS (the figure
    topples) followed by one that PASSES (the nudge repairs it) — and it ends green.
    """
    result = demo.run_demo(FakeCortex(), out=tmp_path(".rrd"))
    oks = [s.verdict.ok for s in result.steps]
    assert oks[0] is False, "the episode must open on a topple (a failing verdict)"
    assert oks[-1] is True, "the episode must end on a repair (a passing verdict)"
    assert False in oks and True in oks, "the run must contain BOTH a fail and a pass"
    # The fail-then-pass transition happens exactly once: no thrashing.
    assert oks == [False, True]


def test_run_demo_full_proof_one_call():
    """
    The single end-to-end assertion the task names: run_demo(FakeCortex(), out=.rrd)
    yields a non-empty .rrd AND a green-ending topple->repair episode.
    """
    out = tmp_path(".rrd")
    result = demo.run_demo(FakeCortex(), out=out)
    # non-empty .rrd
    assert os.path.getsize(out) > 0
    # ends on GREEN after topple -> repair
    assert result.steps[0].verdict.ok is False
    assert result.final_verdict.ok is True


# =========================================================================== #
# 2. THE LANGUAGE IS REAL — export_wdf round-trips through wdf.loads / dumps.
# =========================================================================== #
def test_export_wdf_parses_back_without_error():
    """The exported `.wdf` text is genuinely parseable — `loads` does not raise."""
    text = demo.export_wdf()
    doc = loads(text)  # must not raise
    assert doc is not None
    assert doc.scene is not None


def test_export_wdf_round_trips_to_identity():
    """
    THE HEADLINE GUARANTEE: `loads(dumps(doc)) == doc`.

    The document the demo exports survives a parse->serialize->parse cycle unchanged.
    We assert it both ways:
      - the parsed export re-serialises to byte-identical text (stable language), and
      - re-parsing is idempotent (`loads(dumps(loads(text))) == loads(text)`),
    which together are exactly `loads(dumps(doc)) == doc` for `doc = loads(export)`.
    """
    text = demo.export_wdf()
    doc = loads(text)

    # loads(dumps(doc)) == doc  — the proof the language is round-trippable.
    assert loads(dumps(doc)) == doc

    # And the text form is stable (diffable): dumps is a fixed point through loads.
    assert dumps(doc) == dumps(loads(dumps(doc)))


def test_export_wdf_describes_the_gallery_after_round_trip():
    """The demo's content survives the language: the hero asset and the bet law remain."""
    doc = loads(demo.export_wdf())
    asset_names = {a.name for a in doc.vocabulary.assets}
    assert "bronze_figure" in asset_names, "the hero asset must survive the .wdf export"
    law_names = {law.name for law in doc.scene.laws}
    assert "stable" in law_names, "the stability law (the bet) must survive the export"


# =========================================================================== #
# 3. THE SEAM HOLDS — no module under conscience/ imports cortex.
# =========================================================================== #
def _cortex_import_offenders() -> list[str]:
    """
    Walk every `.py` under `conscience/` and return human-readable offenders of the
    form "<file>:<lineno>: <source line>" for any statement that imports the `cortex`
    package (or a submodule). Uses the AST so it sees real imports and never trips on
    the legitimate identifier `cortex_client`, `CortexClient`, or docstring prose.
    """
    offenders: list[str] = []
    for py in sorted(_CONSCIENCE_PKG.rglob("*.py")):
        src = py.read_text(encoding="utf-8")
        tree = ast.parse(src, filename=str(py))
        lines = src.splitlines()
        for node in ast.walk(tree):
            hit = False
            if isinstance(node, ast.Import):
                # import cortex / import cortex.server / import cortex as c
                hit = any(
                    alias.name == "cortex" or alias.name.startswith("cortex.")
                    for alias in node.names
                )
            elif isinstance(node, ast.ImportFrom):
                # from cortex import X / from cortex.server import Y
                mod = node.module or ""
                hit = mod == "cortex" or mod.startswith("cortex.")
            if hit:
                ln = getattr(node, "lineno", 0)
                text = lines[ln - 1].strip() if 0 < ln <= len(lines) else "<?>"
                offenders.append(f"{py}:{ln}: {text}")
    return offenders


def test_no_conscience_module_imports_cortex_ast():
    """
    AST proof: not one module under `conscience/` imports `cortex` (the seam is
    `contracts.py` + `fixtures.py` only). This is the structural guarantee that the
    conscience renders truth and never computes physics.
    """
    offenders = _cortex_import_offenders()
    assert offenders == [], (
        "conscience/ must never import cortex — found:\n  " + "\n  ".join(offenders)
    )


def test_no_conscience_module_imports_cortex_grep():
    """
    A second, independent grep proof (defence in depth): a regex over the source that
    matches only real `import cortex` / `from cortex(.sub) import` lines — and crucially
    NOT `cortex_client` (word boundary stops `cortex_`), nor the word in docstrings.
    """
    # `import cortex` or `from cortex` followed by a word boundary that is a dot,
    # whitespace, or end-of-line — so `cortex_client` (next char `_`) never matches.
    pattern = re.compile(r"^\s*(?:from|import)\s+cortex(?=[.\s]|$)", re.MULTILINE)
    hits: list[str] = []
    for py in sorted(_CONSCIENCE_PKG.rglob("*.py")):
        for i, line in enumerate(py.read_text(encoding="utf-8").splitlines(), start=1):
            if pattern.match(line):
                hits.append(f"{py}:{i}: {line.strip()}")
    assert hits == [], "grep found a cortex import under conscience/:\n  " + "\n  ".join(hits)


def test_running_the_demo_never_loads_the_cortex_package():
    """
    Runtime proof: after a full `run_demo`, the `cortex` package is not in `sys.modules`.
    Nothing on the demo path pulls cortex in — not even transitively.
    """
    demo.run_demo(FakeCortex(), out=tmp_path(".rrd"))
    cortex_mods = [m for m in sys.modules if m == "cortex" or m.startswith("cortex.")]
    assert cortex_mods == [], (
        "the demo path must not import the cortex package; found: " + ", ".join(cortex_mods)
    )


def test_grep_guard_distinguishes_real_imports_from_identifiers():
    """
    Guard the guard: prove the import-detection actually fires on a real `import cortex`
    and stays silent on the legitimate `cortex_client` identifier and prose mentions.
    Without this, a too-loose grep could pass vacuously and the seam check would be a lie.
    """
    pattern = re.compile(r"^\s*(?:from|import)\s+cortex(?=[.\s]|$)", re.MULTILINE)
    # Real imports -> must be flagged.
    assert pattern.search("import cortex")
    assert pattern.search("from cortex import server")
    assert pattern.search("import cortex.server as s")
    assert pattern.search("    from cortex.world import World")
    # Legitimate look-alikes -> must NOT be flagged.
    assert not pattern.search("from conscience.cortex_client import FakeCortex")
    assert not pattern.search("import cortex_client")
    assert not pattern.search("# the cortex reasoned over these numbers")
    assert not pattern.search("cortex = FakeCortex()")
