"""Parallel-line (hatch) fill for the laser, free of inkex so it can be
tested with plain python.  Points are (x, y) in mm."""

import math

MIN_SEGMENT_MM = 0.001  # drop slivers where a line only grazes the shape


def hatch_segments(loops, spacing_mm, angle_deg=0.0):
    """Fill the region enclosed by `loops` with parallel lines.

    Each loop is a list of points, implicitly closed.  Fill uses the even-odd
    rule, so a loop inside another is a hole.  Lines are `spacing_mm` apart
    and run `angle_deg` counter-clockwise from +X.  They are centred in the
    shape's extent, so a shape thinner than half the spacing gets none.

    Returns ((x0, y0), (x1, y1)) segments in cutting order: line by line,
    each line running the opposite way from the one before (serpentine), and
    the segments of one line (a concave shape or a hole gives several) in
    order along its direction.
    """
    if spacing_mm <= 0:
        raise ValueError("line spacing must be positive")
    c = math.cos(math.radians(angle_deg))
    s = math.sin(math.radians(angle_deg))
    # u runs along the hatch lines, v across them.
    rot = [[(x * c + y * s, -x * s + y * c) for x, y in loop]
           for loop in loops if len(loop) >= 3]
    if not rot:
        return []
    vmin = min(v for loop in rot for _, v in loop)
    vmax = max(v for loop in rot for _, v in loop)
    n = max(0, math.ceil((vmax - vmin) / spacing_mm - 0.5))
    crossings = [[] for _ in range(n)]
    for loop in rot:
        for (ua, va), (ub, vb) in zip(loop, loop[1:] + loop[:1]):
            if va == vb:
                continue
            lo, hi = min(va, vb), max(va, vb)
            # Line k sits at v = vmin + spacing * (k + 0.5).  An edge crosses
            # it when lo <= v < hi; the half-open range keeps a line that
            # passes exactly through a vertex from being counted twice.
            k0 = max(0, math.ceil((lo - vmin) / spacing_mm - 0.5))
            k1 = min(n - 1, math.ceil((hi - vmin) / spacing_mm - 0.5) - 1)
            for k in range(k0, k1 + 1):
                v = vmin + spacing_mm * (k + 0.5)
                crossings[k].append(ua + (v - va) * (ub - ua) / (vb - va))

    out = []
    flip = False
    for k, us in enumerate(crossings):
        us.sort()
        v = vmin + spacing_mm * (k + 0.5)
        line = [(a, b) for a, b in zip(us[0::2], us[1::2]) if b - a >= MIN_SEGMENT_MM]
        if not line:
            continue
        if flip:
            line = [(b, a) for a, b in reversed(line)]
        flip = not flip
        for a, b in line:
            out.append(((a * c - v * s, a * s + v * c),
                        (b * c - v * s, b * s + v * c)))
    return out
