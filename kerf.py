#!/usr/bin/env python3

import os
import subprocess
import tempfile

import inkex
from lxml import etree

from laser_common import mm_to_uu, split_loops

DEBUG = True

INKSCAPE = "inkscape"
SVG_NS = "http://www.w3.org/2000/svg"
NAMEDVIEW_NS = "http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd"


def debug(message):
    if DEBUG:
        inkex.utils.debug(f"Kerf: {message}")


class Kerf(inkex.EffectExtension):

    def add_arguments(self, pars):
        pars.add_argument("--preset", default="0.09")
        pars.add_argument("--custom_mm", type=float, default=0.09)

    @property
    def outset_mm(self):
        if self.options.preset == "custom":
            return self.options.custom_mm
        return float(self.options.preset)

    def effect(self):
        selected = []
        for e in self.svg.selection.values():
            # A selected group stands for every path inside it.
            for p in ([e] if isinstance(e, inkex.PathElement) else e.iterdescendants()):
                if isinstance(p, inkex.PathElement) and p not in selected:
                    selected.append(p)
        if not selected:
            # Nothing selected (or run from the command line): kerf everything.
            selected = [e for e in self.svg.iterdescendants()
                        if isinstance(e, inkex.PathElement)
                        and not isinstance(e.getparent(), inkex.Defs)]
        if not selected:
            raise inkex.AbortExtension("No path objects to apply kerf to.")
        debug(f"{len(selected)} selected paths")

        # Paths stay in the group they came from: kerf each parent's paths
        # together, so a group named for a material keeps its parts.
        by_parent = {}
        for elem in selected:
            by_parent.setdefault(elem.getparent(), []).append(elem)
        for parent, elems in by_parent.items():
            debug(f"{len(elems)} path(s) in {parent.get('inkscape:label') or parent.get_id()}")
            self.kerf_paths(parent, elems)

    def kerf_paths(self, parent, selected):
        # Path > Combine: one path holding every selected subpath.  Paths
        # share a parent, so only their own transforms need baking in.
        combined = inkex.Path()
        for elem in selected:
            combined += elem.path.transform(elem.transform).to_absolute()
        first = selected[0]
        index = list(parent).index(first)
        style = first.style
        for elem in selected:
            parent.remove(elem)

        target = inkex.PathElement()
        target.set("id", "kerf-target")
        target.path = combined
        target.style = style
        target.style["fill-rule"] = "evenodd"
        parent.insert(index, target)
        original_bbox = combined.bounding_box()

        offset_path = self.apply_offset(target)

        # Path > Split Path: independent parts, each keeping its holes.
        loops = [sub for sub in offset_path.break_apart()]
        parts = split_loops(loops)
        debug(f"{len(loops)} loops -> {len(parts)} parts")

        grown = offset_path.bounding_box()
        debug(f"bbox width {original_bbox.width:.4f} -> {grown.width:.4f} "
              f"(wanted +{2 * mm_to_uu(self.svg, self.outset_mm):.4f})")
        if abs(grown.width - original_bbox.width) < 1e-9 and \
           abs(grown.height - original_bbox.height) < 1e-9:
            raise inkex.AbortExtension("The offset did not change the shape; "
                                       "did stroke-to-path and union run?")

        pos = list(parent).index(target)
        parent.remove(target)
        for i, part in enumerate(parts):
            elem = inkex.PathElement()
            elem.path = part
            elem.style = style
            elem.style["fill-rule"] = "evenodd"
            parent.insert(pos + i, elem)

    def apply_offset(self, target):
        """Outset by stroking a copy at twice the kerf with round joins,
        converting that stroke to a path, and uniting it with the original.
        (This Inkscape has no outset action, and headless it won't evaluate
        the Offset path effect.)"""
        width = 2 * mm_to_uu(self.svg, self.outset_mm)
        fill = inkex.PathElement()
        fill.set("id", "kerf-fill")
        fill.path = target.path
        fill.style = {"fill": "#000000", "fill-rule": "evenodd", "stroke": "none"}
        ring = inkex.PathElement()
        ring.set("id", "kerf-ring")
        ring.path = target.path
        ring.style = {"fill": "none", "stroke": "#000000", "stroke-width": f"{width:.9g}",
                      "stroke-linejoin": "round", "stroke-linecap": "round"}

        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "in.svg")
            dst = os.path.join(tmp, "out.svg")
            # Work on a copy of the document containing only the two helper paths.
            root = etree.fromstring(etree.tostring(self.document.getroot()))
            for child in list(root):
                if child.tag not in (f"{{{SVG_NS}}}defs", f"{{{NAMEDVIEW_NS}}}namedview"):
                    root.remove(child)
            root.append(etree.fromstring(etree.tostring(fill)))
            root.append(etree.fromstring(etree.tostring(ring)))
            etree.ElementTree(root).write(src)
            actions = ";".join([
                "select-by-id:kerf-ring", "object-stroke-to-path",
                "select-by-id:kerf-fill,kerf-ring", "path-union",
                f"export-filename:{dst}", "export-plain-svg", "export-do",
            ])
            result = subprocess.run([INKSCAPE, f"--actions={actions}", src],
                                    capture_output=True, text=True, timeout=300)
            if result.stderr.strip():
                debug(f"child stderr: {result.stderr.strip()[:1500]}")
            if result.returncode != 0 or not os.path.exists(dst):
                raise inkex.AbortExtension(f"offset failed: {result.stderr}")
            out = inkex.load_svg(dst).getroot()
        found = [e for e in out.iterdescendants() if isinstance(e, inkex.PathElement)]
        debug(f"{len(found)} path(s) after union")
        if len(found) != 1:
            raise inkex.AbortExtension("offset result not found")
        return found[0].path.transform(found[0].composed_transform()).to_absolute()


if __name__ == "__main__":
    Kerf().run()
