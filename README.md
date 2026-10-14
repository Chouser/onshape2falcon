# Chouser-Laser Inkscape extensions

Inkscape 1.4 extensions for preparing Onshape SVG exports for laser cutting
(gcode is produced afterward in LaserWeb). They appear under
Extensions > Chouser-Laser.

Install by:

    ./install.sh

## Workflow

1. **Import Onshape SVG** (`import_onshape.py`). Ungroups everything (baking in
   transforms), deletes the page-sized background rect, replaces circles that
   have crosshairs with true circles and drops the crosshairs, converts to
   paths with the diagnostic style (light blue 50% fill, 0.1mm black 50%
   stroke), runs Inkscape's Simplify, joins coincident endpoints into closed
   loops (`ENDPOINT_TOLERANCE_MM`, 0.001), and splits the result into
   independent parts with their holes. Finally it resizes the page to the
   machine bed (`bed_x_mm` x `bed_y_mm` in `materials.json`, 400 x 400)
   without rescaling the geometry, so parts outside the bed hang off the
   page.
2. **Kerf** (`kerf.py`). Outsets the selected paths (or all paths if nothing is
   selected) by the chosen kerf with rounded joins, then splits into parts.
   Dropdown presets: 0.09 mm, 0.04 mm, or a custom value.
3. Move/duplicate parts by hand to use the material efficiently.
4. **Separate Holes and Outlines** (`holes_outlines.py`). Produces an
   `outlines` group then a `holes` group; each contains one `part-N` subgroup
   per original path, with matching labels so holes pair with their outline.
   Run this last: LaserWeb reorders paths within a group, so cut order is
   controlled by selecting the hole groups and outline groups separately.

5. **Export Gcode** (`gcode_export.py`), an alternative to step 4 and
   LaserWeb. Put parts into groups whose Inkscape label (or id) is a material
   name from `materials.json` (power %, feed mm/min, passes, plus a `machine`
   section with bed size, gcode templates and `flip_y`). Each path uses the
   nearest enclosing material group; paths in none abort with a list. Per
   material it cuts all holes, then outlines, each nearest-neighbour ordered,
   and writes `; Bounds:` (as `export-gcode.bb` did) with LF line endings.
   Out-of-bounds is reported as a warning. Output goes to the file chosen in the dialog's file picker; if blank, next to the saved
   SVG (`sodipodi:docbase`), else `~/proj/laser-cut/`. The full path is logged.
   `install.sh` copies
   `materials.json` too, saving any differing installed copy as `.bak`. The `machine` templates reproduce LaserWeb's marlin output for
   the CR Falcon (see `p-card-box11-thin.gcode`); `flip_y` measures Y up from
   the page bottom like LaserWeb.

`laser_common.py` holds shared helpers (`mm_to_uu`, `nest_loops`,
`split_loops`). Part paths put holes first and the outline last.

## Testing

There is no unit-test setup; the tests run the extensions in real Inkscape on
the sample files and need to be checked by eye as well.

    ./test_import_onshape.sh   # sample-input01.svg  -> sample-output01.svg
    ./test_kerf.sh             # sample-output01.svg -> sample-kerf01.svg
    ./test_holes_outlines.sh   # sample-kerf01.svg   -> sample-holes01.svg
    ./test_gcode_export.sh     # sample-kerf01.svg   -> sample-material01.gcode (also runs test_gcode_core.py, plain python)

Each test copies `*.inx` and `*.py` into `test-profile/extensions/`, so no
install is needed. The tests chain: run them in that order.

Set `AGENT=false` to run Inkscape directly. Otherwise (the default) the tests
call `./cmd-client NAME cmd-dir/`, which asks a server running on the host
(outside the Claude Code sandbox, where `inkscape` is not installed and `inkex`
can't be imported because numpy is missing) to run a fixed command. The server
script isn't in this repo; its `COMMANDS` table needs these entries, with the
actions in the form `us.chouser.laser.<id-with-dashes>`:

    [inkscape]  import-onshape on sample-input01.svg  -> sample-output01.svg
    [kerf]      select-all:all;us.chouser.laser.kerf  on sample-output01.svg -> sample-kerf01.svg
    [gcode]     us.chouser.laser.gcode-export on sample-material01.svg -> sample-material-out01.svg
    [holes]     select-all:all;us.chouser.laser.holes-outlines on sample-kerf01.svg -> sample-holes01.svg

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
- Not yet checked: whether LaserWeb keeps the nested group structure from
  Separate Holes and Outlines intact.
