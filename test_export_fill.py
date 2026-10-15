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

with tempfile.TemporaryDirectory() as d:
    src = os.path.join(d, "in.svg")
    out = os.path.join(d, "out.gcode")
    with open(src, "w") as f:
        f.write(SVG)
    r = subprocess.run([sys.executable, os.path.join(here, "gcode_export.py"),
                        f"--gcode_file={out}", src], capture_output=True, text=True,
                       env={**os.environ, "PYTHONPATH": here + os.pathsep + os.environ.get("PYTHONPATH", "")})
    assert r.returncode == 0 and os.path.exists(out), r.stderr
    with open(out) as f:
        gcode = f.read()
    err = r.stderr

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
print("ok")
