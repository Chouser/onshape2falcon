#!/usr/bin/env bash
# Run the kerf extension on the output of the import test.
# Server command needed in cmd-server COMMANDS:
#   [kerf]='INKSCAPE_PROFILE_DIR=test-profile/ inkscape --actions="select-all:all;us.chouser.laser.kerf" "test-out/sample-output01.svg" --export-filename="test-out/sample-kerf01.svg"'

input="test-out/sample-output01.svg"
output="test-out/sample-kerf01.svg"

mkdir -p test-out
cp extension/* test-profile/extensions/
if [ "$AGENT" == "false" ]; then
  INKSCAPE_PROFILE_DIR=test-profile/ inkscape --actions="select-all:all;us.chouser.laser.kerf" "$input" --export-filename="$output"
else
  log=$(./cmd-client kerf cmd-dir/ 2>&1); echo "$log"
  if echo "$log" | grep -q -E "Traceback|did not change|failed|not found|No path objects"; then
    echo -e "\e[31mTest failed: extension error\e[0m"; exit 1
  fi
fi

cmp -s "$input" "$output" && { echo -e "\e[31mTest failed: output unchanged\e[0m"; exit 1; }
parts=$(grep -c "<path" "$output")
echo "paths in output: $parts"
[ "$parts" -gt 0 ] || { echo -e "\e[31mTest failed: no paths\e[0m"; exit 1; }
echo -e "\e[32mTest passed (inspect $output visually)\e[0m"
