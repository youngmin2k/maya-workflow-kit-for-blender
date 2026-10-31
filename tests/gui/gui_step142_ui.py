"""In a real window. Run at the default 1.25, ``--ui-scale 0.8`` (1.0)
and ``--ui-scale 1.2`` (1.5) in the 1600 x 900 test window.

#78: a new Maya scene fits the tab stack to Maya's Channel Box width (vertical tab strip on its right edge, no tab
row), the viewport takes the rest; a click on the strip's Attribute Editor tab raises the AE and widens the stack to
Maya's AE stack (cursor fit, ALLSET_FIT_WARP=1), the AE menu bar is one row; the Channel Box tab narrows it again.
#77: the Maya menu bar shows every menu at 1.0 / 1.25 and hides the rest behind » at 1.5 (the shown ones fit the top
bar's left region); the » menu opens with the hidden menus.
#76: the Move manipulator draws the axis colours #e60000 / #00e600 / #0000ff, not Blender's theme gizmo colours;
in wireframe shading an unselected cube's wire is the dormant dark blue #000460."""

import os
import sys
from importlib import import_module

import bpy
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import (MODULE, check, dock_area, dock_region, dock_tab_point, ev, load_maya_layout, run, scale,  # noqa: E402
                 screenshot, setup, step, tap, view3d, win)

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
os.environ["ALLSET_FIT_WARP"] = "1"   # the cursor fit is off in event-simulated sessions unless asked for
C = {}


def mod(name):
    return import_module(f"{MODULE}.{name}")


def redraw():
    for a in win().screen.areas:
        a.tag_redraw()
    mod("ui.status_line").redraw_top_bars()


def shot(name):
    """Window screenshot as (h, w, 3) sRGB floats, row 0 = window bottom; also kept in SHOTS."""
    tag = f"{scale():.2f}".replace(".", "")
    path = os.path.join(SHOTS or bpy.app.tempdir, f"gui_step142_{name}_{tag}.png")
    screenshot(path)
    img = bpy.data.images.load(path, check_existing=False)
    w, h = img.size
    px = np.empty(w * h * 4, np.float32)
    img.pixels.foreach_get(px)
    bpy.data.images.remove(img)
    return px.reshape(h, w, 4)[..., :3]


def hexrgb(h):
    h = h.lstrip("#")
    return np.array([int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)])


def count(px, region, colour, tol=0.07, box=None):
    """Pixels of ``colour`` in ``region`` (or in ``box`` = window (x0, y0, x1, y1))."""
    x0, y0, x1, y1 = box or (region.x, region.y, region.x + region.width, region.y + region.height)
    sub = px[max(0, y0):y1, max(0, x0):x1]
    return int((np.abs(sub - colour).max(axis=-1) < tol).sum())


def to_window(world):
    from bpy_extras.view3d_utils import location_3d_to_region_2d
    area, region = view3d()
    p = location_3d_to_region_2d(region, area.spaces.active.region_3d, world)
    return None if p is None else (round(p.x) + region.x, round(p.y) + region.y)


def prefs():
    return bpy.context.preferences.system


@step
def s_setup():
    setup()
    load_maya_layout()


@step
def s_keymap():
    bpy.ops.allset.keymap_activate()
    _a, r = view3d()
    ev('MOUSEMOVE', 'NOTHING', x=r.x + r.width // 2, y=r.y + r.height // 2)   # over a region: area_move can't poll
    redraw()


for _i in range(10):         # the fit timer (0.5 s) + ALLSET_OT_fit_columns ticks (shelf, dock, column, Outliner)
    step(redraw)


@step
def s_cube():
    area, region = view3d()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        bpy.ops.allset.create(kind='CUBE')
    bpy.context.window_manager.allset_dock = 'CHANNEL_BOX'
    ev('MOUSEMOVE', 'NOTHING', x=region.x + region.width // 2, y=region.y + 40)
    redraw()


def _want(kind):
    tb = mod("ui.toolbox")
    target = tb._dock_target(win(), prefs().ui_scale, prefs().pixel_size, kind)
    return target[1] if target else None


@step
def s_cb_width():
    tb = mod("ui.toolbox")
    md = mod("ui.maya_dock")
    s = prefs().ui_scale
    dock = dock_area()
    want = _want('CHANNEL_BOX')
    main, _r = view3d()
    C["cb"] = dock.width
    check(f"Channel Box raised: the stack is Maya-narrow at UI scale {s:.2f} ({dock.width} px, rule "
          f"{tb.dock_width(s, prefs().pixel_size)}, Maya {round(tb.DOCK_MAYA_PX * s)}; the old fixed width was "
          f"{ {1.0: 466, 1.25: 574, 1.5: 672}.get(round(s, 2), '?') })", want is not None and abs(dock.width - want) <= 3)
    check(f"the viewport takes the rest ({main.width} px, its right edge {main.x + main.width} / dock {dock.x})",
          abs(main.x + main.width - dock.x) <= 8)
    tabs = md.strip_tabs(md.stack_tabs(), dock_region().width, dock_region().height, s)
    check(f"the strip holds Maya's three tabs top-down ({[t[0] for t in tabs]})",
          [t[0] for t in tabs] == ['CHANNEL_BOX', 'ATTRIBUTE_EDITOR', 'MODELING_TOOLKIT'] and tabs[-1][2] > 0)
    px = shot("cb")
    # the strip is drawn: the lowered AE tab differs from the region background next to it
    reg = dock_region()
    _k, x0, y0, x1, y1 = tabs[1]
    inside = px[reg.y + (y0 + y1) // 2, reg.x + x0 + 2]
    left = px[reg.y + (y0 + y1) // 2, reg.x + x0 - 12]
    check(f"the strip draws its lowered tab ({np.round(inside * 255)} vs content {np.round(left * 255)})",
          np.abs(inside - left).max() > 0.02)
    C["ae_tab"] = dock_tab_point('ATTRIBUTE_EDITOR')


@step
def s_ae_hover():
    ev('MOUSEMOVE', 'NOTHING', x=C["ae_tab"][0], y=C["ae_tab"][1])


@step
def s_ae_click():
    ev('LEFTMOUSE', 'PRESS', x=C["ae_tab"][0], y=C["ae_tab"][1])
    ev('LEFTMOUSE', 'RELEASE', x=C["ae_tab"][0], y=C["ae_tab"][1])
    redraw()


for _i in range(8):          # draw -> timer -> cursor fit ticks
    step(redraw)


@step
def s_ae_width():
    wm = bpy.context.window_manager
    check(f"a click on the strip's Attribute Editor tab raises it ({wm.allset_dock})", wm.allset_dock == 'ATTRIBUTE_EDITOR')
    dock = dock_area()
    want = _want('ATTRIBUTE_EDITOR')
    C["ae"] = dock.width
    check(f"AE raised: the stack widens to Maya's AE stack ({C['cb']} -> {dock.width} px, want {want})",
          want is not None and abs(dock.width - want) <= 3 and dock.width > C["cb"] + 50)
    reg = dock_region()
    ae = mod("ui.attribute_editor")
    with bpy.context.temp_override(window=win(), area=dock, region=reg):
        one = ae.fits(bpy.context, ae.MENU_BAR)
    check(f"the AE menu bar is one row left of the strip ({reg.width} px)", one)
    shot("ae")
    C["cb_tab"] = dock_tab_point('CHANNEL_BOX')
    ev('MOUSEMOVE', 'NOTHING', x=C["cb_tab"][0], y=C["cb_tab"][1])


@step
def s_cb_click():
    ev('LEFTMOUSE', 'PRESS', x=C["cb_tab"][0], y=C["cb_tab"][1])
    ev('LEFTMOUSE', 'RELEASE', x=C["cb_tab"][0], y=C["cb_tab"][1])
    redraw()


for _i in range(8):
    step(redraw)


@step
def s_cb_back():
    wm = bpy.context.window_manager
    dock = dock_area()
    check(f"the Channel Box tab narrows the stack again ({wm.allset_dock}, {dock.width} px, was {C['cb']})",
          wm.allset_dock == 'CHANNEL_BOX' and abs(dock.width - C["cb"]) <= 3)
    _a, r = view3d()
    ev('MOUSEMOVE', 'NOTHING', x=r.x + r.width // 2, y=r.y + r.height // 2)
    redraw()


@step
def s_menu_bar():
    sl = mod("ui.status_line")
    names, n = sl.shown_menus(win())
    s = prefs().ui_scale
    bar = sl._top_bars.get(win().as_pointer())
    left = next((r for r in bar.regions if r.type == 'HEADER' and r.alignment != 'RIGHT'), None) if bar else None
    check(f"the menu bar was drawn ({len(names)} menus, {n} shown, left region {left and left.width} px)",
          len(names) == 18 and left is not None)
    if s < 1.4:
        check(f"UI scale {s:.2f}: all 18 Maya menus show in the 1600 px window ({n})", n == 18)
    else:
        widths, fixed, more = sl.menu_bar_widths(bpy.context, names, False)
        end = fixed + more + sum(widths[:n])
        check(f"UI scale {s:.2f}: Maya's » overflow: {n} of 18 menus shown, they end at {end} px of the bar's "
              f"{left and left.width} px", 10 <= n < 18 and end <= left.width)
    shot("menubar")
    C["more"] = n < 18


@step
def s_more_open():
    if C["more"]:
        _a, r = view3d()
        ev('MOUSEMOVE', 'NOTHING', x=r.x + r.width // 2, y=r.y + r.height // 2)
        with bpy.context.temp_override(window=win()):
            bpy.ops.wm.call_menu(name="ALLSET_MT_menu_more")


@step
def s_more_shot():
    if C["more"]:
        shot("menu_more")
        tap('ESC')
    redraw()


@step
def s_move_tool():
    area, region = view3d()
    cube = bpy.context.view_layer.objects.active
    for ob in bpy.context.scene.objects:
        ob.select_set(ob == cube)
    with bpy.context.temp_override(window=win(), area=area, region=region):
        bpy.ops.wm.tool_set_by_id(name="builtin.move")
        bpy.ops.view3d.view_selected()
    C["cube"] = cube.name
    ev('MOUSEMOVE', 'NOTHING', x=region.x + 10, y=region.y + 10)
    redraw()


@step
def s_move_colours():
    px = shot("move")
    _a, region = view3d()
    # around the manipulator only (the navigation gizmo / view axis keep Blender's theme axis colours)
    cx, cy = to_window(bpy.data.objects[C["cube"]].matrix_world.translation)
    r = round(150 * scale())
    box = (cx - r, cy - r, cx + r, cy + r)
    maya = {a: count(px, region, hexrgb(h), box=box) for a, h in mod("ui.manipulator").MAYA_AXIS.items()}
    theme = {a: count(px, region, hexrgb(h), box=box)
             for a, h in (("X", "#ff3653"), ("Y", "#8adb00"), ("Z", "#3b64a5"))}
    check(f"Move manipulator in the Maya-style axis colours (px {maya}; Blender theme gizmo colours {theme})",
          all(v >= 10 for v in maya.values()) and all(theme[a] < maya[a] // 4 + 5 for a in "XYZ"))
    # a second cube, unselected, in wireframe shading
    area, region = view3d()
    unit = mod("operators.units").maya_unit()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        bpy.ops.allset.create(kind='CUBE')
        other = bpy.context.view_layer.objects.active
        other.location.x += 2.0 * unit
        for ob in bpy.context.scene.objects:
            ob.select_set(ob.name == C["cube"])
        bpy.context.view_layer.objects.active = bpy.data.objects[C["cube"]]
        bpy.ops.wm.tool_set_by_id(name="builtin.select_box")
        bpy.ops.view3d.view_all()
    area.spaces.active.shading.type = 'WIREFRAME'
    redraw()


@step
def s_dormant():
    px = shot("wireframe")
    _a, region = view3d()
    blue = count(px, region, hexrgb("#000460"), tol=0.05)
    lead = count(px, region, hexrgb("#43ffa3"))
    check(f"wireframe shading: the unselected cube's wire is Maya's dormant dark blue #000460 ({blue} px; lead green "
          f"{lead} px)", blue >= 40 and lead >= 40)
    view3d()[0].spaces.active.shading.type = 'SOLID'
    redraw()


run()
