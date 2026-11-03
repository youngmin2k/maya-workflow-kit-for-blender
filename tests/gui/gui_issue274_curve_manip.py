"""Issue #274 follow-up in a real UI: in the Maya layout a NURBS curve in edit mode with one CV selected — W gives
the Move tool with the kit's Maya manipulator, a drag on its X arrow moves the CV along X; R gives the Scale tool
with it too. A NURBS surface in edit mode gets it as well."""

import os
import sys
from importlib import import_module

import bpy
from bpy_extras.view3d_utils import location_3d_to_region_2d, region_2d_to_location_3d
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, run, setup, step, tap, view3d, win, load_maya_layout, scale  # noqa: E402

C = {}


def mod(name):
    return import_module(f"{MODULE}.{name}")


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


def tool(mode):
    return bpy.context.workspace.tools.from_space_view3d_mode(mode, create=False)


def override():
    return bpy.context.temp_override(window=win(), area=view3d()[0], region=view3d()[1])


def cv():
    return bpy.data.objects[C["ob"]].data.splines[0].points[C["i"]]


@step
def s_setup():
    setup()
    load_maya_layout()


@step
def s_curve():
    bpy.ops.allset.keymap_activate()
    with override():
        bpy.ops.curve.primitive_nurbs_curve_add(radius=4 * mod("operators.units").maya_unit())
        ob = bpy.context.active_object
        select_only(ob)
        bpy.ops.object.mode_set(mode='EDIT')
        pts = ob.data.splines[0].points
        for i, p in enumerate(pts):
            p.select = i == 2
        C["ob"], C["i"] = ob.name, 2
        bpy.ops.view3d.view_selected()
    hover()


@step
def s_w():
    tap('W')


@step
def s_move_tool():
    t = tool('EDIT_CURVE')
    check(f"W in curve edit mode = Move with the kit's Maya manipulator ({t.idname if t else None}, "
          f"{t.widget if t else None})",
          t is not None and t.idname == "builtin.move" and t.widget == mod("ui.manipulator").GROUP)
    ob = bpy.data.objects[C["ob"]]
    C["center"] = ob.matrix_world @ cv().co.xyz
    C["co"] = cv().co.xyz.copy()
    with override():
        check("the manipulator shows for the selected CV", mod("ui.manipulator").ALLSET_GGT_xform.poll(bpy.context))
    for a in win().screen.areas:
        a.tag_redraw()


def _x_tip():
    c = C["center"]
    _area, region = view3d()
    p = location_3d_to_region_2d(region, region.data, c)
    w = region_2d_to_location_3d(region, region.data, p + Vector((1, 0)), c)
    C["px_world"] = (w - c).length
    n = mod("ui.manipulator").ARROW_PX * bpy.context.preferences.view.gizmo_size / 75.0 * scale()
    return screen(c + Vector((1, 0, 0)) * n * 0.8 * C["px_world"])


@step
def s_hover_arrow():
    C["p"] = _x_tip()
    ev('MOUSEMOVE', 'NOTHING', x=int(C["p"].x), y=int(C["p"].y))


@step
def s_press():
    ev('LEFTMOUSE', 'PRESS', x=int(C["p"].x), y=int(C["p"].y))


@step
def s_move1():
    ev('MOUSEMOVE', 'NOTHING', x=int(C["p"].x) + 40, y=int(C["p"].y))


@step
def s_move2():
    ev('MOUSEMOVE', 'NOTHING', x=int(C["p"].x) + 80, y=int(C["p"].y))


@step
def s_release():
    ev('LEFTMOUSE', 'RELEASE', x=int(C["p"].x) + 80, y=int(C["p"].y))


@step
def s_moved():
    ob = bpy.data.objects[C["ob"]]
    d = ob.matrix_world.to_3x3() @ (cv().co.xyz - C["co"])
    want = 80 * C["px_world"]
    check(f"X arrow drag moves the CV along X ({d.x / want:.2f} of the drag, y {d.y / want:.3f}, z {d.z / want:.3f})",
          d.x > 0.5 * want and abs(d.y) < 0.01 * want and abs(d.z) < 0.01 * want)
    hover()


@step
def s_r():
    tap('R')


@step
def s_scale_tool():
    t = tool('EDIT_CURVE')
    check(f"R in curve edit mode = Scale with the Maya manipulator ({t.idname if t else None})",
          t is not None and t.idname == "builtin.scale" and t.widget == mod("ui.manipulator").GROUP)
    with override():
        bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.surface.primitive_nurbs_surface_surface_add(location=(0, 0, 0))
        ob = bpy.context.active_object
        select_only(ob)
        bpy.ops.object.mode_set(mode='EDIT')
        for i, p in enumerate(ob.data.splines[0].points):
            p.select = i == 5
    hover()


@step
def s_w2():
    tap('W')


@step
def s_surface():
    t = tool('EDIT_SURFACE')
    check(f"W in surface edit mode = Move with the Maya manipulator ({t.idname if t else None}, "
          f"{t.widget if t else None})",
          t is not None and t.idname == "builtin.move" and t.widget == mod("ui.manipulator").GROUP)
    with override():
        check("the manipulator shows for the selected surface CV",
              mod("ui.manipulator").ALLSET_GGT_xform.poll(bpy.context))


run()
