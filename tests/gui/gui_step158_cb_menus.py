"""In the Maya Workflow Kit layout: RMB on the Channel Box's empty space opens Maya's
Channels menu (its first row Key Selected keys the selected channel), Ctrl+RMB opens the Edit menu (shot), the
point light's Color R row is a selectable channel (click selects it). Shots with ``--shots``."""

import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import (MODULE, check, dock_area, dock_region, ev, find_button, load_maya_layout, run,  # noqa: E402
                 screenshot, setup, step, tap, view3d, win)

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
os.environ["ALLSET_FIT_WARP"] = "1"
C = {}
GUI_TIMEOUT = 240


def cbm():
    return import_module(f"{MODULE}.ui.channel_box")


def redraw():
    for a in win().screen.areas:
        a.tag_redraw()


def shot(name):
    if SHOTS:
        screenshot(os.path.join(SHOTS, f"gui_step158_{name}.png"))


def dock():
    return dock_area(), dock_region()


def override():
    area, region = view3d()
    return bpy.context.temp_override(window=win(), area=area, region=region, space_data=area.spaces.active)


def empty_spot():
    """A point in the Channel Box part with no button: the left margin, just above the Layer Editor split."""
    _a, r = dock()
    u = cbm()._unit(bpy.context)
    share = cbm().cb_share(r, u)
    return r.x + 3, int(r.y + r.height - share * r.height + 6)


@step
def s_setup():
    setup()
    load_maya_layout()


@step
def s_keymap():
    bpy.ops.allset.keymap_activate()
    _a, r = view3d()
    ev('MOUSEMOVE', 'NOTHING', x=r.x + r.width // 2, y=r.y + r.height // 2)
    redraw()


for _i in range(10):
    step(redraw)


@step
def s_cube():
    with override():
        bpy.ops.allset.create(kind='CUBE')
    bpy.context.scene.frame_set(7)
    bpy.context.window_manager.allset_dock = 'CHANNEL_BOX'
    cbm().set_selected_channels(["tx"])
    redraw()


@step
def s_hover_empty():
    x, y = C["empty"] = empty_spot()
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)


@step
def s_hover_empty2():
    x, y = C["empty"]
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y + 1)


@step
def s_rmb_empty():
    watching = bool(cbm()._watching)
    check(f"the Channel Box watcher runs over its empty space ({watching}, at {C['empty']})", watching)
    ev('RIGHTMOUSE', 'PRESS')
    ev('RIGHTMOUSE', 'RELEASE')


@step
def s_menu_shot():
    shot("rmb_empty_menu")


@step
def s_pick():
    # Maya's Channels menu is taller than the space under the mouse, so Blender slides it up: pick Key Selected by
    # its underlined letter (K) instead of a row position
    tap('K')


@step
def s_picked():
    ob = bpy.data.objects["pCube1"]
    curves = import_module(MODULE + ".compat").id_fcurves(ob) if ob.animation_data else []
    keyed = [(fc.data_path, fc.array_index) for fc in curves]
    check(f"RMB on empty Channel Box space = Channels menu, first row Key Selected keys Translate X ({keyed})",
          keyed == [("location", 0)])
    tap('ESC')
    x, y = C["empty"]
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)


@step
def s_ctrl_rmb():
    ev('LEFT_CTRL', 'PRESS')
    ev('RIGHTMOUSE', 'PRESS', ctrl=True)
    ev('RIGHTMOUSE', 'RELEASE', ctrl=True)
    ev('LEFT_CTRL', 'RELEASE')


@step
def s_ctrl_wait():
    redraw()


@step
def s_ctrl_shot():
    shot("ctrl_rmb_edit_menu")
    sel = cbm().selected_channels()
    check(f"Ctrl+RMB keeps the channel selection ({sel})", sel == ["tx"])
    tap('ESC')


# --- a light's Intensity is a channel --------------------------------------------------------------------------

@step
def s_light():
    _a, r = view3d()
    ev('MOUSEMOVE', 'NOTHING', x=r.x + r.width // 2, y=r.y + r.height // 2)
    with override():
        bpy.ops.allset.create(kind='POINT_LIGHT')
    cbm().set_selected_channels([])
    cbm().rebuild_rows()
    redraw()


@step
def s_light_wait():
    redraw()


step(find_button(dock, lambda p, _c: p.endswith(".sel") and "rows[" in p and _is_color_r(p), C, "int_name",
                 x_frac=0.25, step_px=6))


def _is_color_r(path):
    import re
    m = re.search(r"rows\[(\d+)\]", path)
    rows = bpy.context.scene.allset_cb.rows
    return m is not None and int(m.group(1)) < len(rows) and rows[int(m.group(1))].name == "maya:colorR"


@step
def s_int_hover():
    check(f"Color R row name found ({C.get('int_name')})", C.get("int_name") is not None)
    if C.get("int_name"):
        x, y = C["int_name"]
        ev('MOUSEMOVE', 'NOTHING', x=x, y=y)


@step
def s_int_click():
    if C.get("int_name"):
        ev('LEFTMOUSE', 'PRESS')
        ev('LEFTMOUSE', 'RELEASE')


@step
def s_int_check():
    redraw()
    sel = cbm().selected_channels()
    check(f"clicking Color R selects the SHAPES channel ({sel})", sel == ["sh:maya:colorR"])


@step
def s_int_shot():
    shot("light_intensity_selected")


run()
