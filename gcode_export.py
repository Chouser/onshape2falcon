#!/usr/bin/env python3

import os

import inkex

import gcode_core
import shared_edges
from laser_common import flatten, is_closed, mm_to_uu, nest_loops

DEBUG = True
DEFAULT_DIR = "~/proj/laser-cut"


def expand(path):
    """expanduser, with fallbacks for when Inkscape's environment has no HOME
    and no passwd entry: the passwd entry, then the home implied by where this
    extension is installed (~/.config/inkscape/extensions)."""
    path = os.path.expanduser(path)
    if not path.startswith("~"):
        return path
    rest = path[2:] if path[1:2] == os.sep else path[1:]
    homes = []
    try:
        import pwd
        homes.append(pwd.getpwuid(os.getuid()).pw_dir)
    except (ImportError, KeyError):
        pass
    here = os.path.abspath(__file__)
    if f"{os.sep}.config{os.sep}" in here:
        homes.append(here.split(f"{os.sep}.config{os.sep}")[0])
    if homes:
        return os.path.join(homes[0], rest)
    raise inkex.AbortExtension(f"Cannot find your home directory to expand {path!r}")


def debug(message):
    if DEBUG:
        inkex.utils.debug(f"GcodeExport: {message}")


class GcodeExport(inkex.EffectExtension):
    """Write gcode straight from the SVG.  Each path is cut with the settings
    of the nearest enclosing group whose label (or id) names a material in
    materials.json.  Per material, all holes are cut before any outlines.
    Only the selected objects are exported, or everything if none are.
    Stretches marked by Mark Shared Edges are cut once (see shared_edges.py)."""

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

    def shared_edge_skips(self, uu_per_mm):
        """Stretches drawn by Mark Shared Edges, as {"pathid:subpath": [pts]}."""
        skips = {}
        for g in self.svg.iterdescendants():
            if g.get("inkscape:label") != "skipped":
                continue
            parent = g.getparent()
            if parent is None or parent.get("inkscape:label") != "shared-edges":
                continue
            for e in g.iterdescendants():
                if isinstance(e, inkex.PathElement) and e.get("data-loop"):
                    path = e.path.to_absolute().transform(e.composed_transform()).to_absolute()
                    skips.setdefault(e.get("data-loop"), []).append(
                        flatten(path, uu_per_mm))
        return skips

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
                        and not any(isinstance(a, inkex.Defs) or a.get("inkscape:label") == "shared-edges"
                                    for a in e.ancestors())):
                    seen.add(id(e))
                    paths.append(e)
        if not paths:
            raise inkex.AbortExtension("No path objects to export.")

        uu_per_mm = mm_to_uu(self.svg, 1)
        skips = self.shared_edge_skips(uu_per_mm)
        skipped = 0
        jobs = {}
        unassigned = []
        for elem in paths:
            mat = self.material_of(elem, cfg["materials"])
            if mat is None:
                unassigned.append(elem.get_id())
                continue
            path = elem.path.to_absolute().transform(elem.composed_transform()).to_absolute()
            loops = list(path.break_apart())
            holes, outlines = jobs.setdefault(mat, ([], []))
            # Nesting treats every subpath as implicitly closed, so an outline
            # left open (e.g. where it abuts a neighbour) still has its holes.
            # Only the cutting differs: a subpath that isn't closed is cut as
            # drawn, and stretches marked by Mark Shared Edges are left out.
            _, depth = nest_loops(loops)
            for k, (l, d) in enumerate(zip(loops, depth)):
                pts = flatten(l, uu_per_mm)
                closed = is_closed(l, pts)
                pieces = shared_edges.apply_skips(
                    pts, closed, skips.get(f"{elem.get_id()}:{k}", []))
                if pieces is None:
                    pieces = [pts if closed else gcode_core.OpenPath(pts)]
                else:
                    pieces = [gcode_core.OpenPath(p) for p in pieces]
                    skipped += 1
                (holes if d % 2 else outlines).extend(pieces)
        if unassigned:
            raise inkex.AbortExtension(
                "Paths not inside a material group (known: "
                + ", ".join(cfg["materials"]) + "): " + ", ".join(unassigned[:10]))

        text, warnings = gcode_core.generate(
            cfg, [(m, h, o) for m, (h, o) in jobs.items()],
            self.svg.get_viewbox()[3] / uu_per_mm)
        for w in warnings:
            debug(w)
        out = expand(self.options.gcode_file or "")
        if not out:
            # input_file is a temp copy; use the document's own name and,
            # when Inkscape provides it (saved documents), its directory.
            name = self.svg.get("sodipodi:docname") or "export.svg"
            base = self.svg.get("sodipodi:docbase") or expand(DEFAULT_DIR)
            out = os.path.join(base, os.path.splitext(name)[0] + ".gcode")
        out = os.path.abspath(out)
        try:
            with open(out, "w", newline="\n") as f:
                f.write(text)
        except OSError as e:
            raise inkex.AbortExtension(f"Cannot write {out}: {e}")
        for m, (h, o) in jobs.items():
            debug(f"{m}: {len(h)} hole(s), {len(o)} outline(s)")
        if skipped:
            debug(f"{skipped} subpath(s) had shared edges left out")
        cut_s, travel_s = gcode_core.estimate_time(text, cfg["machine"])
        debug(f"estimated run time: {gcode_core.format_duration(cut_s + travel_s)} "
              f"(cutting {gcode_core.format_duration(cut_s)}, "
              f"travel {gcode_core.format_duration(travel_s)})")
        debug(f"wrote {out}")


if __name__ == "__main__":
    GcodeExport().run()
