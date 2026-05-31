# Handoff: Gemini API integration for PLUMB's AI semantic bake

**For:** a fresh Claude session helping the user (zajalist) set up the Gemini API key and
finish/verify the AI semantic bake. **Context:** PLUMB is a spatial-validation studio.
The "AI semantic bake" (architecture §3) renders an asset and asks a vision model what it
*is* — class, up/front, per-region materials, affordances. We chose **Gemini** (free tier,
fast multimodal). The backend is already wired; this doc tells you the verified setup, what
exists in the repo, and what remains.

Repo root: `D:\Hackathons\plumb`. Python venv: `D:\Hackathons\plumb\.venv`. Backend:
`uvicorn studio.server:app --port 8000`. Frontend (Vite): `studio/`, dev server on :5180.

---

## 1. Get a free Gemini API key (verified May 2026)

1. Go to **Google AI Studio → https://aistudio.google.com** and sign in with a Google account.
2. Click **"Get API key"** (API Keys page). New accounts start on the **Free Tier** and AI
   Studio auto-creates a default Google Cloud project + key. Copy the key.
3. (Hackathon) The user has a hackathon hub — `https://gemini-hackathon-hub-614365371127.us-west1.run.app/`
   — it may grant extra credits/quota; check it, but a normal free-tier AI Studio key works.

**Docs:** [API key](https://ai.google.dev/gemini-api/docs/api-key) ·
[Quickstart](https://ai.google.dev/gemini-api/docs/quickstart) ·
[Rate limits](https://ai.google.dev/gemini-api/docs/rate-limits)

The current model is **`gemini-3.5-flash`** (multimodal, generous free tier). The SDK is
**`google-genai`** (`pip install -U google-genai` — already installed in the venv). The key
is picked up automatically from env var **`GEMINI_API_KEY`** (or `GOOGLE_API_KEY`; if both
set, `GOOGLE_API_KEY` wins).

---

## 2. Set the key and run

PowerShell (Windows), set it for the backend process **before** launching uvicorn:

```powershell
$env:GEMINI_API_KEY = "PASTE_KEY_HERE"
# (the backend also reads PLUMB_UE_CMD / PLUMB_UE_PROJECT for .uasset conversion — keep those)
D:\Hackathons\plumb\.venv\Scripts\python.exe -m uvicorn studio.server:app --port 8000
```

Verify it's live:

```powershell
# should show "gemini": { "available": true, "sdk": true, "key": true }
(Invoke-WebRequest http://localhost:8000/health).Content
```

Quick backend-only smoke test (no UI needed — point it at any image):

```powershell
D:\Hackathons\plumb\.venv\Scripts\python.exe -c "from studio.semantics import semantic_bake; print(semantic_bake([open(r'C:\path\to\render.png','rb').read()], 'a wooden chair'))"
```

It should print a JSON dict like
`{"class":"chair","up":[0,0,1],"front":[0,1,0],"materials":[...],"affordances":["sit",...],"confidence":0.8}`.

---

## 3. What's already built (don't rebuild these)

- **`studio/semantics.py`** — the Gemini client.
  - `gemini_status() -> {available, sdk, key}` (used by `/health` + the UI).
  - `semantic_bake(images: list[bytes], hint="") -> dict` — sends PNG renders + a strict
    JSON prompt to `gemini-3.5-flash`, parses the JSON. Raises `RuntimeError` if no key.
  - Reads `GEMINI_API_KEY` / `GOOGLE_API_KEY`. Degrades gracefully (no key/SDK → caller 503s).
- **`studio/server.py`**
  - `POST /semantics` — multipart: `images[]` (PNG renders) + `asset_id` + `hint`. Calls
    `semantic_bake`, folds the inferred `class` into the stored PAP's `semantics.cls`, returns
    the JSON. 503 if Gemini unconfigured, 502 on a Gemini error.
  - `GET /health` now includes `gemini`.
- **`studio/src/api.ts`** — `semanticBake(assetId, images: Blob[], hint?) -> AiSemantics`
  and the `Health.gemini` + `AiSemantics` types.

---

## 4. What remains (frontend UI — ~30–60 min)

The backend is ready; the studio just needs a button that captures a render and shows the
result. Suggested wiring:

1. **Enable canvas capture.** In `studio/src/Viewport.tsx`, the `THREE.WebGLRenderer` must be
   created with `preserveDrawingBuffer: true` (otherwise `canvas.toBlob` returns blank).
   Find `new THREE.WebGLRenderer({ antialias: true })` and add it. *(This edit was pending —
   confirm it's present.)*
2. **Capture helper (App.tsx).** Grab the live canvas and turn it into a PNG blob:
   ```ts
   const captureViewport = (): Promise<Blob | null> =>
     new Promise((res) => {
       const c = document.querySelector('.stage canvas') as HTMLCanvasElement | null
       c ? c.toBlob((b) => res(b), 'image/png') : res(null)
     })
   ```
3. **Run + store.** On a button click: `const blob = await captureViewport()`, then
   `const ai = await semanticBake(selected.pap.asset_id, [blob], selected.name)`. Store `ai`
   on the asset (add `ai?: AiSemantics` to the `Asset` type in `AssetsPanel.tsx`) so it
   persists per-asset.
4. **Display + gate.** Read `gemini.available` from `health()` in App (it already fetches
   health for the Unreal flag — add `setGeminiAvailable(!!h.gemini?.available)`). In
   `Properties.tsx` add a "Semantics" section: a **Run AI bake** button (disabled with a
   "set GEMINI_API_KEY" hint when unavailable, spinner while running), then render
   `ai.class`, `ai.affordances` (chips), `ai.materials`, `ai.confidence`. Match the
   graphite-glass theme (teal accent, `--sage` token, no glow).
5. (Optional, nicer) capture 2–3 angles: rotate the OrbitControls camera, render, capture
   each, send all to `/semantics` (the endpoint already accepts up to 4 images).

**Test loop:** set the key → restart backend → bake an asset → open it → Run AI bake → the
class/affordances appear, and `pap.semantics.cls` updates in Properties.

---

## 5. Gotchas

- **Inline image size ≤ 20 MB** per request (we cap at 4 images server-side). Viewport PNGs
  are well under this.
- **Free-tier rate limits** are per-minute/day on flash — fine for demo use; if you hit a
  429, wait or reduce calls.
- Keep the key **out of git** — it lives only in the env var. Never hardcode it in `studio/`.
- The semantic bake is **independent** of the geometric/physical/material-group bake — if
  Gemini is down or unconfigured, everything else still works.
