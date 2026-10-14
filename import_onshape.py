
#!/usr/bin/env python3

import io
import math
import os
import re
import shutil
import subprocess
import tempfile
from collections import defaultdict

import inkex
from laser_common import mm_to_uu, split_loops
from inkex import paths
from lxml import etree


DEBUG = True

INKSCAPE_NS = "http://www.inkscape.org/namespaces/inkscape"
SVG_NS = "http://www.w3.org/2000/svg"

INKSCAPE = "inkscape"

# Endpoints closer than this are joined into one node.
ENDPOINT_TOLERANCE_MM = 0.001

def debug(message):
    if DEBUG:
        inkex.utils.debug(f"ImportOnshape: {message}")

class ImportOnshape(inkex.EffectExtension):

    def effect(self):
        root = self.svg
        shapes = self.flatten(root)
        debug(f"{len(shapes)} shapes after ungrouping")

        shapes = [s for s in shapes if not self.is_background(s)]
        debug(f"{len(shapes)} shapes after removing background")

        shapes = self.replace_crosshair_circles(shapes)
        debug(f"{len(shapes)} shapes after circle replacement")

        # Rebuild the document: only plain paths directly under the root.
        for child in list(root):
            if isinstance(child, inkex.Group):
                root.remove(child)
        for shape in shapes:
            if not shape.get("circle"):
                root.append(self.make_path(shape["path"]))

        # Simplify would distort the true circles, so they sit this step out.
        self.simplify()

        paths = [e.path.to_absolute() for e in root.descendants()
                 if isinstance(e, inkex.PathElement)]
        paths += [s["path"] for s in shapes if s.get("circle")]
        for e in list(root):
            if isinstance(e, inkex.PathElement):
                root.remove(e)

        tol = mm_to_uu(self.svg, ENDPOINT_TOLERANCE_MM)
        loops, open_pieces = self.join(paths, tol)
        debug(f"{len(loops)} closed loops, {len(open_pieces)} unjoined open pieces")
        parts = split_loops(loops)
        debug(f"{len(parts)} separate parts")
        for path in parts + open_pieces:
            root.append(self.make_path(path))

    # ---- helpers -------------------------------------------------------

    def make_path(self, path):
        elem = inkex.PathElement()
        elem.path = path
        elem.style = inkex.Style({
            "fill": "#add8e6",
            "fill-opacity": "0.5",
            "fill-rule": "evenodd",
            "stroke": "#000000",
            "stroke-opacity": "0.5",
            "stroke-width": f"{mm_to_uu(self.svg, 0.1):.6g}",
        })
        return elem

    def flatten(self, node):
        """Return every shape under node with its transformed path and parent."""
        out = []
        for elem in node.iterdescendants():
            if isinstance(elem, (inkex.Group, inkex.Defs, inkex.NamedView)):
                continue
            if not isinstance(elem, inkex.ShapeElement):
                continue
            try:
                path = elem.path.transform(elem.composed_transform())
            except Exception:
                continue
            out.append({"elem": elem, "path": path.to_absolute(),
                        "parent": elem.getparent()})
        return out

    def is_background(self, shape):
        """Background = a rect covering (nearly) the whole page."""
        if not isinstance(shape["elem"], inkex.Rectangle):
            return False
        bb = shape["path"].bounding_box()
        vb = self.svg.get_viewbox()
        return bb.width >= 0.95 * vb[2] and bb.height >= 0.95 * vb[3]

    def replace_crosshair_circles(self, shapes):
        """All crosshairs live together in one group made only of 2-point
        lines, each "+" being two lines sharing a midpoint.  Replace the
        circle centred on each with a true circle, and drop the crosshairs."""
        by_parent = defaultdict(list)
        for s in shapes:
            by_parent[s["parent"]].append(s)

        drop = set()
        replacements = {}
        for group in by_parent.values():
            pts = [list(s["path"].end_points) for s in group]
            if len(group) % 2 or any(len(p) != 2 for p in pts):
                continue
            # Every line must pair up with a partner sharing its midpoint.
            mids = [((p[0].x + p[1].x) / 2, (p[0].y + p[1].y) / 2) for p in pts]
            unpaired = list(range(len(group)))
            centers = []
            while unpaired:
                i = unpaired.pop(0)
                j = next((j for j in unpaired if math.hypot(
                    mids[i][0] - mids[j][0], mids[i][1] - mids[j][1]) <= 0.1), None)
                if j is None:
                    break
                unpaired.remove(j)
                centers.append(mids[i])
            if unpaired:
                continue
            drop.update(id(s) for s in group)
            for cx, cy in centers:
                circle = self.find_circle(shapes, cx, cy)
                if circle is None:
                    debug(f"crosshair at {cx:.2f},{cy:.2f} has no matching circle")
                    continue
                replacements[id(circle["shape"])] = self.circle_path(cx, cy, circle["r"])
                debug(f"circle at {cx:.2f},{cy:.2f} r={circle['r']:.3f}")

        out = []
        for s in shapes:
            if id(s) in drop:
                continue
            if id(s) in replacements:
                s = dict(s, path=replacements[id(s)], circle=True)
            out.append(s)
        return out

    def find_circle(self, shapes, cx, cy):
        for s in shapes:
            pts = list(s["path"].end_points)
            if len(pts) < 8:
                continue
            xs = [p.x for p in pts]
            ys = [p.y for p in pts]
            if math.hypot((min(xs) + max(xs)) / 2 - cx, (min(ys) + max(ys)) / 2 - cy) > 0.5:
                continue
            radii = [math.hypot(p.x - cx, p.y - cy) for p in pts]
            r = sum(radii) / len(radii)
            if r > 0 and (max(radii) - min(radii)) / r < 0.01:
                return {"shape": s, "r": r}
        return None

    @staticmethod
    def circle_path(cx, cy, r):
        k = 0.5522847498 * r
        return inkex.Path(
            f"M {cx + r},{cy} "
            f"C {cx + r},{cy + k} {cx + k},{cy + r} {cx},{cy + r} "
            f"C {cx - k},{cy + r} {cx - r},{cy + k} {cx - r},{cy} "
            f"C {cx - r},{cy - k} {cx - k},{cy - r} {cx},{cy - r} "
            f"C {cx + k},{cy - r} {cx + r},{cy - k} {cx + r},{cy} Z")

    def simplify(self):
        """Run Inkscape's Path > Simplify on every path, in a child process."""
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "in.svg")
            dst = os.path.join(tmp, "out.svg")
            etree.ElementTree(self.document.getroot()).write(src)
            actions = ";".join([
                "select-all:all", "path-simplify",
                f"export-filename:{dst}", "export-plain-svg", "export-do",
            ])
            result = subprocess.run([INKSCAPE, f"--actions={actions}", src],
                                    capture_output=True, text=True, timeout=300)
            if result.returncode != 0 or not os.path.exists(dst):
                raise inkex.AbortExtension(f"simplify failed: {result.stderr}")
            simplified = inkex.load_svg(dst).getroot()
        old = [e for e in self.svg if isinstance(e, inkex.PathElement)]
        new = [e for e in simplified.iterdescendants() if isinstance(e, inkex.PathElement)]
        debug(f"simplify: {len(old)} paths in, {len(new)} out")
        for e in old:
            self.svg.remove(e)
        for e in new:
            self.svg.append(self.make_path(e.path.transform(e.composed_transform()).to_absolute()))

    @staticmethod
    def _close(a, b, tol):
        return math.hypot(a.x - b.x, a.y - b.y) <= tol

    def join(self, paths, tol):
        """Chain subpaths whose endpoints coincide into closed loops."""
        pieces = []
        for p in paths:
            for sub in p.break_apart():
                pts = list(sub.end_points)
                if len(pts) < 2:
                    continue
                closed = any(isinstance(c, inkex.paths.ZoneClose) for c in sub) \
                    or self._close(pts[0], pts[-1], tol)
                pieces.append((sub, closed))

        loops = []
        todo = []
        for sub, closed in pieces:
            (loops if closed else todo).append(sub)
        open_pieces = []
        while todo:
            cur = inkex.Path(list(todo.pop(0)))
            while True:
                start = list(cur.end_points)[0]
                end = list(cur.end_points)[-1]
                if self._close(start, end, tol):
                    cur.close()
                    loops.append(cur)
                    break
                match = None
                for i, other in enumerate(todo):
                    pts = list(other.end_points)
                    if self._close(end, pts[0], tol):
                        match = (i, False)
                        break
                    if self._close(end, pts[-1], tol):
                        match = (i, True)
                        break
                if match is None:
                    open_pieces.append(cur)
                    break
                other = todo.pop(match[0])
                if match[1]:
                    other = other.reverse()
                cur = inkex.Path(list(cur) + list(other)[1:])
        return loops, open_pieces

if __name__ == "__main__":
    ImportOnshape().run()

