# PLUMB Mask System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the viewport's fixed 3-mode toggle with an extensible, provider-driven mask system (geometry / HF / Gemini / MCP sources) sharing one data model, on-disk store, and renderer, plus a UE4-styled grouped rail.

**Architecture:** New `cortex/masks/` package owns the `Mask` model, an atomic on-disk store (`bakes/masks/<asset_id>.json`), and a provider registry. `studio/server.py` (HTTP, UI) and `cortex/server.py` (MCP, agent) both import it. Frontend gets `masks.ts`, `MaskRail.tsx`, per-archetype renderers in `Viewport.tsx`, new `Icons.tsx` glyphs, and a Properties Semantics panel.

**Tech Stack:** Python 3.12 · FastAPI · FastMCP · Pydantic · trimesh/numpy/scipy · google-genai · HF Inference API (HTTP) · React + Vite + three.js + Vitest · pytest.

**Reference spec:** `docs/superpowers/specs/2026-05-31-plumb-mask-system-design.md`

---

## File structure

**Create (backend):**
- `cortex/masks/__init__.py` — public surface (`Mask`, `store`, `registry`, `compute`)
- `cortex/masks/model.py` — `Mask` Pydantic model + archetype data validators + legend derivation
- `cortex/masks/store.py` — atomic JSON store keyed by asset_id; mesh path helpers
- `cortex/masks/registry.py` — `MaskProvider`, `@register`, `catalog()`, `get(key)`, `Asset` adapter
- `cortex/masks/providers/__init__.py` — imports all provider modules (triggers registration)
- `cortex/masks/providers/geometry.py` — materials, curvature, thickness, contact_patches, symmetry_axes, gravity_field
- `cortex/masks/providers/hf.py` — saliency, part_segmentation (HF Inference API; `_hf_token()`)
- `cortex/masks/providers/ai.py` — affordances, fragility (reuse studio/semantics Gemini)
- `cortex/masks/providers/custom.py` — mcp `custom` ingest + `grasp_points` example seed helper

**Modify (backend):**
- `studio/server.py` — `/masks/providers`, `/masks/{id}`, `/masks/{id}/compute`, `DELETE`, `/health` hf flag, persist mesh on bake
- `cortex/server.py` — `list_masks`, `add_mask`, `compute_mask`, `remove_mask` tools
- `contracts.py` — add the 4 tool names to `MCP_TOOLS`
- `studio/semantics.py` — extend prompt to also return affordance regions + per-region fragility; add `_hf_token()` is in hf.py not here

**Create (frontend):**
- `studio/src/masks.ts` — `Mask` types + client (`providers/listMasks/computeMask/deleteMask`)
- `studio/src/MaskRail.tsx` — the UE4 rail
- `studio/src/maskRender.ts` — pure helpers: ramp→color, apply categorical/scalar to groups, build marker/vector objects

**Modify (frontend):**
- `studio/src/Viewport.tsx` — swap toggle → `MaskRail`; maskState; per-archetype renderers; `captureViewport`
- `studio/src/Icons.tsx` — `search`/`eye`/`eye-off`/`plus` glyphs, shared size
- `studio/src/Properties.tsx` — Semantics section
- `studio/src/App.tsx` — fetch health hf flag; pass to Viewport/Properties
- `studio/src/theme.css` — rail styles

**Tests:**
- `tests/test_masks_store.py`, `tests/test_masks_geometry.py`, `tests/test_masks_registry.py`, `tests/test_masks_api.py`, `tests/test_masks_mcp.py`
- `studio/src/MaskRail.test.tsx`

---

## Phase A — Mask core (model + store + registry)

### Task A1: `Mask` model
**Files:** Create `cortex/masks/model.py`, Test `tests/test_masks_store.py` (model bits)
- [ ] Define `Archetype`, `Source`, `Category`, `Role` literals; `Mask` Pydantic model (fields per spec §3).
- [ ] `role_for(archetype)` → categorical/scalar="surface", vector/markers="overlay".
- [ ] `derive_legend(mask)` → swatches for categorical (label+color), ramp+range for scalar, None else.
- [ ] Validator: `data` shape matches archetype (regions / per_part+range / samples|field / points+lines+axes).
- [ ] Test: construct one mask of each archetype; assert role + legend derivation; assert bad data raises.

### Task A2: atomic store
**Files:** Create `cortex/masks/store.py`, Test `tests/test_masks_store.py`
- [ ] `_path(asset_id)` → `bakes/masks/<asset_id>.json`; `BAKES_DIR` from repo root.
- [ ] `list(asset_id)->list[Mask]`, `get(asset_id,id)`, `upsert(mask)->Mask`, `delete(asset_id,id)->bool`.
- [ ] Atomic write: dump to `<file>.tmp` then `os.replace`. Read tolerates missing file (→ []).
- [ ] `mesh_path(asset_id, ext)` / `save_mesh(asset_id, src_path)` → `bakes/meshes/<asset_id>.<ext>`.
- [ ] Tests (use tmp `BAKES_DIR` via monkeypatch): upsert→list round-trip; delete; missing→[]; overwrite same id.

### Task A3: registry + Asset adapter
**Files:** Create `cortex/masks/registry.py`, `cortex/masks/__init__.py`, Test `tests/test_masks_registry.py`
- [ ] `@dataclass MaskProvider(key,name,source,category,archetype,role,needs_images, available:Callable, compute:Callable)`.
- [ ] `_REGISTRY: dict`; `register(provider)`; `catalog()->list[dict]` (metadata incl. `available()`); `get(key)`.
- [ ] `Asset` adapter: `.pap`, `.parts`, `.mesh()` (load trimesh from stored mesh or assemble from parts), `.images`.
- [ ] `compute(asset_id, provider_key, pap, images=None)->Mask`: resolve provider, run, wrap data → Mask, `store.upsert`.
- [ ] `__init__` re-exports + imports `providers` package so registration happens on import.
- [ ] Tests: register a dummy provider; `catalog()` includes it; `get` works; `compute` stores a mask.

---

## Phase B — Geometry providers (deterministic, local)

### Task B1–B6: providers in `cortex/masks/providers/geometry.py`
**Files:** Create `cortex/masks/providers/geometry.py`, Test `tests/test_masks_geometry.py`
Each provider `compute(asset)` returns archetype data; all `available()→True`, `needs_images=False`.
- [ ] `materials` (categorical): regions from `pap.parts` grouped by `part.material`, colour per group → reuse `part.color`.
- [ ] `curvature` (scalar): per-part mean |discrete mean curvature| from the mesh (trimesh `discrete_mean_curvature_measure` sampled to nearest part centroid), normalised → per_part + range.
- [ ] `thickness` (scalar): per-part shape-diameter (ray-cast inward from face centroids, mean per part) → per_part + range.
- [ ] `contact_patches` (markers): faces with normal·(-Z) > cos(20°) and low height → cluster centroids as points labelled "contact".
- [ ] `symmetry_axes` (markers): PCA of vertices (numpy eig of covariance) → 3 axes from centroid as `axes` entries.
- [ ] `gravity_field` (vector): `{"field":"gravity"}` (renderer reuses existing `buildForceField`).
- [ ] Tests on `studio/test_figure.obj` (or `fixtures.py`): each returns valid data; scalar ranges finite; deterministic (two runs equal); validate via `Mask(...)`.

---

## Phase C — HF + Gemini providers

### Task C1: HF token + providers
**Files:** Create `cortex/masks/providers/hf.py`, Test `tests/test_masks_api.py` (mocked)
- [ ] `_hf_token()` → env `HF_TOKEN`/`HUGGINGFACEHUB_API_TOKEN`, `.hf_token` repo-root fallback (gitignore it).
- [ ] `saliency` (scalar, needs_images): POST render to a HF saliency/segmentation model; reduce per-pixel saliency to per-part by projecting part screen-centroids → per_part + range. For v1, if projection is unavailable, distribute the image-level saliency histogram across parts by vertical band. `available()=bool(token)`.
- [ ] `part_segmentation` (categorical, needs_images): HF image-segmentation model on render; map segment labels → regions over parts by nearest band. `available()=bool(token)`.
- [ ] Network isolated behind `_hf_post(model, image_bytes)`; tests monkeypatch it.

### Task C2: Gemini providers
**Files:** Create `cortex/masks/providers/ai.py`; Modify `studio/semantics.py`, Test mocked
- [ ] Extend `semantics.py` with `semantic_masks(images, hint)` → `{affordance_regions:[{label,part_hint}], fragility:[{region,score}]}` (new prompt; reuse client/key logic).
- [ ] `affordances` (categorical/markers, needs_images): map Gemini affordance regions → markers points (labelled). `available()=semantics.gemini_status()['available']`.
- [ ] `fragility` (scalar, needs_images): Gemini per-region fragility → per_part scalar.
- [ ] Test: monkeypatch `semantic_masks`; assert provider returns valid Mask data.

---

## Phase D — MCP custom + cortex tools

### Task D1: custom ingest
**Files:** Create `cortex/masks/providers/custom.py`
- [ ] `ingest(asset_id, name, archetype, role, category, data)->Mask` → validate via `Mask`, `store.upsert`. source="mcp".
- [ ] `grasp_points` example seed helper used in tests/demo.

### Task D2: cortex MCP tools
**Files:** Modify `cortex/server.py`, `contracts.py`, Test `tests/test_masks_mcp.py`
- [ ] Add tool names to `contracts.MCP_TOOLS` (keep `test_server.py` green).
- [ ] `@mcp.tool() list_masks(asset_id)->json`; `add_mask(asset_id,name,archetype,role,category,data_json)->json` (custom.ingest); `compute_mask(asset_id,provider_key)->json` (server-side providers; raises for needs_images without images); `remove_mask(asset_id,mask_id)->json`.
- [ ] Tests: add_mask then list_masks via the tool functions against tmp store; remove_mask.

---

## Phase E — studio HTTP endpoints

### Task E1: endpoints + health + mesh persist
**Files:** Modify `studio/server.py`, Test `tests/test_masks_api.py`
- [ ] On `/bake` and `/bake_cached`: `store.save_mesh(asset_id, mesh_path)` after a successful bake.
- [ ] `GET /masks/providers` → `registry.catalog()`.
- [ ] `GET /masks/{asset_id}` → `{"masks":[m.model_dump()...]}`.
- [ ] `POST /masks/{asset_id}/compute`: multipart (images[] optional) + form `provider_key`; resolve `_ASSETS[asset_id]` PAP; call `masks.compute`; 404 unknown asset, 503 provider unavailable, 502 on compute error.
- [ ] `DELETE /masks/{asset_id}/{mask_id}` → `{ok}`.
- [ ] `/health`: add `"hf": {"available":bool(token),"key":bool(token)}`.
- [ ] Tests via `TestClient`: providers list; compute a geometry mask (bake a fixture first or seed `_ASSETS`); get returns it; delete.

---

## Phase F — Frontend data layer + icons

### Task F1: `masks.ts`
**Files:** Create `studio/src/masks.ts`
- [ ] Mirror `Mask`, `MaskProviderMeta`, archetype data types.
- [ ] `providers()`, `listMasks(assetId)`, `computeMask(assetId, providerKey, images?)` (multipart when images), `deleteMask(assetId, id)`.

### Task F2: icon glyphs
**Files:** Modify `studio/src/Icons.tsx`
- [ ] Add `<symbol id="i-search">`, `i-eye`, `i-eye-off`, `i-plus` in the existing style; ensure the `Icon` size prop is honoured uniformly (fix eye scaling — all rail icons render at one size token).

---

## Phase G — Rail + renderers

### Task G1: `maskRender.ts`
**Files:** Create `studio/src/maskRender.ts`
- [ ] `rampColor(t, ramp)`→hex; `applyCategorical(groups, regions)`, `applyScalar(groups, perPart, range, ramp)`, `clearOverlays(root)`, `buildMarkers(root, data)`, `buildVectorField(...)` (delegates to existing force field for `field:"gravity"`).

### Task G2: `MaskRail.tsx`
**Files:** Create `studio/src/MaskRail.tsx`, Modify `studio/src/theme.css`, Test `studio/src/MaskRail.test.tsx`
- [ ] Props: `assetId`, `available:{hf,gemini}`, `masks`, `catalog`, `state`, `onChangeState`, `onCompute(providerKey)`.
- [ ] Render filter box, Surface group (radio semantics) + Overlays group (eye toggles), bold condensed source pills, per-row thin progress bar while computing, error chip, disabled+hint when source unavailable, "Add mask…" footer.
- [ ] Vitest: renders catalog rows; clicking a surface row calls onCompute/onChangeState; disabled row when unavailable.

### Task G3: Viewport integration
**Files:** Modify `studio/src/Viewport.tsx`
- [ ] Replace `view` toggle with `MaskRail` (docked); `maskState {activeSurface:string, overlays:Set<string>}` (default activeSurface="textured").
- [ ] `captureViewport()` PNG helper; fetch `listMasks` on asset change; auto-compute on first activate.
- [ ] Effect applies active surface mask (textured = original materials; categorical/scalar via maskRender) and toggled overlays (markers/vector). Reuse `buildForceField` for gravity.

---

## Phase H — Properties + App wiring

### Task H1: Semantics panel + health
**Files:** Modify `studio/src/Properties.tsx`, `studio/src/App.tsx`
- [ ] App: `health()` already fetched — set `gemini`/`hf` availability state; pass to Viewport (MaskRail) + Properties.
- [ ] Properties: "Semantics" section showing `pap.semantics` (class/up/front/conf) + affordance chips when present.

---

## Phase I — Verify

- [ ] `./.venv/Scripts/python.exe -m pytest tests/test_masks_*.py tests/test_server.py -q` → all pass.
- [ ] `cd studio && npm run test` (Vitest) → MaskRail + existing pass; `npm run build` typechecks.
- [ ] Launch backend + studio; bake an asset; toggle geometry masks; (if keys) compute HF/Gemini; add an MCP mask via cortex tool and see it appear after refresh. Screenshot.
- [ ] Final commit.

---

## Self-review notes
- Spec coverage: §3 model→A1; §4 store→A2; §5 registry+catalog→A3,B,C,D1; §6 API→E1,D2; §7 frontend→F,G,H; §8 errors/tests→tests across; mesh persistence→E1; HF token fallback→C1.
- HF per-part projection is approximate in v1 (banding fallback) — acceptable; noted in spec §9 as refine-later.
- Naming consistency: `compute(asset_id, provider_key, pap, images)`, `store.upsert/list/get/delete`, `registry.catalog/get`, `maskState{activeSurface,overlays}` used consistently across tasks.
