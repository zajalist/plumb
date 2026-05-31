"""
vultr/serve.py — multi-model mask inference server for a Vultr GPU box.

Deployed TO the box; **not** imported by cortex. It hosts the heavier / arbitrary HF vision
models that HF's curated Inference-Providers router won't serve — a heavier segformer, SAM-style
instance segmentation, CLIPSeg text-prompted masks, and Depth-Anything depth. The cortex-side
``cortex/masks/providers/vultr.py`` POSTs a PNG to one route per model and gets small JSON back.

Design:
- **Lazy load + GPU-resident cache.** Each model loads on its first request and stays in
  ``_MODELS``; the heavy ``torch``/``transformers`` imports are deferred until then, so the app
  (and ``/health``) start instantly and CI can import this module without the ML stack.
- **Bearer auth on every route** (env ``VULTR_TOKEN``). Fail-closed: no token configured ⇒ 401.
- **Small JSON out, never images.** Segmentation routes return ``[{label, score}, …]`` (the shape
  the cortex band-projection consumes); ``/depth`` returns a downsampled scalar grid + min/max.
- Single-user hackathon box: no batching, queue, or persistence (YAGNI).

Run:
    VULTR_TOKEN=$(openssl rand -hex 16) uvicorn serve:app --host 0.0.0.0 --port 8001
"""

from __future__ import annotations

import io
import os

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse

app = FastAPI(title="plumb-vultr-masks")


@app.exception_handler(Exception)
async def _surface_errors(request: Request, exc: Exception) -> JSONResponse:
    """Return the real error (type + message) so the studio rail can show *why* a mask failed,
    instead of a bare 500. (HTTPException — e.g. the 401 auth — is handled by FastAPI separately.)"""
    return JSONResponse(status_code=500, content={"detail": f"{type(exc).__name__}: {exc}"})

_DEVICE = os.environ.get("VULTR_DEVICE", "cuda")
# task → loaded handle (pipeline or (model, processor)); populated lazily by the infer fns.
_MODELS: dict = {}

# Model ids — override via env to swap weights without editing code.
MODELS = {
    "segment": os.environ.get("VULTR_SEGMENT_MODEL", "nvidia/segformer-b4-finetuned-ade-512-512"),
    "sam": os.environ.get("VULTR_SAM_MODEL", "facebook/sam-vit-base"),
    "clipseg": os.environ.get("VULTR_CLIPSEG_MODEL", "CIDAS/clipseg-rd64-refined"),
    "depth": os.environ.get("VULTR_DEPTH_MODEL", "depth-anything/Depth-Anything-V2-Small-hf"),
}
GRID = int(os.environ.get("VULTR_DEPTH_GRID", "24"))  # depth downsample resolution


# --- auth ------------------------------------------------------------------------------------

def require_token(authorization: str = Header(default="")) -> None:
    expected = os.environ.get("VULTR_TOKEN", "")
    if not expected or authorization != f"Bearer {expected}":
        raise HTTPException(status_code=401, detail="unauthorized")


def _cuda() -> bool:
    import torch
    return _DEVICE == "cuda" and torch.cuda.is_available()


def _image(png: bytes):
    from PIL import Image
    return Image.open(io.BytesIO(png)).convert("RGB")


# --- inference (the per-model seams; cortex tests never reach here, serve tests mock these) ---

def infer_segment(png: bytes) -> list[dict]:
    """Semantic segmentation → one entry per detected region: ``{label, score}``."""
    from transformers import pipeline
    if "segment" not in _MODELS:
        _MODELS["segment"] = pipeline("image-segmentation", model=MODELS["segment"],
                                      device=0 if _cuda() else -1)
    out = _MODELS["segment"](_image(png))
    return [{"label": o.get("label", f"seg_{i}"), "score": float(o.get("score") or 0.0)}
            for i, o in enumerate(out)]


def infer_sam(png: bytes) -> list[dict]:
    """SAM automatic masks → synthesised labels ranked by area (SAM emits no class names)."""
    import numpy as np
    from transformers import pipeline
    if "sam" not in _MODELS:
        _MODELS["sam"] = pipeline("mask-generation", model=MODELS["sam"],
                                  device=0 if _cuda() else -1)
    out = _MODELS["sam"](_image(png), points_per_side=16)
    masks = out.get("masks", []) if isinstance(out, dict) else []
    areas = [float(np.asarray(m).mean()) for m in masks]
    order = sorted(range(len(areas)), key=lambda i: areas[i], reverse=True)
    return [{"label": f"part_{rank}", "score": areas[i]} for rank, i in enumerate(order)] \
        or [{"label": "region", "score": 1.0}]


def infer_clipseg(png: bytes, prompt: str) -> list[dict]:
    """CLIPSeg text-prompted mask → a single region named by the prompt, scored by mean prob."""
    import torch
    from transformers import CLIPSegForImageSegmentation, CLIPSegProcessor
    if "clipseg" not in _MODELS:
        proc = CLIPSegProcessor.from_pretrained(MODELS["clipseg"])
        model = CLIPSegForImageSegmentation.from_pretrained(MODELS["clipseg"])
        if _cuda():
            model = model.to("cuda")
        _MODELS["clipseg"] = (proc, model)
    proc, model = _MODELS["clipseg"]
    text = prompt or "object"
    inputs = proc(text=[text], images=[_image(png)], return_tensors="pt")
    if _cuda():
        inputs = {k: v.to("cuda") for k, v in inputs.items()}
    with torch.no_grad():
        logits = model(**inputs).logits
    score = float(torch.sigmoid(logits).mean().item())
    return [{"label": text, "score": score}]


def infer_depth(png: bytes) -> dict:
    """Monocular depth → a downsampled ``GRID``×``GRID`` scalar grid (rows top→bottom) + min/max."""
    import numpy as np
    from PIL import Image
    from transformers import pipeline
    if "depth" not in _MODELS:
        _MODELS["depth"] = pipeline("depth-estimation", model=MODELS["depth"],
                                    device=0 if _cuda() else -1)
    depth = _MODELS["depth"](_image(png))["depth"]
    small = np.asarray(depth.resize((GRID, GRID), Image.BILINEAR), dtype=float)
    return {"grid": small.tolist(), "min": float(small.min()), "max": float(small.max()),
            "h": GRID, "w": GRID}


# --- routes ----------------------------------------------------------------------------------

@app.get("/health")
def health(_: None = Depends(require_token)) -> dict:
    return {"ok": True, "device": _DEVICE, "loaded": sorted(_MODELS), "models": MODELS}


@app.post("/segment")
async def segment(request: Request, _: None = Depends(require_token)):
    return infer_segment(await request.body())


@app.post("/sam")
async def sam(request: Request, _: None = Depends(require_token)):
    return infer_sam(await request.body())


@app.post("/clipseg")
async def clipseg(request: Request, prompt: str = "", _: None = Depends(require_token)):
    return infer_clipseg(await request.body(), prompt)


@app.post("/depth")
async def depth(request: Request, _: None = Depends(require_token)):
    return infer_depth(await request.body())
