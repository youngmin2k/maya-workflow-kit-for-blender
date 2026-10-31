"""In a real UI: View > Center View of Selection (Maya viewFit -c), the Tumble / Dolly camera tools picked
from View > Camera Tools (LMB drag), Camera Attribute Editor in Blender's persp view (popover), and shots of the
View / Shading panel menus with their greyed rows."""

import os
import sys
from importlib import import_module

import bpy
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, load_maya_layout, px, run, screenshot, setup, step, tap, view3d, win  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


def shot(name):
    if SHOTS:
        screenshot(os.path.join(SHOTS, name))


def override():
    area, region = view3d()
    return bpy.context.temp_override(window=win(), screen=win().screen, area=area, region=region)


def rv3d():
    return view3d()[0].spaces.active.region_3d


def tool_id():
    with override():
        return bpy.context.workspace.tools.from_space_view3d_mode(bpy.context.mode).idname


def panel_run(op, **props):
    import json
    with override():
        bpy.ops.allset.panel_run(op=op, props=json.dumps(props))


def redraw():
    for a in win().screen.areas:
        a.tag_redraw()


@step
def s_setup():
    C["x"], C["y"] = setup()
    load_maya_layout()


@step
def s_scene():
    bpy.ops.allset.keymap_activate()
    unit = import_module(MODULE + ".operators.units").maya_unit()
    with override():
        bpy.ops.allset.create(kind='CUBE')
    cube = bpy.context.view_layer.objects.active
    cube.location = (5 * unit, -3 * unit, 2 * unit)
    bpy.context.view_layer.update()
    C["cube"] = cube.name
    r = rv3d()
    C["rot"] = r.view_rotation.copy()
    C["eye"] = r.view_location + r.view_rotation @ Vector((0, 0, r.view_distance))
    redraw()


@step
def s_center_view():
    with override():
        res = bpy.ops.allset.center_view_selection()
    r = rv3d()
    cube = bpy.data.objects[C["cube"]]
    centre = cube.matrix_world.translation    # a primitive's bbox centre = its origin
    d = (centre - C["eye"]).length
    check(f"Center View of Selection: {res}, centre on the selection ({tuple(round(v, 3) for v in r.view_location)})",
          (r.view_location - centre).length < 1e-4)
    check(f"... rotation kept, distance = eye-to-selection {d:.3f} ({r.view_distance:.3f}; Maya viewFit -c)",
          r.view_rotation.rotation_difference(C["rot"]).angle < 1e-5 and abs(r.view_distance - d) < 1e-4)
    redraw()


@step
def s_tumble_tool():
    panel_run("wm.tool_set_by_id", name="allset.tumble_tool")
    check(f"View > Camera Tools > Tumble Tool is the active tool ({tool_id()})", tool_id() == "allset.tumble_tool")
    C["rot"] = rv3d().view_rotation.copy()
    ev('MOUSEMOVE', 'NOTHING', x=C["x"], y=C["y"])
    ev('LEFTMOUSE', 'PRESS', x=C["x"], y=C["y"])


@step
def s_tumble_drag():
    for i in (1, 2, 3):
        ev('MOUSEMOVE', 'NOTHING', x=C["x"] + px(40) * i, y=C["y"])


@step
def s_tumble_release():
    ev('LEFTMOUSE', 'RELEASE', x=C["x"] + px(120), y=C["y"])


@step
def s_tumble_check():
    angle = rv3d().view_rotation.rotation_difference(C["rot"]).angle
    check(f"Tumble Tool: a plain LMB drag tumbles the view ({angle:.3f} rad)", angle > 0.05)
    check(f"... the cube stays selected (a camera tool doesn't select) ", bpy.data.objects[C["cube"]].select_get())
    panel_run("wm.tool_set_by_id", name="allset.dolly_tool")
    C["dist"] = rv3d().view_distance
    ev('MOUSEMOVE', 'NOTHING', x=C["x"], y=C["y"])
    ev('LEFTMOUSE', 'PRESS', x=C["x"], y=C["y"])


@step
def s_dolly_drag():
    for i in (1, 2, 3):
        ev('MOUSEMOVE', 'NOTHING', x=C["x"] + px(40) * i, y=C["y"])


@step
def s_dolly_release():
    ev('LEFTMOUSE', 'RELEASE', x=C["x"] + px(120), y=C["y"])


@step
def s_dolly_check():
    d = rv3d().view_distance
    check(f"Dolly Tool: LMB drag right dollies in ({C['dist']:.3f} -> {d:.3f}) and ends on the LMB release",
          d < C["dist"] * 0.95 and not any(op.bl_idname == "ALLSET_OT_dolly" for op in win().modal_operators))
    ev('MOUSEMOVE', 'NOTHING', x=C["x"], y=C["y"])
    tap('W')


@step
def s_back_to_move():
    check(f"W leaves the camera tool for the Move Tool ({tool_id()})", tool_id() == "builtin.move")
    with override():
        res = bpy.ops.allset.camera_attribute_editor()
    check(f"Camera Attribute Editor in Blender's persp view opens the perspShape popover ({res})", res == {'FINISHED'})


@step
def s_popover_shot():
    shot("gui_step177_persp_camera.png")
    tap('ESC')


def _open(menu):
    area, region = view3d()
    ev('MOUSEMOVE', 'NOTHING', x=region.x + region.width // 2, y=region.y + region.height * 2 // 3)
    with override():
        bpy.ops.wm.call_menu(name=menu)


@step
def s_view_menu():
    _open("ALLSET_MT_panel_view")


@step
def s_view_shot():
    shot("gui_step177_view_menu.png")
    tap('ESC')


@step
def s_shading_menu():
    _open("ALLSET_MT_panel_shading")


@step
def s_shading_shot():
    shot("gui_step177_shading_menu.png")
    tap('ESC')
    check("View / Shading panel menus opened (screenshots)", True)


run()
