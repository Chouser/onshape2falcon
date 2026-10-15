"""Helpers shared by the laser extensions."""

import math
from collections import defaultdict

import inkex


PREVIEW_LABEL = "gcode-preview"  # layer Export Gcode draws; never part of a job


def in_preview(elem):
    """True for anything inside the gcode preview layer, which the other
    extensions must skip when they fall back to "all paths"."""
    return any(a.get("inkscape:label") == PREVIEW_LABEL for a in elem.ancestors())


def mm_to_uu(svg, mm):
    """Millimetres to user units (accounts for the viewBox scale, which
    svg.unittouu ignores when the document has no namedview units)."""
    return inkex.units.convert_unit(f"{mm}mm", "px") / svg.scale


# Note: always call path.to_absolute() before path.transform(): inkex's
# Path.transform loses track of the subpath start when a relative `m` follows
# an unclosed subpath, so everything after it comes out displaced.
STEP_MM = 0.2  # target spacing of points when flattening curves
MEETS_MM = 0.005  # an unclosed path this close to its start counts as closed


def flatten(loop, uu_per_mm):
    """Single-subpath inkex.Path -> list of (x, y) in mm."""
    pts = []
    for seg in loop.proxy_iterator():
        if seg.letter in "zZ":
            continue
        if seg.letter in "mM":
            pts.append((seg.end_point.x, seg.end_point.y))
            continue
        a = seg.previous_end_point
        b = seg.end_point
        if seg.letter in "lLhHvV":
            n = 1
        else:
            span = math.hypot(b.x - a.x, b.y - a.y) / uu_per_mm
            n = max(4, min(200, math.ceil(span * 1.5 / STEP_MM)))
        for k in range(1, n + 1):
            p = seg.point(k / n)
            pts.append((p.x, p.y))
    pts = [(x / uu_per_mm, y / uu_per_mm) for x, y in pts]
    out = [pts[0]]
    for p in pts[1:]:
        if abs(p[0] - out[-1][0]) > 1e-4 or abs(p[1] - out[-1][1]) > 1e-4:
            out.append(p)
    return out


def is_closed(loop, pts):
    """A subpath is closed if it ends in Z or already ends where it started."""
    return loop[-1].letter in "zZ" or math.dist(pts[0], pts[-1]) < MEETS_MM


def _polygon(path):
    pts = []
    for seg in path.proxy_iterator():
        if seg.letter in "zZ":
            continue
        if seg.letter in "mM":
            pts.append((seg.end_point.x, seg.end_point.y))
        else:
            for k in range(1, 9):
                p = seg.point(k / 8)
                pts.append((p.x, p.y))
    return pts

def _area(poly):
    return abs(sum(poly[i][0] * poly[(i + 1) % len(poly)][1]
                   - poly[(i + 1) % len(poly)][0] * poly[i][1]
                   for i in range(len(poly)))) / 2

def _inside(pt, poly):
    x, y = pt
    inside = False
    j = len(poly) - 1
    for i in range(len(poly)):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside

def nest_loops(loops):
    """For each closed loop return (parent, depth): the smallest loop that
    contains it (or None) and how many loops enclose it.  Even depth is an
    outline, odd depth is a hole in its parent."""
    polys = [_polygon(l) for l in loops]
    areas = [_area(p) for p in polys]
    parent = []
    for i, poly in enumerate(polys):
        best = None
        for j, other in enumerate(polys):
            if i != j and areas[j] > areas[i] and _inside(poly[0], other):
                if best is None or areas[j] < areas[best]:
                    best = j
        parent.append(best)

    depth = []
    for i in range(len(loops)):
        d, k = 0, i
        while parent[k] is not None:
            k = parent[k]
            d += 1
        depth.append(d)
    return parent, depth


def split_loops(loops):
    """Group closed loops into independent parts: each outline together
    with the holes directly inside it (holes first, outline last)."""
    parent, depth = nest_loops(loops)
    holes = defaultdict(list)
    for i in range(len(loops)):
        if depth[i] % 2 == 1:
            holes[parent[i]].append(i)
    parts = []
    for i in range(len(loops)):
        if depth[i] % 2 == 0:
            cmds = []
            for k in holes[i] + [i]:
                cmds.extend(loops[k])
            parts.append(inkex.Path(cmds))
    return parts
