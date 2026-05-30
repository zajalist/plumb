"""
Parse `.wdf` text into a `WdfDocument` (Task B3, spec §12.2).

`loads(text) -> WdfDocument` runs the Lark grammar in `grammar.lark` and folds the
parse tree into the `model` dataclasses. It is the inverse of `serialize.dumps`, so
`loads(dumps(doc)) == doc`. Malformed input raises `WdfParseError` (a clean,
catchable error — never a bare Lark stack trace leaking to the caller).

Headless and pure: text in, dataclasses out. No cortex import, no I/O beyond reading
the bundled grammar file.
"""

from __future__ import annotations

import json
from pathlib import Path

from lark import Lark, Transformer, v_args
from lark.exceptions import LarkError

from .model import (
    Asset,
    Field,
    Joint,
    Law,
    Placement,
    Scene,
    Vocabulary,
    WdfDocument,
)

_GRAMMAR_PATH = Path(__file__).with_name("grammar.lark")


class WdfParseError(ValueError):
    """Raised when `.wdf` text does not conform to the §12.2 grammar."""


def _make_parser() -> Lark:
    return Lark(_GRAMMAR_PATH.read_text(encoding="utf-8"), parser="earley", start="start")


_PARSER = _make_parser()


@v_args(inline=True)
class _Builder(Transformer):
    """Fold the Lark tree into `model` dataclasses."""

    # --- leaf tokens ------------------------------------------------------- #
    def NAME(self, tok):
        return str(tok)

    def STRING(self, tok):
        # ESCAPED_STRING is a JSON-compatible double-quoted literal; decode it
        # symmetrically with the `json.dumps` the serializer uses so a name holding
        # a quote / backslash / control char round-trips (MUST-FIX 4). A bare
        # `[1:-1]` would only drop the outer quotes and leave the escapes literal.
        return json.loads(str(tok))

    def QUANTITY(self, tok):
        return str(tok)

    def SIGNED_NUMBER(self, tok):
        # A field/load_cap value is stored as the verbatim source text (the model
        # holds strings like "20" / "5" / "-3.5"), so reproduce the token text
        # unchanged rather than round-tripping through float().
        return str(tok)

    def value(self, child):
        # `value` wraps QUANTITY | NUMBER | STRING | NAME; each leaf callback has
        # already produced a plain string, so the field/load_cap value is that str.
        return child

    def LAW_EXPR(self, tok):
        return str(tok).strip()

    def HARDNESS(self, tok):
        return str(tok)

    def PREPOSITION(self, tok):
        return str(tok)

    def RANGE(self, tok):
        lo_hi = str(tok)[:-3]  # drop trailing "deg"
        lo, hi = lo_hi.split("..")
        return (float(lo), float(hi))

    # --- asset properties -------------------------------------------------- #
    def pair(self, key, value):
        return (key, value)

    def name_list(self, *names):
        return [n for n in names if n is not None]

    def profile_prop(self, name):
        return ("profile", name)

    def material_prop(self, *pairs):
        return ("material", dict(pairs))

    def joint_prop(self, axis, rng):
        lo, hi = rng
        return ("joint", Joint(axis=axis, range_min=lo, range_max=hi))

    def states_prop(self, names):
        return ("states", list(names))

    def affordances_prop(self, names):
        return ("affordances", list(names))

    def tags_prop(self, names):
        return ("tags", list(names))

    def swept_prop(self, name):
        return ("swept_volume", name)

    def loadcap_prop(self, quantity):
        return ("load_cap", quantity)

    def asset_prop(self, prop):
        return prop

    def asset(self, name, *props):
        a = Asset(name=name)
        for key, value in props:
            setattr(a, key, value)
        return a

    def vocabulary(self, *assets):
        return Vocabulary(assets=list(assets))

    # --- scene statements -------------------------------------------------- #
    def field_pair(self, key, value):
        return Field(key=key, value=value)

    def field_stmt(self, *fields):
        return ("fields", list(fields))

    def place_stmt(self, asset, prep, target, state=None):
        return ("placement", Placement(asset=asset, preposition=prep,
                                       target=target, state=state))

    def law_stmt(self, name, expr, hardness):
        return ("law", Law(name=name, expr=expr, hard=(hardness == "hard")))

    def scene_stmt(self, stmt):
        return stmt

    def scene(self, name, *stmts):
        scene = Scene(name=name)
        for kind, payload in stmts:
            if kind == "fields":
                scene.fields.extend(payload)
            elif kind == "placement":
                scene.placements.append(payload)
            elif kind == "law":
                scene.laws.append(payload)
        return scene

    # --- document ---------------------------------------------------------- #
    def start(self, vocabulary, scene=None):
        return WdfDocument(vocabulary=vocabulary, scene=scene)


def loads(text: str) -> WdfDocument:
    """Parse `.wdf` text into a `WdfDocument`. Raises `WdfParseError` on bad input."""
    try:
        tree = _PARSER.parse(text)
        return _Builder().transform(tree)
    except LarkError as exc:
        raise WdfParseError(str(exc)) from exc
