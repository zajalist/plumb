# Vultr-hosted masking — design spec

**Date:** 2026-05-31
**Status:** Approved (brainstorm), implementing.
**Builds on:** [2026-05-31-plumb-mask-system-design.md](2026-05-31-plumb-mask-system-design.md)

## Problem

Today the only ML mask source is `cortex/masks/providers/hf.py`, which calls HuggingFace's
hosted **Inference Providers router** (`router.huggingface.co/hf-inference`). That router only
serves a small curated model set — effectively just `segformer-b0` for `part_segmentation`,
which emits ADE20k *scene* labels, not object-aware part masks. We cannot run SAM, CLIPSeg,
Depth-Anything, or any heavier/niche vision model through it.

We have a **$100 Vultr credit** (MLH / MAJORLEAGUEHACKING perk). A Vultr GPU instance lets us
self-host arbitrary HF models and call them from the studio backend — unlocking "more advanced
masking with more models."

## Goal

Stand up an **extensible model-serving box** on Vultr plus the cortex-side providers that wire
each hosted model into the existing mask registry. Adding a model later = one route on the box
+ one `MaskProvider` registration, with **zero** changes to the rail, HTTP compute, or MCP.

## Non-goals

- Auto-provisioning / autoscaling the box (manual start/stop — see lifecycle).
- Batching, queueing, multi-user concurrency, persistence on the box (single-user hackathon).
- Changing the existing `hf.py` router provider — it stays as a free fallback.
- Frontend changes — new masks reuse existing archetypes (`categorical`/`scalar`), so the rail
  and renderers already handle them.

## Architecture (Approach A — generic remote inference server + thin provider per model)

```
vultr/                       ← deployed TO the Vultr GPU box (self-contained, not imported by cortex)
  serve.py                   FastAPI multi-model server: lazy-load + GPU-resident cache, bearer auth
  requirements.txt           torch, transformers, segment-anything-ish, fastapi, uvicorn, pillow
  bootstrap.sh               install deps, launch uvicorn on 0.0.0.0:8001
  README.md                  bring-up steps + LOUD destroy-after-use cost guardrail

cortex/masks/
  _project.py (or banding)   shared vertical-band projection helper (lifted from hf.py)
  providers/vultr.py         NEW — one MaskProvider per remote model, source="vultr"
  providers/__init__.py      + `from . import vultr`
studio/server.py             /health gains `vultr: {available, url}`; _vultr_status() inline
```

### Data flow (identical to existing image providers)

studio captures viewport renders → `POST /masks/{asset}/compute` (multipart, `images[]`) →
cortex `registry.compute()` → `vultr.py` provider → `_vultr_request(task, png, params)` →
Vultr box runs the model → returns small JSON → provider projects onto parts via the shared
vertical-band heuristic → `store.upsert(mask)` → rail renders by archetype.

## Model lineup (starter)

| Route | Model | Provider key | name | category | archetype → role | params |
|---|---|---|---|---|---|---|
| `/segment` | `nvidia/segformer-b4-finetuned-ade-512-512` | `part_segmentation_hq` | Part segmentation (HQ) | physics | categorical → mask | — |
| `/sam` | SAM2 (or MobileSAM) | `sam_parts` | SAM parts | physics | categorical → mask | — |
| `/clipseg` | `CIDAS/clipseg-rd64-refined` | `text_mask` | Text mask | physics | categorical → mask | `prompt` (str) |
| `/depth` | `depth-anything/Depth-Anything-V2-Small-hf` | `depth` | Depth | artistic | scalar → gradient | — |

`text_mask` pairs with the Gemini provider (Gemini names a part → CLIPSeg masks it). Niche
additions (normals, material-seg) drop in as another route + provider, no plumbing change.

## The Vultr serving app (`vultr/serve.py`)

- **One FastAPI app**, routes: `GET /health`, `POST /segment`, `POST /sam`, `POST /clipseg`,
  `POST /depth`. Inference routes accept a **PNG body** (`Content-Type: image/png`) plus optional
  query/JSON params (CLIPSeg `prompt`). They return **small JSON only — never raw images**.
  - Segmentation routes return `[{label, score}, ...]` (same shape today's `_hf_request`
    returns), so cortex's existing band projection consumes them unchanged.
  - `/depth` returns `{grid: [[...]], min, max, h, w}` — a downsampled scalar grid.
- **Lazy load + cache:** module-level `_MODELS` dict; each model loads on first request and stays
  resident. `/health` reports `{ok, device, loaded: [...], models: [...]}`.
- **Auth:** bearer token from env `VULTR_TOKEN`; every route 401s without it. Bind `0.0.0.0:8001`.
- **No persistence / queue / batching.** YAGNI.

## The cortex provider (`cortex/masks/providers/vultr.py`)

- Mirrors `hf.py`. `_vultr_request(task, image_bytes, params)` is the **mockable network seam**.
- **Config** resolves like the HF/Gemini keys: `PLUMB_VULTR_URL` / `PLUMB_VULTR_TOKEN` env, with
  gitignored `.vultr_url` / `.vultr_token` repo-root file fallbacks.
- `available()` → `True` only when a URL is configured **and** a short-TTL-cached `/health` ping
  succeeds, so the rail greys these out when the box is down (graceful degradation).
- Registers the 4 providers above; segmentation ones reuse the lifted band-projection helper.

## Shared helper

`hf.py` and `vultr.py` both map "ordered segment labels → part_ids by vertical band". Lift
`_znorm` + the band-assignment loop into a shared module (e.g. `cortex/masks/banding.py`) and
have both providers call it. Behaviour-preserving; `test_masks_ai_hf.py` stays green.

## Lifecycle & cost ops

- **Manual start/stop.** Spin a single cheap GPU instance up before a session, destroy it after.
- `vultr/README.md` documents: create GPU instance → `git pull` the `vultr/` folder →
  `bootstrap.sh` → copy public IP into local `.vultr_url`, token into `.vultr_token`.
- **Burn rate stated loudly:** a ~$0.50–1/hr GPU ⇒ ~100–200 hrs of the $100 credit; an always-on
  box would silently drain it. README flags "DESTROY THE INSTANCE AFTER EACH SESSION" up top.

## Testing

- `tests/test_masks_vultr.py` — providers with `_vultr_request` mocked (mirrors
  `test_masks_ai_hf.py`): registration in catalog, band projection for `sam_parts` /
  `part_segmentation_hq`, `prompt` passthrough for `text_mask`, depth scalar shape, and
  `available()` gating (no URL → unavailable; `compute` raises `RuntimeError`).
- `tests/test_vultr_serve.py` — `serve.py` via FastAPI `TestClient` with models monkeypatched:
  `/health` ok, auth rejection (401 without bearer), one inference route returns expected JSON
  shape. No real weights in CI.

## Out-of-scope / later

normals & material-segmentation routes, own-mesh socket sampling, camera-matrix-accurate
back-projection (current band heuristic is the documented approximation, same as hf/gemini).
