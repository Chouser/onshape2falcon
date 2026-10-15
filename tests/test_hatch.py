import math, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "extension"))
import hatch

sq = lambda x, y, w, h=None: [(x, y), (x + w, y), (x + w, y + (h or w)), (x, y + (h or w))]
length = lambda segs: sum(math.dist(a, b) for a, b in segs)
close = lambda p, q: math.dist(p, q) < 1e-9

# 10x10 square, 1mm spacing: ten lines at y=0.5..9.5, alternating direction.
segs = hatch.hatch_segments([sq(0, 0, 10)], 1)
assert len(segs) == 10, segs
assert close(segs[0][0], (0, 0.5)) and close(segs[0][1], (10, 0.5)), segs[0]
assert close(segs[1][0], (10, 1.5)) and close(segs[1][1], (0, 1.5)), segs[1]
assert close(segs[9][0], (10, 9.5)), segs[9]

# A hole splits the lines it crosses; coverage is area / spacing.
segs = hatch.hatch_segments([sq(0, 0, 10), sq(3, 3, 4)], 1)
assert len(segs) == 14, len(segs)   # 6 full lines + 4 lines in two pieces
assert abs(length(segs) - 84) < 1e-9, length(segs)
# On a line that runs right-to-left, the pieces come right piece first.
row = [sg for sg in segs if abs(sg[0][1] - 3.5) < 1e-9]   # y=3.5 is the 4th line: right-to-left
assert len(row) == 2 and row[0][0][0] > row[1][0][0], row

# 90 degrees: vertical lines, first one at the right edge going up.
segs = hatch.hatch_segments([sq(0, 0, 10)], 1, 90)
assert close(segs[0][0], (9.5, 0)) and close(segs[0][1], (9.5, 10)), segs[0]

# Any angle covers the area (to within one line's worth at the edges).
for ang in (0, 30, 45, 117):
    got = length(hatch.hatch_segments([sq(0, 0, 10)], 0.1, ang)) * 0.1
    assert abs(got - 100) < 1.0, (ang, got)

# Concave L: lines through the notch give a single piece each.
L = [(0, 0), (10, 0), (10, 4), (4, 4), (4, 10), (0, 10)]
assert abs(length(hatch.hatch_segments([L], 0.1)) * 0.1 - 64) < 0.5

# Winding direction doesn't matter, and a vertex exactly on a line is
# counted once (diamond with corners at y=0 and y=10, line at y=5 passes
# through its side vertices).
d = [(5, 0), (10, 5), (5, 10), (0, 5)]
for loop in (d, d[::-1]):
    segs = hatch.hatch_segments([loop], 1)
    assert abs(length(segs) - 50) < 1e-9, length(segs)

# Too thin for a line; degenerate input.
assert hatch.hatch_segments([sq(0, 0, 10, 0.4)], 1) == []
assert hatch.hatch_segments([], 1) == [] and hatch.hatch_segments([[(0, 0), (1, 1)]], 1) == []
try:
    hatch.hatch_segments([sq(0, 0, 10)], 0)
    raise SystemExit("zero spacing should fail")
except ValueError:
    pass
print("ok")
