"""Generate the Plumb/Cortex logo: a real camera-iris diaphragm inside a cog ring.

Proper diaphragm geometry: each blade leading edge is a true circular arc.
Adjacent blade circles intersect to define the opening's vertices, so the
central aperture is a clean closed polygon and every line joins exactly.

Pure stdlib. Run:  python assets/logo/gen_logo.py
"""
import math
import os

SIZE = 512
C = SIZE / 2

# ---------------------------------------------------------------- geometry helpers
def add(a, b): return (a[0] + b[0], a[1] + b[1])
def sub(a, b): return (a[0] - b[0], a[1] - b[1])
def mul(a, s): return (a[0] * s, a[1] * s)
def norm(a): return math.hypot(a[0], a[1])
def pol(r, deg): a = math.radians(deg); return (r * math.cos(a), r * math.sin(a))
def f(x): return f"{x:.3f}"

def circle_inter(c0, r0, c1, r1):
    """Two intersection points of two circles (or None)."""
    d = norm(sub(c1, c0))
    if d == 0 or d > r0 + r1 or d < abs(r0 - r1):
        return None
    a = (r0 * r0 - r1 * r1 + d * d) / (2 * d)
    h2 = r0 * r0 - a * a
    if h2 < 0:
        return None
    h = math.sqrt(h2)
    p2 = add(c0, mul(sub(c1, c0), a / d))
    ox = -(c1[1] - c0[1]) * (h / d)
    oy = (c1[0] - c0[0]) * (h / d)
    return [(p2[0] + ox, p2[1] + oy), (p2[0] - ox, p2[1] - oy)]

def ang_at(center, p):
    return math.degrees(math.atan2(p[1] - center[1], p[0] - center[0]))

def sample_arc(center, r, a0, a1, n=40):
    """Sample the SHORT arc on a circle from angle a0 to a1 (degrees)."""
    d = (a1 - a0 + 180) % 360 - 180   # signed shortest delta
    return [add(center, pol(r, a0 + d * t / n)) for t in range(n + 1)]

def arc_through(center, r, p_start, p_end, p_mid):
    """Sample arc center->? from p_start to p_end going the way that passes p_mid."""
    a0 = ang_at(center, p_start)
    a1 = ang_at(center, p_end)
    am = ang_at(center, p_mid)
    # pick direction (sign) so that am lies between a0 and a1
    def span(sign):
        # walk from a0 toward a1 in direction `sign`, total degrees
        d = (a1 - a0) % 360 if sign > 0 else (a0 - a1) % 360
        return d
    for sign in (1, -1):
        total = span(sign)
        dm = ((am - a0) % 360) if sign > 0 else ((a0 - am) % 360)
        if dm <= total + 0.01:
            n = max(8, int(total / 4))
            return [add(center, pol(r, a0 + sign * total * t / n)) for t in range(n + 1)]
    return sample_arc(center, r, a0, a1)

def path_from(points, close=False):
    d = "M " + f(points[0][0] + C) + " " + f(points[0][1] + C)
    for p in points[1:]:
        d += f" L {f(p[0] + C)} {f(p[1] + C)}"
    if close:
        d += " Z"
    return d


# ---------------------------------------------------------------- diaphragm
def diaphragm(N, R_rim, Rc, rb, spin=0.0):
    """Return (blade_edges, opening_pts). blade_edges = list of point-lists."""
    centers = [pol(Rc, spin + i * 360.0 / N) for i in range(N)]
    rim = (0.0, 0.0)

    # inner vertices V_i = inner intersection of circle_i and circle_{i+1}
    V = []
    for i in range(N):
        pts = circle_inter(centers[i], rb, centers[(i + 1) % N], rb)
        if not pts:
            raise ValueError("blade circles do not intersect; adjust Rc/rb")
        V.append(min(pts, key=lambda p: norm(p)))   # nearer center

    # rim points W_i: where blade circle i crosses the rim circle, on the NEAR
    # side just outward of vertex V_i (not the far side of the blade circle).
    W = []
    for i in range(N):
        pts = circle_inter(rim, R_rim, centers[i], rb)
        if not pts:
            raise ValueError("blade circle misses rim; adjust params")
        W.append(min(pts, key=lambda p: norm(sub(p, V[i]))))   # nearest to V_i

    # Each blade k: arc on circle_k from inner vertex V_{k-1} out to rim W_k,
    # passing through V_k.  These interlock at the V's -> clean joined opening.
    edges = []
    for k in range(N):
        c = centers[k]
        start = V[(k - 1) % N]
        end = W[k]
        midv = V[k]
        edges.append(arc_through(c, rb, start, end, midv))
    return edges, V


# ---------------------------------------------------------------- gear
def gear_path(r_tip, r_root, teeth, rot=0.0):
    segs = [(0.00, r_root), (0.24, r_root), (0.35, r_tip),
            (0.65, r_tip), (0.76, r_root)]
    pts = []
    for i in range(teeth):
        base = rot + i * 360.0 / teeth
        for frac, rad in segs:
            pts.append(pol(rad, base + frac * 360.0 / teeth))
    d = "M " + f(pts[0][0] + C) + " " + f(pts[0][1] + C)
    for x, y in pts[1:]:
        d += f" L {f(x + C)} {f(y + C)}"
    return d + " Z"

def circle_d(r):
    return (f"M {f(C + r)} {f(C)} "
            f"A {f(r)} {f(r)} 0 1 0 {f(C - r)} {f(C)} "
            f"A {f(r)} {f(r)} 0 1 0 {f(C + r)} {f(C)} Z")


# ---------------------------------------------------------------- assemble
PARAMS = dict(
    teeth=6, r_tip=246, r_root=214,
    band=192, ring=182,
    N=6, R_rim=152, Rc=92, rb=150, spin=-90,
)

def build(style):
    p = PARAMS
    edges, V = diaphragm(p["N"], p["R_rim"], p["Rc"], p["rb"], p["spin"])
    opening = [v for v in V]  # closed polygon of the aperture (already joined)

    if style == "vintage":
        bg, ink = "#f3ebd4", "#2f5132"
    else:
        bg, ink, accent = "#0f1714", "#74d39f", "#f0a83c"

    s = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {SIZE} {SIZE}" width="{SIZE}" height="{SIZE}">']
    rx = 64 if style == "vintage" else 96
    s.append(f'<rect width="{SIZE}" height="{SIZE}" rx="{rx}" fill="{bg}"/>')

    if style == "vintage":
        # solid ink cog ring (annulus, even-odd knockout)
        s.append(f'<path fill="{ink}" fill-rule="evenodd" d="{gear_path(p["r_tip"], p["r_root"], p["teeth"])} {circle_d(p["band"])}"/>')
        s.append(f'<circle cx="{f(C)}" cy="{f(C)}" r="{f(p["ring"]-6)}" fill="none" stroke="{ink}" stroke-width="4"/>')
        sw = 13
        for e in edges:
            s.append(f'<path d="{path_from(e)}" fill="none" stroke="{ink}" stroke-width="{sw}" stroke-linecap="round" stroke-linejoin="round"/>')
        # clean closed aperture outline (re-traces inner segments -> crisp polygon)
        s.append(f'<path d="{path_from(opening, close=True)}" fill="none" stroke="{ink}" stroke-width="{sw}" stroke-linejoin="round"/>')
    else:
        s.append(f'<path d="{gear_path(p["r_tip"], p["r_root"], p["teeth"])}" fill="none" stroke="{ink}" stroke-width="11" stroke-linejoin="round"/>')
        s.append(f'<circle cx="{f(C)}" cy="{f(C)}" r="{f(p["ring"])}" fill="none" stroke="{ink}" stroke-width="6" opacity="0.5"/>')
        for e in edges:
            s.append(f'<path d="{path_from(e)}" fill="none" stroke="{ink}" stroke-width="13" stroke-linecap="round" stroke-linejoin="round"/>')
        s.append(f'<path d="{path_from(opening, close=True)}" fill="{accent}" fill-opacity="0.12" stroke="{ink}" stroke-width="13" stroke-linejoin="round"/>')

    s.append('</svg>')
    return "\n".join(s)


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    edges, V = diaphragm(PARAMS["N"], PARAMS["R_rim"], PARAMS["Rc"], PARAMS["rb"], PARAMS["spin"])
    r_open = sum(norm(v) for v in V) / PARAMS["N"]
    r_max = max(norm(p) for e in edges for p in e)
    print(f"aperture opening radius ~ {r_open:.1f}px ; blade max radius {r_max:.1f}px ; inner ring {PARAMS['ring']}px")
    for style in ("vintage", "modern"):
        with open(os.path.join(here, f"plumb_{style}.svg"), "w", encoding="utf-8") as fh:
            fh.write(build(style))
        print("wrote", f"plumb_{style}.svg")
