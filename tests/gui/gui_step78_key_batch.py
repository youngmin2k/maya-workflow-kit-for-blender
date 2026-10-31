"""In a real UI: Alt+Q hold + LMB east = Edges, Shift+Q hold + LMB = the pick mask menu (screenshot, SE =
Faces toggled on), Shift+G repeats the last create at the mouse, Ctrl+Shift+C = camera from the view, Graph Editor
3 / 1 = normalized / absolute."""

import os
import sys
from importlib import import_module

import bpy
from bpy_extras import view3d_utils
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, run, screenshot, setup, step, tap, view3d, win  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}
D = 90   # marking menu drag distance (px)


def shot(name):
    if SHOTS:
        screenshot(os.path.join(SHOTS, name))


def tool_id():
    area, region = view3d()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        t = bpy.context.workspace.tools.from_space_view3d_mode(bpy.context.mode, create=False)
    return t.idname if t else None


def screen_xy(co):
    area, region = view3d()
    p = view3d_utils.location_3d_to_region_2d(region, area.spaces.active.region_3d, co)
    return region.x + int(round(p.x)), region.y + int(round(p.y))


def centre():
    x, y = C["mid"]
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)


def mask():
    return tuple(bpy.context.scene.tool_settings.mesh_select_mode)


@step
def s_setup():
    C["mid"] = setup()
    bpy.ops.allset.keymap_activate()
    cube = bpy.data.objects["Cube"]
    for ob in bpy.context.selected_objects:
        ob.select_set(False)
    cube.select_set(True)
    bpy.context.view_layer.objects.active = cube
    bpy.context.scene.tool_settings.mesh_select_mode = (True, False, False)
    centre()
    ev('Q', 'PRESS', alt=True)


@step
def s_alt_q_lmb():
    ev('LEFTMOUSE', 'PRESS', alt=True)


@step
def s_alt_q_drag():
    x, y = C["mid"]
    for f in (1, 2, 3):
        ev('MOUSEMOVE', 'NOTHING', x=x + f * D // 3, y=y, alt=True)


@step
def s_alt_q_release():
    x, y = C["mid"]
    ev('LEFTMOUSE', 'RELEASE', x=x + D, y=y, alt=True)


@step
def s_alt_q_done():
    ev('Q', 'RELEASE', alt=True)
    check(f"Alt+Q hold + LMB east = Edges: edge mode ({bpy.context.mode}, {mask()})",
          bpy.context.mode == 'EDIT_MESH' and mask() == (False, True, False))
    check(f"Alt+Q: the select tool ({tool_id()})", tool_id() == "builtin.select_box")
    centre()
    ev('Q', 'PRESS', shift=True)


@step
def s_shift_q_lmb():
    ev('LEFTMOUSE', 'PRESS', shift=True)


@step
def s_shift_q_drag():
    x, y = C["mid"]
    for f in (1, 2, 3):   # south-east: Faces
        ev('MOUSEMOVE', 'NOTHING', x=x + f * D // 4, y=y - f * D // 4, shift=True)


@step
def s_shift_q_shot():
    s = import_module(MODULE + ".marking.draw").ACTIVE.get("session")
    check("Shift+Q hold + LMB: the pick mask marking menu is open", s is not None)
    shot("gui_step78_shift_q_menu.png")


@step
def s_shift_q_release():
    x, y = C["mid"]
    ev('LEFTMOUSE', 'RELEASE', x=x + 3 * D // 4, y=y - 3 * D // 4, shift=True)


@step
def s_shift_q_done():
    ev('Q', 'RELEASE', shift=True)
    check(f"Shift+Q menu SE Faces toggles faces into the pick mask ({mask()})", mask() == (False, True, True))
    bpy.ops.object.mode_set(mode='OBJECT')
    C["meshes"] = {o.name for o in bpy.data.objects if o.type == 'MESH'}
    area, region = view3d()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        bpy.ops.allset.create('EXEC_DEFAULT', True, kind='CUBE')   # registered, like a menu click
    C["target"] = Vector((3.0, 2.0, 0.0))
    x, y = screen_xy(C["target"])
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)


@step
def s_shift_g():
    ev('G', 'PRESS', shift=True)
    ev('G', 'RELEASE', shift=True)


@step
def s_shift_g_check():
    new = [o for o in bpy.data.objects if o.type == 'MESH' and o.name not in C["meshes"]]
    ob = bpy.context.view_layer.objects.active
    loc = ob.matrix_world.translation if ob else None
    check(f"Shift+G repeats the create ({len(new)} new meshes)", len(new) == 2)
    check(f"Shift+G puts the repeat at the mouse on the ground ({tuple(round(v, 2) for v in loc) if loc else None})",
          loc is not None and (loc - C["target"]).length < 0.05)
    shot("gui_step78_shift_g.png")
    C["cams"] = {o.name for o in bpy.data.objects if o.type == 'CAMERA'}
    centre()
    ev('C', 'PRESS', shift=True, ctrl=True)
    ev('C', 'RELEASE', shift=True, ctrl=True)


@step
def s_camera_check():
    new = [o for o in bpy.data.objects if o.type == 'CAMERA' and o.name not in C["cams"]]
    check(f"Ctrl+Shift+C creates a camera ({[o.name for o in new]})", len(new) == 1)
    if new:
        area, _region = view3d()
        view = area.spaces.active.region_3d.view_matrix
        d = (new[0].matrix_world @ view)
        err = (d.to_3x3() - d.to_3x3().Identity(3)).median_scale if False else \
            max(abs(d[i][j] - (1.0 if i == j else 0.0)) for i in range(4) for j in range(4))
        check(f"the camera sits at the view (matrix error {err:.1e}), lens {new[0].data.lens:.1f}", err < 1e-3)
    area, _region = view3d()
    C["old_type"] = area.ui_type
    area.ui_type = 'FCURVES'


@step
def s_graph():
    area = next(a for a in win().screen.areas if a.ui_type == 'FCURVES')
    region = next(r for r in area.regions if r.type == 'WINDOW')
    C["graph"] = area
    ev('MOUSEMOVE', 'NOTHING', x=region.x + region.width // 2, y=region.y + region.height // 2)
    tap('THREE')


@step
def s_graph_three():
    sp = C["graph"].spaces.active
    check(f"Graph Editor 3 = normalized ({sp.use_normalization})", sp.use_normalization)
    tap('ONE')


@step
def s_graph_one():
    sp = C["graph"].spaces.active
    check(f"Graph Editor 1 = absolute ({sp.use_normalization})", not sp.use_normalization)
    C["graph"].ui_type = C["old_type"]


run()
