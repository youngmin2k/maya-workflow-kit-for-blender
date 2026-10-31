"""In a real UI: Maya marking menus as pies — RMB press-drag-release over the cube,
Shift+RMB / Ctrl+RMB pies, W hold + LMB tool options; screenshots."""

import os
import sys

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import check, ev, run, step, setup, screenshot, tap, view3d, win  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}
DRAG = 120  # px, well past the pie threshold


def shot(name):
    if SHOTS:
        screenshot(os.path.join(SHOTS, name))


def cube():
    return bpy.data.objects["Cube"]


@step
def s_setup():
    C["x"], C["y"] = setup()
    check("Maya keymap active", sys.modules["sim"].maya_keys())
    # Deselect: the RMB menu must target the object under the mouse, not the selection.
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    bpy.context.view_layer.objects.active = None
    ev('RIGHTMOUSE', 'PRESS', x=C["x"], y=C["y"])  # over the cube (factory scene, centred)


def _drawn(key="N", dx=0, dy=DRAG):
    """Where the drag to the radial box ``key`` ends: (dx, dy) from the press (the ring stays at the press
    point wherever the list goes)."""
    return C["x"] + dx, C["y"] + dy


@step
def s_rmb_open():
    shot("gui_step8_rmb_object.png")
    C["at"] = x, y = _drawn()
    ev('MOUSEMOVE', 'NOTHING', x=(C["x"] + x) // 2, y=(C["y"] + y) // 2)
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)


@step
def s_rmb_release():
    ev('RIGHTMOUSE', 'RELEASE', x=C["at"][0], y=C["at"][1])


@step
def s_rmb_done():
    ts = bpy.context.scene.tool_settings
    check("RMB drag north + release = Edge (RMB_MESH N)",
          bpy.context.mode == 'EDIT_MESH' and tuple(ts.mesh_select_mode) == (False, True, False))
    check("the picked cube became the active object", bpy.context.view_layer.objects.active == cube())
    ev('MOUSEMOVE', 'NOTHING', x=C["x"], y=C["y"])
    ev('RIGHTMOUSE', 'PRESS', x=C["x"], y=C["y"], shift=True)


@step
def s_shift_rmb():
    shot("gui_step8_shift_rmb_edge.png")
    ev('RIGHTMOUSE', 'RELEASE', shift=True)  # quick release: the pie stays open
    C["open"] = True


@step
def s_shift_rmb_esc():
    tap('ESC')
    ev('RIGHTMOUSE', 'PRESS', x=C["x"], y=C["y"], ctrl=True)


@step
def s_ctrl_rmb():
    shot("gui_step8_ctrl_rmb_convert.png")
    ev('RIGHTMOUSE', 'RELEASE', ctrl=True)


@step
def s_ctrl_esc():
    tap('ESC')
    # NE "Object Mode" from the component menu: back to objects (Maya: the reverse).
    ev('RIGHTMOUSE', 'PRESS', x=C["x"], y=C["y"])


@step
def s_back_wait():
    pass        # the component menu is drawn before the drag aims at its NE box


@step
def s_back_drag():
    C["at"] = x, y = _drawn("NE", DRAG, DRAG)
    ev('MOUSEMOVE', 'NOTHING', x=(C["x"] + x) // 2, y=(C["y"] + y) // 2)
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)


@step
def s_back_release():
    ev('RIGHTMOUSE', 'RELEASE', x=C["at"][0], y=C["at"][1])


@step
def s_object_mode():
    check("RMB in component mode, drag NE = Object Mode", bpy.context.mode == 'OBJECT')
    slot = bpy.context.scene.transform_orientation_slots[1]   # the Move tool's axis
    slot.type = 'LOCAL'
    ev('MOUSEMOVE', 'NOTHING', x=C["x"], y=C["y"])
    ev('W', 'PRESS')


@step
def s_w_held():
    ev('LEFTMOUSE', 'PRESS', x=C["x"], y=C["y"])


@step
def s_w_pie():
    tool = bpy.context.workspace.tools.from_space_view3d_mode('OBJECT', create=False)
    check("W press switches to the Move tool", tool is not None and tool.idname == "builtin.move")
    shot("gui_step8_w_move_options.png")
    ev('MOUSEMOVE', 'NOTHING', x=C["x"] - DRAG // 2, y=C["y"])
    ev('MOUSEMOVE', 'NOTHING', x=C["x"] - DRAG, y=C["y"])


@step
def s_w_release():
    ev('LEFTMOUSE', 'RELEASE', x=C["x"] - DRAG, y=C["y"])


@step
def s_w_key_release():
    ev('W', 'RELEASE')


@step
def s_w_done():
    slot = bpy.context.scene.transform_orientation_slots[1]   # the Move tool's axis
    check(f"W + LMB drag west = World orientation (got {slot.type})", slot.type == 'GLOBAL')
    ev('MOUSEMOVE', 'NOTHING', x=C["x"], y=C["y"])
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    ev('RIGHTMOUSE', 'PRESS', x=C["x"], y=C["y"], shift=True)


@step
def s_default_pie():
    check("nothing selected: Shift+RMB opens", True)
    shot("gui_step8_shift_rmb_create.png")
    ev('RIGHTMOUSE', 'RELEASE', shift=True)


@step
def s_end():
    tap('ESC')


run()
