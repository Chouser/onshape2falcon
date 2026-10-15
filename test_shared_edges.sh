#!/usr/bin/env bash
# Mark Shared Edges on two kerfed neighbours whose shared edge coincides, then Export Gcode on the result.
# Server commands needed in cmd-server COMMANDS:
#   [shared]='INKSCAPE_PROFILE_DIR=test-profile/ inkscape --actions="us.chouser.laser.mark-shared-edges" "sample-shared01.svg" --export-filename="sample-shared-out01.svg"'
#   [gcode]  (as in test_gcode_export.sh, reading sample-material01.svg)
# Check sample-shared-out01.svg by eye: red = skipped stretch, green = the
# neighbour's edge that cuts it.

python3 test_shared_edges.py || exit 1

cat > sample-shared01.svg <<'SVG'
<?xml version="1.0" encoding="UTF-8"?>
<svg width="400mm" height="400mm" viewBox="0 0 400 400" version="1.2"
     xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape"
     xmlns="http://www.w3.org/2000/svg">
  <g inkscape:label="plywood-5mm">
    <path id="partA" d="M 10 10 H 30 V 30 H 10 Z" style="fill:#aaf;stroke:#000;stroke-width:0.1"/>
    <path id="partB" d="M 30 10 H 50 V 30 H 30 Z M 35 15 h 5 v 5 h -5 Z" style="fill:#aaf;stroke:#000;stroke-width:0.1"/>
    <path id="partC" d="M 100 10 H 120 V 30 H 100 Z" style="fill:#aaf;stroke:#000;stroke-width:0.1"/>
  </g>
</svg>
SVG

cp *.inx *.py materials.json test-profile/extensions/
log=$(./cmd-client shared cmd-dir/ 2>&1); echo "$log"
if echo "$log" | grep -q -E "Traceback|No path objects"; then
  echo -e "\e[31mTest failed: extension error\e[0m"; exit 1
fi
grep -q 'inkscape:label="skipped"' sample-shared-out01.svg || { echo -e "\e[31mTest failed: no skipped group\e[0m"; exit 1; }
n=$(grep -c 'data-loop="partB:0"' sample-shared-out01.svg)
[ "$n" = 1 ] || { echo -e "\e[31mTest failed: expected one stretch skipped on partB, got $n\e[0m"; exit 1; }

cp sample-shared-out01.svg sample-material01.svg
log=$(./cmd-client gcode cmd-dir/ 2>&1); echo "$log"
echo "$log" | grep -q "1 subpath(s) had shared edges left out" || { echo -e "\e[31mTest failed: export did not skip the shared edge\e[0m"; exit 1; }
echo -e "\e[32mTest passed (inspect sample-shared-out01.svg visually)\e[0m"
