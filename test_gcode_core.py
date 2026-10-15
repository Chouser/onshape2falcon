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
print("ok")
