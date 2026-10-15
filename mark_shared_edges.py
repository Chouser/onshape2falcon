#!/usr/bin/env python3

import inkex
from inkex.paths import Line, Move

import shared_edges
from laser_common import flatten, in_preview, is_closed, mm_to_uu

DEBUG = True
GROUP = "shared-edges"


def debug(message):
    if DEBUG:
        inkex.utils.debug(f"MarkSharedEdges: {message}")


class MarkSharedEdges(inkex.EffectExtension):
    """Find places where one shape's edge runs along another's (typical for
    kerfed neighbours) and draw them, so Export Gcode can cut them once.

    Adds a `shared-edges` group with two subgroups:
      skipped  red   the stretch of the later shape that will NOT be cut
      kept     green the neighbour's edge that cuts it instead
    Nothing else is changed, so shapes stay closed.  Run this after arranging
    parts: the marks are drawn in place and do not follow moved shapes.
    Re-running replaces the previous marks.
    """

    def add_arguments(self, pars):
        pars.add_argument("--tolerance", type=float, default=0.1,
                          help="max distance between shared edges, mm")
        pars.add_argument("--min_length", type=float, default=5.0,
                          help="shortest shared stretch to mark, mm")

    def effect(self):
        for g in [g for g in self.svg.iterdescendants()
                  if g.get("inkscape:label") == GROUP]:
            g.getparent().remove(g)

        roots = list(self.svg.selection.values()) or [self.svg]
        seen, elems = set(), []
        for root in roots:
            for e in [root, *root.iterdescendants()]:
                if isinstance(e, inkex.PathElement) and id(e) not in seen \
                        and not any(isinstance(a, inkex.Defs) for a in e.ancestors()) \
                        and not in_preview(e):
                    seen.add(id(e))
                    elems.append(e)
        if not elems:
            raise inkex.AbortExtension("No path objects to check.")

        uu_per_mm = mm_to_uu(self.svg, 1)
        shapes, keys = [], []
        for elem in elems:
            path = elem.path.to_absolute().transform(elem.composed_transform()).to_absolute()
            for k, loop in enumerate(path.break_apart()):
                pts = flatten(loop, uu_per_mm)
                shapes.append((pts, is_closed(loop, pts), elem.get_id()))
                keys.append(f"{elem.get_id()}:{k}")

        found = shared_edges.find_shared(
            shapes, self.options.tolerance, self.options.min_length)

        group = inkex.Group.new(GROUP)
        group.set("inkscape:label", GROUP)
        skipped = inkex.Group.new("skipped")
        skipped.set("inkscape:label", "skipped")
        kept = inkex.Group.new("kept")
        kept.set("inkscape:label", "kept")
        group.append(skipped)
        group.append(kept)
        for f in found:
            with_ = ",".join(keys[j] for j in f["along"])
            self._add(skipped, f["skip"], uu_per_mm, "#e00000", 0.3, keys[f["shape"]], with_)
            self._add(kept, f["keep"], uu_per_mm, "#00a000", 0.15, None, with_)
            x, y = f["skip"][0]
            debug(f"{keys[f['shape']]} runs along {with_}: {_len(f['skip']):.1f} mm "
                  f"from X{x:.1f} Y{y:.1f}")
        self.svg.append(group)

        total = sum(_len(f["skip"]) for f in found)
        debug(f"{len(found)} shared stretch(es), {total:.1f} mm of cutting saved "
              f"(tolerance {self.options.tolerance} mm, min {self.options.min_length} mm)")

    def _add(self, parent, pts, uu_per_mm, color, width_mm, loop_key, along):
        el = inkex.PathElement()
        el.path = inkex.Path(
            [Move(pts[0][0] * uu_per_mm, pts[0][1] * uu_per_mm)]
            + [Line(x * uu_per_mm, y * uu_per_mm) for x, y in pts[1:]])
        el.style = inkex.Style({
            "fill": "none", "stroke": color, "stroke-opacity": "0.8",
            "stroke-width": str(mm_to_uu(self.svg, width_mm))})
        if loop_key:
            el.set("data-loop", loop_key)
        el.set("data-along", along)
        parent.append(el)


def _len(pts):
    import math
    return sum(math.dist(a, b) for a, b in zip(pts, pts[1:]))


if __name__ == "__main__":
    MarkSharedEdges().run()
