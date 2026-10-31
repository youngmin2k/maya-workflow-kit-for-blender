"""In a real UI: the top area reads like Maya 2022.

The user's path: Maya mode switched off and on again in a factory session (Blender's theme) — the switch appends the
Maya layout and keeps the user's theme. Then: menu bar without the menu set dropdown and with every Maya menu on
screen, "Workspace:" dropdown, flat Maya / Blender switch; Status Line led by the menu set, Maya's collapsed groups;
shelf row without a header, tab strip drawn in its WINDOW region and clickable; viewport header = Maya panel menus,
tool header = Maya panel toolbar. Screen pixels: the theme's menu bar colour, the shelf tab strip dimmed like Maya's. Screenshots for the
side-by-side with Maya."""

import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, run, step, setup, screenshot, view3d, win  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


def mod(name):
    return import_module(f"{MODULE}.{name}")


def redraw():
    for a in win().screen.areas:
        a.tag_redraw()
    mod("ui.status_line").redraw_top_bars()


def shot(name):
    path = os.path.join(SHOTS or bpy.app.tempdir, f"{name}_{round(bpy.context.preferences.system.ui_scale * 100)}.png")
    screenshot(path)
    return path


def pixel(path, x, y_top):
    img = bpy.data.images.load(path, check_existing=False)
    try:
        w, h = img.size
        i = ((h - 1 - y_top) * w + x) * 4
        return tuple(round(v * 255) for v in img.pixels[i:i + 3])
    finally:
        bpy.data.images.remove(img)


def near(p, q, tol=4):
    return all(abs(a - b) <= tol for a, b in zip(p, q))


def shelf_row():
    return mod("ui.shelf").shelf_row_area(win().screen)


@step
def s_setup():
    setup()
    sw = mod("switch")
    sw.set_mode(False, layout=False)


@step
def s_maya():
    C["theme_before"] = bpy.context.preferences.themes[0].name
    mod("switch").set_mode(True)


@step
def s_wait():
    bpy.ops.allset.keymap_activate()
    _a, r = view3d()
    ev('MOUSEMOVE', 'NOTHING', x=r.x + r.width // 2, y=r.y + r.height // 2)
    redraw()


@step
def s_wait2():
    redraw()


@step
def s_layout():
    from bpy import context
    check(f"Maya mode keeps the user's theme ({C['theme_before']} -> {context.preferences.themes[0].name})",
          context.preferences.themes[0].name == C["theme_before"])
    sl = mod("ui.status_line")
    with context.temp_override(window=win(), screen=win().screen):
        check("a Status Line is on screen, so the menu bar has no menu set dropdown", sl.status_line_shown(context))
    # every Maya menu fits the menu bar at this scale: logo + the items' widths + the right side
    ms = mod("ui.menu_sets")
    prefs = mod("preferences").get()
    scale = context.preferences.system.ui_scale
    widths = [ms.menu_width_units(getattr(bpy.types, ms.menu_idname(n)).bl_label, context) * 20 * scale
              for n in ms.menus_for_set(prefs.menu_set)]
    right = (7 + 4.5 + 6) * 20 * scale     # workspace label + dropdown + switch
    C["menus_px"] = round(sum(widths) + 40 * scale)
    # #77: when they don't (UI scale 1.5), Maya's » overflow holds the rest, like Maya at 150 %
    names, shown = mod("ui.status_line").shown_menus(win())
    if C["menus_px"] + right <= win().width:
        check(f"all {len(widths)} Maya menus fit a 1600 px window ({C['menus_px']} px + right side {round(right)}; "
              f"shown {shown})", shown == len(names) == len(widths))
    else:
        check(f"{len(widths)} Maya menus need {C['menus_px']} px + right side {round(right)}: {shown} shown, the rest "
              f"behind Maya's » ({names[shown:]})", 10 <= shown < len(names) == len(widths))
    row = shelf_row()
    check("shelf row: no header, tab strip in the WINDOW region",
          row is not None and not row.spaces.active.show_region_header)
    area, _r = view3d()
    check("viewport: Maya panel toolbar shown (tool header)", area.spaces.active.show_region_tool_header)
    pt = mod("ui.panel_toolbar")
    with context.temp_override(window=win(), screen=win().screen, area=area):
        check("viewport header is the Maya panel bar in this layout", pt.maya_layout(context))
    C["shelf_before"] = mod("ui.shelf").current(context)
    # click the Rigging tab
    wr = next(r for r in row.regions if r.type == 'WINDOW')
    with context.temp_override(window=win(), screen=win().screen, area=row, region=wr):
        rects = mod("ui.shelf").tab_rects(context, wr)
    tab = next(r for r in rects if r[4] == "Rigging")
    C["tab_xy"] = (wr.x + (tab[0] + tab[2]) // 2, wr.y + (tab[1] + tab[3]) // 2)
    ev('MOUSEMOVE', 'NOTHING', x=C["tab_xy"][0], y=C["tab_xy"][1])


@step
def s_click_tab():
    x, y = C["tab_xy"]
    ev('LEFTMOUSE', 'PRESS', x=x, y=y)
    ev('LEFTMOUSE', 'RELEASE', x=x, y=y)


@step
def s_tab_check():
    cur = mod("ui.shelf").current(bpy.context)
    check(f"a click on the drawn Rigging tab shows the Rigging shelf ({C['shelf_before']} -> {cur})", cur == "Rigging")
    bpy.ops.allset.shelf_select(shelf="Polygons")
    _a, r = view3d()
    ev('MOUSEMOVE', 'NOTHING', x=r.x + r.width // 2, y=r.y + r.height // 2)
    redraw()


@step
def s_shot_wait():
    redraw()


@step
def s_shot():
    path = shot("step113_top")
    scale = bpy.context.preferences.system.ui_scale
    w = win().width
    th = bpy.context.preferences.themes[0]
    p_menu = pixel(path, int(w * 0.70), int(6 * scale))
    menu_bg = tuple(round(c * 255) for c in th.topbar.space.header[:3])
    check(f"menu bar background = the theme's top bar {menu_bg} (pixel {p_menu})", near(p_menu, menu_bg))
    row = shelf_row()
    top = win().height - (row.y + row.height)        # the shelf row's top edge, from the window top
    p_tab = pixel(path, w - 20, top + int(8 * scale))
    # the tab strip = the theme's Image Editor header dimmed by the ratio #444444 -> #373737 (ui/shelf.TAB_DIM)
    tab_bg = tuple(round(c * 255 * (1 - mod("ui.shelf").TAB_DIM)) for c in th.image_editor.space.header[:3])
    check(f"shelf tab strip = theme header x Maya's dim {tab_bg} (pixel {p_tab})", near(p_tab, tab_bg))
    mod("switch").set_mode(False)


@step
def s_blender():
    check(f"the user's theme was never replaced ({bpy.context.preferences.themes[0].name})",
          bpy.context.preferences.themes[0].name == C["theme_before"])


run()
