"""In a real UI: mesh component keys — Shift+> / Shift+<,
Ctrl+F9 / Ctrl+F11, Ctrl+E, Ctrl+B, D component pivot hold (click a vertex) / tap on and off, Alt+D."""

import os
import sys

import bmesh
import bpy
from bpy_extras import view3d_utils

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import check, ev, run, setup, step, tap, view3d, win  # noqa: E402

C = {}


def ob():
    return bpy.data.objects["Cube"]


def bm():
    return bmesh.from_edit_mesh(ob().data)


def n_sel(kind):
    return sum(e.select for e in getattr(bm(), kind))


def select_face(i=0):
    b = bm()
    for f in b.faces:
        f.select_set(False)
    b.faces.ensure_lookup_table()
    b.faces[i].select_set(True)
    b.select_flush_mode()
    bmesh.update_edit_mesh(ob().data)


def centre():
    ev('MOUSEMOVE', 'NOTHING', x=C["x"], y=C["y"])


def combo(key, **mods):
    ev(key, 'PRESS', **mods)
    ev(key, 'RELEASE', **mods)


def ts():
    return bpy.context.scene.tool_settings


def tool_id():
    area, region = view3d()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        t = bpy.context.workspace.tools.from_space_view3d_mode(bpy.context.mode, create=False)
    return t.idname if t else None


# PR #125's always-running window watchers are not a user modal
WATCHERS = {'ALLSET_OT_joint_outliner_select', 'ALLSET_OT_pose_empty_click'}


@step
def s_setup():
    C["x"], C["y"] = setup()
    for o in bpy.context.view_layer.objects:
        o.select_set(o.name == "Cube")
    bpy.context.view_layer.objects.active = ob()
    centre()
    tap('F11')


@step
def s_face_mode():
    check("F11: face mode", bpy.context.mode == 'EDIT_MESH' and tuple(ts().mesh_select_mode) == (False, False, True))
    select_face()
    centre()
    combo('PERIOD', shift=True)


@step
def s_grow():
    C["grown"] = n_sel("faces")
    check(f"Shift+> grows one face to its neighbours ({C['grown']} faces)", C["grown"] == 5)
    combo('COMMA', shift=True)


@step
def s_shrink():
    check(f"Shift+< shrinks back ({n_sel('faces')} face)", n_sel("faces") == 1)
    combo('F9', ctrl=True)


@step
def s_to_verts():
    check(f"Ctrl+F9: vertex mode with the face's 4 vertices ({n_sel('verts')})",
          tuple(ts().mesh_select_mode) == (True, False, False) and n_sel("verts") == 4)
    combo('F11', ctrl=True)


@step
def s_to_faces():
    check(f"Ctrl+F11: back to faces, all faces touching those vertices ({n_sel('faces')})",
          tuple(ts().mesh_select_mode) == (False, False, True) and n_sel("faces") == 5)
    select_face()
    C["faces"] = len(bm().faces)
    centre()
    combo('E', ctrl=True)


@step
def s_extrude_modal():
    # like Maya Extrude: extruded right away (zero length) + manipulator, no modal
    ex = sys.modules["sim"].import_module(sys.modules["sim"].MODULE + ".operators.extrude")
    _o, rec = ex.active(bpy.context)
    check(f"Ctrl+E: polyExtrudeFace right away, no drag modal ({rec and rec.name}, {list(win().modal_operators)})",
          rec is not None and not [o for o in win().modal_operators if o.bl_idname not in WATCHERS])


@step
def s_extruded():
    check(f"Ctrl+E adds faces ({C['faces']} -> {len(bm().faces)})", len(bm().faces) == C["faces"] + 4)
    C["faces"] = len(bm().faces)
    centre()
    combo('B', ctrl=True)


@step
def s_bevel_modal():
    # like Maya Bevel (#16): beveled right away, no drag modal
    ex = sys.modules["sim"].import_module(sys.modules["sim"].MODULE + ".operators.extrude")
    _o, rec = ex.active(bpy.context)
    mods = [op.bl_idname for op in win().modal_operators if op.bl_idname not in WATCHERS]
    check(f"Ctrl+B: polyBevel right away, no modal ({rec and rec.name}, {mods})",
          rec is not None and rec.name.startswith("polyBevel") and not mods)
    ev('MOUSEMOVE', 'NOTHING', x=C["x"] + 60, y=C["y"])


@step
def s_beveled():
    # the cap of a zero-length extrusion bevels into an inset like Maya (12/20/10 stays, cap shrinks)
    check(f"Ctrl+B on the extruded cap: Maya inset, same face count ({C['faces']} -> {len(bm().faces)})",
          len(bm().faces) == C["faces"])
    ts().transform_pivot_point = 'MEDIAN_POINT'
    C["tool"] = tool_id()
    C["cursor"] = bpy.context.scene.cursor.location.copy()
    centre()
    ev('D', 'PRESS')


@step
def s_d_held():
    check(f"D held in edit mode: cursor tool ({tool_id()}) and cursor pivot",
          tool_id() == "builtin.cursor" and ts().transform_pivot_point == 'CURSOR')
    C["cursor"] = bpy.context.scene.cursor.location.copy()
    # while editing the pivot a click on a vertex, edge or face places it there (Maya custom pivot editing):
    # click the cube corner nearest to the viewer
    area, region = view3d()
    rv3d = area.spaces.active.region_3d
    mw = ob().matrix_world
    eye = rv3d.view_matrix.inverted().translation
    corner = min((mw @ v.co for v in bm().verts), key=lambda p: (p - eye).length)
    rx, ry = view3d_utils.location_3d_to_region_2d(region, rv3d, corner)
    x, y = region.x + int(round(rx)), region.y + int(round(ry))
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
    ev('LEFTMOUSE', 'PRESS', x=x, y=y)
    ev('LEFTMOUSE', 'RELEASE', x=x, y=y)


@step
def s_d_release():
    moved = (bpy.context.scene.cursor.location - C["cursor"]).length > 1e-6
    check("LMB on a vertex with D held places the pivot (3D cursor moved)", moved)
    centre()
    ev('D', 'RELEASE')


@step
def s_d_released():
    check(f"D released: previous tool back ({tool_id()}), placed pivot kept",
          tool_id() == C["tool"] and ts().transform_pivot_point == 'CURSOR')
    tap('D')


@step
def s_d_tap():
    # a D tap keeps the pivot edit on (Maya custom pivot editing) ...
    check(f"D tap: pivot editing stays on ({tool_id()}, {ts().transform_pivot_point})",
          tool_id() == "builtin.cursor" and ts().transform_pivot_point == 'CURSOR')
    tap('D')


@step
def s_d_tap_off():
    # ... and a second tap with nothing placed ends it without a custom pivot
    check(f"D tap again: pivot edit off, no custom pivot ({ts().transform_pivot_point}, {tool_id()})",
          ts().transform_pivot_point == 'BOUNDING_BOX_CENTER' and tool_id() == C["tool"])
    combo('D', alt=True)


@step
def s_select_none():
    check("Alt+D: nothing selected, back in object mode",
          bpy.context.mode == 'OBJECT' and not bpy.context.selected_objects)


run()
