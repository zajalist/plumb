"""
cortex/bake_profiles/ — per-profile PAP enrichment (Task 11).

A **Profile** is a named bundle of:
  * ``detect(pap) -> bool``       — heuristic / authored check
  * ``passes(pap) -> PAP``        — enriches the PAP with profile defaults
  * ``default_states: list[str]``  — canonical rest states for this type
  * ``default_regions: list[dict]``— region stubs (fill volumes, attach bands …)
  * ``default_constraints: list[dict]`` — law specs forwarded to the gate stack

Three concrete profiles are registered here:

  * **articulated** (door)  — hinge joint + swept-volume wedge obstacle
  * **tree**                — seasonal states + attach-band region stub
  * **shelf**               — fill-region capacity + populate() placement loop

Usage
-----
    from cortex.bake_profiles import load_profile

    prof = load_profile(pap)          # authored pap.profile wins; else heuristic detect
    enriched_pap = prof.passes(pap)   # inject defaults into the PAP

Canonical space: Z-up, right-handed, metres, kilograms.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, List

from contracts import PAP

from cortex.bake_profiles import door as _door_mod
from cortex.bake_profiles import tree as _tree_mod
from cortex.bake_profiles import shelf as _shelf_mod


# ---------------------------------------------------------------------------
# Profile dataclass (the protocol)
# ---------------------------------------------------------------------------

@dataclass
class Profile:
    """A named profile that enriches a PAP with type-specific defaults.

    All fields are required; the registry builder fills them from the profile
    module's module-level constants.
    """
    name: str
    detect: Callable[[PAP], bool]
    passes: Callable[[PAP], PAP]
    default_states: List[str] = field(default_factory=list)
    default_regions: List[dict] = field(default_factory=list)
    default_constraints: List[dict] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Rigid-prop (default) profile — used when nothing else matches
# ---------------------------------------------------------------------------

def _rigid_detect(pap: PAP) -> bool:
    return pap.profile == "rigid_prop"


def _rigid_passes(pap: PAP) -> PAP:
    return pap


_RIGID_PROFILE = Profile(
    name="rigid_prop",
    detect=_rigid_detect,
    passes=_rigid_passes,
    default_states=["upright"],
    default_regions=[],
    default_constraints=[{"law": "com_over_base", "node": "self"}],
)


# ---------------------------------------------------------------------------
# Profile registry
# ---------------------------------------------------------------------------

_REGISTRY: dict[str, Profile] = {}


def _register(profile: Profile) -> None:
    _REGISTRY[profile.name] = profile


# Articulated (door) profile.
_register(Profile(
    name="articulated",
    detect=lambda pap: pap.profile == "articulated" or (
        pap.semantics is not None and pap.semantics.cls == "door"
    ),
    passes=_door_mod.passes,
    default_states=["closed", "open", "ajar"],
    default_regions=[],
    default_constraints=[],
))

# Tree profile.
_register(Profile(
    name="tree",
    detect=_tree_mod.detect,
    passes=_tree_mod.passes,
    default_states=_tree_mod.DEFAULT_STATES,
    default_regions=_tree_mod.DEFAULT_REGIONS,
    default_constraints=_tree_mod.DEFAULT_CONSTRAINTS,
))

# Shelf profile.
_register(Profile(
    name="shelf",
    detect=_shelf_mod.detect,
    passes=_shelf_mod.passes,
    default_states=_shelf_mod.DEFAULT_STATES,
    default_regions=_shelf_mod.DEFAULT_REGIONS,
    default_constraints=_shelf_mod.DEFAULT_CONSTRAINTS,
))

# Rigid prop (fallback).
_register(_RIGID_PROFILE)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_profile_by_name(name: str) -> Profile:
    """Return the registered Profile for ``name``.

    Raises :class:`KeyError` if no profile is registered under that name.
    """
    return _REGISTRY[name]


def load_profile(pap: PAP) -> Profile:
    """Pick the best Profile for ``pap``.

    Selection order:
    1. **Authored**: if ``pap.profile`` matches a registered profile name exactly,
       use that profile (the asset author wins).
    2. **Heuristic detect**: try each registered profile's ``detect()`` in
       registration order; return the first match.
    3. **Fallback**: return the rigid-prop default.

    Parameters
    ----------
    pap:
        The PAP to classify.

    Returns
    -------
    Profile:
        The best-matching registered profile.
    """
    # 1. Authored name wins.
    if pap.profile in _REGISTRY:
        return _REGISTRY[pap.profile]

    # 2. Heuristic detect (registration order).
    for prof in _REGISTRY.values():
        if prof.detect(pap):
            return prof

    # 3. Rigid-prop fallback.
    return _RIGID_PROFILE


__all__ = ["Profile", "get_profile_by_name", "load_profile"]
