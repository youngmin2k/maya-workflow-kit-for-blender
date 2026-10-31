"""In a real UI: z / Shift+Z undo-redo (3D View and Outliner), h hide/show,
Ctrl+1 isolate in/out."""

import os
import sys

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import check, ev, run, step, setup, tap, view3d, win  # noqa: E402

C = {}


def has_cube():
    return "Cube" in bpy.data.objects


def centre():
    ev('MOUSEMOVE', 'NOTHING', x=C["x"], y=C["y"])


def outliner_centre():
    area = next(a for a in win().screen.areas if a.type == 'OUTLINER')
    r = next(r for r in area.regions if r.type == 'WINDOW')
    return r.x + r.width // 2, r.y + r.height // 2


def only_cube():
    for o in bpy.context.view_layer.objects:
        o.select_set(o.name == "Cube")
    bpy.context.view_layer.objects.active = bpy.data.objects["Cube"]


@step
def s_setup():
    C["x"], C["y"] = setup()
    only_cube()
    centre()
    tap('DEL')


@step
def s_deleted():
    check("Delete removes the cube", not has_cube())
    centre()
    tap('Z')


@step
def s_z():
    check("z over the 3D View undoes (cube back)", has_cube())
    # the kit keeps window modals of its own running since PR #125: look for zoom only
    mods = [op.bl_idname for op in win().modal_operators]
    check(f"z starts no zoom-border modal ({mods})", not [m for m in mods if "ZOOM" in m.upper()])
    ev('Z', 'PRESS', shift=True)
    ev('Z', 'RELEASE', shift=True)


@step
def s_shift_z():
    check("Shift+Z redoes (cube deleted again)", not has_cube())
    tap('Z')


@step
def s_z_again():
    check("z undoes the redo", has_cube())
    ev('Y', 'PRESS', ctrl=True)
    ev('Y', 'RELEASE', ctrl=True)


@step
def s_ctrl_y():
    check("Ctrl+Y redoes (cube deleted again)", not has_cube())
    x, y = outliner_centre()
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
    tap('Z')


@step
def s_outliner_z():
    check("z over the Outliner undoes too", has_cube())
    only_cube()
    centre()
    tap('H')


@step
def s_h_hide():
    cube = bpy.data.objects["Cube"]
    check("h hides the selection", cube.hide_viewport)
    tap('H')


@step
def s_h_show():
    cube = bpy.data.objects["Cube"]
    check("h again shows it and it is still selected", not cube.hide_viewport and cube.select_get())
    only_cube()
    ev('ONE', 'PRESS', ctrl=True)
    ev('ONE', 'RELEASE', ctrl=True)


@step
def s_isolate_on():
    sp = view3d()[0].spaces.active
    check("Ctrl+1 isolates the selection (local view)", sp.local_view is not None)
    lamp = bpy.data.objects.get("Light")
    check("objects outside the isolation are not shown", lamp is None or not lamp.visible_in_viewport_get(sp))
    ev('ONE', 'PRESS', ctrl=True)
    ev('ONE', 'RELEASE', ctrl=True)


@step
def s_isolate_off():
    check("Ctrl+1 again leaves isolation", view3d()[0].spaces.active.local_view is None)


run()
