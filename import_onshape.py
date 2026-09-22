
#!/usr/bin/env python3

import io
import math
import os
import re
import shutil
import subprocess
import tempfile
from collections import defaultdict

import inkex
from inkex import paths
from lxml import etree


DEBUG = True

INKSCAPE_NS = "http://www.inkscape.org/namespaces/inkscape"
SVG_NS = "http://www.w3.org/2000/svg"

INKSCAPE = "inkscape"

def debug(message):
    if DEBUG:
        inkex.utils.debug(f"ImportOnshape: {message}")

class ImportOnshape(inkex.EffectExtension):

    def add_arguments(self, pars):
        pars.add_argument(
            "--endpoint_tolerance_mm",
            type=float,
            default=0.001,
        )

    def effect(self):
      debug("start")
      debug("FILL IN STEPS HERE")

# The manual steps this extension is meant to replace:
# 
# - select all
# - ungroup until no groups left (the original groupings aren't useful)
# - find the large white rectangle that serves as a background and delete it (I need paths the laser will follow, not objects for their visual effect)
# - select all (should be lots of curve parts) and choose Path -> Object to Path
# - For all, set the fill to be light blue 50% opacity, and the border to be 0.1mm black 50% opacity. The fill provides a diagnostic to show the closed shape and holes. The stroke represents the laser path with opacity that lets me see when strokes overlap.
# - find any circles that have crosshairs marking their center, draw an actual circle with the same center and size, and the same stroke and fill as above. Then delete the original circles. Without this step, the "simplify" below distorts the circles too much. (Don't attempt to automate this step.)
# - select all and choose Path -> Simplify.It's important to do this here before joining the paths because this preserves precise endpoints that are needed for sharp corners.
# - select all and choose Path -> Combine, so now the document has just a single path
# - Select all nodes in the path and choose "Join selected nodes" button. Despite it's name, it only joins pairs of nodes that are at the same location. The single path object now has many closed subpaths in it.
# - Choose Path -> Split Path (not Break Apart). This separates the one path object into several independent parts while preserving holes, so that I can manually arrange to use my cutting material efficiently.

if __name__ == "__main__":
    ImportOnshape().run()

