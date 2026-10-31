"""Issue #274 in a real UI: in the Maya layout, a lattice in edit mode with a point selected — W gives the Move tool
with the kit's Maya manipulator (not Blender's transform gizmo), R the Scale tool with it too; a drag on its X arrow
moves the point along X."""

import os
import sys
from importlib import import_module

import bpy
from bpy_extras.view3d_utils import location_3d_to_region_2d
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, run, setup, step, tap, view3d, win, load_maya_layout, screenshot  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


def mod(name):
    return import_module(f"{MODULE}.{name}")


def shot(name):
    if SHOTS:
        screenshot(os.path.join(SHOTS, name))


def select_only(ob):
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob


def screen(world):
    _area, region = view3d()
    p = location_3d_to_region_2d(region, region.data, world)
    return Vector((region.x + p.x, region.y + p.y))


def hover():
    _area, r = view3d()
    ev('MOUSEMOVE', 'NOTHING', x=r.x + r.width // 2, y=r.y + r.height // 3)


def lattice():
    return bpy.data.objects[C["lat"]]


def tool():
    return bpy.context.workspace.tools.from_space_view3d_mode('EDIT_LATTICE', create=False)


def redraw():
    for a in win().screen.areas:
        a.tag_redraw()


@step
def s_setup():
    setup()
    load_maya_layout()


@step
def s_lattice():
    bpy.ops.allset.keymap_activate()
    u = mod("operators.units").maya_unit()
    lat = bpy.data.objects.new("ffd1Lattice", bpy.data.lattices.new("ffd1LatticeShape"))
    bpy.context.scene.collection.objects.link(lat)
    lat.scale = (8 * u, 8 * u, 8 * u)
    select_only(lat)
    bpy.ops.object.mode_set(mode='EDIT')
    for i, p in enumerate(lat.data.points):
        p.select = i == 7
    C["lat"] = lat.name
    with bpy.context.temp_override(window=win(), area=view3d()[0], region=view3d()[1]):
        bpy.ops.view3d.view_selected()
    hover()


@step
def s_w():
    tap('W')


@step
def s_move_tool():
    t = tool()
    check(f"W in lattice edit mode = Move ({t.idname if t else None})", t is not None and t.idname == "builtin.move")
    check(f"... with the kit's Maya manipulator ({t.widget if t else None})",
          t is not None and t.widget == mod("ui.manipulator").GROUP)
    gzg = mod("ui.manipulator").ALLSET_GGT_xform
    area, region = view3d()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        check("the manipulator shows for the selected point", gzg.poll(bpy.context))
    lat = lattice()
    C["co"] = Vector(lat.data.points[7].co_deform)
    C["center"] = lat.matrix_world @ C["co"]
    redraw()
    shot("issue274_move.png")


def _x_tip():
    """Window point 0.8 along the Move X arrow (108 px x gizmo size / 75 x UI scale)."""
    from sim import scale
    from bpy_extras.view3d_utils import region_2d_to_location_3d
    c = C["center"]
    _area, region = view3d()
    p = location_3d_to_region_2d(region, region.data, c)
    w = region_2d_to_location_3d(region, region.data, p + Vector((1, 0)), c)
    px_world = (w - c).length
    C["px_world"] = px_world
    n = mod("ui.manipulator").ARROW_PX * bpy.context.preferences.view.gizmo_size / 75.0 * scale()
    return screen(c + Vector((1, 0, 0)) * n * 0.8 * px_world)


@step
def s_drag_press():
    p = _x_tip()
    C["p"] = p
    ev('MOUSEMOVE', 'NOTHING', x=int(p.x), y=int(p.y))


@step
def s_drag_press2():
    p = C["p"]
    ev('LEFTMOUSE', 'PRESS', x=int(p.x), y=int(p.y))


@step
def s_drag_move():
    p = C["p"]
    ev('MOUSEMOVE', 'NOTHING', x=int(p.x) + 40, y=int(p.y))


@step
def s_drag_move2():
    p = C["p"]
    ev('MOUSEMOVE', 'NOTHING', x=int(p.x) + 80, y=int(p.y))


@step
def s_drag_release():
    p = C["p"]
    ev('LEFTMOUSE', 'RELEASE', x=int(p.x) + 80, y=int(p.y))


@step
def s_moved():
    lat = lattice()
    d = lat.matrix_world @ Vector(lat.data.points[7].co_deform) - C["center"]
    want = 80 * C["px_world"]
    check(f"X arrow drag moves the point along X ({d.x / want:.2f} of the drag, y {d.y / want:.3f}, "
          f"z {d.z / want:.3f})", d.x > 0.5 * want and abs(d.y) < 0.01 * want and abs(d.z) < 0.01 * want)
    hover()


@step
def s_r():
    tap('R')


@step
def s_scale_tool():
    t = tool()
    check(f"R in lattice edit mode = Scale with the Maya manipulator ({t.idname if t else None}, "
          f"{t.widget if t else None})",
          t is not None and t.idname == "builtin.scale" and t.widget == mod("ui.manipulator").GROUP)
    shot("issue274_scale.png")


run()
