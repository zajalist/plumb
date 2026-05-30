"""
Headless tests for the material-confirm loop (Task B6): `conscience/confirm.py`.

The feature is "AI guesses, human confirms, it locks" (decisions Q6/Q7). Person A
emits `MaterialGuess[]` per CoACD part; Person B folds the confirmed/overridden
materials into `PAP.semantics.materials` and records the lock in `PAP.provenance`.
This task is the LOGIC only — the confirm panel UI is deferred. There is no GPU,
no VLM, no cortex import: we drive everything off the frozen contract types.

Invariants under test:
  1. Accept-all (every decision None) -> materials match the guesses, all locked.
  2. Overriding a part replaces that material, locks it, AND records it in
     `provenance.edited_fields` (an accepted guess locks but is NOT "edited").
  3. Re-baking respects locks: a field already in `provenance.locked` is not
     overwritten by a later, different guess.
  4. The input PAP is never mutated (a fresh PAP is returned).
  5. `confirm_mode` is one of `contracts.CONFIRM_MODES`; it does not change the
     folding logic (prebaked vs live only changes *when* this is called).
"""

from __future__ import annotations

import pytest

from contracts import CONFIRM_MODES, MaterialGuess, MaterialPart, PAP, Provenance, Semantics
from conscience.confirm import FIELD_PREFIX, apply_confirmations, material_field


# --------------------------------------------------------------------------- #
# Fixtures: a freshly-baked PAP with no materials yet, plus a couple of guesses.
# --------------------------------------------------------------------------- #
def _fresh_pap() -> PAP:
    return PAP(asset_id="bronze_figure_03")


def _guesses() -> list[MaterialGuess]:
    return [
        MaterialGuess(part="body", mat="bronze", conf=0.82, source="vlm"),
        MaterialGuess(part="base", mat="marble", conf=0.61, source="texture"),
    ]


# --------------------------------------------------------------------------- #
# 1. Accept-all.
# --------------------------------------------------------------------------- #
def test_accept_all_folds_guesses_and_locks_them():
    pap = _fresh_pap()
    guesses = _guesses()
    decisions = {"body": None, "base": None}

    out = apply_confirmations(pap, guesses, decisions)

    mats = {m.part: m for m in out.semantics.materials}
    assert mats["body"].mat == "bronze"
    assert mats["base"].mat == "marble"
    # accepted guesses keep their model confidence
    assert mats["body"].conf == pytest.approx(0.82)
    assert mats["base"].conf == pytest.approx(0.61)

    # both parts are locked...
    assert material_field("body") in out.provenance.locked
    assert material_field("base") in out.provenance.locked
    # ...but an accepted guess is NOT a human edit.
    assert out.provenance.edited_fields == []


def test_accept_all_marks_provenance_not_auto():
    # A human has signed off on these materials -> provenance is no longer purely auto.
    out = apply_confirmations(_fresh_pap(), _guesses(), {"body": None, "base": None})
    assert out.provenance.auto is False


# --------------------------------------------------------------------------- #
# 2. Override one part.
# --------------------------------------------------------------------------- #
def test_override_replaces_material_and_records_edit():
    out = apply_confirmations(
        _fresh_pap(), _guesses(), {"body": "gold", "base": None}
    )

    mats = {m.part: m for m in out.semantics.materials}
    # the override wins over the guess...
    assert mats["body"].mat == "gold"
    # ...and a human-confirmed override is full confidence.
    assert mats["body"].conf == pytest.approx(1.0)
    # the un-overridden part is untouched.
    assert mats["base"].mat == "marble"

    # both are locked; only the override is "edited".
    assert material_field("body") in out.provenance.locked
    assert material_field("base") in out.provenance.locked
    assert out.provenance.edited_fields == [material_field("body")]


def test_field_path_is_dotted_under_semantics_materials():
    # Matches the spec's provenance convention (e.g. "physical.mass_kg").
    assert material_field("body") == f"{FIELD_PREFIX}.body"
    assert FIELD_PREFIX == "semantics.materials"


# --------------------------------------------------------------------------- #
# 3. Re-baking respects locks.
# --------------------------------------------------------------------------- #
def test_rebake_does_not_overwrite_a_locked_field():
    # First pass: confirm body=bronze, lock it.
    first = apply_confirmations(
        _fresh_pap(), [MaterialGuess(part="body", mat="bronze", conf=0.82, source="vlm")],
        {"body": None},
    )
    assert material_field("body") in first.provenance.locked

    # Re-bake hands a DIFFERENT guess for the same (now locked) part.
    second = apply_confirmations(
        first, [MaterialGuess(part="body", mat="plastic", conf=0.40, source="default")],
        {"body": None},
    )

    mats = {m.part: m for m in second.semantics.materials}
    # the locked value survives the re-bake.
    assert mats["body"].mat == "bronze"
    # no duplicate lock entries.
    assert second.provenance.locked.count(material_field("body")) == 1


def test_rebake_can_add_a_new_unlocked_part():
    first = apply_confirmations(
        _fresh_pap(), [MaterialGuess(part="body", mat="bronze", conf=0.82, source="vlm")],
        {"body": None},
    )
    # Re-bake adds a brand-new part the first pass never saw.
    second = apply_confirmations(
        first, [MaterialGuess(part="base", mat="marble", conf=0.61, source="texture")],
        {"base": None},
    )
    mats = {m.part: m for m in second.semantics.materials}
    assert mats["body"].mat == "bronze"   # old lock preserved
    assert mats["base"].mat == "marble"   # new part folded in
    assert material_field("base") in second.provenance.locked


# --------------------------------------------------------------------------- #
# 4. Purity: the input PAP is never mutated.
# --------------------------------------------------------------------------- #
def test_input_pap_is_not_mutated():
    pap = _fresh_pap()
    apply_confirmations(pap, _guesses(), {"body": None, "base": None})
    assert pap.semantics.materials == []
    assert pap.provenance.locked == []
    assert pap.provenance.edited_fields == []
    assert pap.provenance.auto is True


def test_existing_materials_are_preserved_when_part_differs():
    # A PAP that already carries an (auto, unlocked) material for an unrelated part.
    pap = PAP(
        asset_id="x",
        semantics=Semantics(materials=[MaterialPart(part="arm", mat="iron", conf=0.5)]),
    )
    out = apply_confirmations(
        pap, [MaterialGuess(part="body", mat="bronze", conf=0.82, source="vlm")],
        {"body": None},
    )
    mats = {m.part: m for m in out.semantics.materials}
    assert set(mats) == {"arm", "body"}
    assert mats["arm"].mat == "iron"
    assert mats["body"].mat == "bronze"


def test_confirming_an_existing_unlocked_part_replaces_it_in_place():
    # No duplicate material rows: re-confirming a known part edits the existing row.
    pap = PAP(
        asset_id="x",
        semantics=Semantics(materials=[MaterialPart(part="body", mat="iron", conf=0.3)]),
    )
    out = apply_confirmations(
        pap, [MaterialGuess(part="body", mat="bronze", conf=0.82, source="vlm")],
        {"body": None},
    )
    body_rows = [m for m in out.semantics.materials if m.part == "body"]
    assert len(body_rows) == 1
    assert body_rows[0].mat == "bronze"


# --------------------------------------------------------------------------- #
# 5. confirm_mode is honored as a value but never changes the folding logic.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("mode", CONFIRM_MODES)
def test_confirm_mode_does_not_change_the_result(mode):
    guesses = _guesses()
    decisions = {"body": None, "base": "gold"}
    baseline = apply_confirmations(_fresh_pap(), guesses, decisions)
    out = apply_confirmations(_fresh_pap(), guesses, decisions, confirm_mode=mode)
    assert out.model_dump() == baseline.model_dump()


def test_unknown_confirm_mode_is_rejected():
    with pytest.raises(ValueError):
        apply_confirmations(
            _fresh_pap(), _guesses(), {"body": None, "base": None},
            confirm_mode="sideways",
        )


def test_decision_for_unknown_part_is_an_error():
    # A decision dict must only reference parts present in the guesses.
    with pytest.raises(KeyError):
        apply_confirmations(
            _fresh_pap(), _guesses(), {"body": None, "ghost": None},
        )


def test_missing_decision_defaults_to_accept():
    # A guess with no entry in `decisions` is treated as accept (None).
    out = apply_confirmations(_fresh_pap(), _guesses(), {})
    mats = {m.part: m for m in out.semantics.materials}
    assert mats["body"].mat == "bronze"
    assert mats["base"].mat == "marble"
    assert out.provenance.edited_fields == []
