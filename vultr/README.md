# Vultr mask-inference box

Self-hosts the heavier / arbitrary HF vision models that HF's curated Inference-Providers router
won't serve, so the studio can compute advanced masks (SAM parts, text-prompted masks, depth, a
heavier segformer). Funded by the **$100 MLH/Vultr credit**.

> ## ⚠️ DESTROY THE INSTANCE AFTER EACH SESSION
> A single GPU instance bills **by the hour**. At ~$0.50–1/hr the $100 credit lasts **~100–200
> hours** — but only if you **destroy** (not just stop) the instance when you're done. An
> always-on box silently drains the whole credit in under a week. Spin up → work → destroy.

## What it is

`serve.py` is a small FastAPI app. One route per model; each model lazy-loads into GPU memory on
its first request and stays resident. Every route requires a bearer token. It returns **small
JSON only** — never images.

| Route | Model (default, override via env) | Returns |
|---|---|---|
| `GET /health` | — | `{ok, device, loaded, models}` |
| `POST /segment` | `nvidia/segformer-b4-finetuned-ade-512-512` | `[{label, score}, …]` |
| `POST /sam` | `facebook/sam-vit-base` | `[{label, score}, …]` (labels synthesised by area) |
| `POST /clipseg?prompt=handle` | `CIDAS/clipseg-rd64-refined` | `[{label, score}]` |
| `POST /depth` | `depth-anything/Depth-Anything-V2-Small-hf` | `{grid, min, max, h, w}` |

Inference routes take a **PNG body** (`Content-Type: image/png`).

## Bring-up

1. **Create a GPU instance** on Vultr (Cloud GPU → cheapest single NVIDIA GPU, Ubuntu 22.04).
   Open **port 8001** in the instance firewall.
2. **Get the code onto the box:**
   ```bash
   git clone <this-repo> && cd <repo>/vultr
   # or: scp -r vultr/ root@<ip>:~/vultr
   ```
3. **Run bootstrap** (installs CUDA torch + deps, prints a token, launches the server):
   ```bash
   bash bootstrap.sh
   ```
   If the instance's CUDA version isn't 12.1, edit the `cu121` wheel index in `bootstrap.sh`.
4. **Wire the studio to the box** — back on your machine, in the repo root:
   ```bash
   echo "http://<INSTANCE_PUBLIC_IP>:8001" > .vultr_url
   echo "<TOKEN_PRINTED_BY_BOOTSTRAP>"     > .vultr_token
   ```
   (Both are gitignored. You can also set `PLUMB_VULTR_URL` / `PLUMB_VULTR_TOKEN` env vars.)
5. Restart the studio backend. The Vultr masks now appear (un-greyed) in the mask rail; the
   backend's `GET /health` shows `vultr: {available: true}`.

## Smoke test

```bash
TOK=$(cat .vultr_token); URL=$(cat .vultr_url)
curl -s -H "Authorization: Bearer $TOK" "$URL/health" | jq
curl -s -H "Authorization: Bearer $TOK" -H "Content-Type: image/png" \
     --data-binary @render.png "$URL/segment" | jq
```

## Swapping / adding models

- **Swap weights:** set `VULTR_SEGMENT_MODEL` / `VULTR_SAM_MODEL` / `VULTR_CLIPSEG_MODEL` /
  `VULTR_DEPTH_MODEL` before launching — no code change.
- **Add a model:** add an `infer_<task>()` + a route in `serve.py`, then register a matching
  `MaskProvider` in `cortex/masks/providers/vultr.py`. It auto-appears in the rail, HTTP compute,
  and MCP — no other wiring.

## When you're done

**Destroy the instance** in the Vultr console (Server → Destroy). Stopping is not enough on some
plans — destroy to stop billing. Delete `.vultr_url` locally so the rail greys the masks back out.
