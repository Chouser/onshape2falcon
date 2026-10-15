#!/usr/bin/env bash
# Copy the extensions into Inkscape's user extensions directory.
# Usage: ./install.sh [DEST]   (default ~/.config/inkscape/extensions)
set -eu
cd "$(dirname "$0")/extension"
dest=${1:-$HOME/.config/inkscape/extensions}
mkdir -p "$dest"

# Keep a differing installed materials.json as a backup before replacing it.
if [ -e "$dest/materials.json" ] && ! cmp -s materials.json "$dest/materials.json"; then
  cp "$dest/materials.json" "$dest/materials.json.bak"
  echo "backed up old materials.json to $dest/materials.json.bak"
fi

cp *.py *.inx materials.json "$dest/"
echo "installed to $dest; restart Inkscape"
