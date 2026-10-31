"""#121: in a real UI: Windows > Settings/Preferences > Hotkey Editor opens the kit Hotkey Editor window
(Maya's standard hotkeys, the kit's key for each); typing "select toggle" into its search field filters the list;
Assign New Hotkey takes the next key press (Ctrl+F6), after which Ctrl+F6 over the viewport runs Maya's
SelectToggleMode and F8 no longer does; Restore brings F8 back. Shots: the window, the window after the search."""

import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, load_maya_layout, run, setup, step, view3d, win  # noqa: E402

GUI_TIMEOUT = 200
SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


def mod(name):
    return import_module(MODULE + name)


def shot(name, window=None):
    if SHOTS:
        with bpy.context.temp_override(window=window or win()):
            bpy.ops.screen.screenshot(filepath=os.path.join(SHOTS, name))


def hk():
    """(window, area, WINDOW region) of the Hotkey Editor, else (None, None, None)."""
    mw = mod(".ui.marked_window")
    w = mw.find_window(bpy.context, "HOTKEY_EDITOR")
    if w is None:
        return None, None, None
    area = next(a for a in w.screen.areas if mw.kind_of(a) == "HOTKEY_EDITOR")
    return w, area, next(r for r in area.regions if r.type == 'WINDOW')


def ev2(type, value, **kw):
    """An event into the Hotkey Editor window (sim.ev always goes to the main window)."""
    w, _a, _r = hk()
    if "x" in kw:
        C["pos"] = (kw["x"], kw["y"])
    else:
        kw.update(x=C["pos"][0], y=C["pos"][1])
    w.event_simulate(type=type, value=value, **kw)


def path_under_mouse():
    w, area, region = hk()
    wm = bpy.context.window_manager
    wm.clipboard = ""
    try:
        with bpy.context.temp_override(window=w, screen=w.screen, area=area, region=region):
            bpy.ops.ui.copy_data_path_button(full_path=False)
    except RuntimeError:
        pass
    return wm.clipboard


def redraw():
    for w in bpy.context.window_manager.windows:
        for a in w.screen.areas:
            a.tag_redraw()


def v3d_center():
    _area, r = view3d()
    return r.x + r.width // 2, r.y + r.height // 2


@step
def s_setup():
    setup()
    load_maya_layout()


@step
def s_scene():
    bpy.ops.allset.keymap_activate()
    area, region = view3d()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        bpy.ops.allset.create(kind='CUBE')
    C["cube"] = bpy.context.active_object.name
    x, y = v3d_center()
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)


@step
def s_f8_before():
    C["mode_a"] = bpy.context.mode
    ev('F8', 'PRESS')
    ev('F8', 'RELEASE')


@step
def s_f8_before_done():
    check(f"before: F8 toggles the selection mode ({C['mode_a']} -> {bpy.context.mode})",
          bpy.context.mode != C["mode_a"])
    area, region = view3d()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        if bpy.context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        C["open"] = bpy.ops.allset.menu_item(item="Windows/Settings/Preferences/Hotkey Editor")


@step
def s_opened():
    redraw()


@step
def s_check_open():
    w, area, region = hk()
    check(f"Windows > Settings/Preferences > Hotkey Editor opens the kit window ({C['open']})", w is not None)
    if w is None:
        return
    check("one area, no Blender header (Maya window)",
          len(w.screen.areas) == 1 and not area.spaces.active.show_region_header)
    wm = bpy.context.window_manager
    n = len(mod(".ui.hotkey_editor").rows())
    check(f"the list shows every Maya hotkey ({len(wm.allset_hk_rows)} of {n})", len(wm.allset_hk_rows) == n)
    redraw()


@step
def s_shot_window():
    w, _a, _r = hk()
    if w is not None:
        shot("gui_step215_hotkey_editor.png", w)
    C["sweep"] = None


def _sweep():
    """Find the search field: rows below the region top, right to left, one probe per tick."""
    w, area, region = hk()
    st = C.setdefault("sw", {"dy": 18, "x": None})
    if st["x"] is not None:
        if path_under_mouse() == "allset_hk_search":
            hits = st.setdefault("hits", [])
            hits.append((st["x"], region.y + region.height - st["dy"]))
        elif st.get("hits"):
            xs = [h[0] for h in st["hits"]]
            C["field"] = ((min(xs) + max(xs)) // 2, st["hits"][0][1])
            return True
    if st["x"] is None or st["x"] < region.x + 4:
        if st["x"] is not None:
            st["dy"] += 8
        if st["dy"] > 160:
            return True
        st["x"] = region.x + region.width - 6
    else:
        st["x"] -= 12
    ev2('MOUSEMOVE', 'NOTHING', x=st["x"], y=region.y + region.height - st["dy"])
    return False


@step
def s_find_field():
    if hk()[0] is None:
        return
    if not _sweep():
        import sim
        sim._steps.insert(0, s_find_field)


@step
def s_hover_field():
    f = C.get("field")
    check(f"the search field is found ({f})", f is not None)
    if f:
        ev2('MOUSEMOVE', 'NOTHING', x=f[0], y=f[1])


@step
def s_click_field():
    if C.get("field"):
        ev2('LEFTMOUSE', 'PRESS')
        ev2('LEFTMOUSE', 'RELEASE')


@step
def s_type():
    if C.get("field"):
        for ch in "select toggle":
            ev2('TEXTINPUT', 'PRESS', unicode=ch)


@step
def s_enter():
    if C.get("field"):
        ev2('RET', 'PRESS')
        ev2('RET', 'RELEASE')
    redraw()


@step
def s_searched():
    wm = bpy.context.window_manager
    shown = [r.command for r in wm.allset_hk_rows]
    check(f"typed search = {wm.allset_hk_search!r}", wm.allset_hk_search == "select toggle")
    check(f"the list shows SelectToggleMode only ({shown})", shown == ["SelectToggleMode"])
    check("its kit key is F8", bool(wm.allset_hk_rows) and wm.allset_hk_rows[0].kit_key == "F8")
    wm.allset_hk_active = 0
    redraw()


@step
def s_shot_search():
    w, _a, _r = hk()
    if w is not None:
        shot("gui_step215_hotkey_search.png", w)


@step
def s_capture():
    w, area, region = hk()
    if w is None:
        return
    ev2('MOUSEMOVE', 'NOTHING', x=region.x + region.width // 2, y=region.y + region.height // 2)
    with bpy.context.temp_override(window=w, area=area, region=region):
        C["capture"] = bpy.ops.allset.hotkey_assign('INVOKE_DEFAULT')
    redraw()


@step
def s_capture_key():
    wm = bpy.context.window_manager
    check(f"Assign New Hotkey waits for a key ({C.get('capture')}, capturing={wm.allset_hk_capture})",
          wm.allset_hk_capture)
    if hk()[0] is not None:
        ev2('MOUSEMOVE', 'NOTHING')          # a plain move doesn't end the capture
        ev2('F6', 'PRESS', ctrl=True)
        ev2('F6', 'RELEASE', ctrl=True)


@step
def s_captured():
    he = mod(".ui.hotkey_editor")
    wm = bpy.context.window_manager
    row = next(r for r in he.rows() if r["command"] == "SelectToggleMode")
    C["row"] = row["index"]
    text = he.kit_text(bpy.context, row)
    check(f"the pressed Ctrl+F6 is the new key ({text}, capturing={wm.allset_hk_capture})",
          text == "Ctrl+F6 *" and not wm.allset_hk_capture)
    x, y = v3d_center()
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
    C["mode0"] = bpy.context.mode


@step
def s_old_key():
    ev('F8', 'PRESS')
    ev('F8', 'RELEASE')


@step
def s_old_key_done():
    check(f"F8 no longer toggles the selection mode ({C['mode0']} -> {bpy.context.mode})",
          bpy.context.mode == C["mode0"])
    ev('F6', 'PRESS', ctrl=True)
    ev('F6', 'RELEASE', ctrl=True)


@step
def s_new_key_done():
    check(f"Ctrl+F6 runs SelectToggleMode ({C['mode0']} -> {bpy.context.mode})", bpy.context.mode != C["mode0"])
    area, region = view3d()
    if bpy.context.mode != 'OBJECT':
        with bpy.context.temp_override(window=win(), area=area, region=region):
            bpy.ops.object.mode_set(mode='OBJECT')
    C["restore"] = bpy.ops.allset.hotkey_restore(row=C["row"])


@step
def s_restored():
    he = mod(".ui.hotkey_editor")
    text = he.kit_text(bpy.context, he.row_of(C["row"]))
    check(f"Restore gives F8 back ({C['restore']}, {text})", text == "F8")
    check("no user-modified keymap left",
          not any(km.is_user_modified for km in bpy.context.window_manager.keyconfigs.user.keymaps))
    w = hk()[0]
    if w is not None:
        with bpy.context.temp_override(window=w):
            bpy.ops.wm.window_close()


run()
