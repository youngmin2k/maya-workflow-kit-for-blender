"""In a real UI: Windows > General Editors submenu, Windows > Animation Editors >
Graph Editor opens a Graph Editor window, Display > Heads Up Display > Poly Count turns the
viewport statistics on, File > Export Selection menu; screenshots."""

import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, run, step, setup, screenshot, view3d, win  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


def shot(name):
    if SHOTS:
        screenshot(os.path.join(SHOTS, name))


def menu_id(path):
    """Blender Menu idname drawn for a Maya submenu path."""
    menu_sets = import_module(MODULE + ".ui.menu_sets")
    top = path.split("/")[0]
    name = next(n for n, (label, *_r) in import_module(MODULE + ".ui.menu_data").MENUS.items() if label == top)
    root = menu_sets.menu_idname(name)
    for cls_name in dir(bpy.types):
        cls = getattr(bpy.types, cls_name)
        if cls_name.startswith(root) and getattr(cls, "__doc__", "") == f"Maya menu: {path}":
            return cls_name
    return None


@step
def s_setup():
    setup()
    C["windows0"] = len(bpy.context.window_manager.windows)


@step
def s_open_windows():   # one tick after setup: the splash is gone
    with bpy.context.temp_override(window=win()):
        bpy.ops.wm.call_menu(name=menu_id("Windows"))


@step
def s_wait1():
    pass


@step
def s_windows_shot():
    shot("gui_step34_windows_menu.png")
    C["general"] = menu_id("Windows/General Editors")
    check("Windows > General Editors is a submenu", C["general"] is not None)
    # Hover the "General Editors" row of the open menu (placed at the mouse; rows read
    # on the first screenshot: 25 px apart, General Editors 104 px under the menu title).
    h = win().height
    C["rows"] = {"General Editors": (560, h - 463), "Animation Editors": (560, h - 513)}
    x, y = C["rows"]["General Editors"]
    ev('MOUSEMOVE', 'NOTHING', x=x - 20, y=y)
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)


@step
def s_wait2():
    pass


@step
def s_wait2b():
    pass


@step
def s_general_shot():
    shot("gui_step34_general_editors.png")
    x, y = C["rows"]["Animation Editors"]
    ev('MOUSEMOVE', 'NOTHING', x=x - 20, y=y)
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)


@step
def s_wait3():
    pass


@step
def s_wait3b():
    pass


@step
def s_anim_shot():
    shot("gui_step34_animation_editors.png")
    for _ in range(3):
        ev('ESC', 'PRESS')
        ev('ESC', 'RELEASE')


@step
def s_open_graph():
    with bpy.context.temp_override(window=win()):
        res = bpy.ops.allset.open_editor(ui_type='FCURVES')
    places = import_module(MODULE + ".ui.window_places")
    check("Graph Editor opens", res == {'FINISHED'} or places.deferred())   # may open one tick later


@step
def s_graph_window():
    wins = bpy.context.window_manager.windows
    check(f"a new window ({C['windows0']} -> {len(wins)})", len(wins) == C["windows0"] + 1)
    if len(wins) > C["windows0"]:
        area = wins[-1].screen.areas[0]
        check(f"the new window is a Graph Editor ({area.ui_type})", area.ui_type == 'FCURVES')
        with bpy.context.temp_override(window=wins[-1]):
            bpy.ops.wm.window_close()


@step
def s_hud():
    area, region = view3d()
    overlay = area.spaces.active.overlay
    C["stats0"] = overlay.show_stats
    menu_sets = import_module(MODULE + ".ui.menu_sets")
    kind, target, props = import_module(MODULE + ".ui.menu_map").spec("Display/Heads Up Display/Poly Count")
    import json
    with bpy.context.temp_override(window=win()):
        bpy.ops.allset.menu_run(op=target, props=json.dumps(props))
    check("Heads Up Display > Poly Count toggles the statistics overlay",
          overlay.show_stats != C["stats0"])
    _ = menu_sets
    ev('MOUSEMOVE', 'NOTHING', x=region.x + 300, y=region.y + 300)


@step
def s_hud_shot():
    shot("gui_step34_poly_count.png")
    with bpy.context.temp_override(window=win()):
        bpy.ops.wm.call_menu(name="ALLSET_MT_export_selection")


@step
def s_export_shot():
    shot("gui_step34_export_selection.png")
    ev('ESC', 'PRESS')
    ev('ESC', 'RELEASE')


run()
