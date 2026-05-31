"""
cortex/placement_store.py — learned placement distributions, by example.

A "Placement Distribution" is taught by demonstration: for an asset, the user places it
against reference surfaces (tagged floor / table / wall / terrain …) and each placement is
captured as one **example** in that surface's frame:

  * ``normal_offset`` — signed distance of the asset origin from the surface along its
    normal (negative = embedded: roots sunk into terrain, a ruin settled into the ground).
  * ``tilt_deg``      — lean of the asset's up-axis away from the surface normal.
  * ``yaw_deg``       — spin about the normal.
  * ``lateral``       — [u, v] offset in the surface plane.

Examples with the same ``tag`` form a distribution (mean ± spread). At runtime the MCP
``place_on_surface(asset, tag)`` returns that distribution's best guess + a random draw, so
an agent placing the asset on "terrain" / "a table" in Unreal gets a physically-plausible
pose learned from the demonstrations.

Shared on disk (``bakes/placements/<asset_id>.json``, atomic writes) so the studio (which
captures the examples) and the FastMCP server (which serves them to the agent) converge —
same pattern as the mask store. No scene is ever stored; this is per-asset placement stats.
"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path

BAKES_DIR = Path(__file__).resolve().parents[1] / "bakes"


def _file(asset_id: str) -> Path:
    return BAKES_DIR / "placements" / f"{asset_id}.json"


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def load(asset_id: str) -> dict:
    f = _file(asset_id)
    if not f.exists():
        return {"asset_id": asset_id, "examples": []}
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"asset_id": asset_id, "examples": []}


def save(asset_id: str, examples: list[dict]) -> None:
    _atomic_write(_file(asset_id), json.dumps({"asset_id": asset_id, "examples": examples}))


def add_example(asset_id: str, example: dict) -> dict:
    """Append one captured placement example; returns the stored record."""
    data = load(asset_id)
    ex = {
        "tag": str(example.get("tag", "surface")),
        "orientation": str(example.get("orientation", "horizontal")),
        "normal_offset": float(example.get("normal_offset", 0.0)),
        "tilt_deg": float(example.get("tilt_deg", 0.0)),
        "yaw_deg": float(example.get("yaw_deg", 0.0)),
        "lateral": [float(x) for x in (example.get("lateral") or [0.0, 0.0])][:2] or [0.0, 0.0],
        "noise": example.get("noise"),  # {amp, freq, seed} when the reference plane was terrain-displaced
    }
    data["examples"].append(ex)
    save(asset_id, data["examples"])
    return ex


def clear(asset_id: str, tag: str | None = None) -> int:
    """Drop all examples (or just one tag's). Returns how many remain."""
    data = load(asset_id)
    if tag is None:
        data["examples"] = []
    else:
        data["examples"] = [e for e in data["examples"] if e.get("tag") != tag]
    save(asset_id, data["examples"])
    return len(data["examples"])


def _stats(values: list[float]) -> tuple[float, float]:
    if not values:
        return 0.0, 0.0
    mean = sum(values) / len(values)
    var = sum((v - mean) ** 2 for v in values) / len(values)
    return mean, math.sqrt(var)


def distribution(asset_id: str, tag: str) -> dict | None:
    """Aggregate the examples tagged ``tag`` into a placement distribution, or ``None``."""
    ex = [e for e in load(asset_id).get("examples", []) if e.get("tag") == tag]
    if not ex:
        return None
    no_m, no_s = _stats([e["normal_offset"] for e in ex])
    ti_m, ti_s = _stats([e["tilt_deg"] for e in ex])
    yw_m, yw_s = _stats([e["yaw_deg"] for e in ex])
    lu_m, lu_s = _stats([e["lateral"][0] for e in ex])
    lv_m, lv_s = _stats([e["lateral"][1] for e in ex])
    return {
        "tag": tag,
        "n": len(ex),
        "orientation": ex[-1].get("orientation", "horizontal"),
        "mean": {"normal_offset": no_m, "tilt_deg": ti_m, "yaw_deg": yw_m, "lateral": [lu_m, lv_m]},
        "spread": {"normal_offset": no_s, "tilt_deg": ti_s, "yaw_deg": yw_s, "lateral": [lu_s, lv_s]},
    }


def tags(asset_id: str) -> dict[str, int]:
    """Surface tags this asset has examples for → example count."""
    out: dict[str, int] = {}
    for e in load(asset_id).get("examples", []):
        out[e.get("tag", "surface")] = out.get(e.get("tag", "surface"), 0) + 1
    return out


def all_assets() -> list[str]:
    """Every asset_id that has captured placement examples on disk."""
    d = BAKES_DIR / "placements"
    if not d.is_dir():
        return []
    return sorted(p.stem for p in d.glob("*.json"))


def to_wdf(asset_ids: list[str] | None = None, scene_name: str = "placement") -> str:
    """Render the learned placement language as a ``.wdf`` document: each asset → a
    vocabulary noun, each surface distribution → a soft ``settle_on`` law (sink + tilt
    mean/spread in the surface frame). Round-trips through ``conscience.wdf`` (the studio
    can open it). Returns the ``.wdf`` text."""
    from conscience.wdf.model import Asset, Law, Placement, Scene, Vocabulary, WdfDocument
    from conscience.wdf.serialize import dumps

    ids = asset_ids if asset_ids else all_assets()
    assets, placements, laws = [], [], []
    for aid in ids:
        atags = sorted({t for t in tags(aid)})  # surface tags double as descriptive tags
        assets.append(Asset(name=aid, profile="rigid_prop", tags=atags or ["asset"]))
        for tag in tags(aid):
            d = distribution(aid, tag)
            if not d:
                continue
            m, s = d["mean"], d["spread"]
            expr = (f"settle_on({tag}, sink_m={m['normal_offset']:.3f}, sink_sd={s['normal_offset']:.3f}, "
                    f"tilt_deg={m['tilt_deg']:.2f}, tilt_sd={s['tilt_deg']:.2f}, n={d['n']})")
            laws.append(Law(name=f"{aid}_on_{tag}", expr=expr, hard=False))
            placements.append(Placement(asset=aid, target=tag, preposition="on"))
    doc = WdfDocument(vocabulary=Vocabulary(assets=assets),
                      scene=Scene(name=scene_name, placements=placements, laws=laws))
    return dumps(doc)
