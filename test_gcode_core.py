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
print("ok")
