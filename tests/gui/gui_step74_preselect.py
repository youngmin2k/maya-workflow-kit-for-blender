"""In a real UI: pre-selection follows the select mode (edge mode lights the edge, also next to
its vertex; face mode the face) and stays on with the Move tool, except over the manipulator's handles.
Clicks still select."""

import os
import sys
from importlib import import_module

import bmesh
import bpy
from bpy_extras import view3d_utils
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, run, screenshot, setup, step, view3d, win  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


def shot(name):
    if SHOTS:
        screenshot(os.path.join(SHOTS, name))


def cube():
    return bpy.data.objects["Cube"]


def bm():
    # keep the wrapper referenced while its elements are used
    C["bm"] = bmesh.from_edit_mesh(cube().data)
    return C["bm"]


def xy(p):
    area, region = view3d()
    q = view3d_utils.location_3d_to_region_2d(region, area.spaces.active.region_3d, cube().matrix_world @ p)
    return region.x + int(round(q.x)), region.y + int(round(q.y))


def eye():
    area, _r = view3d()
    return area.spaces.active.region_3d.view_matrix.inverted().translation


def front_faces():
    b = bm()
    b.faces.ensure_lookup_table()
    e = cube().matrix_world.inverted() @ eye()
    faces = [f for f in b.faces if (e - f.calc_center_median()).dot(f.normal) > 0]
    return sorted(faces, key=lambda f: -(e - f.calc_center_median()).normalized().dot(f.normal))


def state():
    gz = C["pre"].gizmo()
    return None if gz is None else (gz.is_highlight, gz.vert_index, gz.edge_index, gz.face_index)


def hover(p):
    x, y = xy(p)
    ev('MOUSEMOVE', 'NOTHING', x=x + 3, y=y + 2)
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
    C["at"] = (x, y)


def set_tool(name):
    area, region = view3d()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        bpy.ops.wm.tool_set_by_id(name=name)


@step
def s_setup():
    setup()
    C["pre"] = import_module(MODULE + ".operators.preselect")
    for o in bpy.context.view_layer.objects:
        o.select_set(o == cube())
    bpy.context.view_layer.objects.active = cube()
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='DESELECT')
    bpy.ops.mesh.select_mode(type='EDGE')
    set_tool("builtin.select_box")


@step
def s_edge_pick():
    # the edge shared by the two most visible faces: clearly in front
    f0, f1 = front_faces()[:2]
    shared = [e for e in f0.edges if e in f1.edges][0]
    C["edge"] = shared.index
    a, b = shared.verts[0].co.copy(), shared.verts[1].co.copy()
    C["edge_pts"] = (a, b)
    hover((a + b) / 2)


@step
def s_edge_mid():
    st = state()
    check(f"edge mode: hovering an edge lights that edge ({st}, edge {C['edge']})",
          st is not None and st[0] and st[2] == C["edge"] and st[1] == -1)


@step
def s_edge_shot():
    shot("gui_step74_edge.png")
    a, b = C["edge_pts"]
    hover(a + (b - a) * 0.06)


@step
def s_edge_near_vertex():
    st = state()
    check(f"edge mode next to a vertex still lights the edge, not the vertex ({st})",
          st is not None and st[0] and st[1] == -1 and st[2] >= 0)
    bpy.ops.mesh.select_mode(type='FACE')
    f = front_faces()[0]
    C["face"] = f.index
    C["face_c"] = f.calc_center_median()
    hover(C["face_c"])


@step
def s_face():
    st = state()
    check(f"face mode: hovering a face lights that face ({st}, face {C['face']})",
          st is not None and st[0] and st[3] == C["face"])


@step
def s_face_shot():
    shot("gui_step74_face.png")
    x, y = C["at"]
    ev('LEFTMOUSE', 'PRESS', x=x, y=y)
    ev('LEFTMOUSE', 'RELEASE', x=x, y=y)


@step
def s_click():
    sel = [f.index for f in bm().faces if f.select]
    check(f"a click on the highlighted face selects it ({sel})", sel == [C["face"]])
    set_tool("builtin.move")
    f2 = front_faces()[1]
    C["face2"] = f2.index
    hover(f2.calc_center_median() * 0.6 + C["face_c"] * 0.0 + f2.calc_center_median() * 0.0)


@step
def s_move_tool_face():
    st = state()
    check(f"Move tool: another face is still pre-selected ({st}, face {C['face2']})",
          st is not None and st[0] and st[3] == C["face2"])


@step
def s_move_shot():
    shot("gui_step74_move_tool.png")
    # over the X arrow of the manipulator (at the selected face's centre)
    area, region = view3d()
    rv3d = area.spaces.active.region_3d
    c = cube().matrix_world @ C["face_c"]
    c2 = view3d_utils.location_3d_to_region_2d(region, rv3d, c)
    p1 = view3d_utils.location_3d_to_region_2d(region, rv3d, c + rv3d.view_rotation @ Vector((1, 0, 0)))
    man = import_module(MODULE + ".ui.manipulator")
    length = man.ARROW_PX * bpy.context.preferences.view.gizmo_size / 75.0 * (bpy.context.preferences.system.ui_scale or 1)
    tip = view3d_utils.location_3d_to_region_2d(region, rv3d, c + Vector((1, 0, 0)) * (length / (p1 - c2).length))
    m = c2 + (tip - c2) * 0.6
    ev('MOUSEMOVE', 'NOTHING', x=region.x + int(m.x) + 2, y=region.y + int(m.y))
    ev('MOUSEMOVE', 'NOTHING', x=region.x + int(m.x), y=region.y + int(m.y))


@step
def s_move_arrow():
    st = state()
    check(f"Move tool: over the manipulator arrow nothing is pre-selected ({st})", st is None or not st[0])


@step
def s_arrow_shot():
    shot("gui_step74_move_arrow.png")
    bpy.ops.object.mode_set(mode='OBJECT')


run()
