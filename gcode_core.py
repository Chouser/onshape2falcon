"""Gcode generation for the laser, free of inkex so it can be tested with
plain python.  Loops are lists of (x, y) points in mm, closed implicitly."""

import json
import math
import re


class OpenPath(list):
    """A polyline that must not be closed.  Plain lists are closed loops."""


def load_config(path):
    with open(path) as f:
        cfg = json.load(f)
    if "machine" not in cfg or "materials" not in cfg:
        raise ValueError(f"{path}: needs 'machine' and 'materials'")
    return cfg


def _dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def order_loops(loops, start=(0.0, 0.0)):
    """Greedy nearest-neighbour order, rotating nothing: each loop is cut
    from its own first point.  Returns a new list."""
    todo = list(loops)
    out = []
    pos = start
    while todo:
        best = min(todo, key=lambda l: _dist(pos, l[0]))
        todo.remove(best)
        out.append(best)
        pos = best[0]
    return out


def _fmt(v):
    s = f"{v:.2f}"
    return "0.00" if s == "-0.00" else s


def _map(pt, machine, page_height_mm):
    """SVG y grows down; with flip_y the output is measured up from the
    bottom of the page, as LaserWeb does."""
    x, y = pt
    if machine.get("flip_y"):
        y = page_height_mm - y
    return (round(x, 2), round(y, 2))


def _clean(loop):
    """Drop points that repeat after rounding (including a closing point equal
    to the start, since generate() adds the closing move itself)."""
    out = type(loop)([loop[0]])
    for pt in loop[1:]:
        if pt != out[-1]:
            out.append(pt)
    while not isinstance(out, OpenPath) and len(out) > 1 and out[-1] == out[0]:
        out.pop()
    return out


DEFAULT_TRAVEL_MM_MIN = 6000.0   # G0 speed when machine has no "travel_mm_min"
_WORD = re.compile(r"([A-Za-z])\s*(-?\d*\.?\d+)")


def parse_moves(text, machine=None):
    """Read G0/G1 moves (absolute positioning, mm, modal F) out of gcode and
    ignore everything else.  Returns a list of (kind, start, end, speed) with
    speed in mm/min and kind one of:
      "cut"     G1: the laser is firing
      "lead"    G0 that carries its own F: a laser-off move at feed rate,
                as used for the lead-in and lead-out of fill lines
      "travel"  any other G0: a rapid, at machine["travel_mm_min"]"""
    travel_rate = (machine or {}).get("travel_mm_min", DEFAULT_TRAVEL_MM_MIN)
    pos = (0.0, 0.0)
    feed = travel_rate
    mode = None
    moves = []
    for line in text.splitlines():
        words = _WORD.findall(line.split(";", 1)[0])
        vals = {}
        for letter, num in words:
            letter = letter.upper()
            if letter == "G" and float(num) in (0, 1):
                mode = int(float(num))
            elif letter in "XYF":
                vals[letter] = float(num)
        if "F" in vals:
            feed = vals["F"]
        if not ("X" in vals or "Y" in vals):
            continue
        end = (vals.get("X", pos[0]), vals.get("Y", pos[1]))
        if mode == 1:
            moves.append(("cut", pos, end, feed))
        elif mode == 0 and "F" in vals:
            moves.append(("lead", pos, end, feed))
        elif mode == 0:
            moves.append(("travel", pos, end, travel_rate))
        pos = end
    return moves


def estimate_time(text, machine=None):
    """Estimate how long gcode text takes to run.  Returns (cut_s, travel_s);
    travel includes laser-off lead moves.

    Sums each move's length over its speed.  The real machine also spends
    time accelerating, so treat this as a lower bound, most noticeable on
    paths made of many tiny segments."""
    cut = travel = 0.0
    for kind, a, b, speed in parse_moves(text, machine):
        if speed <= 0:
            continue
        t = _dist(a, b) / speed * 60
        if kind == "cut":
            cut += t
        else:
            travel += t
    return cut, travel


def format_duration(seconds):
    s = int(round(seconds))
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    if h:
        return f"{h}h {m:02d}m {sec:02d}s"
    if m:
        return f"{m}m {sec:02d}s"
    return f"{sec}s"


def bounds(points):
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return min(xs), min(ys), max(xs), max(ys)


def generate(cfg, jobs, page_height_mm=0.0):
    """jobs: list of (material_name, holes, outlines), each a list of loops.
    Holes of every job are cut before its outlines.  Returns (gcode_text,
    warnings)."""
    m = cfg["machine"]
    warnings = []
    lines = []
    allpts = []
    for name, holes, outlines in jobs:
        mat = cfg["materials"][name]
        s = f'{m["s_max"] * mat["power_pct"] / 100:.2f}'
        feed = mat["feed_mm_min"]
        lines.append(f"; material {name}: {mat['power_pct']}% F{feed} x{mat.get('passes', 1)}")
        for kind, loops in (("holes", holes), ("outlines", outlines)):
            if not loops:
                continue
            lines.append(f"; {name} {kind}: {len(loops)}")
            ordered = order_loops([c for c in (_clean(type(l)(_map(p, m, page_height_mm) for p in l))
                                      for l in loops) if len(c) > 1])
            for _ in range(mat.get("passes", 1)):
                for loop in ordered:
                    allpts.extend(loop)
                    x0, y0 = loop[0]
                    lines.append(m["travel"].format(x=_fmt(x0), y=_fmt(y0)))
                    lines.append(m["laser_on"].format(s=s))
                    moves = loop[1:]
                    if not isinstance(loop, OpenPath):
                        moves = moves + [loop[0]]
                    for i, (x, y) in enumerate(moves):
                        tpl = m["cut_first"] if i == 0 else m["cut"]
                        lines.append(tpl.format(x=_fmt(x), y=_fmt(y), feed=feed))
                    if m["laser_off"]:
                        lines.append(m["laser_off"])
    if not allpts:
        raise ValueError("no geometry to cut")
    x0, y0, x1, y1 = bounds(allpts)
    if x0 < 0 or y0 < 0 or x1 > m["bed_x_mm"] or y1 > m["bed_y_mm"]:
        warnings.append(f"OUT OF BOUNDS: X{_fmt(x0)} Y{_fmt(y0)} to "
                        f"X{_fmt(x1)} Y{_fmt(y1)} (bed {m['bed_x_mm']}x{m['bed_y_mm']})")
    head = [f"; Bounds: X{_fmt(x0)} Y{_fmt(y0)} to X{_fmt(x1)} Y{_fmt(y1)}"]
    body = m["header"] + lines + m["footer"]
    cut_s, travel_s = estimate_time("\n".join(body), m)
    head.append(f"; Estimated time: {format_duration(cut_s + travel_s)} "
                f"(cutting {format_duration(cut_s)}, travel {format_duration(travel_s)})")
    text = "\n".join(head + body) + "\n"
    return text, warnings
