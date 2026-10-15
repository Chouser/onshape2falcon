#!/usr/bin/env bash
# Run holes_outlines on the output of the kerf test.
# Server command needed in cmd-server COMMANDS:
#   [holes]='INKSCAPE_PROFILE_DIR=test-profile/ inkscape --actions="select-all:all;us.chouser.laser.holes-outlines" "test-out/sample-kerf01.svg" --export-filename="test-out/sample-holes01.svg"'

input="test-out/sample-kerf01.svg"
output="test-out/sample-holes01.svg"

mkdir -p test-out
cp extension/* test-profile/extensions/
if [ "$AGENT" == "false" ]; then
  INKSCAPE_PROFILE_DIR=test-profile/ inkscape --actions="select-all:all;us.chouser.laser.holes-outlines" "$input" --export-filename="$output"
else
  log=$(./cmd-client holes cmd-dir/ 2>&1); echo "$log"
  if echo "$log" | grep -q -E "Traceback|failed|No path objects"; then
    echo -e "\e[31mTest failed: extension error\e[0m"; exit 1
  fi
fi

for label in holes outlines; do
  grep -q "inkscape:label=\"$label\"" "$output" || { echo -e "\e[31mTest failed: no $label group\e[0m"; exit 1; }
done
echo -e "\e[32mTest passed (inspect $output visually)\e[0m"
