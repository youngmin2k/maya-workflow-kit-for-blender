"""In a real UI: edit-mode marquee selects occluded vertices (Maya selectPrefUseDepth
false) with the X-ray flag set only during the drag; Move tool fallback marquee too; option off =
Blender's visible-only selection; pre-selection highlight with the select tools; screenshots."""

import os
import sys
from importlib import import_module

import bmesh
import bpy
from bpy_extras import view3d_utils

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, run, step, setup, screenshot, view3d  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


def shot(name):
    if SHOTS:
        screenshot(os.path.join(SHOTS, name))


def cube():
    return bpy.data.objects["Cube"]


def shading():
    return view3d()[0].spaces.active.shading


def prefs():
    return bpy.context.preferences.addons[MODULE].preferences


def rect():
    area, region = view3d()
    rv3d = area.spaces.active.region_3d
    ob = cube()
    pts = [view3d_utils.location_3d_to_region_2d(region, rv3d, ob.matrix_world @ v.co) for v in ob.data.vertices]
    xs, ys = [p.x for p in pts], [p.y for p in pts]
    m = 25
    return (region.x + int(min(xs)) - m, region.y + int(min(ys)) - m,
            region.x + int(max(xs)) + m, region.y + int(max(ys)) + m)


def selected():
    bm = bmesh.from_edit_mesh(cube().data)
    return sum(v.select for v in bm.verts)


def deselect():
    bpy.ops.mesh.select_all(action='DESELECT')


def set_tool(idname):
    area, region = view3d()
    with bpy.context.temp_override(window=bpy.context.window_manager.windows[0], area=area, region=region):
        bpy.ops.wm.tool_set_by_id(name=idname)


@step
def s_setup():
    setup()
    bpy.context.view_layer.objects.active = cube()
    cube().select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_mode(type='VERT')
    deselect()
    C["r"] = rect()
    C["alpha"] = shading().xray_alpha
    check("starts without X-ray", not shading().show_xray)


def drag(tag, mid_check=None):
    @step
    def press():
        x0, y0 = C["r"][:2]
        ev('MOUSEMOVE', 'NOTHING', x=x0, y=y0)
        ev('LEFTMOUSE', 'PRESS', x=x0, y=y0)

    @step
    def move():
        x0, y0, x1, y1 = C["r"]
        ev('MOUSEMOVE', 'NOTHING', x=(x0 + x1) // 2, y=(y0 + y1) // 2)
        ev('MOUSEMOVE', 'NOTHING', x=x1, y=y1)

    @step
    def during():
        C[tag + "_during"] = (shading().show_xray, shading().xray_alpha)
        if mid_check:
            mid_check()

    @step
    def release():
        x1, y1 = C["r"][2:]
        ev('LEFTMOUSE', 'RELEASE', x=x1, y=y1)

    @step
    def result():
        C[tag] = selected()

    @step
    def settle():   # the watch timer restores the view after the select modal ended
        pass


def _shot_during():
    shot("gui_step30_marquee_drag.png")


drag("through", _shot_during)


@step
def s_through():
    check("marquee in edit mode selects all 8 cube vertices (occluded one too)", C["through"] == 8)
    check("X-ray flag on with alpha 1.0 while dragging", C["through_during"] == (True, 1.0))
    check("X-ray off and alpha back after the drag",
          not shading().show_xray and abs(shading().xray_alpha - C["alpha"]) < 1e-6)
    shot("gui_step30_marquee_done.png")
    deselect()
    set_tool("builtin.move")


drag("fallback")


@step
def s_fallback():
    check(f"Move tool: marquee in empty space (fallback select box) selects 8 ({C['fallback']})", C["fallback"] == 8)
    check("X-ray restored after the fallback drag", not shading().show_xray)
    set_tool("builtin.select_box")
    deselect()
    prefs().select_through = False


drag("off")


@step
def s_off():
    check("option off: Blender visible-only marquee (7 of 8)", C["off"] == 7)
    check("option off: X-ray never touched", C["off_during"][0] is False)
    prefs().select_through = True
    deselect()
    shading().show_xray = True
    shading().xray_alpha = 0.5


drag("user_xray")


@step
def s_user_xray():
    check("user X-ray on: selects 8 and stays on with the user's alpha",
          C["user_xray"] == 8 and shading().show_xray and abs(shading().xray_alpha - 0.5) < 1e-6)
    shading().show_xray = False
    deselect()
    C["pre"] = import_module(MODULE + ".operators.preselect")
    C["v"] = front_vert()
    x, y = vert_xy(C["v"])
    ev('MOUSEMOVE', 'NOTHING', x=x + 30, y=y + 30)


def vert_xy(i, ob=None):
    area, region = view3d()
    rv3d = area.spaces.active.region_3d
    ob = ob or cube()
    p = view3d_utils.location_3d_to_region_2d(region, rv3d, ob.matrix_world @ ob.data.vertices[i].co)
    return region.x + int(p.x), region.y + int(p.y)


def front_vert():
    area, _region = view3d()
    eye = area.spaces.active.region_3d.view_matrix.inverted().translation
    return min(range(8), key=lambda i: (cube().matrix_world @ cube().data.vertices[i].co - eye).length)


def gz_state():
    gz = C["pre"].gizmo()
    return None if gz is None else (gz.is_highlight, gz.vert_index, gz.edge_index, gz.face_index)


@step
def s_pre_hover():
    x, y = vert_xy(C["v"])
    ev('MOUSEMOVE', 'NOTHING', x=x + 2, y=y + 1)
    ev('MOUSEMOVE', 'NOTHING', x=x + 1, y=y + 1)


@step
def s_pre_hover_check():
    st = gz_state()
    check("pre-selection: hovering a vertex highlights it", st is not None and st[0] and st[1] == C["v"])


@step
def s_pre_shot():
    shot("gui_step30_preselect_vertex.png")
    x, y = vert_xy(C["v"])
    ev('LEFTMOUSE', 'PRESS', x=x + 1, y=y + 1)
    ev('LEFTMOUSE', 'RELEASE', x=x + 1, y=y + 1)


@step
def s_pre_click():
    bm = bmesh.from_edit_mesh(cube().data)
    check("click on the highlighted vertex still selects it",
          [v.index for v in bm.verts if v.select] == [C["v"]])
    deselect()
    # A marquee that starts on the highlighted vertex is still a marquee.
    x, y = vert_xy(C["v"])
    C["drag_from"] = (x + 1, y + 1)
    ev('LEFTMOUSE', 'PRESS', x=x + 1, y=y + 1)


@step
def s_pre_drag_move():
    x, y = C["drag_from"]
    ev('MOUSEMOVE', 'NOTHING', x=x - 60, y=y - 60)
    ev('MOUSEMOVE', 'NOTHING', x=x - 160, y=y - 160)


@step
def s_pre_drag_release():
    x, y = C["drag_from"]
    ev('LEFTMOUSE', 'RELEASE', x=x - 160, y=y - 160)


@step
def s_pre_drag_done():
    check("marquee starting on a highlighted vertex selects (box, not swallowed)", selected() >= 2)
    deselect()
    bpy.ops.mesh.select_mode(type='FACE')
    x, y = vert_xy(C["v"])
    ev('MOUSEMOVE', 'NOTHING', x=x + 20, y=y - 25)
    ev('MOUSEMOVE', 'NOTHING', x=x + 21, y=y - 26)


@step
def s_pre_face():
    st = gz_state()
    with bpy.context.temp_override(window=bpy.context.window_manager.windows[0], area=view3d()[0]):
        on = C["pre"]._enabled(bpy.context)
    # face mode lights the face under the cursor (the kit gizmo follows the select mode).
    check(f"face mode: the face under the cursor is pre-selected, not a vertex ({st})",
          on and st is not None and st[0] and st[1] == -1 and st[3] >= 0)


@step
def s_pre_face_shot():
    shot("gui_step30_preselect_face.png")
    bpy.ops.mesh.select_mode(type='VERT')
    set_tool("builtin.move")
    x, y = vert_xy(C["v"])
    ev('MOUSEMOVE', 'NOTHING', x=x + 2, y=y + 1)
    ev('MOUSEMOVE', 'NOTHING', x=x + 1, y=y + 1)


@step
def s_pre_move_tool():
    with bpy.context.temp_override(window=bpy.context.window_manager.windows[0], area=view3d()[0]):
        on = C["pre"]._enabled(bpy.context)
    st = gz_state()
    # the Move tool keeps pre-selection (Maya pre_06); nothing is selected, so no manipulator.
    check(f"Move tool: the vertex is pre-selected ({st})", on and st is not None and st[0] and st[1] == C["v"])
    set_tool("builtin.select_box")


run()
