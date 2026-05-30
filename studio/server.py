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

app = FastAPI(title="PLUMB Studio backend")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)

# In-memory asset registry (asset_id -> PAP). Reset on restart; the studio is the
# source of truth for the session, the backend just bakes + remembers.
_ASSETS: dict = {}


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
    """Run the real composition bake on an uploaded mesh and return its PAP.

    ``materials`` is an optional JSON map (part key -> material name) forwarded to
    ``cortex.bake.bake_asset``; absent => a pure auto-bake (every part ``default``).
    """
    from cortex.bake import bake_asset

    raw = await mesh.read()
    suffix = "." + (mesh.filename or "asset.obj").rsplit(".", 1)[-1]
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        f.write(raw)
        path = f.name

    asset_id = (mesh.filename or "asset").rsplit(".", 1)[0]
    part_materials = json.loads(materials) if materials else None
    try:
        pap = bake_asset(asset_id, path, part_materials=part_materials)
    except Exception as e:  # bad mesh / decomposition failure — surface, don't crash
        raise HTTPException(status_code=422, detail=f"bake failed: {e}") from e

    _ASSETS[asset_id] = pap
    return pap.model_dump()
