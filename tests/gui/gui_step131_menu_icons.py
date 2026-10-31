"""Lane MENU (#23) in a real UI: Maya menus show the kit-drawn picture of the same command beside the items
Maya draws with an icon (Create > Polygon / NURBS Primitives, Mesh, Edit Mesh, Mesh Tools, Deform, Constrain, Key,
Windows > General Editors), made at the menu icon size before any menu opens; labels, the right-aligned Maya
hotkeys and the option-box marks stay aligned. Screenshots go to ALLSET_GUI_SHOTS (run once
with --ui-scale 0.8 = effective 1.0 on a 125 % display, once without)."""

import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, run, scale, setup, step, tap, win, load_maya_layout  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
ms = import_module(MODULE + ".ui.menu_sets")
mi = import_module(MODULE + ".ui.menu_icons")

# (shot name, menu idname, x of the mouse when it opens); Create > Measure Tools = a Maya menu without kit icons
# (the control shot for the text column)
MENUS = [
    ("control_measure_tools", ms.SUBMENU_IDS["Create/Measure Tools"], 400),
    ("poly_primitives", ms.SUBMENU_IDS["Create/Polygon Primitives"], 400),
    ("nurbs_primitives", ms.SUBMENU_IDS["Create/NURBS Primitives"], 400),
    ("mesh", ms.menu_idname("mainMeshMenu"), 400),
    ("edit_mesh", ms.menu_idname("mainEditMeshMenu"), 400),
    ("mesh_tools", ms.menu_idname("mainMeshToolsMenu"), 400),
    ("deform", ms.menu_idname("mainRigDeformationsMenu"), 400),
    ("constrain", ms.menu_idname("mainRigConstraintsMenu"), 400),
    ("key", ms.menu_idname("mainKeysMenu"), 400),
    ("general_editors", ms.SUBMENU_IDS["Windows/General Editors"], 400),
    ("visualize", ms.menu_idname("mainVisualizeMenu"), 400),      # Maya 2026 Visualize
]


def v3d():
    area = max((a for a in win().screen.areas if a.type == 'VIEW_3D'), key=lambda a: a.width * a.height)
    return area, next(r for r in area.regions if r.type == 'WINDOW')


def shot(name):
    if SHOTS:
        with bpy.context.temp_override(window=win()):
            bpy.ops.screen.screenshot(filepath=os.path.join(SHOTS, f"step131_menu_{name}_{scale():.2f}.png"))


@step
def s_setup():
    setup()
    bpy.ops.allset.make_maya(open_layout=False)
    load_maya_layout()


@step
def s_prefs():
    bpy.ops.allset.keymap_activate()
    # an open tooltip hides the popup menu from screen.screenshot: no tooltips in this session
    bpy.context.preferences.view.show_tooltips = False


for _i in range(6):      # the Maya mode switch re-registers the UI: the timer starts again from there
    step(lambda: None)


@step
def s_ready():
    mi = import_module(MODULE + ".ui.menu_icons")      # the enabled add-on's module
    n = mi.icon_px()
    check(f"menu icons made from the timer at the menu icon size {n} px before a menu opens "
          f"(ready {mi._ready[0]}, building {mi._building[0]}, left {len(mi._todo)})", mi._ready[0] == n)
    v = mi.icon_value("Create/Polygon Primitives/Cube")
    pv = next((p for p in mi._pcoll[0].values() if p.icon_id == v), None) if mi._pcoll else None
    check("Polygon Cube icon is a preview of exactly that size", pv is not None and tuple(pv.icon_size) == (n, n))
    check("no icon for an item Maya draws without one", mi.icon_value("Create/Polygon Primitives/Interactive Creation")
          == 0)


def _menu_steps(name, idname, x):
    def park():
        area, region = v3d()
        ev('MOUSEMOVE', 'NOTHING', x=x, y=region.y + region.height // 2)

    def open_menu():
        area, region = v3d()
        with bpy.context.temp_override(window=win(), area=area, region=region):
            bpy.ops.wm.call_menu(name=idname)

    def take():
        shot(name)
        tap('ESC')
        check(f"{name} menu opened with icons (see screenshot)", True)

    step(park)
    step(open_menu)
    step(lambda: None)
    step(lambda: None)
    step(take)


for _name, _idname, _x in MENUS:
    _menu_steps(_name, _idname, _x)

run()
