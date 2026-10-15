import math, shared_edges as se

def rect(x0, y0, x1, y1): return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
def circle(cx, cy, r, n=360):
    return [(cx + r * math.cos(2 * math.pi * k / n), cy + r * math.sin(2 * math.pi * k / n)) for k in range(n)]
def plen(p, closed=False):
    q = p + [p[0]] if closed else p
    return sum(math.dist(a, b) for a, b in zip(q, q[1:]))

# Two kerfed neighbours: edges 0.18 apart (A right edge x=20.09, B left x=19.91)
A = rect(0, 0, 20.09, 20); B = rect(19.91, 0, 40, 20); C = rect(100, 0, 120, 20)
found = se.find_shared([(A, True), (B, True), (C, True)])
assert len(found) == 1 and found[0]["shape"] == 1, found
print("skip len %.2f" % plen(found[0]["skip"]), "keep len %.2f" % plen(found[0]["keep"]))
assert 19.5 < plen(found[0]["skip"]) < 20.5
assert 19.5 < plen(found[0]["keep"]) < 20.5
# Applying: B loses its left edge, remaining 3 edges form one open piece
pieces = se.apply_skips(B, True, [found[0]["skip"]])
assert len(pieces) == 1, len(pieces)
print("B piece len %.2f (full perimeter %.2f)" % (plen(pieces[0]), plen(B, True)))
assert abs(plen(pieces[0]) - (plen(B, True) - 20)) < 0.5
assert se.apply_skips(A, True, []) is None
assert se.apply_skips(C, True, [found[0]["skip"]]) is None  # unrelated shape untouched

# Plug in a hole: ring B has an inner loop r=9.91, plug A is r=10.09 -> whole hole loop is shared
plug = circle(0, 0, 10.09); ring_out = circle(0, 0, 20); ring_hole = circle(0, 0, 9.91)
f = se.find_shared([(plug, True), (ring_out, True), (ring_hole, True)])
assert [x["shape"] for x in f] == [2], f
assert se.apply_skips(ring_hole, True, [f[0]["skip"]]) == []
# stepped, curved neighbour: arc-shaped shared edge on one side only
half = [(10.09 * math.cos(t / 180 * math.pi), 10.09 * math.sin(t / 180 * math.pi)) for t in range(0, 181)]
sector_a = half + [(-10.09, 0)] if False else half
other = [(9.91 * math.cos(t / 180 * math.pi), 9.91 * math.sin(t / 180 * math.pi)) for t in range(0, 181)] + [(-15, 0), (-15, 15), (15, 15), (15, 0)]
f = se.find_shared([(half, False), (other, True)])
assert len(f) == 1 and f[0]["shape"] == 1 and plen(f[0]["skip"]) > 25, f
# crossing at an angle is not shared
X = rect(0, 0, 20, 20); Y = [(10, -5), (30, 5), (30, 25), (10, 15)]
print("crossing:", se.find_shared([(X, True), (Y, True)]))
# near-miss beyond tolerance is not shared
assert se.find_shared([(rect(0, 0, 20, 20), True), (rect(21, 0, 40, 20), True)]) == []
# Subpaths of one part (outline + holes) never match each other, even when close
slot1 = rect(5, 5, 15, 8); slot2 = rect(5, 8.1, 15, 11)   # holes 0.1 apart, same part
part = rect(0, 0, 20, 20)
assert se.find_shared([(part, True, "p"), (slot1, True, "p"), (slot2, True, "p")]) == []
assert se.find_shared([(part, True, "p"), (slot1, True, "p"), (slot2, True, "q")]) != []
print("ok")
