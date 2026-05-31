"""
In-memory model of a `.wdf` document (Task B3, spec §12.2).

A `.wdf` file is a portable language: a `vocabulary` (typed, rule-bearing assets)
plus a `scene` (instances placed in states, under laws, inside environment fields).
This module is the data layer only — `serialize.dumps` renders it to the §12.2
surface syntax and `parse.loads` reads it back, with the guarantee that
`loads(dumps(doc)) == doc`.

We use small dataclasses (not the `contracts` types): `Transform`/`PAP` describe a
single baked asset's geometry in canonical space, whereas `.wdf` is the human-facing
*language* (names, states, laws, prepositions) — a different shape entirely. The
contract seam stays at the verdict, exactly as the plan requires.

`@dataclass(eq=True)` gives us the structural equality the round-trip test needs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Joint:
    """An articulation (e.g. a door hinge): `joint: { axis: hinge, range: 0..95deg }`."""
    axis: str
    range_min: float
    range_max: float


@dataclass
class Asset:
    """A noun — a baked Physical Asset Profile, named and rule-bearing (§12.1).

    Only `name` is required. Everything else mirrors the §12.2 asset block:
    `profile`, `material` (part -> material), `states`, `affordances`, `tags`,
    and the articulated extras `joint` / `swept_volume` / `load_cap`.
    """
    name: str
    profile: Optional[str] = None
    material: dict[str, str] = field(default_factory=dict)
    states: list[str] = field(default_factory=list)
    affordances: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    joint: Optional[Joint] = None
    swept_volume: Optional[str] = None
    load_cap: Optional[str] = None


@dataclass
class Field:
    """An environment field — tense/mood that modulates the scene: `field season: autumn`."""
    key: str
    value: str


@dataclass
class Placement:
    """A placed instance: `place bronze_figure on pedestal state upright`.

    `preposition` is the spatial relation (`on`, `at`, `in`, `against`, `near`);
    `target` is what it relates to; `state` is the optional adjective it sits in.
    """
    asset: str
    target: str
    preposition: str = "at"
    state: Optional[str] = None


@dataclass
class Law:
    """A constraint — what must hold true: `law stable: com_over_base(...) hard`.

    `hard` gates the commit; `soft` (hard=False) accumulates into the repair objective.
    """
    name: str
    expr: str
    hard: bool = True


@dataclass(eq=False)
class Vocabulary:
    """The dictionary — the importable asset+profile pack for a scene.

    A vocabulary is an *unordered* dictionary keyed by asset name, so equality is
    order-insensitive: two vocabularies are equal when they hold the same assets
    regardless of list order. This keeps `loads(dumps(doc)) == doc` true even when
    the in-memory assets aren't alphabetical (`dumps` emits them sorted for stable
    diffs, while `parse` preserves file order).
    """
    assets: list[Asset] = field(default_factory=list)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Vocabulary):
            return NotImplemented
        return {a.name: a for a in self.assets} == {a.name: a for a in other.assets}


@dataclass
class Scene:
    """The sentence — instances composed under laws inside environment fields."""
    name: str
    fields: list[Field] = field(default_factory=list)
    placements: list[Placement] = field(default_factory=list)
    laws: list[Law] = field(default_factory=list)


@dataclass
class WdfDocument:
    """One portable, diffable, validatable document = vocabulary + scene (§12.2)."""
    vocabulary: Vocabulary = field(default_factory=Vocabulary)
    scene: Optional[Scene] = None
