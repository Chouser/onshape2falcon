#!/usr/bin/env bash

# Test script for ImportOnshape extension
input="tests/data/sample-input01.svg"
output="sample-output01.svg"

# Run extension
cp extension/* test-profile/extensions/
if [ "$AGENT" == "false" ]; then
  INKSCAPE_PROFILE_DIR=test-profile/ inkscape --actions="us.chouser.laser.import-onshape" "$input" --export-filename="$output"
else
  ./cmd-client inkscape cmd-dir/
fi

# Verify background rectangle deletion
if grep -q "<rect" "$output"; then
  echo -e "\e[31mTest failed: Background rectangle still present\e[0m"
  exit 1
fi

# Verify ungrouping
if grep -q "<g" "$output"; then
  echo -e "\e[31mTest failed: Nested groups remain\e[0m"
  exit 1
fi

echo -e "\e[32mTest passed: Background rectangle deleted and all elements ungrouped\e[0m"
