"""
The material-confirm loop (Task B6) — AI guesses, human confirms, it locks.

Logic only; the confirm-panel UI is deferred (decisions Q6/Q7). Person A's bake
emits a `MaterialGuess` per CoACD part (VLM render-and-ask + texture sampling);
this module folds the human's decision over those guesses back into a PAP:

    * accept a guess  (decision `None`)   -> the guessed material, at its model
                                             confidence, lands in semantics.materials.
    * override a guess (decision `str`)   -> the human's material replaces it, at
                                             full confidence (1.0), and the field is
                                             recorded in `provenance.edited_fields`.

Either way the resolved part is added to `provenance.locked`, the PAP is no longer
purely `auto`, and a *fresh* PAP is returned (the input is never mutated). Because
locks are honored, re-baking is idempotent: a part already in `provenance.locked`
is left exactly as it is, so a later (possibly worse) guess can never clobber a
field a human has signed off on (`spec §5.5` provenance / "re-baking respects locks").

`confirm_mode` is one of `contracts.CONFIRM_MODES` ("prebaked" | "live"). It only
records *when* the confirm happens (offline before the demo vs. live on stage); the
folding logic is identical for both, so it is validated but otherwise inert here.

Pure consumer of the frozen contract — no physics, no VLM, no `cortex` import.
"""

from __future__ import annotations

from contracts import CONFIRM_MODES, MaterialGuess, MaterialPart, PAP

# Provenance field-path convention mirrors the spec (e.g. "physical.mass_kg"); a
# per-part material lives at "semantics.materials.<part>".
FIELD_PREFIX = "semantics.materials"

# A human override is, by definition, certain.
CONFIRMED_CONF = 1.0


def material_field(part: str) -> str:
    """The dotted provenance path for one part's material, e.g. ``semantics.materials.body``."""
    return f"{FIELD_PREFIX}.{part}"


def apply_confirmations(
    pap: PAP,
    guesses: list[MaterialGuess],
    decisions: dict[str, str | None],
    *,
    confirm_mode: str = "prebaked",
) -> PAP:
    """
    Fold human-confirmed/overridden material guesses into a copy of ``pap``.

    For each guess:
      * ``decisions[guess.part] is None`` (or absent) -> accept the guess as-is.
      * ``decisions[guess.part]`` is a ``str``        -> override with that material
        and record the field in ``provenance.edited_fields``.

    The resolved material is written to ``semantics.materials`` (replacing any
    existing row for the same part, never duplicating it) and the field is locked.
    A field already present in ``provenance.locked`` is left untouched — re-baking
    respects locks.

    Args:
        pap: the baked profile to fold confirmations into (never mutated).
        guesses: the AI's per-part material guesses.
        decisions: ``part -> None`` (accept) or ``part -> str`` (override). A part
            absent from this dict defaults to accept. Every key MUST name a part
            that appears in ``guesses``.
        confirm_mode: one of ``contracts.CONFIRM_MODES``; affects only *when* this
            is called, not the result.

    Returns:
        A new ``PAP`` with the confirmed materials, locks, and edits applied.

    Raises:
        ValueError: ``confirm_mode`` is not in ``contracts.CONFIRM_MODES``.
        KeyError: a key in ``decisions`` names a part with no corresponding guess.
    """
    if confirm_mode not in CONFIRM_MODES:
        raise ValueError(
            f"confirm_mode must be one of {CONFIRM_MODES!r}, got {confirm_mode!r}"
        )

    guess_parts = {g.part for g in guesses}
    unknown = set(decisions) - guess_parts
    if unknown:
        raise KeyError(
            f"decisions reference parts with no guess: {sorted(unknown)}"
        )

    # Deep-copy so the input PAP is never mutated.
    out = pap.model_copy(deep=True)
    materials: list[MaterialPart] = list(out.semantics.materials)
    by_part: dict[str, int] = {m.part: i for i, m in enumerate(materials)}
    locked: list[str] = list(out.provenance.locked)
    edited: list[str] = list(out.provenance.edited_fields)

    touched = False
    for guess in guesses:
        field = material_field(guess.part)

        # Re-baking respects locks: a confirmed field is never overwritten.
        if field in locked:
            continue

        decision = decisions.get(guess.part)  # absent -> accept
        if decision is None:
            mat, conf = guess.mat, guess.conf
            is_override = False
        else:
            mat, conf = decision, CONFIRMED_CONF
            is_override = True

        row = MaterialPart(part=guess.part, mat=mat, conf=conf)
        if guess.part in by_part:
            materials[by_part[guess.part]] = row
        else:
            by_part[guess.part] = len(materials)
            materials.append(row)

        locked.append(field)
        if is_override and field not in edited:
            edited.append(field)
        touched = True

    out.semantics.materials = materials
    out.provenance.locked = locked
    out.provenance.edited_fields = edited
    # A human has signed off on at least one field -> the PAP is no longer purely auto.
    if touched:
        out.provenance.auto = False

    return out
