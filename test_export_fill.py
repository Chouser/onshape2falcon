"""Run Export Gcode on a small SVG with a fill material, using inkex directly
(no Inkscape needed).  Skips if inkex or numpy can't be imported."""
import os, subprocess, sys, tempfile

try:
    import inkex  # noqa: F401
except ImportError as e:
    print(f"SKIP: cannot import inkex ({e})")
    sys.exit(0)

here = os.path.dirname(os.path.abspath(__file__))
SVG = """<svg xmlns="http://www.w3.org/2000/svg" xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape"
     width="400mm" height="400mm" viewBox="0 0 400 400">
  <g inkscape:label="engrave-plywood">
    <path d="M 100 100 H 120 V 120 H 100 Z M 105 105 H 115 V 115 H 105 Z" style="fill:#000"/>
  </g>
  <g inkscape:label="paper">
    <path d="M 200 100 H 220 V 120 H 200 Z" style="fill:none;stroke:#000"/>
  </g>
</svg>"""

def run_export(src, out, *extra):
    r = subprocess.run([sys.executable, os.path.join(here, "gcode_export.py"),
                        f"--gcode_file={out}", *extra, src], capture_output=True, text=True,
                       env={**os.environ, "PYTHONPATH": here + os.pathsep + os.environ.get("PYTHONPATH", "")})
    assert r.returncode == 0 and os.path.exists(out), r.stderr
    with open(out) as f:
        return f.read(), r.stdout, r.stderr


def preview_layers(svg_text):
    svg = inkex.load_svg(svg_text.encode()).getroot()
    return svg, [g for g in svg.iterdescendants() if g.get("inkscape:label") == "gcode-preview"]


with tempfile.TemporaryDirectory() as d:
    src = os.path.join(d, "in.svg")
    out = os.path.join(d, "out.gcode")
    with open(src, "w") as f:
        f.write(SVG)
    gcode, svg_out, err = run_export(src, out)

L = gcode.splitlines()
# The ring (20mm square, 10mm hole) is filled at 0.1mm: 200 lines, of which the
# 100 through the hole are in two pieces, and the paper square is cut once.
assert "engrave-plywood: 1 filled shape(s)" in err, err
assert "; engrave-plywood fill: 300 line(s), spacing 0.1mm, angle 0" in gcode
# Page is 400mm so flip_y puts the square at Y=280..300 in machine coordinates.
assert "; Bounds: X97.00 Y280.00 to X220.00 Y300.00" == L[0], L[0]
assert "G0 X97.00 Y280.05" in L and "G0 X100.00 Y280.05 F3000" in L
assert "; engrave-plywood fill perimeter: 2" in gcode          # outer square and the hole
assert "; paper outlines: 1" in gcode and "; engrave-plywood outlines" not in gcode

# The preview layer: locked, one path per kind of move, in SVG space (not flipped).
svg, layers = preview_layers(svg_out)
assert len(layers) == 1 and layers[0].get("sodipodi:insensitive") == "true", layers
kinds = {p.get("inkscape:label"): p for p in layers[0]}
assert set(kinds) == {"travel", "lead", "cut"}, kinds.keys()
assert kinds["cut"].get("d").startswith("M 100.000 119.950 L 120.000 119.950"), kinds["cut"].get("d")[:60]
assert "stroke-dasharray" in kinds["travel"].get("style")

# Running again on the result replaces the layer rather than stacking another,
# and its paths are not mistaken for unassigned geometry.
with tempfile.TemporaryDirectory() as d:
    again = os.path.join(d, "again.svg")
    with open(again, "w") as f:
        f.write(svg_out)
    gcode2, svg_out2, _ = run_export(again, os.path.join(d, "out2.gcode"))
    assert gcode2 == gcode
    # (inkex writes nothing when the document comes out identical, as here.)
    assert len(preview_layers(svg_out2 or svg_out)[1]) == 1
    # Preview off: the old layer is removed and none is added.
    _, svg_out3, _ = run_export(again, os.path.join(d, "out3.gcode"), "--preview=false")
    assert preview_layers(svg_out3)[1] == []

# The other extensions' "all paths" fallback skips the layer.
sys.path.insert(0, here)
from laser_common import in_preview
paths = [e for e in svg.iterdescendants() if isinstance(e, inkex.PathElement)]
assert [in_preview(e) for e in paths].count(True) == 3 and len(paths) == 5, len(paths)
print("ok")
