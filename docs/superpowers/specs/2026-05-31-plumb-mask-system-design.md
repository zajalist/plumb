# PLUMB Mask System — design spec

**Date:** 2026-05-31 · **Status:** approved, implementing · **Author:** Badr + Claude

## 1. Goal

Replace the viewport's fixed 3-mode toggle (`textured` / `masks` / `inertia`) with an
**extensible mask system**: many semantic overlays on a baked asset, computed from three
kinds of source — deterministic/ML, AI, and agent-authored — all sharing one data model,
store, and renderer. This round delivers the **framework + a starter catalog (~12 masks)**
proving every source × every render archetype.

## 2. Decisions (locked during brainstorming)

- **Scope:** framework + starter set across all 3 sources (not deep-on-one).
- **Render archetypes (all four):** `categorical` (flat colours per region), `scalar`
  (continuous heatmap), `vector` (arrows/field), `markers` (points/lines/axes).
  These absorb today's `materials` (categorical) and `inertia` (scalar+vector).
- **ML masks: hybrid** — pure-geometry masks computed locally with `trimesh`/`numpy`
  (deterministic, free, no install); true-ML masks via the **HuggingFace Inference API**
  (HTTP + token, no `torch`/`transformers` install).
- **MCP:** add new mask tools to the **existing** `cortex/server.py` FastMCP surface.
- **Persistence:** the two backends (`studio/server.py` HTTP, `cortex/server.py` MCP) hold
  separate in-memory state, so masks live in a **shared on-disk store** keyed by `asset_id`.
- **UI:** a **grouped rail, UE4 Details-panel styled** — slate category bars, disclosure
  arrows, eye-toggle visibility, bold condensed source pills, filter box, "Add mask…"
  footer. One **surface mask** active (radio semantics) + any number of **overlays**
  (eye-toggles). PLUMB teal selection accent. Inter body font.
- **Compute:** auto-compute on click, with a **thin per-row progress bar** (no spinner).
- **Retouch boundary:** viewport + rail + Properties "Semantics" panel only — not a
  full-app restyle.
- **Architecture:** Approach 1 — shared mask core + provider registry.

## 3. Data model — `cortex/masks/model.py`

```
Mask (Pydantic, mirrored in studio/src/masks.ts):
  id: str            # stable per asset+provider, e.g. "graspability"
  asset_id: str
  name: str          # display label
  source: Literal["geometry","hf","gemini","mcp"]
  category: Literal["material","physics","artistic","affordance","custom"]
  archetype: Literal["categorical","scalar","vector","markers"]
  role: Literal["surface","overlay"]     # derived: categorical/scalar→surface; vector/markers→overlay
  data: dict          # archetype-specific (below)
  legend: dict        # derived: {"kind":"swatches","items":[...]} | {"kind":"ramp","range":[lo,hi],"ramp":"..."}
  confidence: float | None
  provider_key: str
  version: int = 1
```

`data` by archetype (binds to the PAP's convex `parts`, which carry id + centroid + verts/tris):
- **categorical:** `{"regions":[{"label","color","part_ids":[...]}]}`
- **scalar:** `{"per_part":{part_id: float}, "range":[lo,hi], "ramp":"plasma", "per_vertex": optional {mesh_key: float[]}}`
- **vector:** `{"samples":[{"origin":[x,y,z],"vec":[x,y,z]}]}` or `{"field":"gravity"}` (procedural, reuses existing code)
- **markers:** `{"points":[{"pos","label","kind"}], "lines":[{"a","b","label"}], "axes":[{"origin","dir","label"}]}`

## 4. Storage — `cortex/masks/store.py`

`bakes/masks/<asset_id>.json` = `{"asset_id", "masks": {id: Mask}}`. API: `list(asset_id)`,
`get(asset_id, id)`, `upsert(mask)`, `delete(asset_id, id)`. Writes are **atomic**
(temp file + `os.replace`). The bake additionally persists the converted mesh to
`bakes/meshes/<asset_id>.<ext>` so geometry providers can load it on demand.
`bakes/` is already gitignored.

## 5. Provider registry — `cortex/masks/registry.py` + `cortex/masks/providers/`

Each provider self-registers via `@register`:
```
MaskProvider:
  key, name, source, category, archetype, role
  needs_images: bool          # True → requires client renders (HF/Gemini)
  available() -> bool         # gates on token/key/deps
  compute(asset, images=None) -> data   # asset exposes pap, mesh path/trimesh, parts
```

### Starter catalog (~12)
| source | masks |
|---|---|
| geometry | `materials`(categorical, port) · `curvature`(scalar) · `thickness`(scalar) · `contact_patches`(markers) · `symmetry_axes`(markers) · `gravity_field`(vector, port inertia) |
| hf (Inference API, needs_images) | `saliency`(scalar, artistic) · `part_segmentation`(categorical, physics) |
| gemini (needs_images) | `affordances`(categorical/markers) · `fragility`(scalar) |
| mcp (ingested, no compute) | `custom`(any archetype) + example `grasp_points`(markers) |

- HF key resolved like the Gemini key: env `HF_TOKEN`/`HUGGINGFACEHUB_API_TOKEN`, with a
  `.hf_token` repo-root file fallback (gitignored), mirroring `semantics._key()`.
- Gemini providers reuse `studio/semantics.py` (extend its prompt to also return
  affordance regions + a fragility-per-region score). This folds in the leftover Gemini
  frontend work from the earlier handoff.

## 6. API surface

**studio HTTP (`studio/server.py`):**
- `GET /masks/providers` → catalog metadata (key, name, source, category, archetype, role, available)
- `GET /masks/{asset_id}` → `{masks:[Mask...]}` from the store
- `POST /masks/{asset_id}/compute` → run a provider, store, return the `Mask`.
  multipart with `images[]` when `needs_images`; JSON `{provider_key}` otherwise.
- `DELETE /masks/{asset_id}/{mask_id}`
- `GET /health` gains `hf: {available, key}` beside `gemini`.

**cortex MCP (`cortex/server.py`):** `list_masks(asset_id)`, `add_mask(asset_id, name,
archetype, role, category, data_json)`, `compute_mask(asset_id, provider_key)`,
`remove_mask(asset_id, mask_id)` — all delegate to `cortex.masks`. Registered in
`contracts.MCP_TOOLS` so the existing test (`test_server.py`) stays green.

## 7. Frontend

- `studio/src/masks.ts` — `Mask` types + client (`providers()`, `listMasks()`,
  `computeMask()`, `deleteMask()`).
- `studio/src/MaskRail.tsx` — the UE4 rail: filter, Surface (radio) / Overlays (eye-toggle)
  groups, bold condensed source pills, "Add mask…" footer, auto-compute-on-click with a
  thin per-row progress bar, per-row error chip, disabled+hint when source unavailable.
- `studio/src/Viewport.tsx` — replace the 3-button toggle with `MaskRail`; `maskState
  {activeSurface, overlays:Set<string>}`; per-archetype renderers:
  categorical (recolour part meshes by region colour), scalar (per-part colour from ramp;
  per-vertex vertex-colours when present), vector (arrow field, reuse `buildForceField`),
  markers (sphere/line/axis sprites). Capture renders for image providers via the existing
  `preserveDrawingBuffer` + a `captureViewport()` helper.
- `studio/src/Icons.tsx` — add `search` / `eye` / `eye-off` / `plus` glyphs in the existing
  SVG-symbol style, all using **one shared size token** (fixes the eye-scaling nit).
- `studio/src/Properties.tsx` — "Semantics" section (class / up / front / confidence) fed by
  the Gemini bake, plus mask provenance.

## 8. Errors & testing

- Unavailable source → `available:false` in the catalog → rail row disabled with a hint
  (mirrors the existing `gemini.available` gate). Compute failure → 502/503 → row error chip
  + retry. Store writes atomic. Client queues concurrent computes.
- Tests: store round-trip; each geometry provider deterministic on `fixtures.py` /
  `studio/test_figure.obj`; registry registration; API via FastAPI `TestClient`; HF/Gemini
  providers with mocked network; MCP `add_mask`/`list_masks` on a temp store; a `MaskRail`
  render/toggle test (Vitest).

## 9. Out of scope (later rounds)

Local `torch` models; per-vertex masks from 2D ML (back-projection); layer-stack/opacity UI;
mask diffing/versioning beyond `version`; full-app restyle.
