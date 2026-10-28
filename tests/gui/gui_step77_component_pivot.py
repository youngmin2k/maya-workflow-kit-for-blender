"""Step 77 in a real UI: Maya Insert in component mode — F9, W, Insert = cursor tool + cursor pivot,
a click on a side face places and orients the pivot ("Maya Pivot" Move axis), a drag moves it, Insert again
= Move tool back with the pivot kept; Insert on + F8 out of edit mode closes it, the tool comes back in
edit mode. Plan: docs/steps/step_77.md."""

import os
import sys

import bpy
import bmesh
from bpy_extras import view3d_utils
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, run, screenshot, setup, step, tap, view3d, win  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


def shot(name):
    if SHOTS:
        screenshot(os.path.join(SHOTS, name))


def ts():
    return bpy.context.scene.tool_settings


def cursor():
    return bpy.context.scene.cursor


def move_slot():
    from importlib import import_module
    pivot = import_module(MODULE + ".operators.pivot")
    return bpy.context.scene.transform_orientation_slots[pivot.MOVE_SLOT].type


def tool_id():
    area, region = view3d()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        t = bpy.context.workspace.tools.from_space_view3d_mode(bpy.context.mode, create=False)
    return t.idname if t else None


def screen_xy(co):
    area, region = view3d()
    p = view3d_utils.location_3d_to_region_2d(region, area.spaces.active.region_3d, co)
    return region.x + int(round(p.x)), region.y + int(round(p.y))


def hover(xy):
    ev('MOUSEMOVE', 'NOTHING', x=xy[0], y=xy[1])


def click(xy):
    hover(xy)
    ev('LEFTMOUSE', 'PRESS', x=xy[0], y=xy[1])
    ev('LEFTMOUSE', 'RELEASE', x=xy[0], y=xy[1])


@step
def s_setup():
    C["mid"] = setup()
    cube = bpy.data.objects["Cube"]
    for ob in bpy.context.selected_objects:
        ob.select_set(False)
    cube.select_set(True)
    bpy.context.view_layer.objects.active = cube
    cursor().location = (0, 0, 0)
    cursor().rotation_mode = 'XYZ'
    cursor().rotation_euler = (0, 0, 0)
    hover(screen_xy(Vector((0, 0, 0))))
    tap('F9')


@step
def s_move_tool():
    check(f"F9: vertex mode ({bpy.context.mode})", bpy.context.mode == 'EDIT_MESH')
    tap('W')


@step
def s_insert_on():
    C["tool"] = tool_id()
    C["pivot"] = ts().transform_pivot_point
    check(f"W: Move tool ({C['tool']})", C["tool"] == "builtin.move")
    tap('INSERT')


@step
def s_insert_check():
    check(f"Insert: cursor tool ({tool_id()}) and cursor pivot ({ts().transform_pivot_point})",
          tool_id() == "builtin.cursor" and ts().transform_pivot_point == 'CURSOR')
    ob = bpy.context.edit_object
    bm = bmesh.from_edit_mesh(ob.data)
    C['world'] = [ob.matrix_world @ v.co for v in bm.verts]
    C['selection'] = tuple(tuple(e.index for e in elements if e.select) for elements in (bm.verts, bm.edges, bm.faces))
    click(screen_xy(Vector((1.0, -0.3, 0.2))))          # the +X side face


@step
def s_clicked():
    loc, rot = cursor().location.copy(), cursor().matrix.to_3x3()
    C["loc"] = loc
    check(f"click on the side face places the pivot there ({tuple(round(v, 2) for v in loc)})",
          abs(loc.x - 1.0) < 0.05)
    normal = rot.col[2]
    check(f"the pivot turns to the face (cursor Z = {tuple(round(v, 2) for v in normal)})",
          abs(normal.x) > 0.9)
    shot("gui_step77_insert_on.png")
    xy = screen_xy(Vector((1.0, 0.3, -0.3)))
    hover(xy)
    ev('LEFTMOUSE', 'PRESS', x=xy[0], y=xy[1])
    C["drag"] = xy


@step
def s_drag_move():
    x, y = C["drag"]
    hover((x + 20, y + 10))
    hover((x + 40, y + 20))


@step
def s_drag_release():
    x, y = C["drag"]
    ev('LEFTMOUSE', 'RELEASE', x=x + 40, y=y + 20)


@step
def s_dragged():
    moved = (cursor().location - C["loc"]).length > 1e-3
    check(f"Insert + drag moves the pivot ({tuple(round(v, 2) for v in cursor().location)})", moved)
    ob = bpy.context.edit_object
    bm = bmesh.from_edit_mesh(ob.data)
    selection = tuple(tuple(e.index for e in elements if e.select) for elements in (bm.verts, bm.edges, bm.faces))
    check("component pivot dragging preserves selection and world geometry",
          selection == C['selection'] and all((p-ob.matrix_world @ v.co).length < 1e-5 for p, v in zip(C['world'], bm.verts)))
    hover(C["mid"])
    tap('INSERT')


@step
def s_insert_off():
    check(f"Insert again: Move tool back ({tool_id()}), placed pivot kept ({ts().transform_pivot_point})",
          tool_id() == "builtin.move" and ts().transform_pivot_point == 'CURSOR')
    check(f"the turned pivot is the Move axis ({move_slot()})", move_slot() == "Maya Pivot")
    shot("gui_step77_insert_off.png")
    tap('INSERT')


@step
def s_insert_again():
    check(f"Insert on again ({tool_id()})", tool_id() == "builtin.cursor")
    tap('F8')


@step
def s_left_edit():
    pass


@step
def s_left_edit_check():
    check(f"F8 to object mode closes the pivot edit ({bpy.context.mode}, pivot {ts().transform_pivot_point})",
          bpy.context.mode == 'OBJECT' and ts().transform_pivot_point != 'CURSOR')
    tap('F8')


@step
def s_back():
    pass


@step
def s_back_check():
    check(f"back in edit mode: the Move tool returns ({tool_id()})",
          bpy.context.mode == 'EDIT_MESH' and tool_id() == "builtin.move")


run()
