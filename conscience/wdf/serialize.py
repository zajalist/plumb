"""
Serialize a `WdfDocument` to the §12.2 surface syntax (Task B3).

`dumps(doc) -> str` produces a **stable, diffable** rendering: assets in the
`vocabulary` are sorted by name (a vocabulary is a dictionary — order is not
meaningful, so sorting keeps diffs clean), while the `scene` keeps author order
for fields, placements and laws (a sentence's word order carries intent).

The output is exactly what `parse.loads` reads back, so the headline guarantee
`loads(dumps(doc)) == doc` holds. Two-space indentation, one statement per line.
"""

from __future__ import annotations

import json

from .model import Asset, Law, Placement, Scene, WdfDocument

_IND = "  "


def _fmt_num(x: float) -> str:
    """Render a number in exponent-free fixed-point so the grammar can read it back.

    `repr(1e-5)` is `'1e-05'`, which the RANGE/QUANTITY terminals reject. `format(x,
    'f')` always emits plain decimal; we strip the redundant trailing zeros/point so
    integral bounds stay clean (`20`, not `20.000000`).
    """
    if x == int(x):
        return str(int(x))
    return format(x, "f").rstrip("0").rstrip(".")


def _asset_block(asset: Asset) -> list[str]:
    lines = [f"{_IND}asset {asset.name} {{"]
    if asset.profile is not None:
        lines.append(f"{_IND*2}profile: {asset.profile}")
    if asset.material:
        parts = ", ".join(f"{k}: {asset.material[k]}" for k in sorted(asset.material))
        lines.append(f"{_IND*2}material: {{ {parts} }}")
    if asset.joint is not None:
        j = asset.joint
        rng = f"{_fmt_num(j.range_min)}..{_fmt_num(j.range_max)}deg"
        lines.append(f"{_IND*2}joint: {{ axis: {j.axis}, range: {rng} }}")
    if asset.states:
        lines.append(f"{_IND*2}states: [ {', '.join(asset.states)} ]")
    if asset.affordances:
        lines.append(f"{_IND*2}affordances: [ {', '.join(asset.affordances)} ]")
    if asset.tags:
        lines.append(f"{_IND*2}tags: [ {', '.join(asset.tags)} ]")
    if asset.swept_volume is not None:
        lines.append(f"{_IND*2}swept_volume: {asset.swept_volume}")
    if asset.load_cap is not None:
        lines.append(f"{_IND*2}load_cap: {asset.load_cap}")
    lines.append(f"{_IND}}}")
    return lines


def _placement_line(p: Placement) -> str:
    line = f"{_IND}place {p.asset} {p.preposition} {p.target}"
    if p.state is not None:
        line += f" state {p.state}"
    return line


def _law_line(law: Law) -> str:
    return f"{_IND}law {law.name}: {law.expr} {'hard' if law.hard else 'soft'}"


def _scene_block(scene: Scene) -> list[str]:
    # json.dumps produces a properly escaped double-quoted string literal (escaping
    # ", \\ and control chars / newlines), which `parse` decodes symmetrically with
    # json.loads. A raw f-string here would corrupt any name holding those chars.
    lines = [f"scene {json.dumps(scene.name)} {{"]
    for f in scene.fields:
        lines.append(f"{_IND}field {f.key}: {f.value}")
    if scene.fields and (scene.placements or scene.laws):
        lines.append("")
    for p in scene.placements:
        lines.append(_placement_line(p))
    if scene.placements and scene.laws:
        lines.append("")
    for law in scene.laws:
        lines.append(_law_line(law))
    lines.append("}")
    return lines


def dumps(doc: WdfDocument) -> str:
    """Render `doc` to canonical, diffable `.wdf` text (the §12.2 grammar)."""
    out: list[str] = ["vocabulary {"]
    for asset in sorted(doc.vocabulary.assets, key=lambda a: a.name):
        out.extend(_asset_block(asset))
    out.append("}")
    if doc.scene is not None:
        out.append("")
        out.extend(_scene_block(doc.scene))
    return "\n".join(out) + "\n"
