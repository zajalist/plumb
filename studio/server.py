"""PLUMB Studio backend — a thin FastAPI bridge that exposes the real ``cortex``
to the browser over request/response HTTP (Option A, per the design spec).

The studio UI never runs physics; it POSTs to these endpoints and renders the
returned PAP / Verdict JSON (mirrors of the frozen ``contracts.py``). Run with::

    ./.venv/Scripts/python.exe -m uvicorn studio.server:app --port 8000
"""
from __future__ import annotations

import json
import tempfile

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="PLUMB Studio backend")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)

# In-memory asset registry (asset_id -> PAP) + the session world that holds placed
# assets. Reset on restart; the studio is the source of truth for the session, the
# backend bakes + remembers + validates.
_ASSETS: dict = {}


def _world():
    """Lazily create the session WorldModel (import cortex on demand)."""
    global _WORLD
    if _WORLD is None:
        from cortex.world import WorldModel

        _WORLD = WorldModel()
    return _WORLD


_WORLD = None


class Placement(BaseModel):
    """A proposed placement of a baked asset at a transform (canonical space)."""

    object: str
    pos: list[float]
    quat: list[float] = [0.0, 0.0, 0.0, 1.0]


def _place(p: Placement):
    """Ensure ``p.object`` sits in the session world at ``p`` and return its Transform."""
    from contracts import Transform

    if p.object not in _ASSETS:
        raise HTTPException(status_code=404, detail=f"unknown asset {p.object!r}; bake it first")
    tf = Transform(pos=p.pos, quat=p.quat)
    world = _world()
    if p.object in world.nodes():
        world.update_transform(p.object, tf)
    else:
        world.add(p.object, _ASSETS[p.object], tf)
    return tf


def _cortex_available() -> bool:
    try:
        import cortex.bake  # noqa: F401

        return True
    except Exception:
        return False


@app.get("/health")
def health() -> dict:
    """Liveness + whether the real cortex is importable in this process."""
    return {"ok": True, "cortex": _cortex_available()}


@app.post("/bake")
async def bake(mesh: UploadFile = File(...), materials: str | None = Form(None)) -> dict:
    """Run the real composition bake on an uploaded mesh and return its PAP + masks.

    ``materials`` is an optional JSON map (part key -> material name) forwarded to
    ``cortex.bake``; absent => a pure auto-bake (default-density physics + a
    low-confidence material guess per part). The response is the PAP plus a
    ``parts`` array: the per-part masks (volume fraction, displayed material +
    confidence, mask colour, hollowness) the studio renders and the human confirms.
    """
    from cortex.bake import bake_asset_detailed

    raw = await mesh.read()
    suffix = "." + (mesh.filename or "asset.obj").rsplit(".", 1)[-1]
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        f.write(raw)
        path = f.name

    asset_id = (mesh.filename or "asset").rsplit(".", 1)[0]
    part_materials = json.loads(materials) if materials else None
    try:
        pap, parts = bake_asset_detailed(asset_id, path, part_materials=part_materials)
    except Exception as e:  # bad mesh / decomposition failure — surface, don't crash
        raise HTTPException(status_code=422, detail=f"bake failed: {e}") from e

    _ASSETS[asset_id] = pap
    return {**pap.model_dump(), "parts": parts}


@app.post("/validate")
def validate(p: Placement) -> dict:
    """Place the asset at ``p`` and run the real gate stack. Returns the Verdict."""
    from contracts import Diff
    from cortex.orchestrator import validate_operation

    tf = _place(p)
    verdict = validate_operation(_world(), Diff(object=p.object, transform=tf))
    return verdict.model_dump()


@app.post("/repair")
def repair(p: Placement) -> dict:
    """Run the SLSQP repair for the placed asset. Returns the suggested Transform."""
    from cortex.repair import suggest_transform

    _place(p)
    new_tf = suggest_transform(_world(), p.object, intent={})
    return new_tf.model_dump()


@app.post("/commit")
def commit(p: Placement) -> dict:
    """Commit the placement into the session world (UE5 dispatch is a later WP)."""
    _place(p)
    return {"ok": True, "object": p.object}
