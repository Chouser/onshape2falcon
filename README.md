# onshape2falcon

Inkscape 1.4 extensions that take a project from an Onshape SVG export to gcode
for a Creality CR Falcon laser cutter. They appear under Extensions >
onshape2falcon.

To install:  `./install.sh`

## Workflow

1. **Import Onshape SVG** (`import_onshape.py`).

   Takes an Onshape-exported SVG and turns it into proper path objects:

   - Ungroups everything (baking in transforms)
   - Deletes the page-sized background rect
   - Replaces circles that have crosshairs with true circles and drops the crosshairs
   - Converts to paths with style that lets you distinguish shape from hole and shows overlaps.
   - Runs Inkscape's Simplify and joins coincident endpoints into closed
   loops
   - Splits the result into independent parts with their holes.
   - Resizes the page to the machine bed (`bed_x_mm` x `bed_y_mm` in `materials.json`)

   Now you can group shapes by material so you can apply kerfs.

2. **Kerf** (`kerf.py`).

   Outsets the selected paths (or all paths if nothing is selected) by the
   chosen kerf with rounded joins.

   Now you're all set to duplicate, position, rotate, etc. to form groups that will fit on your cutting material and bed. Also label each group with the material id from `materials.json` (e.g. `plywood-5mm`)

3. **Mark Shared Edges** (`mark_shared_edges.py`), optional

   Where kerfed neighbours touch, both parts would cut the same line twice.
   This finds edges of a later shape that run alongside an earlier shape's
   (within the tolerance, default 0.1 mm, and roughly parallel) and draws them
   in a `shared-edges` group: red `skipped` stretches won't be cut, green `kept`
   stretches are the neighbour's edge that cuts it instead. Shapes stay
   closed, so hole detection is unaffected. Check that the red and green
   look right before exporting. Run it after arranging parts; the marks don't
   follow moved shapes, and re-running replaces them. The earlier shape in
   document order keeps the shared edge.

4. **Export Gcode** (`gcode_export.py`)

   Generates a Creality Falcon gcode file for the selected paths (or all paths if none selected), based on the nearest enclosing group with a material id as its name. If this doesn't work for your laser cutter, see "Separate Holes and Outlines below".

   The gcode header includes a `; Estimated time:` line, and the extension
reports the same estimate when it runs. It sums each move's length over its
feed rate (rapids use `travel_mm_min` in the `machine` section of
`materials.json`) and ignores acceleration, so real runs will be a bit longer.

   The generated gcode is arranged to cut all holes first, then outlines,
   each nearest-neighbor ordered.

   Paths are closed only if they end in `z` or already end where they
   started. Open paths are cut as drawn, with no closing move, but still count as
   enclosing shapes, so an open outline's holes are still cut first.
   Stretches marked by Mark Shared Edges are left out; the rest of such a
   shape is cut as one open path.

    **Fill (engraving).** A material whose entry in `materials.json` has a
`fill` section is engraved instead of cut: the inside of each path (holes left
out) is hatched with parallel lines, going back and forth. For example:

    ```
    "engrave-plywood": {"power_pct": 30, "feed_mm_min": 3000, "passes": 1,
      "fill": {"line_spacing_mm": 0.1, "angle_deg": 0,
               "lead_in_mm": 3, "lead_out_mm": 3, "perimeter_pass": true}}
    ```

    - `line_spacing_mm` (required): distance between lines; smaller is denser.
    - `angle_deg`: direction of the lines, counter-clockwise from the X axis as
      you see it on the bed (default 0).
    - `lead_in_mm` / `lead_out_mm`: each line is extended this far beyond the
      shape at both ends, travelled with the laser off at the cutting feed rate, so
      the head is at full speed when it enters and leaves the shape (default 0).
      The extra travel counts toward the bounds check.
    - `perimeter_pass`: after hatching a shape, trace its outline and holes once.
      `perimeter_power_pct` and `perimeter_feed_mm_min` override the material's
      power and feed for that pass.
    - `passes` repeats the hatching, not the perimeter pass.

    Name a group after the material and put the shapes in it, as for cutting.
Shared edges are not applied to filled shapes. The lead moves use the
`lead` template in the `machine` section (`G0` with its own `F` by default),
which assumes your firmware keeps the laser off for `G0`, as the rapids between
cuts already do. Check this at low power before trusting it.

    **Preview.** After writing the gcode, Export Gcode draws it into a locked
`gcode-preview` layer so you can check it before cutting: red where the laser
fires, orange for the laser-off lead-in/out moves, dashed blue for travel. It is
read back from the gcode text, so it shows exactly what will run. The next
export replaces the layer (untick "Draw the gcode in a gcode-preview layer" to
remove it without drawing a new one), and the other extensions ignore it.
Delete the layer before sending the SVG anywhere you don't want it.

5. **Separate Holes and Outlines** (`holes_outlines.py`)

   Produces an `outlines` group and a `holes` group; each contains one `part-N`
   subgroup per original path, with matching labels so holes pair with their
   outline. The resulting SVG is useful as inputs to tools like LaserWeb in order to cut holes first.

`laser_common.py` holds shared helpers for the plugins.

## Using this yourself

This was written for my own setup. Things you will probably want to
change:

- `laser-sd-sync.nix` (a NixOS module that copies the newest `*.gcode` to the
  laser's SD card as `go.gcode` when the card is inserted) hardcodes the user
  `chouser` (in the `sudo -u` calls), uid 1000 (the mount options and the
  `/run/user/1000` paths) and `gcodeDir = "/home/chouser/proj/laser-cut"`. It
  also expects the card's filesystem label to be `lasercut`.
- `gcode_export.py` falls back to writing gcode in `~/proj/laser-cut`
  (`DEFAULT_DIR`) when the file field is blank and Inkscape doesn't say where
  the SVG is. Keep it in step with `gcodeDir` above.
- `materials.json`: the material names, power, feed and passes are tuned to
  my CR Falcon and the materials I like to use, so you'll likely need to change those as well, then run `./install` again.

## Testing

There is no unit-test setup; run the tests from the repo root. They run the extensions in real Inkscape on
the sample files and need to be checked by eye as well.

    ./tests/test_import_onshape.sh   # tests/data/sample-input01.svg  -> test-out/sample-output01.svg
    ./tests/test_kerf.sh             # test-out/sample-output01.svg -> test-out/sample-kerf01.svg
    ./tests/test_holes_outlines.sh   # test-out/sample-kerf01.svg   -> test-out/sample-holes01.svg
    ./tests/test_shared_edges.sh     # synthetic test-out/sample-shared01.svg -> test-out/sample-shared-out01.svg, then Export Gcode (also runs test_shared_edges.py)
    ./tests/test_gcode_export.sh     # test-out/sample-kerf01.svg   -> test-out/sample-material01.gcode (also runs test_gcode_core.py, plain python)

Each test copies `extension/*` into `test-profile/extensions/`, so no
install is needed. The tests chain: run them in that order.

Set `AGENT=false` to run Inkscape directly. Otherwise (the default) the tests
call `./cmd-client NAME cmd-dir/`, which asks a server running on the host
(outside the contagent sandbox, where `inkscape` is not installed and `inkex`
can't be imported because numpy is missing) to run a fixed command. The server
script isn't in this repo; its `COMMANDS` table needs these entries:

    [inkscape]='INKSCAPE_PROFILE_DIR=test-profile/ inkscape --actions="us.chouser.laser.import-onshape" "tests/data/sample-input01.svg" --export-filename="test-out/sample-output01.svg"'
    [kerf]='INKSCAPE_PROFILE_DIR=test-profile/ inkscape --actions="select-all:all;us.chouser.laser.kerf" "test-out/sample-output01.svg" --export-filename="test-out/sample-kerf01.svg"'
    [holes]='INKSCAPE_PROFILE_DIR=test-profile/ inkscape --actions="select-all:all;us.chouser.laser.holes-outlines" "test-out/sample-kerf01.svg" --export-filename="test-out/sample-holes01.svg"'
    [shared]='INKSCAPE_PROFILE_DIR=test-profile/ inkscape --actions="us.chouser.laser.mark-shared-edges" "test-out/sample-shared01.svg" --export-filename="test-out/sample-shared-out01.svg"'
    [gcode]='INKSCAPE_PROFILE_DIR=test-profile/ inkscape --actions="us.chouser.laser.gcode-export" "test-out/sample-material01.svg" --export-filename="test-out/sample-material-out01.svg"'

All use `INKSCAPE_PROFILE_DIR=test-profile/`. If the server isn't running,
`cmd-client` blocks forever writing to the request FIFO; use `timeout`.

## Tips for working on this

- `exts/` is a read-only copy of Inkscape's stock extensions (including
  `inkex`), for reference. Use it to look up the `inkex` API.
- Extension debug output goes to stderr, which Inkscape reports under a
  "Script Error" header. That header does not mean the run failed; look at the
  messages beneath it. `test_kerf.sh` and `test_holes_outlines.sh` detect
  failure by grepping for specific error messages.
- Selection does not reach an extension run from the command line, even after
  `select-all`. `kerf.py` and `holes_outlines.py` therefore fall back to all
  paths when nothing is selected.
- `svg.unittouu` ignores the viewBox scale when the document has no namedview
  units, which gave a 0.032 mm stroke instead of 0.1 mm. Use
  `laser_common.mm_to_uu`. The Onshape samples are 889mm wide with a viewBox
  of 10500 units, so one user unit is about 0.085 mm.
- This Inkscape's CLI has no `path-outset` action, and headless
  `object-to-path` does not evaluate the Offset path effect. Kerf instead
  strokes a copy at twice the kerf with round joins, runs
  `object-stroke-to-path`, and unions it with the original via `path-union`.
  `inkscape --action-list` shows what is available.
- Inkscape's Simplify distorts the replacement circles, so they skip it and
  are re-added afterward.
- Inkscape writes arcs (`A r r 0 0 0 x y`) in path output, so naive regex
  scraping of coordinates from `d` attributes gives wrong bounding boxes.
- Measured kerf growth runs about 2% below the requested amount (about
  0.002 mm at 0.09 mm). Not investigated.
