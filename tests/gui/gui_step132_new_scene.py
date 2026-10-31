"""#44: in Maya mode Ctrl+N over the viewport = Maya's New Scene = a new untitled file in the Maya layout
(Status Line + Shelf strips), like File > New Scene — not Blender's default General file."""

import os
import sys

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import check, ev, run, step, setup, screenshot, view3d, win  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")


def strips():
    return [a for a in win().screen.areas if a.type == 'IMAGE_EDITOR'
            and getattr(a.spaces.active, "mask", None) is not None and a.spaces.active.mask.name.startswith(".Allset")]


@step
def s_setup():
    setup()


@step
def s_press():
    check(f"factory file first: no Maya strips ({len(strips())})", not strips())
    _area, r = view3d()
    ev('MOUSEMOVE', 'NOTHING', x=r.x + r.width // 2, y=r.y + r.height // 2)
    ev('LEFT_CTRL', 'PRESS')
    ev('N', 'PRESS', ctrl=True)
    ev('N', 'RELEASE', ctrl=True)
    ev('LEFT_CTRL', 'RELEASE')


@step
def s_confirm_if_asked():
    if bpy.data.is_dirty:      # unsaved changes: Maya's Save Changes menu first: D = Don't Save
        ev('D', 'PRESS')
        ev('D', 'RELEASE')


@step
def s_wait():
    pass


@step
def s_check():
    if SHOTS:
        screenshot(os.path.join(SHOTS, "gui_step132_new_scene.png"))
    check(f"Ctrl+N opened the Maya layout ({len(strips())} strips, file {bpy.data.filepath!r})",
          len(strips()) == 2 and not bpy.data.filepath)


run()
