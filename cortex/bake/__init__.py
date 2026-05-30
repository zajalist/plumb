"""
cortex/bake/ — the asset bake pipeline.

  geometry.py  (Task 2) — load mesh -> AABB/OBB, volume, watertight, convex parts.
  physical.py  (Task 3) — composition-aware mass / CoM / inertia.
  __init__:bake_asset    (Task 3) — composes geometry + physical into a full PAP.

Geometry is the first stage and the only one Task 2 owns; the convex parts it
produces are consumed by the physical bake and the collision gate.
"""
