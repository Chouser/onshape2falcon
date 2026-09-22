#!/usr/bin/env bash

# Test script for ImportOnshape extension
input="sample-input01.svg"
output="sample-output01.svg"

# Create backup of original
cp "$input" "$output"

# Run extension
cp *.inx *.py test-profile/extensions/
INKSCAPE_PROFILE_DIR=test-profile/ inkscape --actions="us.chouser.laser.import-onshape" "sample-input01.svg" --export-filename="sample-output01.svg"

# Verify background rectangle deletion
if grep -q "<rect" "$output"; then
  echo "\e[31mTest failed: Background rectangle still present\e[0m"
  exit 1
fi

# Verify ungrouping
if grep -q "<g" "$output"; then
  echo "\e[31mTest failed: Nested groups remain\e[0m"
  exit 1
fi

echo "\e[32mTest passed: Background rectangle deleted and all elements ungrouped\e[0m"
