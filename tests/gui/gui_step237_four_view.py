"""Issue #148: Maya Four View = four real 3D View panels (ui/four_view.py) in the Maya layout.

Space tap (``allset.toggle_quad_view``) splits the viewport into top / persp / front / side areas, each with its own
header, shading and Show settings; Space tap over a panel keeps that panel alone; the next tap brings the four back with
every panel's settings. Panels > Layouts, save / open, switching to Blender. Shots with ``--shots``."""

import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sim  # noqa: E402
from sim import MODULE, check, load_maya_layout, run, screenshot, setup, step, view3d, win  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}
LOOKS = {"top": 'WIREFRAME', "persp": 'MATERIAL', "front": 'SOLID', "side": 'WIREFRAME'}


def mod(name):
    return import_module(f"{MODULE}.{name}")


def fv():
    return mod("ui.four_view")


def redraw():
    for a in win().screen.areas:
        a.tag_redraw()


def shot(name):
    path = os.path.join(SHOTS or bpy.app.tempdir, f"gui_step237_{name}.png")
    screenshot(path)


def tap(area):
    """Space tap with the mouse over ``area``."""
    region = next(r for r in area.regions if r.type == 'WINDOW')
    with bpy.context.temp_override(window=win(), area=area, region=region, space_data=area.spaces.active,
                                   region_data=region.data):
        return bpy.ops.allset.toggle_quad_view()


def looks():
    return {role: a.spaces.active.shading.type for role, a in fv().roles(win().screen).items()}


def keys_work(tag):
    """W hold + LMB in the main panel opens the Move tool marking menu: the panel takes keys (a joined area
    took none until the screen was refreshed)."""
    def move():
        # event simulation: the first key after a layout change, sent in the same tick as the move, is lost
        # (also with the old Quad View off: a real mouse moves first)
        a = fv().panes(win().screen)[0] if len(fv().panes(win().screen)) == 1 else fv().roles(win().screen)["top"]
        x, y = a.x + a.width // 3, a.y + a.height // 2
        C["xy"] = (x, y)
        sim.ev('MOUSEMOVE', 'NOTHING', x=x, y=y)

    def go():
        x, y = C["xy"]
        sim.ev('MOUSEMOVE', 'NOTHING', x=x + 1, y=y)
        sim.ev('W', 'PRESS', x=x, y=y)
        sim.ev('LEFTMOUSE', 'PRESS', x=x, y=y)

    def look():
        s = mod("marking.draw").ACTIVE.get("session")
        check(f"{tag}: the panel takes keys (W + LMB menu)", s is not None)
        x, y = C["xy"]
        for k in ('LEFTMOUSE', 'W'):
            sim.ev(k, 'RELEASE', x=x, y=y)
        sim.ev('ESC', 'PRESS', x=x, y=y)
        sim.ev('ESC', 'RELEASE', x=x, y=y)
    step(move)
    step(go)
    step(redraw)
    step(look)
    step(redraw)


def panel_set(key, area):
    region = next(r for r in area.regions if r.type == 'WINDOW')
    with bpy.context.temp_override(window=win(), area=area, region=region, space_data=area.spaces.active):
        return bpy.ops.allset.panel_set(key=key)


@step
def s_setup():
    setup()
    load_maya_layout()


for _i in range(5):
    step(redraw)


@step
def s_four():
    area, region = view3d()
    with bpy.context.temp_override(window=win(), area=area, region=region, space_data=area.spaces.active):
        bpy.ops.allset.create(kind='CUBE')
    C["n0"] = len(fv().panes(win().screen))
    check("one viewport panel before", C["n0"] == 1)
    check("Space tap -> FINISHED", tap(area) == {'FINISHED'})
    redraw()


step(redraw)


@step
def s_four_check():
    screen = win().screen
    placed = fv().roles(screen)
    check(f"four real 3D View areas ({len(fv().panes(screen))})", len(fv().panes(screen)) == 4 and len(placed) == 4)
    view = mod("operators.view")
    keys = {role: view.ortho_key(a.spaces.active.region_3d) for role, a in placed.items()}
    check(f"Maya cameras by place {keys}", keys.get("persp") is None and str(keys.get("top")).startswith("TOP")
          and str(keys.get("front")).startswith("FRONT") and str(keys.get("side")).startswith("SIDE"))
    check("each panel has its own header (panel menu bar)",
          all(any(r.type == 'HEADER' and r.height > 1 for r in a.regions) for a in placed.values()))
    check("no Blender Quad View", not any(a.spaces.active.region_quadviews for a in placed.values()))
    for role, look in LOOKS.items():
        placed[role].spaces.active.shading.type = look
    placed["side"].spaces.active.shading.show_xray = True
    placed["top"].spaces.active.overlay.show_floor = False
    redraw()


step(redraw)
keys_work("a split-off panel")


@step
def s_mixed_shot():
    check(f"panels keep different shading {looks()}", looks() == LOOKS)
    shot("01_mixed")
    C["persp"] = fv().roles(win().screen)["persp"].as_pointer()
    tap(fv().roles(win().screen)["persp"])
    redraw()


step(redraw)


@step
def s_single():
    screen = win().screen
    panes = fv().panes(screen)
    check(f"Space tap over persp: one panel ({len(panes)})", len(panes) == 1)
    sp = panes[0].spaces.active
    check(f"the persp panel stays with its own shading ({sp.shading.type}, {sp.region_3d.view_perspective})",
          sp.shading.type == 'MATERIAL' and sp.region_3d.view_perspective == 'PERSP')
    shot("02_single")


keys_work("the panel kept from the four view")


@step
def s_single_back():
    tap(fv().panes(win().screen)[0])
    redraw()


step(redraw)


@step
def s_back():
    screen = win().screen
    check(f"four panels again ({len(fv().panes(screen))})", len(fv().panes(screen)) == 4)
    check(f"each panel's settings came back {looks()}", looks() == LOOKS)
    placed = fv().roles(screen)
    check("side keeps X-ray, top keeps its grid off", placed["side"].spaces.active.shading.show_xray
          and not placed["top"].spaces.active.overlay.show_floor)
    shot("03_back")
    # Space tap over the side panel: the side camera alone
    tap(placed["side"])
    redraw()


step(redraw)


@step
def s_side_alone():
    panes = fv().panes(win().screen)
    sp = panes[0].spaces.active if len(panes) == 1 else None
    key = mod("operators.view").ortho_key(sp.region_3d) if sp else None
    check(f"Space tap over side keeps the side panel ({len(panes)}, {key})",
          sp is not None and str(key).startswith("SIDE") and sp.shading.show_xray)
    # Panels > Layouts > Four View, then Single Perspective View (keeps the persp panel whatever the mouse)
    panel_set("LAYOUT_FOUR", panes[0])
    redraw()


step(redraw)


@step
def s_layouts():
    screen = win().screen
    check("Panels > Layouts > Four View", len(fv().panes(screen)) == 4 and looks() == LOOKS)
    panel_set("LAYOUT_SINGLE", fv().roles(screen)["top"])
    redraw()


step(redraw)


@step
def s_single_persp():
    panes = fv().panes(win().screen)
    check(f"Single Perspective View keeps persp ({len(panes)})", len(panes) == 1
          and panes[0].spaces.active.region_3d.view_perspective == 'PERSP')
    tap(panes[0])
    redraw()


step(redraw)


@step
def s_save():
    C["path"] = os.path.join(bpy.app.tempdir, "four237.blend")
    bpy.ops.wm.save_as_mainfile(filepath=C["path"])
    bpy.ops.wm.open_mainfile(filepath=C["path"])


for _i in range(3):
    step(redraw)


@step
def s_reopened():
    screen = win().screen
    check(f"four view after save / open ({len(fv().panes(screen))}, {looks()})",
          fv().is_four(screen) and looks() == LOOKS)
    shot("04_reopened")
    mod("switch").set_mode(False)


for _i in range(3):
    step(redraw)


@step
def s_blender():
    n = sum(1 for a in win().screen.areas if a.type == 'VIEW_3D')
    check(f"switching to Blender folds the four view back ({n} 3D Views)", not fv().is_four(win().screen))


run()
