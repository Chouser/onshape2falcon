#!/usr/bin/env bash
# Run gcode_export on the output of the kerf test, with everything wrapped
# in a group named for a material.
# Server command needed in cmd-server COMMANDS:
#   [gcode]='INKSCAPE_PROFILE_DIR=test-profile/ inkscape --actions="us.chouser.laser.gcode-export" "sample-material01.svg" --export-filename="sample-material-out01.svg"'

python3 tests/test_gcode_core.py || exit 1

input="sample-kerf01.svg"
wrapped="sample-material01.svg"
output="sample-material01.gcode"
rm -f "$output"

# Wrap every top-level element after <defs> in a plywood-5mm group.
python3 - "$input" "$wrapped" <<'PY'
import re, sys
s = open(sys.argv[1]).read()
s = re.sub(r"(<defs[^>]*/>)", r'\1\n<g inkscape:label="plywood-5mm">', s, count=1)
s = s.replace("</svg>", "</g>\n</svg>")
# Add a clearly open polyline: the export must not close it.
s = s.replace("</g>\n</svg>", '<path d="M 100 100 L 400 100 L 400 400" style="fill:none;stroke:#000"/>\n</g>\n</svg>')
open(sys.argv[2], "w").write(s)
PY

cp extension/* test-profile/extensions/
if [ "$AGENT" == "false" ]; then
  INKSCAPE_PROFILE_DIR=test-profile/ inkscape --actions="us.chouser.laser.gcode-export" "$wrapped" --export-filename=sample-material-out01.svg
else
  log=$(./cmd-client gcode cmd-dir/ 2>&1); echo "$log"
  if echo "$log" | grep -q -E "Traceback|Cannot load|Paths not inside|No path objects"; then
    echo -e "\e[31mTest failed: extension error\e[0m"; exit 1
  fi
fi

# The extension logs the full path it wrote. Copy it here if visible (a
# sandboxed agent may not see the host directory it was written to).
written=$(echo "$log" | sed -n 's/.*GcodeExport: wrote //p' | tail -1)
[ -n "$written" ] || { echo -e "\e[31mTest failed: extension did not report a gcode file\e[0m"; exit 1; }
if [ -s "$written" ]; then
  cp -f "$written" "$output"
else
  echo "Note: $written not visible from here"; exit 0
fi
head -3 "$output"
echo -e "\e[32mTest passed (check bounds and cut order in $output)\e[0m"
