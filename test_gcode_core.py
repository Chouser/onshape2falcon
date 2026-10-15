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
assert g.format_duration(3725) == "1h 02m 05s" and g.format_duration(59.6) == "1m 00s"
# generate() puts the estimate in the header: 3 passes x 200mm at F140 = 257s.
t, _ = g.generate(cfg, [("plywood-5mm", [], [sq(0, 0, 50)])])
assert t.splitlines()[1].startswith("; Estimated time: 4m 17s"), t.splitlines()[1]
print(t.splitlines()[1])
print("ok")
