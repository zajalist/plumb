"""
cortex/gates/reach.py — the Reachability gate (Task 6).

``reach(world, walkway_poly, agent_r=0.45, start=None, goal=None) -> GateResult``

Algorithm
---------
1. **Obstacle footprints:** For every node in the world, project its bounding box
   (AABB half-extents) to the floor (XY plane) as a rectangle at the node's world
   position, then intersect with the walkway polygon. Obstacles that don't overlap
   the walkway are ignored.

2. **Narrowest gap width:** Compute the Minkowski difference of the walkway polygon
   with the union of obstacle footprints inflated by ``agent_r`` (i.e. the
   configuration-space free space). The narrowest passage width is the minimum
   "clearance" an agent of radius ``agent_r`` can thread through:

       width = min over all cross-sections of (free-space width) = 2 * agent_r * ok?

   In practice we sample many cross-section lines across the walkway and measure
   the total clear span (minus obstacle projections) at each. The reported
   ``value_m`` is the minimum free-span width across all sampled sections.

3. **Flood-fill reachability (optional):** If ``start`` and ``goal`` are provided,
   rasterise the walkway and obstacle footprints onto a coarse grid and run a
   breadth-first flood fill from ``start`` to verify ``goal`` is reachable.

4. **Gate decision:** ``ok = value_m >= 2 * agent_r``. If start/goal flood-fill
   shows the goal is unreachable, override to ``ok = False``.

Canonical space: Z-up, right-handed, metres. The floor is the XY plane; Z is
ignored (obstacles are projected down). Pure numpy + shapely; no Recast.
"""

from __future__ import annotations

from collections import deque
from typing import Optional

import numpy as np
from shapely.geometry import MultiPolygon, Point, Polygon
from shapely.ops import unary_union

from contracts import GateName, GateResult

# Default agent radius in metres. 0.45m → diameter 0.90m (broad-shoulder adult).
_DEFAULT_AGENT_R: float = 0.45

# Number of cross-section samples along the walkway's medial axis for gap measurement.
_N_CROSS_SECTIONS: int = 40

# Flood-fill grid resolution in metres per cell.
_GRID_RES: float = 0.1


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def reach(
    world,
    walkway_poly: list[list[float]],
    agent_r: float = _DEFAULT_AGENT_R,
    start: Optional[list[float]] = None,
    goal: Optional[list[float]] = None,
) -> GateResult:
    """Reachability gate: narrowest free passage width along the walkway polygon.

    Parameters
    ----------
    world:
        A :class:`~cortex.world.WorldModel` — obstacles are extracted from its nodes.
    walkway_poly:
        2D polygon (list of [x, y] vertices) defining the navigable region on the floor.
    agent_r:
        Agent radius in metres (default 0.45 m → 0.9 m diameter).
    start:
        Optional [x, y] start point for flood-fill reachability (world XY).
    goal:
        Optional [x, y] goal point for flood-fill reachability (world XY).

    Returns
    -------
    GateResult with:
      * ``gate = GateName.reach``
      * ``value_m`` = narrowest free-span width in metres
      * ``ok = value_m >= 2 * agent_r`` (and goal reachable if provided)
      * ``detail`` e.g. ``"walkway 94cm >= 90cm"``
    """
    walkway = Polygon(walkway_poly)
    diameter = 2.0 * agent_r

    # Build obstacle footprints intersected with the walkway.
    obs_footprints = _obstacle_footprints(world, walkway)

    # Compute narrowest free-span width.
    width = _narrowest_gap(walkway, obs_footprints, agent_r)

    ok = width >= diameter

    # Flood-fill override: if start/goal given, confirm navigability.
    if ok and start is not None and goal is not None:
        reachable = _flood_fill_reachable(walkway, obs_footprints, agent_r, start, goal)
        if not reachable:
            ok = False

    # If start/goal given and already not ok, double-check via flood fill.
    if not ok and start is not None and goal is not None:
        # Still not ok — no need to re-check, but report the flood-fill status.
        pass

    detail = _detail(width, diameter)

    return GateResult(
        gate=GateName.reach,
        ok=ok,
        value_m=float(width),
        detail=detail,
    )


# --------------------------------------------------------------------------- #
# Obstacle extraction
# --------------------------------------------------------------------------- #
def _obstacle_footprints(world, walkway: Polygon) -> list[Polygon]:
    """Project each world node's AABB footprint to XY, intersect with walkway."""
    footprints: list[Polygon] = []
    for nid in world.nodes():
        node = world.get(nid)
        fp = _node_footprint(node)
        clipped = fp.intersection(walkway)
        if not clipped.is_empty and clipped.area > 0:
            footprints.append(clipped)
    return footprints


def _node_footprint(node) -> Polygon:
    """World-XY rectangle for a node (AABB half-extents + world position)."""
    pap = node.pap
    tf = node.transform

    half = list(pap.geometry.aabb) or list(pap.geometry.obb) or [0.5, 0.5, 0.5]
    hx = float(half[0]) if len(half) > 0 else 0.5
    hy = float(half[1]) if len(half) > 1 else 0.5

    # Apply transform: scale → rotate (only yaw in XY) → translate.
    # For simplicity use scale and translation only (no yaw for AABB).
    scale = np.asarray(tf.scale, dtype=float)
    pos = np.asarray(tf.pos, dtype=float)

    shx = hx * float(scale[0])
    shy = hy * float(scale[1])
    cx, cy = float(pos[0]), float(pos[1])

    # Apply yaw rotation from quaternion to the footprint corners.
    quat = tf.quat
    x_q, y_q, z_q, w_q = float(quat[0]), float(quat[1]), float(quat[2]), float(quat[3])
    yaw = 2.0 * np.arctan2(z_q, w_q)  # yaw angle from quaternion

    corners_local = np.array([
        [-shx, -shy],
        [ shx, -shy],
        [ shx,  shy],
        [-shx,  shy],
    ])
    # Rotate corners by yaw.
    cos_y, sin_y = np.cos(yaw), np.sin(yaw)
    rot = np.array([[cos_y, -sin_y], [sin_y, cos_y]])
    corners_world = (rot @ corners_local.T).T + np.array([cx, cy])

    return Polygon(corners_world)


# --------------------------------------------------------------------------- #
# Narrowest gap measurement
# --------------------------------------------------------------------------- #
def _narrowest_gap(
    walkway: Polygon,
    obs_footprints: list[Polygon],
    agent_r: float,
) -> float:
    """Minimum free-span width across sampled cross-sections of the walkway.

    Strategy: sample ``_N_CROSS_SECTIONS`` evenly-spaced X-slices (and Y-slices)
    across the walkway bounding box. For each slice line, compute the total
    walkway span minus obstacle projections; the minimum across all slices is
    the narrowest passage width.

    If there are no obstacles, returns the walkway's inscribed diameter
    (minimum bounding box side).
    """
    if not obs_footprints:
        return _walkway_clear_width(walkway)

    obs_union = unary_union(obs_footprints)
    free_space = walkway.difference(obs_union)

    if free_space.is_empty:
        return 0.0

    minx, miny, maxx, maxy = walkway.bounds
    width_x = maxx - minx
    width_y = maxy - miny

    min_width = float("inf")

    # Sample horizontal (X-parallel) cross-sections.
    for i in range(_N_CROSS_SECTIONS + 1):
        t = i / _N_CROSS_SECTIONS
        y = miny + t * width_y
        line = _horizontal_line(minx - 0.01, maxx + 0.01, y)
        span = _free_span_on_line(free_space, line)
        if span < min_width:
            min_width = span

    # Sample vertical (Y-parallel) cross-sections.
    for i in range(_N_CROSS_SECTIONS + 1):
        t = i / _N_CROSS_SECTIONS
        x = minx + t * width_x
        line = _vertical_line(x, miny - 0.01, maxy + 0.01)
        span = _free_span_on_line(free_space, line)
        if span < min_width:
            min_width = span

    return float(min_width) if min_width != float("inf") else 0.0


def _walkway_clear_width(walkway: Polygon) -> float:
    """Width of an empty walkway: minimum of AABB side lengths."""
    minx, miny, maxx, maxy = walkway.bounds
    return min(maxx - minx, maxy - miny)


def _horizontal_line(x0: float, x1: float, y: float):
    """Shapely LineString: horizontal at y from x0 to x1."""
    from shapely.geometry import LineString
    return LineString([(x0, y), (x1, y)])


def _vertical_line(x: float, y0: float, y1: float):
    """Shapely LineString: vertical at x from y0 to y1."""
    from shapely.geometry import LineString
    return LineString([(x, y0), (x, y1)])


def _free_span_on_line(free_space, line) -> float:
    """Total length of the intersection between ``free_space`` and ``line``."""
    inter = free_space.intersection(line)
    if inter.is_empty:
        return 0.0
    # May be MultiLineString, LineString, or Point.
    if hasattr(inter, "geoms"):
        return sum(g.length for g in inter.geoms)
    return float(inter.length)


# --------------------------------------------------------------------------- #
# Flood-fill reachability
# --------------------------------------------------------------------------- #
def _flood_fill_reachable(
    walkway: Polygon,
    obs_footprints: list[Polygon],
    agent_r: float,
    start: list[float],
    goal: list[float],
) -> bool:
    """BFS flood-fill on a coarse grid: can an agent of radius ``agent_r`` reach goal?

    The configuration-space obstacle is each footprint inflated by ``agent_r``
    (Minkowski sum with a disk). Cells whose centres fall inside an inflated
    obstacle or outside the walkway shrunk by ``agent_r`` are impassable.
    """
    # Shrink walkway by agent_r → free C-space boundary.
    walkway_cs = walkway.buffer(-agent_r)
    if walkway_cs.is_empty:
        return False

    # Inflate obstacles by agent_r.
    if obs_footprints:
        obs_union = unary_union(obs_footprints).buffer(agent_r)
    else:
        obs_union = None

    minx, miny, maxx, maxy = walkway.bounds

    def _cell(px: float, py: float) -> tuple[int, int]:
        ci = int((px - minx) / _GRID_RES)
        cj = int((py - miny) / _GRID_RES)
        return ci, cj

    def _centre(ci: int, cj: int) -> tuple[float, float]:
        return minx + (ci + 0.5) * _GRID_RES, miny + (cj + 0.5) * _GRID_RES

    nx = max(1, int(np.ceil((maxx - minx) / _GRID_RES)))
    ny = max(1, int(np.ceil((maxy - miny) / _GRID_RES)))

    def _passable(ci: int, cj: int) -> bool:
        if ci < 0 or ci >= nx or cj < 0 or cj >= ny:
            return False
        px, py = _centre(ci, cj)
        pt = Point(px, py)
        if not walkway_cs.covers(pt):
            return False
        if obs_union is not None and obs_union.covers(pt):
            return False
        return True

    sc = _cell(float(start[0]), float(start[1]))
    gc = _cell(float(goal[0]), float(goal[1]))

    if not _passable(*sc):
        # Start in obstacle — try the nearest passable cell.
        sc = _nearest_passable(sc, nx, ny, _passable)
        if sc is None:
            return False

    if not _passable(*gc):
        gc = _nearest_passable(gc, nx, ny, _passable)
        if gc is None:
            return False

    if sc == gc:
        return True

    visited: set[tuple[int, int]] = {sc}
    queue: deque[tuple[int, int]] = deque([sc])

    while queue:
        ci, cj = queue.popleft()
        for dci, dcj in [(1, 0), (-1, 0), (0, 1), (0, -1),
                         (1, 1), (1, -1), (-1, 1), (-1, -1)]:
            nb = (ci + dci, cj + dcj)
            if nb == gc:
                return True
            if nb not in visited and _passable(*nb):
                visited.add(nb)
                queue.append(nb)

    return False


def _nearest_passable(
    cell: tuple[int, int],
    nx: int,
    ny: int,
    passable_fn,
    radius: int = 5,
) -> Optional[tuple[int, int]]:
    """Find the nearest passable cell within ``radius`` of ``cell``."""
    ci0, cj0 = cell
    for r in range(1, radius + 1):
        for dci in range(-r, r + 1):
            for dcj in range(-r, r + 1):
                if abs(dci) == r or abs(dcj) == r:
                    nb = (ci0 + dci, cj0 + dcj)
                    if 0 <= nb[0] < nx and 0 <= nb[1] < ny and passable_fn(*nb):
                        return nb
    return None


# --------------------------------------------------------------------------- #
# Human-readable detail
# --------------------------------------------------------------------------- #
def _detail(width_m: float, diameter_m: float) -> str:
    """Human string, e.g. ``"walkway 94cm >= 90cm"`` or ``"walkway 62cm < 90cm"``."""
    w_cm = int(round(width_m * 100))
    d_cm = int(round(diameter_m * 100))
    op = ">=" if width_m >= diameter_m else "<"
    return f"walkway {w_cm}cm {op} {d_cm}cm"
