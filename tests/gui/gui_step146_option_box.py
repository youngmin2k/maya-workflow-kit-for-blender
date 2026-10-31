"""#82: a Maya menu item's option box opens by holding the item, without a drag.

Press and hold Display > Grid, Key > Set Key, Constrain > Parent: after Blender's hold time (0.2 s) its hold menu
opens below the item and the kit puts the pointer on the menu's Option Box row (``menu_sets.LAST_WARP``), so letting
go runs ``allset.menu_option_box`` and not the command. A plain click on the label still runs the command.
"""

import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, px, run, setup, step, tap, view3d, win  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {"calls": []}
CASES = [("mainDisplayMenu", "Display/Grid"), ("mainKeysMenu", "Key/Set Key"),
         ("mainRigConstraintsMenu", "Constrain/Parent"), ("mainKeysMenu", "Key/Cut Keys")]


def mod(name):
    return import_module(MODULE + name)


def shot(name):
    if SHOTS:
        with bpy.context.temp_override(window=win()):
            bpy.ops.screen.screenshot(filepath=os.path.join(SHOTS, name))


def _spy(cls, tag):
    orig = cls.execute

    def execute(self, context):
        C["calls"].append((tag + ("_hold" if getattr(self, "from_hold", False) else ""), getattr(self, "item", "")))
        return orig(self, context)
    cls.execute = execute
    C.setdefault("restore", []).append((cls, orig))


def open_menu(name):
    area, region = view3d()
    with bpy.context.temp_override(window=win(), area=area, region=region, space_data=area.spaces.active):
        bpy.ops.wm.call_menu(name=mod(".ui.menu_sets").menu_idname(name))


def closes():
    """Blender closes a menu the mouse left (4.5; 5.x only with Preferences > menu_close_leave)."""
    return mod(".ui.menu_sets").compat.menus_close_on_leave(bpy.context.preferences)


def dark_share(point, half=None):
    """Share of dark pixels (menu background, < 45 / 255) in a box around a window point: a screenshot read back."""
    import tempfile
    import numpy as np
    half = half or px(30)
    path = os.path.join(SHOTS or tempfile.gettempdir(), "146_probe_pixels.png")
    with bpy.context.temp_override(window=win()):
        bpy.ops.screen.screenshot(filepath=path)
    img = bpy.data.images.load(path)
    w, h = img.size
    a = np.empty(w * h * 4, dtype=np.float32)
    img.pixels.foreach_get(a)
    bpy.data.images.remove(img)
    a = a.reshape(h, w, 4)[:, :, :3].mean(axis=2)
    x, y = point
    box = a[max(0, y - half):y + half, max(0, x - half):x + half]
    return float((box < 45 / 255).mean())


def first_row(menu):
    """The menu's first item (shots at effective scale 1.25): Display opens mid-viewport with Grid 34 px above the
    mouse (gui_step143_user grid_box); Key is taller than the window, so Blender pins it to the window top (Set Key
    87 px down); Constrain opens with its tear-off line at the mouse, Parent 23 px under it."""
    if menu == "mainDisplayMenu":
        return C["x"], C["open"][1] + px(9)   # Maya 2026 Display menu
    if menu == "mainKeysMenu":
        return C["x"], win().height - px(87 if C["case"] == "Key/Set Key" else 444)
    return C["x"], C["open"][1] - px(23)


def open_point(menu):
    """Where the mouse opens the menu: Display mid-viewport; the long Key / Constrain menus near the window top, so
    Blender doesn't move them (a menu that doesn't fit below the mouse is moved up, under another row)."""
    if menu == "mainDisplayMenu":
        return C["x"], C["y"]
    return C["x"], win().height - px(160)


@step
def s_setup():
    C["x"], C["y"] = setup()
    bpy.ops.allset.keymap_activate()
    bpy.context.preferences.view.show_tooltips = False
    ms = mod(".ui.menu_sets")
    _spy(ms.ALLSET_OT_menu_option_box, "box")
    _spy(ms.ALLSET_OT_menu_item, "item")


def hold_case(menu, path):
    tag = path.split("/")[-1].replace(" ", "_")

    def s_open():
        C["case"] = path
        del C["calls"][:]
        del mod(".ui.menu_sets").LAST_WARP[:]
        C["open"] = open_point(menu)
        ev('MOUSEMOVE', 'NOTHING', x=C["open"][0], y=C["open"][1])
        open_menu(menu)

    def s_hover():
        C["row"] = first_row(menu)
        ev('MOUSEMOVE', 'NOTHING', x=C["row"][0] - 4, y=C["row"][1])

    def s_hover2():
        ev('MOUSEMOVE', 'NOTHING', x=C["row"][0], y=C["row"][1])

    def s_settle():
        pass

    def s_press():
        ev('LEFTMOUSE', 'PRESS', x=C["row"][0], y=C["row"][1])

    def s_held():
        pass           # 0.4 s: past Blender's 0.2 s hold time; the hold menu opens and the pointer moves

    def s_release():
        shot(f"146_{tag}_held.png")
        warp = [w[1:] for w in mod(".ui.menu_sets").LAST_WARP if w[0] == 'HOLD_ROW']
        C["warp"] = list(warp[0]) if warp else []
        C["held_calls"] = list(C["calls"])
        x, y = C["warp"] if warp else C["row"]
        mod(".ui.menu_sets").AWAY_TICK = 0.3       # the simulated back move (s_back) comes after the warp back
        ev('MOUSEMOVE', 'NOTHING', x=x, y=y)      # the warp's own move (simulation keeps the pointer in sim._pos)
        ev('LEFTMOUSE', 'RELEASE', x=x, y=y)
        # cursor_warp sends no event under --enable-event-simulate (a real session gets the OS move in a
        # normal GUI Blender), so queue the move the option box's away warp makes, right
        # behind the release like Blender's own move after the hold menu closes
        if closes():
            away_x = 2 if x > win().width // 2 else win().width - 3
            ev('MOUSEMOVE', 'NOTHING', x=away_x, y=y)

    def s_away():
        pass

    def s_back():
        moves = {m[0]: m[1:] for m in mod(".ui.menu_sets").LAST_WARP}
        if 'BACK' in moves:
            ev('MOUSEMOVE', 'NOTHING', x=moves['BACK'][0], y=moves['BACK'][1])

    def s_result():
        shot(f"146_{tag}_option_box.png")
        print("GUI146", path, "warp", C["warp"], "row", C["row"], "held", C["held_calls"], "calls", C["calls"],
              flush=True)
        check(f"{path}: holding the item moves the pointer onto the hold menu's Option Box row "
              f"({C['warp']} from {C['row']})",
              len(C["warp"]) == 2 and C["warp"][0] == C["row"][0] and 0 < C["row"][1] - C["warp"][1] <= px(45))
        check(f"{path}: holding runs nothing yet ({C['held_calls']})", not C["held_calls"])
        moves = list(mod(".ui.menu_sets").LAST_WARP)
        print("GUI146 moves", moves, flush=True)
        check(f"{path}: hold and let go without a drag = the option box, run again after the menu closed "
              f"({C['calls']})", C["calls"] == [("box_hold", path), ("box", path)])
        # (simulated events update the window's event state when queued, so here AWAY starts from the far point the
        # test queued behind the release and BACK returns there; in a real session BACK = the hold row)
        if closes():
            check(f"{path}: the pointer went away (closes the Maya menu) and came back ({moves})",
                  [m[0] for m in moves] == ['HOLD_ROW', 'AWAY', 'BACK'])
        else:
            check(f"{path}: 5.x menus stay open until a click: no away / back warp ({moves})",
                  [m[0] for m in moves] == ['HOLD_ROW'])
        tap('ESC')

    def s_after_esc():
        shot(f"146_{tag}_after_esc.png")
        mod(".ui.menu_sets").AWAY_TICK = 0.05
        share = dark_share((C["row"][0] - px(200), C["row"][1]), px(20))
        if closes():
            check(f"{path}: the Maya menu is closed after the option window (dark share {share:.2f} at the item)",
                  share < 0.3)
        else:   # Blender 5.x default (menu_close_leave off): no Python call closes it (compat.menus_close_on_leave)
            check(f"{path}: 5.x: the Maya menu stays open under the option window until a click / Esc "
                  f"(dark share {share:.2f} at the item)", share > 0.5)

    def s_close():
        shot(f"146_{tag}_after_esc2.png")
        tap('ESC')
        ev('MOUSEMOVE', 'NOTHING', x=C["x"], y=C["y"])
    for f in (s_open, s_hover, s_hover2, s_settle, s_settle, s_press, s_held, s_release, s_away, s_back, s_result, s_after_esc, s_close):
        step(f)


for _menu, _path in CASES:
    hold_case(_menu, _path)


# --- a plain click on the label is still the command ---------------------------------------------------------

@step
def s_c_open():
    del C["calls"][:]
    C["open"] = open_point("mainDisplayMenu")
    open_menu("mainDisplayMenu")


@step
def s_c_hover():
    C["row"] = first_row("mainDisplayMenu")
    ev('MOUSEMOVE', 'NOTHING', x=C["row"][0] - 4, y=C["row"][1])


@step
def s_c_hover2():
    ev('MOUSEMOVE', 'NOTHING', x=C["row"][0], y=C["row"][1])


@step
def s_c_settle():
    pass


@step
def s_c_settle2():
    pass


@step
def s_c_click():
    ev('LEFTMOUSE', 'PRESS', x=C["row"][0], y=C["row"][1])
    ev('LEFTMOUSE', 'RELEASE', x=C["row"][0], y=C["row"][1])


@step
def s_c_result():
    shot("146_click_grid.png")
    check(f"a click on Grid runs the command ({C['calls']})", C["calls"] == [("item", "Display/Grid")])
    for cls, orig in C.get("restore", ()):
        cls.execute = orig
    tap('ESC')


run()
