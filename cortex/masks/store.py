"""
cortex/masks/store.py — the shared on-disk mask store (design spec §4).

The two backends never share memory: ``studio/server.py`` (HTTP, the UI) and
``cortex/server.py`` (FastMCP, the agent) run as separate processes. They converge HERE,
on disk: masks live in ``bakes/masks/<asset_id>.json`` so an agent-authored mask shows up
in the UI on its next ``GET /masks`` and vice-versa. Writes are atomic (temp + os.replace)
so a half-written file is never read.

The bake also parks the converted mesh + the convex parts here so geometry providers can
recompute on demand (the studio's in-memory PAP doesn't keep the parts geometry).
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from .model import Mask

# repo root = cortex/masks/store.py -> parents[2]
BAKES_DIR = Path(__file__).resolve().parents[2] / "bakes"


def _masks_file(asset_id: str) -> Path:
    return BAKES_DIR / "masks" / f"{asset_id}.json"


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def _read_raw(asset_id: str) -> dict:
    f = _masks_file(asset_id)
    if not f.exists():
        return {"asset_id": asset_id, "masks": {}}
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"asset_id": asset_id, "masks": {}}


def list_masks(asset_id: str) -> list[Mask]:
    raw = _read_raw(asset_id)
    out: list[Mask] = []
    for m in raw.get("masks", {}).values():
        try:
            out.append(Mask.model_validate(m))
        except Exception:
            continue  # tolerate a stale/garbage entry rather than break the whole list
    return out


def get(asset_id: str, mask_id: str) -> Mask | None:
    m = _read_raw(asset_id).get("masks", {}).get(mask_id)
    return Mask.model_validate(m) if m else None


def upsert(mask: Mask) -> Mask:
    raw = _read_raw(mask.asset_id)
    raw.setdefault("masks", {})[mask.id] = mask.model_dump()
    _atomic_write(_masks_file(mask.asset_id), json.dumps(raw, indent=0))
    return mask


def delete(asset_id: str, mask_id: str) -> bool:
    raw = _read_raw(asset_id)
    if mask_id in raw.get("masks", {}):
        del raw["masks"][mask_id]
        _atomic_write(_masks_file(asset_id), json.dumps(raw, indent=0))
        return True
    return False


# --- baked geometry parked for geometry providers ------------------------------ #

def mesh_path(asset_id: str) -> Path | None:
    d = BAKES_DIR / "meshes"
    if not d.exists():
        return None
    hits = sorted(d.glob(f"{asset_id}.*"))
    return hits[0] if hits else None


def save_mesh(asset_id: str, src_path: str) -> Path:
    dst = BAKES_DIR / "meshes" / f"{asset_id}{Path(src_path).suffix.lower()}"
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src_path, dst)
    return dst


def save_parts(asset_id: str, parts: list[dict]) -> None:
    _atomic_write(BAKES_DIR / "parts" / f"{asset_id}.json", json.dumps(parts))


def load_parts(asset_id: str) -> list[dict]:
    f = BAKES_DIR / "parts" / f"{asset_id}.json"
    if not f.exists():
        return []
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
