"""In a real UI (Maya Workflow Kit layout): the Shift+Q pick-mask menu shows check boxes for Faces (and Poly Vertices /
Poly Edges in their submenus), a Status Line selection mask turned off survives File > New, and the Tool Settings
popup has Maya's Reset Tool button."""

import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, run, step, setup, screenshot, view3d, win, load_maya_layout  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


def centre():
    _a, r = view3d()
    C["x"], C["y"] = r.x + r.width // 2, r.y + r.height // 2
    ev('MOUSEMOVE', 'NOTHING', x=C["x"], y=C["y"])


def redraw():
    for a in win().screen.areas:
        a.tag_redraw()


@step
def s_setup():
    setup()
    load_maya_layout()


@step
def s_scene():
    bpy.ops.allset.keymap_activate()
    area, region = view3d()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        bpy.ops.allset.create(kind='CUBE')
        bpy.ops.object.mode_set(mode='EDIT')
    bpy.context.scene.tool_settings.mesh_select_mode = (True, False, True)   # vertices + faces
    centre()
    ev('Q', 'PRESS', shift=True, x=C["x"], y=C["y"])


@step
def s_lmb():
    ev('LEFTMOUSE', 'PRESS', shift=True, x=C["x"], y=C["y"])


@step
def s_menu_wait():
    redraw()


@step
def s_menu_shot():
    d = import_module(MODULE + ".marking.draw")
    s = d.ACTIVE.get("session")
    check("Shift+Q hold + LMB shows the pick-mask menu", s is not None)
    if s is not None:
        faces = [it for it in s.layout.items if it.label == "Faces"]
        check(f"Faces is a check box, on ({[d.checked(it.action) for it in faces]})",
              faces and d.checked(faces[0].action) is True)
    if SHOTS:
        screenshot(os.path.join(SHOTS, "gui_step93_shift_q.png"))


@step
def s_release():
    ev('LEFTMOUSE', 'RELEASE', shift=True, x=C["x"], y=C["y"])
    ev('Q', 'RELEASE', shift=True, x=C["x"], y=C["y"])


@step
def s_mask_off():
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    status_line = import_module(MODULE + ".ui.status_line")
    status_line.set_mask("SURFACES", False)              # Status Line: meshes not selectable
    load_maya_layout()     # File > New


@step
def s_after_new():
    bpy.ops.allset.keymap_activate()
    area, _r = view3d()
    sp = area.spaces.active
    check(f"after File > New meshes are still unselectable (show_object_select_mesh {sp.show_object_select_mesh})",
          not sp.show_object_select_mesh)
    check("other masks untouched", sp.show_object_select_camera and sp.show_object_select_light)
    status_line = import_module(MODULE + ".ui.status_line")
    status_line.set_mask("SURFACES", True)
    centre()
    area, region = view3d()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        bpy.ops.wm.tool_set_by_id(name="builtin.move")
        bpy.ops.wm.call_panel(name="VIEW3D_PT_active_tool", keep_open=True)


@step
def s_panel_wait():
    redraw()


@step
def s_panel_shot():
    if SHOTS:
        screenshot(os.path.join(SHOTS, "gui_step93_reset_tool.png"))
    tool_settings = import_module(MODULE + ".ui.tool_settings")
    check("the Tool Settings panel draws the Reset Tool row",
          tool_settings.draw_reset_row in bpy.types.VIEW3D_PT_active_tool._dyn_ui_initialize())
    ev('ESC', 'PRESS')
    ev('ESC', 'RELEASE')


run()
