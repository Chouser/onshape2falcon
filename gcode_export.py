#!/usr/bin/env python3

import math
import os

import inkex

import gcode_core
from laser_common import mm_to_uu, nest_loops

DEBUG = True
DEFAULT_DIR = os.path.expanduser("~/proj/laser-cut")
STEP_MM = 0.2  # target spacing of points when flattening curves


def debug(message):
    if DEBUG:
        inkex.utils.debug(f"GcodeExport: {message}")


def flatten(loop, uu_per_mm):
    """Closed single-subpath inkex.Path -> list of (x, y) in mm."""
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
    if len(out) > 1 and abs(out[0][0] - out[-1][0]) < 1e-4 \
            and abs(out[0][1] - out[-1][1]) < 1e-4:
        out.pop()
    return out


class GcodeExport(inkex.EffectExtension):
    """Write gcode straight from the SVG.  Each path is cut with the settings
    of the nearest enclosing group whose label (or id) names a material in
    materials.json.  Per material, all holes are cut before any outlines.
    Only the selected objects are exported, or everything if none are."""

    def add_arguments(self, pars):
        pars.add_argument("--gcode_file", default="",
                          help="gcode file (default: next to the SVG, else ~/proj/laser-cut)")
        pars.add_argument("--config", default="",
                          help="materials file (default: next to this script)")

    def material_of(self, elem, materials):
        lowered = {k.lower(): k for k in materials}
        for anc in elem.ancestors():
            for name in (anc.get("inkscape:label"), anc.get_id()):
                if name and name.lower() in lowered:
                    return lowered[name.lower()]
        return None

    def effect(self):
        here = os.path.dirname(os.path.abspath(__file__))
        cfg_path = self.options.config or os.path.join(here, "materials.json")
        try:
            cfg = gcode_core.load_config(cfg_path)
        except (OSError, ValueError) as e:
            raise inkex.AbortExtension(f"Cannot load materials: {e}")

        # Export the selection (selected paths and everything inside selected
        # groups); with nothing selected, or from the command line, export all.
        roots = list(self.svg.selection.values()) or [self.svg]
        seen = set()
        paths = []
        for root in roots:
            for e in [root, *root.iterdescendants()]:
                if (isinstance(e, inkex.PathElement) and id(e) not in seen
                        and not any(isinstance(a, inkex.Defs) for a in e.ancestors())):
                    seen.add(id(e))
                    paths.append(e)
        if not paths:
            raise inkex.AbortExtension("No path objects to export.")

        uu_per_mm = mm_to_uu(self.svg, 1)
        jobs = {}
        unassigned = []
        for elem in paths:
            mat = self.material_of(elem, cfg["materials"])
            if mat is None:
                unassigned.append(elem.get_id())
                continue
            path = elem.path.transform(elem.composed_transform()).to_absolute()
            loops = list(path.break_apart())
            _, depth = nest_loops(loops)
            holes, outlines = jobs.setdefault(mat, ([], []))
            for loop, d in zip(loops, depth):
                (holes if d % 2 else outlines).append(flatten(loop, uu_per_mm))
        if unassigned:
            raise inkex.AbortExtension(
                "Paths not inside a material group (known: "
                + ", ".join(cfg["materials"]) + "): " + ", ".join(unassigned[:10]))

        text, warnings = gcode_core.generate(
            cfg, [(m, h, o) for m, (h, o) in jobs.items()],
            self.svg.get_viewbox()[3] / uu_per_mm)
        for w in warnings:
            debug(w)
        out = os.path.expanduser(self.options.gcode_file or "")
        if not out:
            # input_file is a temp copy; use the document's own name and,
            # when Inkscape provides it (saved documents), its directory.
            name = self.svg.get("sodipodi:docname") or "export.svg"
            base = self.svg.get("sodipodi:docbase") or DEFAULT_DIR
            out = os.path.join(base, os.path.splitext(name)[0] + ".gcode")
        out = os.path.abspath(out)
        with open(out, "w", newline="\n") as f:
            f.write(text)
        for m, (h, o) in jobs.items():
            debug(f"{m}: {len(h)} hole(s), {len(o)} outline(s)")
        debug(f"wrote {out}")


if __name__ == "__main__":
    GcodeExport().run()
