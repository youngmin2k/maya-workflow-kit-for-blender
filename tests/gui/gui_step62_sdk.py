"""In a real UI, Maya's hand order (rigging):
locator1 Translate X = driver, pCube1 Rotate Y = driven -> Key -> tx 1 / ry 90 typed in the Channel Box ->
Key -> tx 0.5 -> ry 45. Clicks the Channel Box rows and the Set Driven Key buttons in the dock; screenshots."""

import math
import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, dock_area, dock_region, ev, find_button, px, run, screenshot, setup, step, tap, view3d, win  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {"tries": 0}

# Sidebar points read from gui_step62_sdk_loaded / _scrolled.png (1600 x 900, scale 1.25, UI region
# (971, 94, 350, 709)): (px left of the region's right edge, px below the top of the sidebar content).
TX_LABEL, RY_LABEL = (266, 114), (266, 193)        # Channel Box row labels (select the channel)
TX_FIELD, RY_FIELD = (136, 114), (136, 193)        # their value fields
KEY_CUBE, LOAD_DRIVEN_CUBE = (260, 734), (260, 759)  # buttons with pCube1 as lead (CB + SHAPES)
SHAPES_ROWS = 56                                     # locator1 has no SHAPES section
LOAD_DRIVER_LOCATOR = (118, 734 - SHAPES_ROWS)


def shot(name):
    if SHOTS:
        screenshot(os.path.join(SHOTS, name))


def ui_region():
    return dock_region()       # the Maya tab stack (was the 3D View sidebar)


def dock():
    return dock_area(), dock_region()


# the dock is its own area, so x offsets from the old sidebar's right edge (which held Blender's tab strip)
# don't hold. Channel Box columns are found once by data path; the Set Driven Key button grid (two columns) by its
# share of the width (old sidebar content 325 px: Key / Load Driven at 28 %, Load Driver at 71 %).
GRID = {260: 0.28, 118: 0.71}


def redraw():
    for a in win().screen.areas:
        a.tag_redraw()


def point(spot):
    """Screen position of a sidebar spot (content offset), following the region's scroll."""
    dx, dy = spot
    r = ui_region()
    top = r.view2d.view_to_region(0, 0, clip=False)[1]       # content top in region pixels (scrolled)
    if dx == 136:
        x = C["x_field"]
    elif dx == 266:
        x = C["x_label"]
    else:
        x = r.x + int(r.width * GRID[dx])
    return x, r.y + top - px(dy)


def visible(spot):
    _x, y = point(spot)
    r = ui_region()
    return r.y + 10 < y < r.y + r.height - 10


def scroll(spot):
    """Wheel the sidebar until the spot is inside it (scale 0.8: nothing to scroll)."""
    def s_scroll():
        if not visible(spot) and C["tries"] < 40:
            C["tries"] += 1
            r = ui_region()
            _x, y = point(spot)
            kind = 'WHEELDOWNMOUSE' if y < r.y else 'WHEELUPMOUSE'
            ev(kind, 'PRESS', x=r.x + r.width // 2, y=r.y + r.height // 2)
            sys.modules["sim"]._steps.insert(0, s_scroll)
            return
        C["tries"] = 0
        redraw()
    return s_scroll


BUTTONS = {KEY_CUBE: ("sdk_key", 0.28), LOAD_DRIVEN_CUBE: ("which='DRIVEN'", 0.28),
           LOAD_DRIVER_LOCATOR: ("which='DRIVER'", 0.71)}


def click(spot):
    """Hover in one tick, press + release in the next: a Blender button activates on hover. Set Driven Key buttons
    are looked up by their command (their height follows the dock's)."""
    if spot in BUTTONS:
        text, frac = BUTTONS[spot]
        state = {}

        def s_find():
            if not state:
                state["f"] = find_button(dock, lambda _path, cmd: text in cmd, C, "button", x_frac=frac,
                                         start_frac=0.4)
            state["f"]()

        def s_hover_found():
            check(f"Set Driven Key button {text} found ({C['button']})", C["button"] is not None)
            if C["button"]:
                ev('MOUSEMOVE', 'NOTHING', x=C["button"][0], y=C["button"][1])

        def s_press_found():    # a press goes to the hovered button: hover first (the sweep ended on the next one)
            if C["button"]:
                x, y = C["button"]
                ev('LEFTMOUSE', 'PRESS', x=x, y=y)
                ev('LEFTMOUSE', 'RELEASE', x=x, y=y)
        return [s_find, s_hover_found, s_press_found]

    def s_hover():
        x, y = point(spot)
        ev('MOUSEMOVE', 'NOTHING', x=x, y=y)

    def s_press():
        x, y = point(spot)
        ev('LEFTMOUSE', 'PRESS', x=x, y=y)
        ev('LEFTMOUSE', 'RELEASE', x=x, y=y)
    return [s_hover, s_press]


def type_into(spot, text):
    """Hover, click the field, select all, type, Enter (gui_step38)."""
    def s_hover():
        x, y = point(spot)
        ev('MOUSEMOVE', 'NOTHING', x=x, y=y)

    def s_type():
        ev('A', 'PRESS', ctrl=True)
        ev('A', 'RELEASE', ctrl=True)
        for ch in text:
            ev('TEXTINPUT', 'PRESS', unicode=ch)
        tap('RET')
    return [scroll(spot), s_hover, *click(spot), s_type]


def select(name):
    def s_select():
        for o in bpy.context.view_layer.objects:
            o.select_set(o.name == name)
        bpy.context.view_layer.objects.active = bpy.data.objects[name]
        redraw()
    return s_select


def steps(*fns):
    for fn in fns:
        for f in (fn if isinstance(fn, list) else [fn]):
            step(f)


def columns():
    """Channel Box value / label columns on the Translate X row (locator1 selected), by data path."""
    def s_row():
        r = ui_region()
        top = r.view2d.view_to_region(0, 0, clip=False)[1]
        C["tx_row"] = r.y + r.height - (r.y + top - px(TX_FIELD[1]))
    out = [s_row]

    def finder(key, match):
        state = {}

        def s_find():
            if not state:
                state["f"] = find_button(dock, match, C, key, rows=(C["tx_row"],))
            state["f"]()
        return s_find
    out.append(finder("x_field_at", lambda path, _cmd: path.endswith("tx_text")))
    out.append(finder("x_label_at", lambda path, cmd: "cb_select_channel" in cmd or path.endswith("tx_sel")))

    def s_done():
        check(f"Channel Box columns found in the dock ({C['x_field_at']}, {C['x_label_at']})",
              C["x_field_at"] and C["x_label_at"])
        C["x_field"] = C["x_field_at"][0] if C["x_field_at"] else 0
        C["x_label"] = C["x_label_at"][0] if C["x_label_at"] else 0
    out.append(s_done)
    return out


def sdk():
    return bpy.context.window_manager.allset_sdk


def ry():
    return math.degrees(bpy.data.objects["pCube1"].rotation_euler[1])


@step
def s_setup():
    setup()
    cube = bpy.data.objects["Cube"]
    cube.name = "pCube1"
    loc = bpy.data.objects.new("locator1", None)
    loc.empty_display_type = 'PLAIN_AXES'
    loc.location = (0, -3, 0)       # Translate X 0 = the first driven key (Maya scenario)
    bpy.context.scene.collection.objects.link(loc)
    dock_area('CHANNEL_BOX')    # Maya's tab stack right of the viewport
    bpy.ops.allset.sdk_window()          # Key > Set Driven Key > Set... (menu mapping: headless test)
    redraw()


def s_check_driver():
    st = sdk()
    check(f"Load Driver: locator1 / Translate X (got {st.driver.object and st.driver.object.name} "
          f"/ {st.driver_attr})", st.driver.object is not None and st.driver.object.name == "locator1"
          and st.driver_attr == "tx")


def s_check_driven():
    st = sdk()
    names = [i.object.name for i in st.driven if i.object]
    check(f"Load Driven: pCube1 / Rotate Y (got {names} / {st.driven_attrs})",
          names == ["pCube1"] and st.driven_attrs == "ry")


def s_check_key1():
    dk = import_module(MODULE + ".operators.driven_key")
    fc = dk.sdk_fcurve(bpy.data.objects["pCube1"], "ry")
    check("Key: a driven key on pCube1 Rotate Y", fc is not None and len(fc.keyframe_points) == 1)
    shot("gui_step62_sdk_key1.png")


def s_check_posed():
    loc = bpy.data.objects["locator1"]
    check(f"Channel Box: locator1 Translate X = 1 (got {loc.location.x:.3f})", abs(loc.location.x - 1) < 1e-4)
    check(f"Channel Box: pCube1 Rotate Y = 90 is held while posing (got {ry():.2f})", abs(ry() - 90) < 1e-3)


def s_check_key2():
    dk = import_module(MODULE + ".operators.driven_key")
    fc = dk.sdk_fcurve(bpy.data.objects["pCube1"], "ry")
    check("second Key: two driven keys", fc is not None and len(fc.keyframe_points) == 2)


def s_check_result():
    bpy.context.view_layer.update()
    check(f"locator1 Translate X 0.5 -> pCube1 Rotate Y 45 (got {ry():.2f})", abs(ry() - 45) < 1e-2)
    redraw()


def s_shot_result():
    shot("gui_step62_sdk_result.png")
    area, region = view3d()
    ev('MOUSEMOVE', 'NOTHING', x=region.x + region.width // 2, y=region.y + region.height // 2)
    with bpy.context.temp_override(window=win(), area=area, region=region):
        bpy.ops.allset.add_attribute('INVOKE_DEFAULT')    # Modify > Add Attribute... dialog


def s_wait_dialog():
    redraw()


def s_shot_dialog():
    shot("gui_step62_add_attribute.png")
    tap('ESC')
    check("Add Attribute dialog opened (screenshot)", True)


steps(select("locator1"), columns(),
      # driver: select locator1, click Translate X in the Channel Box, Load Driver
      scroll(TX_LABEL), click(TX_LABEL), click(LOAD_DRIVER_LOCATOR), s_check_driver,
      # driven: select pCube1, click Rotate Y, Load Driven, Key
      select("pCube1"), scroll(RY_LABEL), click(RY_LABEL), click(LOAD_DRIVEN_CUBE),
      s_check_driven, click(KEY_CUBE), s_check_key1,
      # pose: tx 1, ry 90, Key
      select("locator1"), type_into(TX_FIELD, "1"), select("pCube1"), type_into(RY_FIELD, "90"),
      s_check_posed, click(KEY_CUBE), s_check_key2,
      # drive: tx 0.5 -> ry 45
      select("locator1"), type_into(TX_FIELD, "0.5"), s_check_result, select("pCube1"), scroll(KEY_CUBE),
      s_shot_result, s_wait_dialog, s_shot_dialog)

run()
