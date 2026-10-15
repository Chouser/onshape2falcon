import json, gcode_core as g

cfg = json.load(open("materials.json"))
cfg["machine"]["flip_y"] = False
sq = lambda x, y, s: [(x, y), (x + s, y), (x + s, y + s), (x, y + s)]
text, warn = g.generate(cfg, [("plywood-5mm", [sq(10, 10, 5)], [sq(0, 0, 50)])])
print(text, warn)
assert text.index("holes") < text.index("outlines")
assert text.startswith("; Bounds: X0.00 Y0.00 to X50.00 Y50.00\n") and not warn
_, warn = g.generate(cfg, [("paper", [], [sq(390, 0, 20)])])
assert warn and "OUT OF BOUNDS" in warn[0]
cfg["machine"]["flip_y"] = True
t, _ = g.generate(cfg, [("paper", [], [sq(0, 0, 50)])], 100)
assert "G0 X0.00 Y100.00" in t and "M3 S700.00" in t, t
cfg["machine"]["flip_y"] = False
t, _ = g.generate(cfg, [("paper", [], [[(0, 0), (0.001, 0), (10, 0), (10, 10), (0, 0.002)]])])
assert [l for l in t.splitlines() if l.startswith("G1 X")] == \
    ["G1 X10.00 Y0.00 F1500", "G1 X10.00 Y10.00", "G1 X0.00 Y0.00"], t
t, _ = g.generate(cfg, [("paper", [], [g.OpenPath([(0, 0), (10, 0), (10, 10)])])])
assert [l for l in t.splitlines() if l.startswith("G1 X")] == \
    ["G1 X10.00 Y0.00 F1500", "G1 X10.00 Y10.00"], t   # no closing move
# Time estimate: 100mm cut at F600 = 10s, plus 50mm rapid at 3000 = 1s.
cut, trav = g.estimate_time("G0 X0 Y0\nG1 X100 Y0 F600 ; cut\nG0 X50 Y0\nM5\n", {"travel_mm_min": 3000})
assert abs(cut - 10) < 1e-9 and abs(trav - (50 / 3000 * 60)) < 1e-9, (cut, trav)
# F is modal; Y-only moves count; a bare "G1S0" has no motion.
cut, _ = g.estimate_time("G1 X60 F1200\nG1 Y60\nG1S0\n", {})
assert abs(cut - 6) < 1e-9, cut
# A G0 with its own F is a laser-off lead move at that speed (100mm at F1200 = 5s).
cut, trav = g.estimate_time("G0 X0 Y0\nG0 X100 Y0 F1200\nG1 X100 Y60\n", {"travel_mm_min": 3000})
assert abs(trav - 5) < 1e-9 and abs(cut - 60 / 1200 * 60) < 1e-9, (cut, trav)
assert [(k, b) for k, a, b, sp in g.parse_moves("G0 X5 Y5\nG0 X9 Y5 F100\nG1 Y9 F200\nM5\n")] == \
    [("travel", (5, 5)), ("lead", (9, 5)), ("cut", (9, 9))]
assert g.format_duration(3725) == "1h 02m 05s" and g.format_duration(59.6) == "1m 00s"
# generate() puts the estimate in the header: 3 passes x 200mm at F140 = 257s.
t, _ = g.generate(cfg, [("plywood-5mm", [], [sq(0, 0, 50)])])
assert t.splitlines()[1].startswith("; Estimated time: 4m 17s"), t.splitlines()[1]
print(t.splitlines()[1])

# --- Fill materials.
import copy
fcfg = copy.deepcopy(cfg)
fcfg["machine"]["flip_y"] = False
fcfg["materials"]["engrave"] = {"power_pct": 20, "feed_mm_min": 3000, "passes": 1, "fill": {
    "line_spacing_mm": 1, "lead_in_mm": 3, "lead_out_mm": 2, "perimeter_pass": True,
    "perimeter_power_pct": 50, "perimeter_feed_mm_min": 600}}
sq2 = lambda x, y, w: [(x, y), (x + w, y), (x + w, y + w), (x, y + w)]
t, warn = g.generate(fcfg, [("engrave", [], [], [[sq2(20, 20, 10)]])])
L = t.splitlines()
assert not warn, warn
# First line: hop to the lead-in start, laser on, lead-in at feed, cut, lead-out.
i = L.index("G0 X17.00 Y20.50")
assert L[i + 1:i + 3] == ["M3", "M3 S200.00"], L[i:i + 4]
assert L[i + 3:i + 6] == ["G0 X20.00 Y20.50 F3000", "G1 X30.00 Y20.50 F3000", "G0 X32.00 Y20.50 F3000"], L[i:i + 8]
# Serpentine: the next line starts at the far end, 1mm up, 2mm of lead-in beyond it.
assert L[i + 6] == "G0 X33.00 Y21.50" and L[i + 9] == "G0 X30.00 Y21.50 F3000", L[i + 6:i + 12]
assert L[i + 10] == "G1 X20.00 Y21.50 F3000"
# Ten hatch lines, then a perimeter pass at its own power and feed.
assert sum(1 for l in L if l.startswith("G1 X") and l.endswith("F3000")) == 10
assert L.index("; engrave fill perimeter: 1") > L.index("G1 X20.00 Y29.50 F3000")
assert "M3 S500.00" in L and "G1 X30.00 Y20.00 F600" in L, "perimeter settings"
assert "; Bounds: X17.00 Y20.00 to X33.00 Y30.00" == L[0], L[0]
# Time: 10 x 10mm cutting at F3000 is 2s, plus the perimeter 40mm at F600 = 4s.
assert "(cutting 6s," in L[1], L[1]
# No lead moves when the leads are 0; no perimeter unless asked; passes repeat the hatch.
f2 = copy.deepcopy(fcfg)
f2["materials"]["engrave"]["fill"].update(lead_in_mm=0, lead_out_mm=0, perimeter_pass=False)
f2["materials"]["engrave"]["passes"] = 2
t, _ = g.generate(f2, [("engrave", [], [], [[sq2(20, 20, 10)]])])
assert " F3000" in t and "perimeter" not in t
assert not any(l.startswith("G0") and l.endswith("F3000") for l in t.splitlines())
assert sum(1 for l in t.splitlines() if l.startswith("G1 X")) == 20
# A hole in the shape is skipped by the hatch and traced by the perimeter pass.
t, _ = g.generate(fcfg, [("engrave", [], [], [[sq2(20, 20, 10), sq2(23, 23, 4)]])])
assert "; engrave fill perimeter: 2" in t
assert sum(1 for l in t.splitlines() if l.startswith("G1 X") and l.endswith("F3000")) == 14
# Leads that reach past the bed are reported.
_, warn = g.generate(fcfg, [("engrave", [], [], [[sq2(1, 20, 10)]])])
assert warn and "OUT OF BOUNDS" in warn[0]
# Fill shapes can share a job with cuts; fills need a material that has fill settings.
t, _ = g.generate(fcfg, [("engrave", [], [sq2(0, 0, 5)], [[sq2(20, 20, 10)]])])
assert "; engrave outlines: 1" in t and "; engrave fill:" in t
try:
    g.generate(fcfg, [("paper", [], [], [[sq2(20, 20, 10)]])])
    raise SystemExit("fill on a non-fill material should fail")
except ValueError:
    pass
# Bad fill settings are rejected when the config loads.
import tempfile, os
for bad in ({}, {"line_spacing_mm": 0}, {"line_spacing_mm": 1, "lead_in_mm": -1},
            {"line_spacing_mm": 1, "perimeter": True}, {"line_spacing_mm": "1"}):
    c = copy.deepcopy(cfg)
    c["materials"]["paper"]["fill"] = bad
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "m.json")
        json.dump(c, open(path, "w"))
        try:
            g.load_config(path)
            raise SystemExit(f"should reject fill {bad}")
        except ValueError as e:
            assert "paper" in str(e)
print("ok")
