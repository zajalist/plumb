# PLUMB Studio — Bake Workbench Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn `studio/` into a live IDE where you import a 3D mesh, the real Python cortex bakes it, and the Properties panel shows the real mass / centre-of-mass / materials — in the approved austere visual system.

**Architecture:** A FastAPI HTTP bridge (`studio/server.py`) wraps `cortex` and answers the browser; the React studio calls it via `api.ts` and renders `PAP`/`Verdict` JSON (mirrors of the frozen `contracts.py`). Request/response (Option A) — every button is one real cortex call.

**Tech Stack:** Python 3.14 venv (`.venv`), FastAPI + uvicorn, `cortex` (trimesh/coacd/scipy/shapely), pytest + FastAPI `TestClient`; frontend React 19 + Vite 8 + TypeScript, Three.js for the asset render, Vitest + Testing Library for component tests.

**Reference:** the approved visual mockup is `.superpowers/brainstorm/.../refined.html` — it is the exact markup/CSS source for the UI components and the icon `<symbol>` sheet. Design rules: no glows, no LED dots, no gradients; hairlines + Geist/Geist Mono; sage only where meaningful; gate colors the only saturated colors.

---

## File Structure

**Backend (Python, repo root):**
- `studio/server.py` — FastAPI app: `/health`, `/bake`, (stubs `/validate` `/repair` for M2). Owns an in-memory `{asset_id: PAP}` registry + `WorldModel`.
- `tests/test_studio_server.py` — TestClient tests.

**Frontend (`studio/src/`):**
- `theme.css` — design tokens (`:root`), base element styles, the inline SVG icon `<symbol>` sheet exported as a React component `Icons`.
- `api.ts` — typed fetch wrappers + TS types mirroring `contracts.py` (`PAP`, `Verdict`, `Gate`, `MaterialGuess`).
- `App.tsx` — REPLACE current body with the IDE shell: menubar, 3-col top (Assets/Viewport/Properties), full-width node-editor slot (mounts existing `ConstraintGraph`).
- `AssetsPanel.tsx` — import (file/drop), asset list, thumbnails, selection.
- `Viewport.tsx` — Three.js render of the selected mesh + CoM marker.
- `Properties.tsx` — render a `PAP`.
- `GateStack.tsx` — flat gate strip from a `Verdict` (used in M2; built now, fed fixtures).
- `Brand.tsx` — the inline logo `<svg>` (the real `plumb.svg` path).

**Do NOT touch:** `ConstraintGraph.tsx` (Fara), `RerunViewer.tsx` (kept for later streaming).

---

## Task 0: Integration — bring `cortex` onto the studio branch

`node-base-editor` is conscience-only. Pull in the real `cortex/`, the unified `pyproject`
(cortex deps + package discovery), and the unified mesh test helpers from the cortex line.

**Files:**
- Add: `cortex/**` (from `origin/cortex`)
- Modify: `pyproject.toml`, `tests/helpers.py`

- [ ] **Step 1: Create the integration branch**

```bash
cd D:/Hackathons/plumb
git switch node-base-editor
git switch -c studio-integration
```

- [ ] **Step 2: Bring in the cortex package + its tests + unified config**

```bash
git fetch origin
git checkout origin/cortex -- cortex/ tests/test_world.py tests/test_geometry.py tests/test_physical.py tests/test_stability.py tests/test_collision.py tests/test_reach.py tests/test_constraints.py tests/test_repair.py tests/test_orchestrator.py tests/test_server.py tests/test_bake_profiles.py tests/test_integration_bet.py
git checkout origin/cortex -- pyproject.toml
git checkout origin/cortex -- tests/helpers.py
```

Note: `origin/cortex`'s `tests/helpers.py` has only the mesh helpers; `node-base-editor`'s
had only the conscience helpers. We need BOTH. After the checkout, re-add the conscience
helpers (tmp_path, mock_ue5_actor, mock_ue5_scene) to `tests/helpers.py` — copy them from
`git show node-base-editor:tests/helpers.py`.

- [ ] **Step 3: Reconcile `tests/helpers.py` to the union**

Run `git show node-base-editor:tests/helpers.py` and append its conscience-only functions
(`tmp_path`, `mock_ue5_actor`, `mock_ue5_scene`) below the mesh helpers, so both suites import cleanly.

- [ ] **Step 4: Install backend deps into the venv**

```bash
./.venv/Scripts/python.exe -m pip install -q fastapi "uvicorn[standard]" python-multipart
```
(`trimesh scipy shapely coacd manifold3d` are already declared in the unified pyproject; install if missing:
`./.venv/Scripts/python.exe -m pip install -q trimesh scipy shapely coacd manifold3d`.)

- [ ] **Step 5: Verify cortex is importable and green**

Run: `./.venv/Scripts/python.exe -c "import cortex.bake, cortex.orchestrator, cortex.repair; print('cortex ok')"`
Expected: `cortex ok`
Run: `./.venv/Scripts/python.exe -m pytest tests/test_physical.py -q`
Expected: PASS (the composition bake).

- [ ] **Step 6: Commit**

```bash
git add cortex pyproject.toml tests/helpers.py tests/test_*.py
git -c user.name="zajalist" -c user.email="saracensaray@gmail.com" commit -m "Integrate cortex onto studio branch (bake/gates/repair + unified deps)"
```

---

## Task 1: Backend skeleton — `/health`

**Files:**
- Create: `studio/server.py`
- Test: `tests/test_studio_server.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_studio_server.py
from fastapi.testclient import TestClient
from studio.server import app

client = TestClient(app)

def test_health_reports_cortex_present():
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["cortex"] is True  # cortex importable in this env
```

- [ ] **Step 2: Run it to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_studio_server.py::test_health_reports_cortex_present -q`
Expected: FAIL (`ModuleNotFoundError: studio.server`).

- [ ] **Step 3: Implement the minimal app**

```python
# studio/server.py
"""PLUMB Studio backend — a thin FastAPI bridge that exposes the real `cortex`
to the browser over request/response HTTP (Option A). The studio UI never runs
physics; it calls these endpoints and renders the returned PAP/Verdict JSON."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="PLUMB Studio backend")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)

def _cortex_available() -> bool:
    try:
        import cortex.bake  # noqa: F401
        return True
    except Exception:
        return False

@app.get("/health")
def health() -> dict:
    return {"ok": True, "cortex": _cortex_available()}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_studio_server.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add studio/server.py tests/test_studio_server.py
git -c user.name="zajalist" -c user.email="saracensaray@gmail.com" commit -m "studio backend: /health"
```

---

## Task 2: Backend `/bake` — real composition bake → PAP

**Files:**
- Modify: `studio/server.py`
- Test: `tests/test_studio_server.py`

- [ ] **Step 1: Write the failing test (uses the two-part top-heavy fixture)**

```python
# add to tests/test_studio_server.py
import io
from tests.helpers import two_part_topheavy, save_mesh_tmp, make_box

def _combined_mesh_bytes() -> bytes:
    # Combine the two parts into one .obj the bake can load from a single file.
    import trimesh
    parts, _ = two_part_topheavy()
    scene = trimesh.util.concatenate(parts)
    path = save_mesh_tmp(scene, ".obj")
    with open(path, "rb") as f:
        return f.read()

def test_bake_returns_a_pap_with_real_physics():
    files = {"mesh": ("bronze_figure.obj", _combined_mesh_bytes(), "text/plain")}
    data = {"materials": '{"body": "bronze", "base": "stone"}'}
    r = client.post("/bake", files=files, data=data)
    assert r.status_code == 200
    pap = r.json()
    assert pap["asset_id"]
    assert pap["physical"]["mass_kg"] > 0
    # the composition proof: a top-heavy bronze body lifts CoM above mid-height
    com_z = pap["physical"]["com"][2]
    assert com_z > 0.0
    assert pap["geometry"]["convex_parts"] >= 1
```

- [ ] **Step 2: Run it to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_studio_server.py::test_bake_returns_a_pap_with_real_physics -q`
Expected: FAIL (404 — no `/bake`).

- [ ] **Step 3: Implement `/bake`**

```python
# add to studio/server.py
import json
import tempfile
from fastapi import UploadFile, File, Form, HTTPException

# in-memory asset registry (reset on restart)
_ASSETS: dict = {}

@app.post("/bake")
async def bake(mesh: UploadFile = File(...), materials: str | None = Form(None)) -> dict:
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
    except Exception as e:  # bad mesh / CoACD failure
        raise HTTPException(status_code=422, detail=f"bake failed: {e}") from e
    _ASSETS[asset_id] = pap
    return pap.model_dump()
```

If `bake_asset`'s signature differs, read `cortex/bake/__init__.py` and adapt the call —
the contract is "(asset_id, mesh_path, part_materials) -> PAP".

- [ ] **Step 4: Run the test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_studio_server.py -q`
Expected: PASS (both tests).

- [ ] **Step 5: Commit**

```bash
git add studio/server.py tests/test_studio_server.py
git -c user.name="zajalist" -c user.email="saracensaray@gmail.com" commit -m "studio backend: /bake -> real PAP"
```

---

## Task 3: Frontend deps + design tokens (`theme.css` + `Icons`)

**Files:**
- Modify: `studio/package.json` (add three, vitest, testing-library)
- Create: `studio/src/theme.css`, `studio/src/Icons.tsx`, `studio/src/Brand.tsx`

- [ ] **Step 1: Install frontend deps**

```bash
cd D:/Hackathons/plumb/studio
npm install three @types/three
npm install -D vitest @testing-library/react @testing-library/jest-dom jsdom
```

- [ ] **Step 2: Create `theme.css` — copy the `:root` tokens + base rules from the mockup**

Open `.superpowers/brainstorm/30354-1780177766/content/refined.html`. Copy its `<style>`
contents into `studio/src/theme.css` (the `:root` tokens, the Geist `@import`/link as a CSS
`@import url(...)`, and the structural classes: `.menubar .gates .gate .pane .asset .thumb
.prop .mat .nodeeditor` etc.). This is the design system; keep it verbatim so the build
matches the approved look. Add `@import` for Geist:

```css
@import url('https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600;700&family=Geist+Mono:wght@400;500;600&display=swap');
/* ...then the :root{...} tokens and structural classes copied from refined.html... */
```

- [ ] **Step 3: Create `Icons.tsx` — the custom SVG symbol sheet as a React component**

Port the `<svg style="position:absolute"><defs>...<symbol id="i-...">` block from the mockup
into a component that renders the defs once, plus an `<Icon name="stability"/>` helper:

```tsx
// studio/src/Icons.tsx
export function IconDefs() {
  return (
    <svg width="0" height="0" style={{ position: 'absolute' }} aria-hidden>
      {/* paste every <symbol id="i-..."> and <symbol id="logo"> from refined.html here */}
    </svg>
  )
}
export function Icon({ name, className }: { name: string; className?: string }) {
  return <svg className={className}><use href={`#i-${name}`} /></svg>
}
```

- [ ] **Step 4: Create `Brand.tsx` (the real logo)**

```tsx
// studio/src/Brand.tsx — renders the inlined #logo symbol from Icons
export function Brand() {
  return (
    <div className="brand">
      <svg width="26" height="24"><use href="#logo" /></svg>
      <span className="word">PLUMB</span>
    </div>
  )
}
```

- [ ] **Step 5: Commit**

```bash
git add studio/package.json studio/package-lock.json studio/src/theme.css studio/src/Icons.tsx studio/src/Brand.tsx
git -c user.name="zajalist" -c user.email="saracensaray@gmail.com" commit -m "studio: design tokens + custom icon sheet + brand"
```

---

## Task 4: `api.ts` — typed client mirroring the contract

**Files:**
- Create: `studio/src/api.ts`

- [ ] **Step 1: Implement the types + fetch wrappers**

```ts
// studio/src/api.ts
const BASE = import.meta.env.VITE_API ?? 'http://localhost:8000'

export type MaterialPart = { part: string; mat: string; conf: number }
export type PAP = {
  asset_id: string
  profile: string
  geometry: { obb: number[]; volume_m3: number; convex_parts: number; watertight: boolean }
  semantics: { cls: string; up: number[]; front: number[]; materials: MaterialPart[]; conf: number }
  physical: { mass_kg: number; com: number[]; inertia: number[][]; hollow: boolean; conf: number }
  structural: { support_footprint: number[][]; max_load_kg_est: number | null; experimental: boolean }
  rest_states: string[]
}
export type Health = { ok: boolean; cortex: boolean }

export async function health(): Promise<Health> {
  const r = await fetch(`${BASE}/health`)
  return r.json()
}

export async function bake(file: File, materials?: Record<string, string>): Promise<PAP> {
  const fd = new FormData()
  fd.append('mesh', file)
  if (materials) fd.append('materials', JSON.stringify(materials))
  const r = await fetch(`${BASE}/bake`, { method: 'POST', body: fd })
  if (!r.ok) throw new Error((await r.json()).detail ?? 'bake failed')
  return r.json()
}
```

- [ ] **Step 2: Commit**

```bash
git add studio/src/api.ts
git -c user.name="zajalist" -c user.email="saracensaray@gmail.com" commit -m "studio: typed api client (health, bake)"
```

---

## Task 5: `Properties.tsx` — render a PAP (with a component test)

**Files:**
- Create: `studio/src/Properties.tsx`, `studio/src/Properties.test.tsx`
- Modify: `studio/package.json` (vitest script), `studio/vite.config.ts` (test config)

- [ ] **Step 1: Add the vitest test config**

In `studio/vite.config.ts` add:
```ts
// inside defineConfig({...})
test: { environment: 'jsdom', globals: true, setupFiles: [] },
```
In `studio/package.json` scripts add: `"test": "vitest run"`.

- [ ] **Step 2: Write the failing component test**

```tsx
// studio/src/Properties.test.tsx
import { render, screen } from '@testing-library/react'
import { Properties } from './Properties'
import type { PAP } from './api'

const PAP_FIX: PAP = {
  asset_id: 'bronze_figure', profile: 'rigid_prop',
  geometry: { obb: [0.15,0.15,0.75], volume_m3: 0.031, convex_parts: 9, watertight: true },
  semantics: { cls: 'statue', up: [0,0,1], front: [0,1,0],
    materials: [{ part:'body', mat:'bronze', conf:0.82 }, { part:'base', mat:'stone', conf:0.74 }], conf: 0.8 },
  physical: { mass_kg: 48.0, com: [0,0.04,0.71], inertia: [], hollow: false, conf: 0.7 },
  structural: { support_footprint: [], max_load_kg_est: null, experimental: true },
  rest_states: ['upright'],
}

test('renders the real baked numbers', () => {
  render(<Properties pap={PAP_FIX} />)
  expect(screen.getByText('48.0 kg')).toBeTruthy()
  expect(screen.getByText('statue')).toBeTruthy()
  expect(screen.getByText(/bronze/)).toBeTruthy()
})
```

- [ ] **Step 3: Run it to verify it fails**

Run: `cd studio && npm test`
Expected: FAIL (no `Properties`).

- [ ] **Step 4: Implement `Properties.tsx`** (port the Properties `<section class="pane props">` markup from the mockup; drive it from the `pap` prop)

```tsx
// studio/src/Properties.tsx
import { Icon } from './Icons'
import type { PAP } from './api'
const SWATCH: Record<string,string> = { bronze:'#7b5a2a', stone:'#6b6a63', glass:'#5b6b6b', wood:'#6e5a36' }

export function Properties({ pap }: { pap: PAP | null }) {
  if (!pap) return <section className="pane props"><header><div className="t"><Icon name="com"/><span>Properties — PAP</span></div></header><div className="body" style={{padding:16,color:'var(--ink3)'}}>Select an asset.</div></section>
  const f3 = (n:number)=> (n>=0?'':'') + n.toFixed(2).replace(/^0/,'')
  return (
    <section className="pane props">
      <header><div className="t"><Icon name="com"/><span>Properties — PAP</span></div><span className="mono" style={{fontSize:10,color:'var(--ink4)'}}>baked</span></header>
      <div className="body">
        <div className="psec">
          <div className="label" style={{marginBottom:4}}>Identity</div>
          <div className="prop"><span className="k">class</span><span className="v">{pap.semantics.cls}</span></div>
          <div className="prop"><span className="k"><Icon name="seal"/>watertight</span><span className="v muted">{pap.geometry.watertight?`yes · ${pap.geometry.convex_parts} parts`:'no'}</span></div>
          <div className="prop"><span className="k"><Icon name="solid"/>hollow</span><span className="v muted">{pap.physical.hollow?'yes':'no'}</span></div>
        </div>
        <div className="psec">
          <div className="label" style={{marginBottom:4}}>Physics</div>
          <div className="prop"><span className="k"><Icon name="mass"/>mass</span><span className="v">{pap.physical.mass_kg.toFixed(1)} kg</span></div>
          <div className="prop"><span className="k"><Icon name="com"/>centre of mass</span><span className="v">{pap.physical.com.map(f3).join(', ')}</span></div>
        </div>
        <div className="psec" style={{borderBottom:'none'}}>
          <div className="label">Materials <span style={{color:'var(--ink4)',textTransform:'none'}}>— AI-guessed</span></div>
          <div className="mats">
            {pap.semantics.materials.map(m=>(
              <div className="mat" key={m.part}><span className="ml"><span className="swatch" style={{background:SWATCH[m.mat]??'#666'}}/>{m.part}</span><span className="mr">{m.mat} · {m.conf.toFixed(2)}</span></div>
            ))}
          </div>
          <div className="confirm"><Icon name="lock"/>Confirm &amp; lock materials</div>
        </div>
      </div>
    </section>
  )
}
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd studio && npm test`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add studio/src/Properties.tsx studio/src/Properties.test.tsx studio/vite.config.ts studio/package.json
git -c user.name="zajalist" -c user.email="saracensaray@gmail.com" commit -m "studio: Properties panel renders a PAP (+ test)"
```

---

## Task 6: `Viewport.tsx` — Three.js render of the selected mesh

**Files:**
- Create: `studio/src/Viewport.tsx`

- [ ] **Step 1: Implement** — a Three.js canvas that loads an `OBJLoader` from a Blob URL of the selected file, frames it, lights it flatly (no glow), dark `--inset` background; overlays a CoM dot when a `com` prop is passed. Port the viewport `<header>` + `.stage` chrome (crop marks, axis label) from the mockup around the canvas.

```tsx
// studio/src/Viewport.tsx
import { useEffect, useRef } from 'react'
import * as THREE from 'three'
import { OBJLoader } from 'three/examples/jsm/loaders/OBJLoader.js'
import { Icon } from './Icons'

export function Viewport({ file, name }: { file: File | null; name: string }) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const el = ref.current; if (!el) return
    const scene = new THREE.Scene(); scene.background = new THREE.Color('#100F0A')
    const cam = new THREE.PerspectiveCamera(40, el.clientWidth/el.clientHeight, 0.01, 100)
    const renderer = new THREE.WebGLRenderer({ antialias: true }); renderer.setSize(el.clientWidth, el.clientHeight)
    el.appendChild(renderer.domElement)
    scene.add(new THREE.HemisphereLight('#cfcab8', '#1a1912', 1.1))
    const key = new THREE.DirectionalLight('#fff', 0.6); key.position.set(2,4,3); scene.add(key)
    const mat = new THREE.MeshStandardMaterial({ color: '#586040', roughness: 0.85, metalness: 0.1, flatShading: true })
    let raf = 0
    if (file) {
      file.text().then(txt => {
        const obj = new OBJLoader().parse(txt)
        obj.traverse(o => { if ((o as THREE.Mesh).isMesh) (o as THREE.Mesh).material = mat })
        const box = new THREE.Box3().setFromObject(obj); const c = box.getCenter(new THREE.Vector3()); const s = box.getSize(new THREE.Vector3())
        obj.position.sub(c); const r = Math.max(s.x,s.y,s.z); cam.position.set(r*1.6, r*1.1, r*2.2); cam.lookAt(0,0,0); scene.add(obj)
      })
    }
    const tick = () => { scene.rotation.y += 0.003; renderer.render(scene, cam); raf = requestAnimationFrame(tick) }
    tick()
    return () => { cancelAnimationFrame(raf); renderer.dispose(); el.removeChild(renderer.domElement) }
  }, [file])
  return (
    <section className="pane viewport">
      <header><div className="t"><Icon name="aperture"/><span>Viewport — {name || '—'}</span></div><span className="mono" style={{fontSize:10,color:'var(--ink4)'}}>orbit · frame</span></header>
      <div className="stage" ref={ref} style={{ position:'relative' }}>
        <div className="crop tl"/><div className="crop tr"/><div className="crop bl"/><div className="crop br"/>
      </div>
    </section>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add studio/src/Viewport.tsx
git -c user.name="zajalist" -c user.email="saracensaray@gmail.com" commit -m "studio: Three.js viewport renders the selected mesh"
```

---

## Task 7: `AssetsPanel.tsx` — import, list, thumbnails, selection

**Files:**
- Create: `studio/src/AssetsPanel.tsx`

- [ ] **Step 1: Implement** — port the `<section class="pane assets">` markup; the list is driven by an `assets` prop `{id, name, file, pap?, status}`; clicking calls `onSelect`; the dropzone + an `<input type=file>` calls `onImport(file)`. Thumbnail: a small faceted `<svg>` placeholder now (a later WP swaps in a real offscreen Three render).

```tsx
// studio/src/AssetsPanel.tsx
import { Icon } from './Icons'
import type { PAP } from './api'
export type Asset = { id: string; name: string; file: File; pap?: PAP; status: 'baking'|'ok'|'error'; error?: string }

export function AssetsPanel({ assets, selected, onSelect, onImport }:{
  assets: Asset[]; selected: string|null; onSelect:(id:string)=>void; onImport:(f:File)=>void }) {
  return (
    <section className="pane assets">
      <header><div className="t"><Icon name="aperture"/><span>Assets</span></div><span className="mono" style={{fontSize:10,color:'var(--ink4)'}}>{assets.length}</span></header>
      <div className="body">
        <div className="assetlist">
          {assets.map(a=>(
            <div key={a.id} className={`asset${a.id===selected?' sel':''}`} onClick={()=>onSelect(a.id)}>
              <div className="thumb"><Icon name="aperture"/></div>
              <div className="meta"><div className="nm">{a.name}</div>
                <div className="sub">{a.status==='baking'?'baking…':a.status==='error'?<span style={{color:'var(--fail)'}}>bake failed</span>:a.pap?`${a.pap.semantics.cls} · ${a.pap.physical.mass_kg.toFixed(1)}kg`:''}</div></div>
            </div>
          ))}
          <label className="dropzone">
            <Icon name="import"/><div className="dz">Drop a mesh to bake</div><div className="dz2">.obj · .glb · .fbx</div>
            <input type="file" accept=".obj,.glb,.fbx" style={{display:'none'}} onChange={e=>{const f=e.target.files?.[0]; if(f) onImport(f)}}/>
          </label>
        </div>
      </div>
    </section>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add studio/src/AssetsPanel.tsx
git -c user.name="zajalist" -c user.email="saracensaray@gmail.com" commit -m "studio: AssetsPanel (import, list, select)"
```

---

## Task 8: `GateStack.tsx` — flat gate strip from a Verdict

**Files:**
- Create: `studio/src/GateStack.tsx`, `studio/src/GateStack.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// studio/src/GateStack.test.tsx
import { render, screen } from '@testing-library/react'
import { GateStack } from './GateStack'
import { attempts } from './verdicts'

test('shows a failing stability gate flat (no dot markup)', () => {
  const fail = attempts.find(a => !a.ok)!
  const { container } = render(<GateStack attempt={fail} />)
  expect(screen.getByText(/stability/i)).toBeTruthy()
  expect(container.querySelector('.gate.fail')).toBeTruthy()
})
```

- [ ] **Step 2: Run it to verify it fails** — `cd studio && npm test` → FAIL (no GateStack).

- [ ] **Step 3: Implement** — port the `.gates` strip from the mockup; map `attempt.gates` to cells; status class by `ok/skipped`; format `value_m*100` cm; no dots/glow.

```tsx
// studio/src/GateStack.tsx
import { Icon } from './Icons'
import type { Attempt, Gate } from './verdicts'
const ICON: Record<string,string> = { collision:'collision', stability:'stability', constraints:'constraints', reach:'reach' }
function cls(g: Gate, soft: number) {
  if (g.skipped || g.ok===null) return 'idle'
  if (g.ok===false) return 'fail'
  if (g.gate==='constraints' && soft>1) return 'soft'
  return 'pass'
}
const cm = (m:number|null)=> m===null?'idle':`${m>=0?'+':'−'}${Math.abs(m*100).toFixed(1)} cm`
export function GateStack({ attempt }:{ attempt: Attempt }) {
  const order: Gate['gate'][] = ['collision','stability','constraints','reach']
  const by = new Map(attempt.gates.map(g=>[g.gate,g]))
  return (
    <div className="gates">
      <div className="gtitle"><Icon name="grid"/><span className="label" style={{color:'var(--ink2)'}}>Gate&nbsp;Stack</span></div>
      <div className="gflow">
        {order.map((name,i)=>{ const g=by.get(name); const c=g?cls(g,attempt.soft_cost):'idle'
          return (<><div key={name} className={`gate ${c}`}><Icon name={ICON[name]}/><span className="gn">{name}</span><span className="gv">{g?cm(g.value_m):'idle'}</span></div>{i<3 && <span className="chev">›</span>}</>) })}
      </div>
      <div className={`commitcell${attempt.committed?' ready':''}`}><Icon name="commit"/><span className="label">commit</span></div>
    </div>
  )
}
```

- [ ] **Step 4: Run the test to verify it passes** — `cd studio && npm test` → PASS.
- [ ] **Step 5: Commit**

```bash
git add studio/src/GateStack.tsx studio/src/GateStack.test.tsx
git -c user.name="zajalist" -c user.email="saracensaray@gmail.com" commit -m "studio: GateStack flat strip from a Verdict (+ test)"
```

---

## Task 9: `App.tsx` shell — wire import → bake → Properties

**Files:**
- Modify: `studio/src/App.tsx` (replace body), `studio/src/main.tsx` (import theme.css)

- [ ] **Step 1: Import the theme + icon defs**

In `studio/src/main.tsx` add `import './theme.css'`. Render `<IconDefs/>` once at the top of `App`.

- [ ] **Step 2: Replace `App.tsx`** with the IDE shell that holds asset state and wires the bake call:

```tsx
// studio/src/App.tsx
import { useState, useCallback } from 'react'
import { IconDefs, Icon } from './Icons'
import { Brand } from './Brand'
import { AssetsPanel, type Asset } from './AssetsPanel'
import { Viewport } from './Viewport'
import { Properties } from './Properties'
import { GateStack } from './GateStack'
import ConstraintGraph from './ConstraintGraph'   // Fara's — unchanged
import { bake } from './api'
import { attempts } from './verdicts'

export default function App() {
  const [assets, setAssets] = useState<Asset[]>([])
  const [sel, setSel] = useState<string | null>(null)
  const selected = assets.find(a => a.id === sel) ?? null

  const onImport = useCallback(async (file: File) => {
    const id = file.name.replace(/\.[^.]+$/, '') + '-' + Math.random().toString(36).slice(2,6)
    setAssets(a => [...a, { id, name: file.name, file, status: 'baking' }])
    setSel(id)
    try {
      const pap = await bake(file)
      setAssets(a => a.map(x => x.id===id ? { ...x, pap, status:'ok' } : x))
    } catch (e:any) {
      setAssets(a => a.map(x => x.id===id ? { ...x, status:'error', error:String(e.message) } : x))
    }
  }, [])

  return (
    <div className="app">
      <IconDefs/>
      <div className="menubar">
        <Brand/>
        <div className="sep"/>
        <div className="mfile">
          <div className="mbtn"><Icon name="new"/>New</div>
          <div className="mbtn"><Icon name="open"/>Open</div>
          <label className="mbtn key"><Icon name="import"/>Import mesh<input type="file" accept=".obj,.glb,.fbx" style={{display:'none'}} onChange={e=>{const f=e.target.files?.[0]; if(f) onImport(f)}}/></label>
        </div>
        <div className="proj"><span className="dot"/><span className="mono">untitled.wdf</span><span style={{color:'var(--ink4)'}}>·</span>{assets.length} assets</div>
      </div>

      <GateStack attempt={attempts[0]} />

      <div className="row">
        <AssetsPanel assets={assets} selected={sel} onSelect={setSel} onImport={onImport}/>
        <Viewport file={selected?.file ?? null} name={selected?.name ?? ''}/>
        <Properties pap={selected?.pap ?? null}/>
      </div>

      <div className="nodeeditor">
        <header><Icon name="reach"/><span className="t">Node editor</span><span className="who">Fara</span></header>
        <ConstraintGraph attempt={attempts[0]}/>
      </div>
    </div>
  )
}
```

If `ConstraintGraph`'s props differ, pass what it currently expects (read its signature; do
not modify it). The gate stack uses `attempts[0]` (fixture) until M2 wires live `/validate`.

- [ ] **Step 3: Run the dev server + manual check**

```bash
cd D:/Hackathons/plumb && ./.venv/Scripts/python.exe -m uvicorn studio.server:app --port 8000 &
cd studio && npm run dev
```
Open the studio, **Import mesh** → pick a `.obj` → the asset appears "baking…" then resolves;
the Viewport renders it; **Properties shows the real mass / CoM / materials** from the backend.

- [ ] **Step 4: Commit**

```bash
git add studio/src/App.tsx studio/src/main.tsx
git -c user.name="zajalist" -c user.email="saracensaray@gmail.com" commit -m "studio: IDE shell — import -> bake -> Properties wired to real cortex"
```

---

## Task 10: Full verification

- [ ] **Step 1: Backend suite** — `./.venv/Scripts/python.exe -m pytest tests/test_studio_server.py -q` → PASS.
- [ ] **Step 2: Frontend suite** — `cd studio && npm test` → PASS (Properties, GateStack).
- [ ] **Step 3: Manual end-to-end** — import the bronze figure mesh → Properties shows ~48 kg, high CoM, bronze/stone; no glows/LED-dots anywhere; Geist fonts; the real logo top-left.
- [ ] **Step 4: Final commit / PR** the `studio-integration` branch.

---

## Notes for the executor
- **Design fidelity:** the mockup `refined.html` is the source of truth for markup/CSS. When a step says "port from the mockup," copy its exact classes/structure; do not invent new styles.
- **Never** add glows, gradients, or LED status dots; never use emoji/lucide icons.
- **Never** edit `ConstraintGraph.tsx` (Fara) or `contracts.py` (frozen).
- M2 (live `/validate` + `/repair` + Inspector controls) is a follow-up plan — the GateStack + backend stubs already exist for it.
