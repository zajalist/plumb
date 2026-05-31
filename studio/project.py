"""
studio/project.py — project persistence: save/open a project that bundles BOTH the
``.wdf`` semantic data AND the actual 3D model files, in one environment on disk.

A project lives at ``<PLUMB_PROJECTS>/<name>/``:
  project.wdf      — the scene's semantic language (vocabulary of assets + their
                     per-mask materials), generated from the baked assets.
  manifest.json    — the asset records (id, name, main file, file list, PAP) so a
                     re-open restores everything without re-baking.
  models/<id>/...  — the real model files (gltf + bin + textures, glb, obj, …).

Default dir: ``~/plumb_projects`` (override with ``PLUMB_PROJECTS``).
"""

from __future__ import annotations

import json
import os
import re
import time

PROJ_DIR = os.environ.get("PLUMB_PROJECTS") or os.path.join(os.path.expanduser("~"), "plumb_projects")


def _safe(name: str) -> str:
    s = "".join(c for c in (name or "") if c.isalnum() or c in "-_ .").strip()
    return s or "untitled"


def _ident(s: str) -> str:
    """A valid .wdf identifier (letters/digits/underscore, not starting with a digit)."""
    out = re.sub(r"\W", "_", s or "asset")
    return ("a_" + out) if out[:1].isdigit() else out


def projects_dir() -> str:
    os.makedirs(PROJ_DIR, exist_ok=True)
    return PROJ_DIR


def _project_path(name: str) -> str:
    return os.path.join(projects_dir(), _safe(name))


def _generate_wdf(name: str, assets: list[dict]) -> str:
    """Build a .wdf vocabulary+scene from the baked assets (each asset → a noun with
    its per-mask materials; placements drop them at the origin)."""
    try:
        from conscience.wdf import Asset, Placement, Scene, Vocabulary, WdfDocument, dumps
    except Exception:
        return ""
    vocab, placements = [], []
    for a in assets:
        ident = _ident(a.get("id") or a.get("name") or "asset")
        materials = {str(m.get("id")): str(m.get("material", "default")) for m in a.get("masks", [])}
        vocab.append(Asset(name=ident, profile=a.get("profile") or "rigid_prop", material=materials))
        placements.append(Placement(asset=ident, target="origin", preposition="at"))
    doc = WdfDocument(
        vocabulary=Vocabulary(assets=vocab),
        scene=Scene(name=_ident(name), placements=placements),
    )
    try:
        return dumps(doc)
    except Exception:
        return ""


def save_project(name: str, assets: list[dict], files: dict[str, bytes]) -> dict:
    """Write a project. ``assets`` are the manifest records; ``files`` maps
    ``"<asset_id>__<filename>"`` → bytes (the model files)."""
    root = _project_path(name)
    os.makedirs(os.path.join(root, "models"), exist_ok=True)

    for key, data in files.items():
        aid, _, fn = key.partition("__")
        mdir = os.path.join(root, "models", _safe(aid))
        os.makedirs(mdir, exist_ok=True)
        with open(os.path.join(mdir, os.path.basename(fn)), "wb") as f:
            f.write(data)

    with open(os.path.join(root, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump({"name": name, "assets": assets, "saved": time.time()}, f)
    wdf = _generate_wdf(name, assets)
    if wdf:
        with open(os.path.join(root, "project.wdf"), "w", encoding="utf-8") as f:
            f.write(wdf)
    return {"name": _safe(name), "assets": len(assets)}


def list_projects() -> list[dict]:
    out = []
    for entry in sorted(os.listdir(projects_dir())) if os.path.isdir(PROJ_DIR) else []:
        man = os.path.join(PROJ_DIR, entry, "manifest.json")
        if os.path.isfile(man):
            try:
                with open(man, encoding="utf-8") as f:
                    m = json.load(f)
                out.append({"name": entry, "assets": len(m.get("assets", [])), "saved": m.get("saved", 0)})
            except Exception:
                continue
    return sorted(out, key=lambda p: p.get("saved", 0), reverse=True)


def load_project(name: str) -> dict | None:
    root = _project_path(name)
    man = os.path.join(root, "manifest.json")
    if not os.path.isfile(man):
        return None
    with open(man, encoding="utf-8") as f:
        manifest = json.load(f)
    wdf = ""
    wp = os.path.join(root, "project.wdf")
    if os.path.isfile(wp):
        with open(wp, encoding="utf-8") as f:
            wdf = f.read()
    return {"manifest": manifest, "wdf": wdf}


def model_file(name: str, asset_id: str, filename: str) -> str | None:
    p = os.path.join(_project_path(name), "models", _safe(asset_id), os.path.basename(filename))
    return p if os.path.isfile(p) else None
