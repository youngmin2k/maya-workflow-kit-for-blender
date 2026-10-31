"""#54: in a real UI: the Maya menus #54 named (Deform, Mesh Tools, Mesh Display, Effects, Fields > Solvers)
show the kit's new menu-only drawings (ui/menu_drawings*.py) on every item Maya draws with an icon, made at the menu
icon size before a menu opens. Screenshots go to ALLSET_GUI_SHOTS (look at them: icons readable, labels aligned)."""

import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, run, scale, setup, step, tap, win, load_maya_layout  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
ms = import_module(MODULE + ".ui.menu_sets")

MENUS = [
    ("deform", ms.menu_idname("mainRigDeformationsMenu")),
    ("deform_nonlinear", ms.SUBMENU_IDS["Deform/Nonlinear"]),
    ("mesh_tools", ms.menu_idname("mainMeshToolsMenu")),
    ("mesh_display", ms.menu_idname("mainMeshDisplayMenu")),
    ("effects", ms.menu_idname("mainDynEffectsMenu")),
    ("fields_solvers", ms.menu_idname("mainFieldsSolverMenu")),
]


def v3d():
    area = max((a for a in win().screen.areas if a.type == 'VIEW_3D'), key=lambda a: a.width * a.height)
    return area, next(r for r in area.regions if r.type == 'WINDOW')


def shot(name):
    if SHOTS:
        with bpy.context.temp_override(window=win()):
            bpy.ops.screen.screenshot(filepath=os.path.join(SHOTS, f"step142_menu_{name}_{scale():.2f}.png"))


@step
def s_setup():
    setup()
    bpy.ops.allset.make_maya(open_layout=False)
    load_maya_layout()


@step
def s_prefs():
    bpy.ops.allset.keymap_activate()
    bpy.context.preferences.view.show_tooltips = False     # a tooltip hides the popup from screen.screenshot


for _i in range(6):      # the Maya mode switch re-registers the UI: the preview timer starts again from there
    step(lambda: None)


@step
def s_ready():
    mi = import_module(MODULE + ".ui.menu_icons")
    data = import_module(MODULE + ".ui.menu_icon_data")
    n = mi.icon_px()
    check(f"menu icons (incl. menu drawings) made at {n} px before a menu opens (ready {mi._ready[0]})",
          mi._ready[0] == n)
    for path in ("Deform/Nonlinear/Bend", "Mesh Tools/Insert Edge Loop", "Mesh Display/Soften Edge",
                 "Effects/Fire", "Fields/Solvers/Gravity", "Deform/Wire"):
        pic = data.ICONS.get(path)
        v = mi.icon_value(path)
        pv = next((p for p in mi._pcoll[0].values() if p.icon_id == v), None) if mi._pcoll and v else None
        check(f"{path}: menu drawing {pic} has a {n} px preview", pic is not None and pic[0] == "menu"
              and pv is not None and tuple(pv.icon_size) == (n, n))


def _menu_steps(name, idname):
    def park():
        area, region = v3d()
        ev('MOUSEMOVE', 'NOTHING', x=400, y=region.y + region.height // 2)

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


for _name, _idname in MENUS:
    _menu_steps(_name, _idname)

run()
