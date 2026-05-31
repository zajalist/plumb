"""
Tests for the `.wdf` language (Task B3) — FULL round-trip.

The headline guarantee is `loads(dumps(doc)) == doc` for a non-trivial document.
`.wdf` is the portable, diffable, validatable language of §12.2: a `vocabulary`
(typed assets) + a `scene` (placements, laws, fields). These tests build a
Gallery-like document, prove the round-trip is identity, parse the literal §12.2
example text, and prove malformed text raises a clear error.

Headless: pure text in / text out — no GPU, no Unreal, no cortex import.
"""

from __future__ import annotations

import pytest

from conscience.wdf import (
    Asset,
    Field,
    Joint,
    Law,
    Placement,
    Scene,
    Vocabulary,
    WdfDocument,
    WdfParseError,
    dumps,
    loads,
)


# --------------------------------------------------------------------------- #
# A non-trivial Gallery document, built in memory (the spec running example).
# --------------------------------------------------------------------------- #
def gallery_document() -> WdfDocument:
    bronze = Asset(
        name="bronze_figure",
        profile="rigid_prop",
        material={"body": "bronze"},
        states=["upright", "fell"],
        affordances=["base_contact"],
    )
    oak_door = Asset(
        name="oak_door",
        profile="articulated",
        joint=Joint(axis="hinge", range_min=0.0, range_max=95.0),
        swept_volume="keep_clear",
    )
    vocabulary = Vocabulary(assets=[bronze, oak_door])

    scene = Scene(
        name="the_gallery",
        fields=[Field(key="season", value="autumn")],
        placements=[
            Placement(asset="bronze_figure", preposition="on", target="pedestal",
                      state="upright"),
            Placement(asset="oak_door", preposition="at", target="north_wall"),
        ],
        laws=[
            Law(name="stable", expr="com_over_base(margin >= 2cm)", hard=True),
            Law(name="facing", expr="bronze.front -> entrance(<= 8deg)", hard=False),
            Law(name="door_clear", expr="keep_clear(oak_door.swept)", hard=True),
        ],
    )
    return WdfDocument(vocabulary=vocabulary, scene=scene)


# --------------------------------------------------------------------------- #
# The headline guarantee.
# --------------------------------------------------------------------------- #
def test_round_trip_identity_for_nontrivial_document():
    doc = gallery_document()
    assert loads(dumps(doc)) == doc


def test_dumps_is_deterministic_and_idempotent():
    doc = gallery_document()
    once = dumps(doc)
    twice = dumps(loads(once))
    assert once == twice


# --------------------------------------------------------------------------- #
# Document content survives serialization (the asset/law presence checks).
# --------------------------------------------------------------------------- #
def test_round_trip_preserves_assets():
    doc = gallery_document()
    back = loads(dumps(doc))
    names = {a.name for a in back.vocabulary.assets}
    assert names == {"bronze_figure", "oak_door"}
    door = next(a for a in back.vocabulary.assets if a.name == "oak_door")
    assert door.profile == "articulated"
    assert door.joint is not None
    assert door.joint.axis == "hinge"
    assert door.joint.range_min == 0.0
    assert door.joint.range_max == 95.0
    assert door.swept_volume == "keep_clear"


def test_round_trip_preserves_laws_hard_and_soft():
    doc = gallery_document()
    back = loads(dumps(doc))
    laws = {law.name: law for law in back.scene.laws}
    assert laws["stable"].hard is True
    assert laws["door_clear"].hard is True
    assert laws["facing"].hard is False


def test_round_trip_preserves_field():
    doc = gallery_document()
    back = loads(dumps(doc))
    fields = {f.key: f.value for f in back.scene.fields}
    assert fields["season"] == "autumn"


# --------------------------------------------------------------------------- #
# Parse the literal §12.2 example surface syntax (must match the spec).
# --------------------------------------------------------------------------- #
SPEC_EXAMPLE = """
vocabulary {
  asset bronze_figure {
    profile: rigid_prop
    material: { body: bronze }
    states: [ upright, fell ]
    affordances: [ base_contact ]
  }
  asset oak_door {
    profile: articulated
    joint: { axis: hinge, range: 0..95deg }
    swept_volume: keep_clear
  }
}

scene "the_gallery" {
  field season: autumn

  place bronze_figure on pedestal state upright
  place oak_door at north_wall

  law stable: com_over_base(margin >= 2cm) hard
  law facing: bronze.front -> entrance(<= 8deg) soft
  law door_clear: keep_clear(oak_door.swept) hard
}
"""


def test_parse_spec_example_assets_present():
    doc = loads(SPEC_EXAMPLE)
    names = {a.name for a in doc.vocabulary.assets}
    assert "bronze_figure" in names
    assert "oak_door" in names


def test_parse_spec_example_laws_present_with_hardness():
    doc = loads(SPEC_EXAMPLE)
    laws = {law.name: law for law in doc.scene.laws}
    assert laws["stable"].hard is True
    assert laws["facing"].hard is False
    assert laws["door_clear"].hard is True


def test_parse_spec_example_scene_name_and_field():
    doc = loads(SPEC_EXAMPLE)
    assert doc.scene.name == "the_gallery"
    assert any(f.key == "season" and f.value == "autumn" for f in doc.scene.fields)


def test_parse_spec_example_placements():
    doc = loads(SPEC_EXAMPLE)
    placements = {p.asset: p for p in doc.scene.placements}
    assert placements["bronze_figure"].preposition == "on"
    assert placements["bronze_figure"].target == "pedestal"
    assert placements["bronze_figure"].state == "upright"
    assert placements["oak_door"].preposition == "at"
    assert placements["oak_door"].target == "north_wall"
    assert placements["oak_door"].state is None


def test_spec_example_round_trips():
    # Parse the spec text, re-serialize, re-parse: stable identity through our form.
    doc = loads(SPEC_EXAMPLE)
    assert loads(dumps(doc)) == doc


# --------------------------------------------------------------------------- #
# Malformed text raises a clear parse error.
# --------------------------------------------------------------------------- #
def test_malformed_text_raises_parse_error():
    with pytest.raises(WdfParseError):
        loads("vocabulary { asset { this is not valid wdf @@@ }")


def test_truncated_document_raises_parse_error():
    with pytest.raises(WdfParseError):
        loads("scene \"x\" {")


# --------------------------------------------------------------------------- #
# Serialized output is the §12.2 grammar (diffable, sorted, stable).
# --------------------------------------------------------------------------- #
def test_dumps_emits_vocabulary_and_scene_blocks():
    text = dumps(gallery_document())
    assert "vocabulary {" in text
    assert 'scene "the_gallery" {' in text
    assert "asset bronze_figure {" in text
    assert "law stable:" in text
    assert "hard" in text and "soft" in text


def test_round_trip_preserves_tags_and_load_cap():
    # glass_vase from §12.2: a fragile hollow asset with tags + load_cap.
    vase = Asset(
        name="glass_vase",
        material={"shell": "glass", "interior": "hollow"},
        states=["upright", "fell"],
        tags=["fragile"],
        load_cap="0.5kg",
    )
    doc = WdfDocument(vocabulary=Vocabulary(assets=[vase]),
                      scene=Scene(name="s", laws=[Law(name="cap", expr="byTag(fragile).load <= cap", hard=True)]))
    back = loads(dumps(doc))
    assert back == doc
    a = back.vocabulary.assets[0]
    assert a.tags == ["fragile"]
    assert a.load_cap == "0.5kg"
    assert a.material == {"shell": "glass", "interior": "hollow"}


def test_parse_multi_field_separator():
    # §12.2 packs two environment fields on one line with `·`.
    doc = loads('vocabulary {} scene "s" { field season: autumn · time: dusk }')
    fields = {f.key: f.value for f in doc.scene.fields}
    assert fields == {"season": "autumn", "time": "dusk"}


def test_dumps_sorts_assets_and_laws_for_stable_diffs():
    # Build with assets/laws in reverse order; output must still be sorted.
    doc = gallery_document()
    doc.vocabulary.assets.reverse()
    doc.scene.laws.reverse()
    text = dumps(doc)
    assert text.index("asset bronze_figure") < text.index("asset oak_door")
    # round-trip is still identity regardless of input ordering
    assert loads(text) == loads(dumps(loads(text)))


# --------------------------------------------------------------------------- #
# MUST-FIX 1 — round-trip is identity for an UNSORTED in-memory vocabulary.
# `dumps` sorts assets by name, but `parse` keeps file order; a vocabulary is a
# dictionary, so equality must be order-insensitive over assets.
# --------------------------------------------------------------------------- #
def test_round_trip_identity_for_unsorted_vocabulary():
    doc = WdfDocument(vocabulary=Vocabulary(assets=[Asset(name="zebra"),
                                                    Asset(name="apple")]))
    assert loads(dumps(doc)) == doc


def test_vocabulary_equality_is_order_insensitive():
    a = Vocabulary(assets=[Asset(name="zebra"), Asset(name="apple")])
    b = Vocabulary(assets=[Asset(name="apple"), Asset(name="zebra")])
    assert a == b


def test_documents_with_reordered_assets_are_equal():
    d1 = WdfDocument(vocabulary=Vocabulary(assets=[Asset(name="b"), Asset(name="a")]))
    d2 = WdfDocument(vocabulary=Vocabulary(assets=[Asset(name="a"), Asset(name="b")]))
    assert d1 == d2


# --------------------------------------------------------------------------- #
# MUST-FIX 2 — dumps must never emit something loads can't parse back.
# (a) numeric field value, (b) unit-less load_cap, (c) sci-notation floats.
# --------------------------------------------------------------------------- #
def test_round_trip_numeric_field_value():
    doc = WdfDocument(vocabulary=Vocabulary(),
                      scene=Scene(name="s", fields=[Field(key="temp", value="20")]))
    assert loads(dumps(doc)) == doc


def test_round_trip_unitless_load_cap():
    vase = Asset(name="glass_vase", load_cap="5")
    doc = WdfDocument(vocabulary=Vocabulary(assets=[vase]))
    assert loads(dumps(doc)) == doc


def test_round_trip_negative_and_decimal_field_values():
    # The widened value grammar must also accept signed/decimal numerics so the
    # round-trip invariant holds for any numeric a field can legitimately carry.
    for raw in ("-3.5", "-7", "0.25"):
        doc = WdfDocument(vocabulary=Vocabulary(),
                          scene=Scene(name="s", fields=[Field(key="tilt", value=raw)]))
        back = loads(dumps(doc))
        assert back == doc
        assert back.scene.fields[0].value == raw


def test_round_trip_sub_unit_float_joint_range():
    # A sub-unit float bound (1e-5 == 0.00001) must not be emitted in sci-notation.
    door = Asset(name="hinge",
                 joint=Joint(axis="hinge", range_min=1e-5, range_max=95.0))
    doc = WdfDocument(vocabulary=Vocabulary(assets=[door]))
    text = dumps(doc)
    assert "e-" not in text and "E-" not in text  # no exponent form leaks out
    assert loads(text) == doc


def test_round_trip_string_field_value_still_works():
    # NAME-shaped values must keep working after the grammar is widened.
    doc = WdfDocument(vocabulary=Vocabulary(),
                      scene=Scene(name="s", fields=[Field(key="season", value="autumn")]))
    assert loads(dumps(doc)) == doc


# --------------------------------------------------------------------------- #
# MUST-FIX 3 — LAW_EXPR must not truncate on a literal 'hard'/'soft' inside it.
# Only a TRAILING hardness keyword terminates the expression.
# --------------------------------------------------------------------------- #
def test_round_trip_law_expr_containing_literal_hard_and_soft():
    law = Law(name="L", expr="limit hard cap and soft floor", hard=True)
    doc = WdfDocument(vocabulary=Vocabulary(),
                      scene=Scene(name="s", laws=[law]))
    back = loads(dumps(doc))
    assert back == doc
    assert back.scene.laws[0].expr == "limit hard cap and soft floor"
    assert back.scene.laws[0].hard is True


def test_round_trip_law_expr_ending_in_word_before_hardness():
    law = Law(name="L", expr="limit hard cap", hard=True)
    doc = WdfDocument(vocabulary=Vocabulary(), scene=Scene(name="s", laws=[law]))
    assert loads(dumps(doc)) == doc


# --------------------------------------------------------------------------- #
# MUST-FIX 4 — scene-name STRING escapes must be symmetric (write escapes,
# read unescapes), so a name with a quote/backslash/newline round-trips.
# --------------------------------------------------------------------------- #
def test_round_trip_scene_name_with_quote_and_backslash():
    doc = WdfDocument(vocabulary=Vocabulary(),
                      scene=Scene(name='a"b\\c'))
    back = loads(dumps(doc))
    assert back == doc
    assert back.scene.name == 'a"b\\c'


def test_round_trip_scene_name_with_newline():
    doc = WdfDocument(vocabulary=Vocabulary(), scene=Scene(name="line1\nline2"))
    back = loads(dumps(doc))
    assert back == doc
    assert back.scene.name == "line1\nline2"
