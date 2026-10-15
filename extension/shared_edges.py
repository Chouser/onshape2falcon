"""Find stretches where one shape's edge runs along another's, so a laser can
cut them once.  Free of inkex so it can be tested with plain python.

Shapes are lists of (x, y) points in mm.  The Mark Shared Edges extension finds
the stretches to skip and draws them; the gcode export resamples each shape
the same way and leaves those stretches out."""

import math
from collections import defaultdict

STEP_MM = 0.1       # spacing shapes are resampled to before comparing
MIN_COS = 0.9       # edges closer than this to parallel are not "shared"
BRIDGE_MM = 0.3     # unmatched gaps this short inside a match are bridged


def resample(pts, closed=True, step=STEP_MM):
    """Insert points so no edge is longer than step (original points kept)."""
    out = []
    n = len(pts)
    for i in range(n if closed else n - 1):
        a, b = pts[i], pts[(i + 1) % n]
        out.append(a)
        k = math.ceil(math.dist(a, b) / step)
        for j in range(1, k):
            t = j / k
            out.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
    if not closed:
        out.append(pts[-1])
    return out


def _seg_near(p, a, b):
    """(distance, closest point, inside) from p to segment a-b; `inside` is
    False when p projects beyond the segment's ends."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    ll = dx * dx + dy * dy
    raw = 0 if ll == 0 else ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / ll
    t = max(0, min(1, raw))
    q = (a[0] + t * dx, a[1] + t * dy)
    return math.dist(p, q), q, raw == t


class _Grid:
    """Segments bucketed by midpoint; query returns those near a point.
    Segments must be no longer than `step` and queries no farther than
    `reach` for the 3x3 cell search to find everything."""

    def __init__(self, reach, step=STEP_MM):
        self.cell = reach + step
        self.cells = defaultdict(list)

    def _key(self, p):
        return (math.floor(p[0] / self.cell), math.floor(p[1] / self.cell))

    def add(self, a, b, owner=None):
        self.cells[self._key(((a[0] + b[0]) / 2, (a[1] + b[1]) / 2))].append((a, b, owner))

    def near(self, p):
        kx, ky = self._key(p)
        for x in (kx - 1, kx, kx + 1):
            for y in (ky - 1, ky, ky + 1):
                yield from self.cells.get((x, y), ())


def _edges(pts, closed):
    n = len(pts)
    return [(pts[i], pts[(i + 1) % n]) for i in range(n if closed else n - 1)]


def find_shared(shapes, tol=0.25, min_len=1.0, step=STEP_MM):
    """shapes: list of (points, closed, group); shapes in the same group (the
    subpaths of one part) never match each other.  A later shape's stretch that runs
    within `tol` of, and roughly parallel to, an earlier shape's edge is
    reported as {"shape": i, "skip": [pts], "keep": [pts], "along": [earlier shape indexes]}: cut `keep` (on the
    earlier shape), skip `skip`."""
    grid = _Grid(tol, step)
    found = []
    groups = [sh[2] if len(sh) > 2 else None for sh in shapes]
    for i, (pts, closed, *_) in enumerate(shapes):
        P = resample(pts, closed, step)
        n = len(P)
        match = [None] * n
        partner = [None] * n
        for k, p in enumerate(P):
            a = P[k - 1] if (closed or k > 0) else P[k]
            b = P[(k + 1) % n] if (closed or k < n - 1) else P[k]
            tx, ty = b[0] - a[0], b[1] - a[1]
            tl = math.hypot(tx, ty)
            if tl == 0:
                continue
            best = None
            for s, e, owner in grid.near(p):
                d, q, inside = _seg_near(p, s, e)
                # Past the end of a neighbour's edge (a corner) is not shared.
                if not inside or d > tol or (best is not None and d >= best[0]):
                    continue
                if groups[i] is not None and groups[owner] == groups[i]:
                    continue
                sx, sy = e[0] - s[0], e[1] - s[1]
                sl = math.hypot(sx, sy)
                if sl and abs(tx * sx + ty * sy) / (tl * sl) >= MIN_COS:
                    best = (d, q, owner)
            if best:
                match[k] = best[1]
                partner[k] = best[2]
        found.extend(_runs(i, P, match, partner, closed, min_len, step))
        for s, e in _edges(P, closed):
            grid.add(s, e, i)
    return found


def _runs(i, P, match, partner, closed, min_len, step):
    n = len(P)
    marked = [m is not None for m in match]
    # Bridge short unmatched gaps (corners, noise) between matched points.
    gap = math.ceil(BRIDGE_MM / step)
    k = 0
    while k < n:
        if not marked[k]:
            j = k
            while j < n and not marked[j]:
                j += 1
            left = (k > 0 and marked[k - 1]) or (closed and marked[n - 1] and k == 0)
            right = (j < n and marked[j]) or (closed and marked[0] and j == n)
            if left and right and j - k <= gap:
                for m in range(k, j):
                    marked[m] = True
            k = j
        else:
            k += 1
    if not any(marked):
        return []
    if all(marked):
        run_idx = [list(range(n)) + ([0] if closed else [])]
    else:
        start = marked.index(False) if closed else 0
        order = list(range(start + 1, n)) + list(range(0, start + 1)) if closed else list(range(n))
        run_idx, cur = [], []
        for idx in order:
            if marked[idx]:
                cur.append(idx)
            elif cur:
                run_idx.append(cur)
                cur = []
        if cur:
            run_idx.append(cur)
    out = []
    for idx in run_idx:
        pts = [P[x] for x in idx]
        length = sum(math.dist(a, b) for a, b in zip(pts, pts[1:]))
        if length >= min_len:
            keep = []
            for x in idx:
                q = match[x]
                if q is not None and (not keep or keep[-1] != q):
                    keep.append(q)
            along = sorted({partner[x] for x in idx if partner[x] is not None})
            out.append({"shape": i, "skip": pts, "keep": keep, "along": along})
    return out


def apply_skips(pts, closed, skips, step=STEP_MM, tol=0.02):
    """Cut `pts` leaving out the stretches in `skips` (polylines, as found by
    find_shared for this shape).  Returns None if nothing is skipped, else a
    list of open polylines (possibly empty)."""
    if not skips:
        return None
    P = resample(pts, closed, step)
    grid = _Grid(tol, step)
    for sk in skips:
        for s, e in zip(sk, sk[1:]):
            # skip polylines can have long edges; subdivide so the grid finds them
            seg = resample([s, e], False, step)
            for a, b in zip(seg, seg[1:]):
                grid.add(a, b)
    on = [any(_seg_near(p, s, e)[0] <= tol for s, e, _ in grid.near(p)) for p in P]
    n = len(P)
    edges = [(k, k + 1) for k in range(n - 1)] + ([(n - 1, 0)] if closed else [])
    gone = [on[a] and on[b] for a, b in edges]
    if not any(gone):
        return None
    if closed:
        s = gone.index(True)
        edges = edges[s + 1:] + edges[:s + 1]
        gone = gone[s + 1:] + gone[:s + 1]
    pieces, cur = [], None
    for (a, b), g in zip(edges, gone):
        if g:
            if cur:
                pieces.append(cur)
            cur = None
        else:
            if cur is None:
                cur = [P[a]]
            cur.append(P[b])
    if cur:
        pieces.append(cur)
    return pieces
