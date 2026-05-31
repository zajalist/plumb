# PLUMB

**A spatial cortex and a language for physically-grounded, intent-aware 3D worlds.**

> AI places objects in 3D worlds by vibes, so things float, clip walls, block doors, and topple.
> PLUMB sits between the agent and the engine and validates every move before it commits. 
> It never just says "no": it returns the exact margin you failed by and the direction to fix it.

<!-- TODO tagline: "glTF and USD describe geometry. PLUMB describes meaning, physics, and intent." -->

## Inspiration

LLMs are fluent in language but naive about gravity. Ask one to arrange a room and it floats the
statue, clips the chair into the wall, and blocks the door. The fix is not a better prompt, it is a
grounding loop: propose, validate against real physics, repair, commit. And the asset itself must
know what it is, because a hollow glass vase and a solid bronze statue are identical to a naive
geometry pass yet physically nothing alike.

## What it does

AI is being handed the job of building 3D worlds: game levels, simulations, virtual spaces. But it
has no sense of physical reality, so it produces scenes that break the instant physics runs, and a
human has to fix every mistake by hand. There is no real automated workflow.

PLUMB is the trust layer that makes it a workflow. It gives every object real physics (a statue
knows it is top-heavy, a vase knows it is fragile and hollow), it lets a person set the rules a
scene must obey, and it checks every AI decision against real physics before it touches the scene,
auto-fixing the ones that fail. Nothing commits until it is proven correct.

**Who it is for:**

- **Game studios and level designers:** AI set-dressing that is guaranteed stable, clip-free, and navigable.
- **AI and agent developers:** spatial validation as one tool call, so an agent asks "is this valid, and how do I fix it" and converges in a step or two instead of burning tokens guessing.
- **Simulation and robotics teams:** mass-produce physically valid training scenes.
- **Architects and accessibility auditors:** "is this path wheelchair-wide?", get a pass/fail and an automatic fix.

The output is one portable `.wdf` file that describes a whole validated world in plain text. glTF
and USD describe geometry; `.wdf` describes meaning, physics, and intent.

### How it works

One loop: Bake, Author, Propose, Gate, Repair, Commit. Every asset is baked once into a Physical
Asset Profile with real mass, centre of mass, inertia, and material (type-aware, so a door knows
its swing arc). A human authors the rules in a node graph. The agent proposes a move; it runs the
gates (Collision, Stability, Constraints, Reach) and stops at the first hard fail. The verdict is a
number and a fix vector ("Stability minus 7 cm, shift plus 6 cm toward centre"), and repair uses the
same maths that rejected the move to fix it. Only validated moves reach the engine.

The unifying idea: every gate is a cost function, so the thing that rejects a placement is the
thing that fixes it. That is why PLUMB answers why and how, not just no.

## How we built it

Two halves meet at one frozen contract (`contracts.py`). The cortex is headless Python: `trimesh`
plus CoACD decompose and density-weight the mesh for mass and CoM, the gates run (Stability as a
CoM-over-support-polygon margin, Collision as convex-part clearance, Reach as floor projection),
repair is `scipy` SLSQP, and everything is exposed as MCP tools via FastMCP. The studio is the IDE
(React, TypeScript, Vite, Three.js): drop a mesh, a FastAPI backend runs the real bake, and a node
editor lights up green/amber/red from the real verdict. Gemini powers the semantic bake. The
conscience drives the agent loop, visualises in Rerun, round-trips the `.wdf` language, and bridges
to Unreal Engine. One canonical space throughout: Z-up, right-handed, metres, kilograms.

## Challenges we ran into

Drop simulations are flaky, so we gate on a deterministic quasi-static margin instead. Single-mesh
mass inference is weak science, so structural outputs are labelled priors and stay human-
overridable. Coordinate conversions (handedness, winding, cm to m) silently corrupt physics, so
they live behind one adapter with golden round-trip tests. The node editor started cluttered with
fifteen node types, so we collapsed it to five abstract ones.

## Accomplishments that we're proud of

The bake knows the statue is top-heavy because the bronze is up top, a real composition-aware CoM.
The verdict always gives a number and a fix, never a dead end. The node editor animates from the
real backend verdict. And a whole physically-grounded world fits in one portable `.wdf` file.

## What we learned

A grounding loop beats a better prompt. Validation and repair are the same maths, so build them
once. Labelling what you are unsure of and letting a human override it is what earns trust.

## What's next for Plumb

More bake archetypes (seasonal trees, auto-filling shelves) and terrain-aware placement on uneven
ground. Adapting PLUMB beyond Unreal to other engines like Unity, Blender, and Omniverse, since the
canonical world model and `.wdf` are engine-agnostic and only the thin adapter changes. And `.wdf`
vocabulary packs, so teams import reusable asset and profile libraries like code libraries.

## Built With

`python` · `fastapi` · `uvicorn` · `trimesh` · `coacd` · `scipy` · `shapely` · `numpy` ·
`pydantic` · `fastmcp` (Anthropic MCP) · `mujoco` · `rerun` · `lark` · `httpx` ·
`react` · `typescript` · `vite` · `three.js` · `react-flow` (@xyflow) ·
`google-gemini` (AI Studio) · `unreal-engine-5`

>
