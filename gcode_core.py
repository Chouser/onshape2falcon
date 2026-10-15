"""Gcode generation for the laser, free of inkex so it can be tested with
plain python.  Loops are lists of (x, y) points in mm, closed implicitly."""

import json
import math
import re

import hatch


class OpenPath(list):
    """A polyline that must not be closed.  Plain lists are closed loops."""


def load_config(path):
    with open(path) as f:
        cfg = json.load(f)
    if "machine" not in cfg or "materials" not in cfg:
        raise ValueError(f"{path}: needs 'machine' and 'materials'")
    for name, mat in cfg["materials"].items():
        if isinstance(mat, dict) and "fill" in mat:
            try:
                check_fill(mat["fill"])
            except ValueError as e:
                raise ValueError(f"{path}: material {name!r}: {e}")
    return cfg


FILL_KEYS = {"line_spacing_mm", "angle_deg", "lead_in_mm", "lead_out_mm",
             "perimeter_pass", "perimeter_power_pct", "perimeter_feed_mm_min"}


def check_fill(fill):
    """Raise ValueError if a material's "fill" settings are unusable."""
    if not isinstance(fill, dict):
        raise ValueError("'fill' must be an object")
    unknown = set(fill) - FILL_KEYS
    if unknown:
        raise ValueError(f"unknown fill setting(s): {', '.join(sorted(unknown))}")
    num = lambda k: isinstance(fill.get(k), (int, float)) and not isinstance(fill.get(k), bool)
    if not num("line_spacing_mm") or fill["line_spacing_mm"] <= 0:
        raise ValueError("fill needs line_spacing_mm greater than 0")
    for k in ("angle_deg", "lead_in_mm", "lead_out_mm", "perimeter_power_pct",
              "perimeter_feed_mm_min"):
        if k in fill and not num(k):
            raise ValueError(f"fill {k} must be a number")
    for k in ("lead_in_mm", "lead_out_mm"):
        if fill.get(k, 0) < 0:
            raise ValueError(f"fill {k} can't be negative")


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


def _power(m, pct):
    return f'{m["s_max"] * pct / 100:.2f}'


def _clean_all(loops, m, page_height_mm):
    """Map loops to machine coordinates and drop the degenerate ones."""
    return [c for c in (_clean(type(l)(_map(p, m, page_height_mm) for p in l))
                        for l in loops) if len(c) > 1]


def _emit_loop(lines, m, loop, s, feed):
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


def _lead_points(seg, lead_in, lead_out):
    """Where a fill line really starts and ends: the segment extended along
    its own direction by the lead-in and lead-out."""
    (x0, y0), (x1, y1) = seg
    d = math.hypot(x1 - x0, y1 - y0)
    ux, uy = (x1 - x0) / d, (y1 - y0) / d
    return ((x0 - ux * lead_in, y0 - uy * lead_in),
            (x1 + ux * lead_out, y1 + uy * lead_out))


def _emit_fill(lines, allpts, m, name, mat, shape, passes):
    """Hatch one shape (a list of loops in machine coordinates), then trace
    its perimeter if asked.  Returns the head position afterwards."""
    fill = mat["fill"]
    s = _power(m, mat["power_pct"])
    feed = mat["feed_mm_min"]
    lead_in = fill.get("lead_in_mm", 0)
    lead_out = fill.get("lead_out_mm", 0)
    lead_tpl = m.get("lead", "G0 X{x} Y{y} F{feed}")
    segs = hatch.hatch_segments(shape, fill["line_spacing_mm"], fill.get("angle_deg", 0))
    pos = None
    if segs:
        lines.append(f"; {name} fill: {len(segs)} line(s), "
                     f"spacing {fill['line_spacing_mm']}mm, angle {fill.get('angle_deg', 0)}")
    for _ in range(passes if segs else 0):
        for seg in segs:
            a, b = _lead_points(seg, lead_in, lead_out)
            allpts.extend((a, b))
            lines.append(m["travel"].format(x=_fmt(a[0]), y=_fmt(a[1])))
            lines.append(m["laser_on"].format(s=s))
            if lead_in > 0:
                lines.append(lead_tpl.format(x=_fmt(seg[0][0]), y=_fmt(seg[0][1]), feed=feed))
            lines.append(m["cut_first"].format(x=_fmt(seg[1][0]), y=_fmt(seg[1][1]), feed=feed))
            if lead_out > 0:
                lines.append(lead_tpl.format(x=_fmt(b[0]), y=_fmt(b[1]), feed=feed))
            pos = b
        if m["laser_off"]:
            lines.append(m["laser_off"])
    if fill.get("perimeter_pass"):
        ps = _power(m, fill.get("perimeter_power_pct", mat["power_pct"]))
        pfeed = fill.get("perimeter_feed_mm_min", feed)
        lines.append(f"; {name} fill perimeter: {len(shape)}")
        for loop in order_loops(shape, start=pos or (0.0, 0.0)):
            allpts.extend(loop)
            _emit_loop(lines, m, loop, ps, pfeed)
            pos = loop[0]
    return pos


def generate(cfg, jobs, page_height_mm=0.0):
    """jobs: list of (material_name, holes, outlines[, fills]).  holes and
    outlines are lists of loops; holes of every job are cut before its
    outlines.  fills, for materials with "fill" settings, is a list of
    shapes, each a list of loops: the shape's interior is hatched (loops
    inside others are holes), then its perimeter traced if the material says
    so.  Returns (gcode_text, warnings)."""
    m = cfg["machine"]
    warnings = []
    lines = []
    allpts = []
    for name, holes, outlines, *rest in jobs:
        mat = cfg["materials"][name]
        fills = rest[0] if rest else []
        if fills and "fill" not in mat:
            raise ValueError(f"material {name!r} has no 'fill' settings")
        s = _power(m, mat["power_pct"])
        feed = mat["feed_mm_min"]
        passes = mat.get("passes", 1)
        lines.append(f"; material {name}: {mat['power_pct']}% F{feed} x{passes}")
        for kind, loops in (("holes", holes), ("outlines", outlines)):
            if not loops:
                continue
            lines.append(f"; {name} {kind}: {len(loops)}")
            ordered = order_loops(_clean_all(loops, m, page_height_mm))
            for _ in range(passes):
                for loop in ordered:
                    allpts.extend(loop)
                    _emit_loop(lines, m, loop, s, feed)
        shapes = [c for c in (_clean_all(sh, m, page_height_mm) for sh in fills) if c]
        pos = (0.0, 0.0)
        while shapes:
            # Nearest shape first, judged by where its first loop starts.
            shape = min(shapes, key=lambda sh: _dist(pos, sh[0][0]))
            shapes.remove(shape)
            pos = _emit_fill(lines, allpts, m, name, mat, shape, passes) or shape[0][0]
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
