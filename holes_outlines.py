#!/usr/bin/env python3

import inkex

from laser_common import in_preview, nest_loops

DEBUG = True


def debug(message):
    if DEBUG:
        inkex.utils.debug(f"HolesOutlines: {message}")


class HolesOutlines(inkex.EffectExtension):
    """Turn each selected path into a matched pair of groups, so a laser
    program can be told to cut all the holes before all the outlines:

        outlines  <- group
            part-1 <- group of that path's outline path(s)
            part-2 ...
        holes     <- group
            part-1 <- group of that path's hole paths
            part-2 ...

    Leaves the original paths alone, so they can still be moved and
    duplicated as units before running this.
    """

    def effect(self):
        selected = [e for e in self.svg.selection.values()
                    if isinstance(e, inkex.PathElement)]
        if not selected:
            # Nothing selected (or run from the command line): use everything.
            selected = [e for e in self.svg.iterdescendants()
                        if isinstance(e, inkex.PathElement)
                        and not isinstance(e.getparent(), inkex.Defs)
                        and not in_preview(e)]
        if not selected:
            raise inkex.AbortExtension("No path objects to separate.")

        parent = selected[0].getparent()
        index = list(parent).index(selected[0])

        holes_group = inkex.Group.new("holes")
        holes_group.set("inkscape:label", "holes")
        outlines_group = inkex.Group.new("outlines")
        outlines_group.set("inkscape:label", "outlines")

        for n, elem in enumerate(selected, 1):
            path = elem.path.to_absolute().transform(elem.composed_transform()).to_absolute()
            loops = list(path.break_apart())
            _, depth = nest_loops(loops)
            holes = [l for l, d in zip(loops, depth) if d % 2 == 1]
            outlines = [l for l, d in zip(loops, depth) if d % 2 == 0]
            debug(f"part-{n}: {len(outlines)} outline(s), {len(holes)} hole(s)")
            for group, loops_ in ((holes_group, holes), (outlines_group, outlines)):
                if not loops_:
                    continue
                sub = inkex.Group.new(f"part-{n}")
                sub.set("inkscape:label", f"part-{n}")
                for loop in loops_:
                    piece = inkex.PathElement()
                    piece.path = loop
                    piece.style = elem.style
                    sub.append(piece)
                group.append(sub)

        for elem in selected:
            elem.getparent().remove(elem)
        parent.insert(index, outlines_group)
        parent.insert(index + 1, holes_group)


if __name__ == "__main__":
    HolesOutlines().run()
