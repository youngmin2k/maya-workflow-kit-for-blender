"""In a real UI: symmetry Object X on, drag the Move gizmo's X arrow with the +X half of the
cube selected -> the -X half moves the mirrored way (interactive transforms read the mesh flags);
Status Line and W hold Symmetry ▸ screenshots."""

import os
import sys

import bmesh
import bpy
from bpy_extras.view3d_utils import location_3d_to_region_2d
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, run, screenshot, setup, step, tap, view3d, win  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


def shot(name):
    if SHOTS:
        screenshot(os.path.join(SHOTS, name))


def v3d_override():
    area, region = view3d()
    return bpy.context.temp_override(window=win(), area=area, region=region)


def cube():
    return bpy.data.objects["Cube"]


def zs():
    """Top-corner z by (x, y) sign; bottom corners keyed with y sign * 2."""
    bm = bmesh.from_edit_mesh(cube().data)
    out = {}
    for v in bm.verts:
        key = (round(v.co.x), round(v.co.y)) if v.co.z > 0 else (round(v.co.x) * 2, round(v.co.y) * 2)
        out[key] = round(v.co.z, 4)
    return out


def arrow(origin, axis):
    _area, region = view3d()
    o = location_3d_to_region_2d(region, region.data, origin)
    a = location_3d_to_region_2d(region, region.data, origin + axis * 0.1)
    d = (a - o).normalized()
    size = bpy.context.preferences.view.gizmo_size * bpy.context.preferences.system.ui_scale
    p = o + d * size * 0.75
    return int(region.x + p.x), int(region.y + p.y), d


@step
def s_setup():
    C["x"], C["y"] = setup()
    for o in bpy.context.view_layer.objects:
        o.select_set(o is cube())
    bpy.context.view_layer.objects.active = cube()
    with v3d_override():
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_mode(type='VERT')
        bpy.ops.mesh.select_all(action='DESELECT')
        bpy.ops.wm.tool_set_by_id(name="builtin.move")
        bpy.ops.allset.symmetry(mode="OBJECT_X")
    me = cube().data
    check("Object X sets the mesh X mirror flag only",
          (me.use_mirror_x, me.use_mirror_y, me.use_mirror_z) == (True, False, False))
    # Then pick one vertex on the +X side (the mirror is not selected).
    bm = bmesh.from_edit_mesh(me)
    for v in bm.verts:
        v.select = v.co.x > 0 and v.co.y > 0 and v.co.z > 0
    bm.select_flush(True)
    bmesh.update_edit_mesh(me)
    for a in win().screen.areas:
        a.tag_redraw()


@step
def s_hover():
    C["z0"] = zs()
    origin = cube().matrix_world @ Vector((1, 1, 1))  # gizmo at the selected vertex
    x, y, d = arrow(origin, cube().matrix_world.to_3x3() @ Vector((0, 0, 1)))
    C["g"] = (x, y, d)
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
    ev('MOUSEMOVE', 'NOTHING', x=x + 1, y=y)


@step
def s_press():
    x, y, _d = C["g"]
    ev('LEFTMOUSE', 'PRESS', x=x, y=y)


@step
def s_move():
    x, y, d = C["g"]
    for i in range(1, 9):
        ev('MOUSEMOVE', 'NOTHING', x=x + int(d.x * 60) * i // 8, y=y + int(d.y * 60) * i // 8)


@step
def s_release():
    x, y, d = C["g"]
    ev('LEFTMOUSE', 'RELEASE', x=x + int(d.x * 60), y=y + int(d.y * 60))


@step
def s_moved():
    z = zs()
    picked, mirror = z[(1, 1)], z[(-1, 1)]
    check(f"Z arrow drag moved the picked +X vertex ({C['z0'][(1, 1)]} -> {picked})", picked > 1.05)
    check(f"its unselected -X mirror moved the same ({mirror})", abs(mirror - picked) < 1e-3)
    check("the other vertices stayed", all(abs(z[k] - C["z0"][k]) < 1e-6 for k in z if k not in ((1, 1), (-1, 1))))
    for a in win().screen.areas:
        a.tag_redraw()


@step
def s_status_shot():
    shot("gui_step36_status_line.png")
    x, y = C["x"] - 150, C["y"] - 60
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
    ev('W', 'PRESS', x=x, y=y)
    ev('LEFTMOUSE', 'PRESS', x=x, y=y)


@step
def s_menu_north():
    x, y = C["x"] - 150, C["y"] - 60
    for i in range(1, 9):
        ev('MOUSEMOVE', 'NOTHING', x=x, y=y + 100 * i // 8)


@step
def s_menu_wait():
    for a in win().screen.areas:
        a.tag_redraw()


@step
def s_menu_wait2():
    for a in win().screen.areas:
        a.tag_redraw()


@step
def s_menu_shot():
    shot("gui_step36_w_symmetry.png")
    x, y = C["x"] - 150, C["y"] + 40
    ev('LEFTMOUSE', 'RELEASE', x=x, y=y)
    ev('W', 'RELEASE', x=x, y=y)
    tap('ESC')
    check("W hold menu opened toward Symmetry (screenshot)", True)


@step
def s_tool_settings():
    ev('MOUSEMOVE', 'NOTHING', x=C["x"], y=C["y"])
    with v3d_override():
        bpy.ops.allset.editor_toggle(editor='TOOL_SETTINGS')


@step
def s_tool_settings_wait():
    for a in win().screen.areas:
        a.tag_redraw()


@step
def s_tool_settings_shot():
    shot("gui_step36_tool_settings.png")
    # Tool Settings is a dock left of the viewport; the second toggle closes it
    from importlib import import_module
    tool_dock = import_module(MODULE + ".ui.tool_dock")
    shown = tool_dock.shown(win().screen)
    with v3d_override():
        bpy.ops.allset.editor_toggle(editor='TOOL_SETTINGS')
    check("Tool Settings dock drawn (screenshot), closed by the second toggle",
          shown and not tool_dock.shown(win().screen))


run()
