"""PLUMB Studio backend — a thin FastAPI bridge that exposes the real ``cortex``
to the browser over request/response HTTP (Option A, per the design spec).

The studio UI never runs physics; it POSTs to these endpoints and renders the
returned PAP / Verdict JSON (mirrors of the frozen ``contracts.py``). Run with::

    ./.venv/Scripts/python.exe -m uvicorn studio.server:app --port 8000
"""
from __future__ import annotations

import json
import os
import tempfile
import uuid

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
# token -> converted .glb path, for batch .uasset conversion (one UE boot, bake later).
_GLB_CACHE: dict[str, str] = {}


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
    """Liveness + whether cortex, Unreal convert, and the Gemini semantic bake are wired."""
    from studio.semantics import gemini_status
    from studio.uasset import ue_status

    return {"ok": True, "cortex": _cortex_available(), "ue": ue_status(), "gemini": gemini_status()}


@app.post("/semantics")
async def semantics(
    asset_id: str = Form(""),
    hint: str = Form(""),
    images: list[UploadFile] = File(...),
) -> dict:
    """AI semantic bake: send viewport renders to Gemini → class / up / front /
    per-region materials / affordances. Folds the inferred class into the stored PAP."""
    from studio.semantics import gemini_status, semantic_bake

    if not gemini_status()["available"]:
        raise HTTPException(
            status_code=503,
            detail="Gemini not configured — set GEMINI_API_KEY (free key at https://aistudio.google.com).",
        )
    imgs = [await im.read() for im in images][:4]
    if not imgs:
        raise HTTPException(status_code=422, detail="no render images provided")
    try:
        sem = semantic_bake(imgs, hint)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Gemini error: {e}") from e

    # fold the inferred class into the stored PAP so the rest of the app sees it.
    cls = sem.get("class")
    if cls and asset_id in _ASSETS:
        try:
            _ASSETS[asset_id].semantics.cls = str(cls)
        except Exception:
            pass
    return sem


def _maybe_decimate(path: str, target_faces: int) -> str:
    """Best-effort quadric-decimate ``path`` to ~``target_faces`` so CoACD stays fast.

    Returns a new temp mesh path on success, else the original path unchanged (the
    setting is a hint, never a hard failure — we never block a bake on it).
    """
    try:
        import trimesh

        mesh = trimesh.load(path, force="mesh", process=False)
        if not isinstance(mesh, trimesh.Trimesh) or len(mesh.faces) <= target_faces:
            return path
        simplified = mesh.simplify_quadric_decimation(face_count=target_faces)
        if simplified is None or len(simplified.faces) == 0:
            return path
        out = tempfile.NamedTemporaryFile(suffix=".obj", delete=False)
        out.close()
        simplified.export(out.name)
        return out.name
    except Exception:
        return path  # decimation unsupported / failed → bake the original


@app.post("/bake")
async def bake(
    mesh: UploadFile = File(...),
    materials: str | None = Form(None),
    profile: str = Form("rigid_prop"),
    decimate: int | None = Form(None),
    cap: bool = Form(False),
    extras: list[UploadFile] = File(default=[]),
) -> dict:
    """Run the real composition bake on an uploaded mesh and return its PAP + masks.

    ``materials`` is an optional JSON map (part key -> material name); absent => a pure
    auto-bake (default-density physics + a low-confidence guess per part). ``profile``
    selects the bake archetype; ``decimate`` (target face count) best-effort simplifies
    dense meshes first so CoACD stays fast. ``extras`` are sidecar files for
    non-self-contained formats — a ``.gltf`` references its geometry in a ``.bin`` (and
    textures) by relative name, so we stage them alongside it. The response is the PAP
    plus a ``parts`` array: the per-part masks the studio renders and the human confirms.
    """
    from cortex.bake import bake_asset_detailed

    from studio.uasset import convert_uasset, is_uasset, ue_status

    fn = mesh.filename or "asset.obj"
    raw = await mesh.read()

    if is_uasset(fn):
        # Unreal .uasset → headless glTF first (then bake the glb like any other mesh).
        with tempfile.NamedTemporaryFile(suffix=".uasset", delete=False) as f:
            f.write(raw)
            upath = f.name
        if not ue_status()["available"]:
            raise HTTPException(
                status_code=503,
                detail="Unreal not configured (set PLUMB_UE_CMD + PLUMB_UE_PROJECT) — import .obj/.glb/.stl instead",
            )
        glb = convert_uasset(fn, upath)
        if not glb:
            raise HTTPException(status_code=422, detail=f"Unreal produced no mesh for {fn}")
        path = glb
    else:
        # Save into a temp DIR (not a lone temp file) so a .gltf can resolve its
        # sibling .bin / textures by the relative names baked into the file.
        work = tempfile.mkdtemp(prefix="plumb_mesh_")
        path = os.path.join(work, os.path.basename(fn))
        with open(path, "wb") as f:
            f.write(raw)
        for ex in extras:
            if ex.filename:
                with open(os.path.join(work, os.path.basename(ex.filename)), "wb") as f:
                    f.write(await ex.read())
        # Sidecars are staged flat (by basename), but a .gltf may reference them with
        # subfolders (textures/foo.jpg). Rewrite its buffer/image URIs to basenames so
        # they resolve against the flat staging dir regardless of the original nesting.
        if fn.lower().endswith(".gltf"):
            try:
                with open(path, encoding="utf-8") as f:
                    doc = json.load(f)
                for coll in ("buffers", "images"):
                    for item in doc.get(coll, []):
                        uri = item.get("uri")
                        if uri and not uri.startswith("data:"):
                            item["uri"] = os.path.basename(uri.split("?")[0])
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(doc, f)
            except Exception:
                pass

    if decimate:
        path = _maybe_decimate(path, int(decimate))

    asset_id = fn.rsplit(".", 1)[0]
    part_materials = json.loads(materials) if materials else None
    try:
        pap, parts = bake_asset_detailed(asset_id, path, part_materials=part_materials, profile=profile, cap=cap)
    except Exception as e:  # bad mesh / decomposition failure — surface, don't crash
        msg = str(e)
        if fn.lower().endswith(".gltf") and ("No such file" in msg or ".bin" in msg):
            msg = (".gltf needs its external files — drop the .gltf together with its "
                   ".bin and textures, or import the self-contained .glb instead.")
        raise HTTPException(status_code=422, detail=f"bake failed: {msg}") from e

    _ASSETS[asset_id] = pap
    return {**pap.model_dump(), "parts": parts}


@app.post("/convert")
async def convert(files: list[UploadFile] = File(...)) -> dict:
    """Batch-convert dropped ``.uasset`` files to glTF in ONE Unreal boot.

    Returns ``{results: [{name, token, ok}]}``; bake each ``token`` via
    ``/bake_cached`` (fast — the conversion already happened). Non-uasset files are
    ignored here (the UI bakes those directly through ``/bake``).
    """
    from studio.uasset import convert_uassets, is_uasset, ue_status

    if not ue_status()["available"]:
        raise HTTPException(status_code=503, detail="Unreal not configured (PLUMB_UE_CMD + PLUMB_UE_PROJECT)")

    staged: dict[str, str] = {}
    for uf in files:
        if not is_uasset(uf.filename or ""):
            continue
        raw = await uf.read()
        with tempfile.NamedTemporaryFile(suffix=".uasset", delete=False) as f:
            f.write(raw)
            staged[uf.filename] = f.name
    if not staged:
        raise HTTPException(status_code=422, detail="no .uasset files in request")

    converted = convert_uassets(staged)
    results = []
    for name, glb in converted.items():
        if glb:
            token = uuid.uuid4().hex
            _GLB_CACHE[token] = glb
            results.append({"name": name, "token": token, "ok": True})
        else:
            results.append({"name": name, "token": None, "ok": False})
    return {"results": results}


class CachedBake(BaseModel):
    """Bake a previously-converted asset by its conversion ``token``."""

    token: str
    materials: dict | None = None
    profile: str = "rigid_prop"
    decimate: int | None = None


@app.post("/bake_cached")
def bake_cached(b: CachedBake) -> dict:
    """Bake a glb already produced by ``/convert`` (no re-conversion)."""
    from cortex.bake import bake_asset_detailed

    glb = _GLB_CACHE.get(b.token)
    if not glb or not os.path.exists(glb):
        raise HTTPException(status_code=404, detail="unknown or expired conversion token")
    path = _maybe_decimate(glb, int(b.decimate)) if b.decimate else glb
    asset_id = os.path.splitext(os.path.basename(glb))[0]
    try:
        pap, parts = bake_asset_detailed(asset_id, path, part_materials=b.materials, profile=b.profile)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"bake failed: {e}") from e
    _ASSETS[asset_id] = pap
    return {**pap.model_dump(), "parts": parts}


@app.post("/open_wdf")
async def open_wdf(doc: UploadFile = File(...)) -> dict:
    """Parse a ``.wdf`` document and return its scene as JSON.

    The vocabulary's per-asset ``material`` maps are the declared semantic *masks*;
    the scene's ``laws`` are the constraints. The studio renders both — no bake
    needed, the language already carries the meaning.
    """
    from dataclasses import asdict

    from conscience.wdf import WdfParseError, loads

    text = (await doc.read()).decode("utf-8", "replace")
    try:
        parsed = loads(text)
    except WdfParseError as e:
        raise HTTPException(status_code=422, detail=f".wdf parse error: {e}") from e
    return asdict(parsed)


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
