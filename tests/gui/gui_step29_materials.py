"""In a real UI: material items of the RMB marking menu (Favorite submenu, Existing
submenu), Lighting/Shading menu, Material Attributes in the Attribute Editor, Shift+T; screenshots."""

import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, run, step, setup, screenshot, tap, view3d, win  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


def shot(name):
    if SHOTS:
        screenshot(os.path.join(SHOTS, name))


def cube():
    return bpy.data.objects["Cube"]


def session():
    return C["draw"].ACTIVE.get("session")


def item_xy(label):
    """Window position of a list row of the open marking menu (its label without ▸)."""
    s = session()
    it = next(i for i in s.layout.items if i.label == label)
    _area, r = view3d()
    cx, cy = s.center
    x0, y0, x1, y1 = it.rect
    return r.x + int(cx + (x0 + x1) / 2), r.y + int(cy + (y0 + y1) / 2)


def rmb_click():
    ev('MOUSEMOVE', 'NOTHING', x=C["x"], y=C["y"])
    ev('RIGHTMOUSE', 'PRESS', x=C["x"], y=C["y"])
    ev('RIGHTMOUSE', 'RELEASE', x=C["x"], y=C["y"])  # quick click: click mode


def click(x, y):
    ev('LEFTMOUSE', 'PRESS', x=x, y=y)
    ev('LEFTMOUSE', 'RELEASE', x=x, y=y)


@step
def s_setup():
    C["x"], C["y"] = setup()
    C["draw"] = import_module(MODULE + ".marking.draw")
    bpy.data.materials.new("blinn5")
    # Nothing selected: the RMB menu's material items act on the object under the mouse.
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    rmb_click()


@step
def s_rmb_open():
    s = session()
    check("RMB click keeps the object menu open", s is not None and s.mode == "CLICK")
    labels = [i.label for i in s.layout.items]
    check("RMB list ends with Maya's material items",
          labels[-4:] == ["Material Attributes...", "Assign New Material", "Assign Favorite Material",
                          "Assign Existing Material"])


@step
def s_rmb_shot():
    shot("gui_step29_rmb_materials.png")
    x, y = item_xy("Assign Favorite Material")
    ev('MOUSEMOVE', 'NOTHING', x=x - 10, y=y)
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)


@step
def s_favorite_open():
    s = session()
    check("hovering Assign Favorite Material opens its submenu", s is not None and len(s.stack) == 2)
    C["blinn"] = item_xy("Blinn")
    ev('MOUSEMOVE', 'NOTHING', x=C["blinn"][0], y=C["blinn"][1])


@step
def s_favorite_shot():
    shot("gui_step29_rmb_favorite.png")
    click(*C["blinn"])


@step
def s_favorite_done():
    mat = cube().active_material
    # Maya numbers a new node one past the highest (naming.next_number): blinn5 exists -> blinn6
    check("Favorite > Blinn assigned blinn6 to the cube under the menu", mat is not None and mat.name == "blinn6")
    check("menu closed", not C["draw"].ACTIVE)
    rmb_click()


@step
def s_existing_open():
    x, y = item_xy("Assign Existing Material")
    ev('MOUSEMOVE', 'NOTHING', x=x - 10, y=y)
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)


@step
def s_existing_list():
    # Maya: the submenu lists the scene's materials as you move onto it (#283)
    s = session()
    check("hovering Assign Existing Material opens its submenu", s is not None and len(s.stack) == 2)
    labels = [i.label for i in s.layout.items] if s is not None else []
    want = sorted((m.name for m in bpy.data.materials if not m.is_grease_pencil), key=str.lower)
    check(f"it lists the scene's materials ({labels})", labels == want and "blinn5" in labels)
    C["existing"] = item_xy("blinn5")
    ev('MOUSEMOVE', 'NOTHING', x=C["existing"][0], y=C["existing"][1])


@step
def s_existing_shot():
    shot("gui_step29_rmb_existing.png")
    click(*C["existing"])


@step
def s_existing_done():
    mat = cube().active_material
    check(f"Assign Existing Material > blinn5 assigned it to the cube under the menu ({mat.name if mat else None})",
          mat is not None and mat.name == "blinn5")
    check("menu closed", not C["draw"].ACTIVE)
    cube().active_material = bpy.data.materials["blinn6"]


@step
def s_attributes():
    area, r = view3d()
    region = next(rg for rg in area.regions if rg.type == 'WINDOW')
    with bpy.context.temp_override(window=win(), area=area, region=region):
        check("Material Attributes runs", bpy.ops.allset.material_attributes() == {'FINISHED'})
    wm = bpy.context.window_manager
    check("dock = Attribute Editor on the material tab",
          wm.allset_dock == 'ATTRIBUTE_EDITOR' and wm.allset_ae_tab == "MAT:0")
    ev('MOUSEMOVE', 'NOTHING', x=C["x"] + 5, y=C["y"])


@step
def s_attributes_wait():
    md = import_module(MODULE + ".ui.maya_dock")
    check("the Attribute Editor is shown (its own floating window: this layout has no tab stack)",
          md.kind_visible(bpy.context.window_manager, 'ATTRIBUTE_EDITOR'))
    ev('MOUSEMOVE', 'NOTHING', x=C["x"], y=C["y"])


@step
def s_attributes_shot():
    shot("gui_step29_ae_material.png")
    bpy.context.window_manager.allset_dock = 'CHANNEL_BOX'
    prefs = bpy.context.preferences.addons[MODULE].preferences
    prefs.menu_set = 'renderingMenuSet'
    menu_sets = import_module(MODULE + ".ui.menu_sets")
    with bpy.context.temp_override(window=win()):
        bpy.ops.wm.call_menu(name=menu_sets.menu_idname("mainShadingMenu"))


@step
def s_menu_shot():
    shot("gui_step29_shading_menu.png")
    tap('ESC')
    with bpy.context.temp_override(window=win()):
        bpy.ops.wm.call_menu(name="ALLSET_MT_assign_existing_material")


@step
def s_menu_existing_shot():
    shot("gui_step29_existing_menu.png")
    tap('ESC')
    cube().select_set(True)
    bpy.context.view_layer.objects.active = cube()
    ev('MOUSEMOVE', 'NOTHING', x=C["x"], y=C["y"])
    ev('T', 'PRESS', x=C["x"], y=C["y"], shift=True)
    ev('T', 'RELEASE', x=C["x"], y=C["y"], shift=True)


@step
def s_shift_t():
    pass


@step
def s_shift_t_shot():
    shot("gui_step29_shift_t.png")
    # The search popup lists the types; typing narrows it, Return picks.
    for ch in "phong":
        ev('TEXTINPUT', 'PRESS', unicode=ch)


@step
def s_shift_t_pick():
    tap('RET')


@step
def s_shift_t_done():
    mat = cube().active_material
    check("Shift+T > type 'phong' > Return assigned phong1", mat is not None and mat.name == "phong1")


run()
