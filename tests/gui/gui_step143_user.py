"""User reports in a real UI.

- #82: a Maya menu item's option box (Display > Grid): a click on the box mark runs the command (Python can't tell
  where on the item a click landed); press and hold the item, drag onto the "Option Box" row Blender opens below it
  and release = the option box (``allset.menu_option_box``). The hold also works work without the drag
  (gui_step146_option_box.py); the drag keeps working.
- #80: face -> Ctrl+E -> extrude manipulator; W then shows the Move manipulator, and its centre drag moves the new
  faces; F9 / F10 / F11 switch the component mode with the mouse over the viewport.
- #84: the double-click loop pick (``allset.loop_pick`` invoked at the mouse; event simulation can't send
  DOUBLE_CLICK) raises nothing (5.1+ has no ``ring`` keyword).
"""

import os
import sys
from importlib import import_module

import bmesh
import bpy
from bpy_extras import view3d_utils

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, px, run, setup, step, tap, view3d, win  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {"calls": []}


def mod(name):
    return import_module(MODULE + name)


def shot(name):
    if SHOTS:
        with bpy.context.temp_override(window=win()):
            bpy.ops.screen.screenshot(filepath=os.path.join(SHOTS, name))


def cube():
    return bpy.data.objects["Cube"]


def v3d_ctx():
    area, region = view3d()
    return bpy.context.temp_override(window=win(), area=area, region=region, space_data=area.spaces.active)


def redraw():
    for a in win().screen.areas:
        a.tag_redraw()


def ts():
    return bpy.context.scene.tool_settings


def _spy(cls, tag):
    """Record calls of a registered operator's execute (Blender looks the method up on the class per call)."""
    orig = cls.execute

    def execute(self, context):
        C["calls"].append((tag, getattr(self, "item", "")))
        return orig(self, context)
    cls.execute = execute
    C.setdefault("restore", []).append((cls, orig))


def cap_point():
    """Window point of the selected faces' centre."""
    area, region = view3d()
    bm = bmesh.from_edit_mesh(cube().data)
    vs = [v.co for v in bm.verts if v.select]
    c = cube().matrix_world @ (sum(vs, vs[0] * 0) / len(vs))
    p = view3d_utils.location_3d_to_region_2d(region, area.spaces.active.region_3d, c)
    return region.x + round(p.x), region.y + round(p.y)


def selected_centre():
    bm = bmesh.from_edit_mesh(cube().data)
    vs = [v.co.copy() for v in bm.verts if v.select]
    return sum(vs, vs[0] * 0) / len(vs)


# --- #82 option boxes ------------------------------------------------------------------------------------

@step
def s_setup():
    C["x"], C["y"] = setup()
    bpy.ops.allset.keymap_activate()
    bpy.context.preferences.view.show_tooltips = False
    ms = mod(".ui.menu_sets")
    _spy(ms.ALLSET_OT_menu_option_box, "box")
    _spy(ms.ALLSET_OT_menu_item, "item")


def open_display():
    with v3d_ctx():
        bpy.ops.wm.call_menu(name=mod(".ui.menu_sets").menu_idname("mainDisplayMenu"))


# Maya 2026 Display menu: Grid's row is 9 px above the mouse
GRID_ROW_UP = 9


def grid_box():
    """Window point of Grid's option box mark: Blender opens this menu with its "Heads Up Display" row near the mouse
    (first-open shot 143_display_menu.png at effective scale 1.25: Grid's row 34 px above the mouse, its box mark
    63 px right of it)."""
    return C["x"] + px(63), C["y"] + px(GRID_ROW_UP)


@step
def s_open_display():
    ev('MOUSEMOVE', 'NOTHING', x=C["x"], y=C["y"])
    open_display()


@step
def s_hover_box():
    shot("143_display_menu.png")
    C["row"] = grid_box()
    ev('MOUSEMOVE', 'NOTHING', x=C["row"][0] - 4, y=C["row"][1])


@step
def s_hover_box2():
    ev('MOUSEMOVE', 'NOTHING', x=C["row"][0], y=C["row"][1])


@step
def s_settle_box():
    shot("143_box_hover.png")      # one tick on the row before the click (a click right after the move was lost once)


@step
def s_settle_box2():
    pass        # 5.2: one more tick before the first click in a just-opened menu


@step
def s_click_box():
    ev('LEFTMOUSE', 'PRESS', x=C["row"][0], y=C["row"][1])
    ev('LEFTMOUSE', 'RELEASE', x=C["row"][0], y=C["row"][1])


@step
def s_clicked_box():
    C["click"] = list(C["calls"])
    del C["calls"][:]
    print("GUI143 click on the box mark:", C["click"], flush=True)
    # #82 (0.4.0): the item is one button (a second button on a menu line staircases the menu) and Python
    # can't tell where on it the click landed (the operator runs with the opener's region), so a click on
    # the box mark runs the command like a click on the label
    check(f"#82 a click on Grid's box mark runs the command ({C['click']})",
          C["click"] == [("item", "Display/Grid")])
    tap('ESC')       # an option window, if one opened
    ev('MOUSEMOVE', 'NOTHING', x=C["x"], y=C["y"])


@step
def s_reopen():
    open_display()


@step
def s_hover_label():
    C["row"] = (C["x"], grid_box()[1])        # on the label: the command
    ev('MOUSEMOVE', 'NOTHING', x=C["row"][0] - 4, y=C["row"][1])


@step
def s_hover_label2():
    ev('MOUSEMOVE', 'NOTHING', x=C["row"][0], y=C["row"][1])


@step
def s_press_label():
    ev('LEFTMOUSE', 'PRESS', x=C["row"][0], y=C["row"][1])


@step
def s_holding():
    pass     # held across ticks (0.4 s each): Blender's hold menu opens after its hold time


@step
def s_held():
    # Blender opens the hold menu below the held button: the button stays down while the mouse goes onto its row
    shot("143_grid_held.png")
    ev('MOUSEMOVE', 'NOTHING', x=C["row"][0], y=C["row"][1] - px(14))


@step
def s_onto_option_box():
    ev('MOUSEMOVE', 'NOTHING', x=C["row"][0], y=C["row"][1] - px(30))


@step
def s_on_option_box():
    shot("143_hold_menu.png")
    C["after_hold"] = list(C["calls"])
    ev('LEFTMOUSE', 'RELEASE', x=C["row"][0], y=C["row"][1] - px(30))


@step
def s_released():
    pass


@step
def s_option_box_result():
    shot("143_option_box.png")
    print("GUI143 calls after hold:", C["after_hold"], "after click:", C["calls"], flush=True)
    check(f"#82 press and hold on Grid runs nothing yet ({C['after_hold']})", not C["after_hold"])
    check(f"#82 hold, drag onto the hold menu's Option Box row, release: the option box ({C['calls']})", ("box", "Display/Grid") in C["calls"])     # box_hold, then box
    tap('ESC')


@step
def s_restore_spies():
    for cls, orig in C.get("restore", ()):
        cls.execute = orig
    tap('ESC')


# --- #80 extrude, then W; F9 / F10 / F11 --------------------------------------------------------------------

@step
def s_edit():
    ev('MOUSEMOVE', 'NOTHING', x=C["x"], y=C["y"])
    for o in bpy.context.view_layer.objects:
        o.select_set(o.name == "Cube")
    bpy.context.view_layer.objects.active = cube()
    with v3d_ctx():
        bpy.ops.object.mode_set('EXEC_DEFAULT', True, mode='EDIT')
    ts().mesh_select_mode = (False, False, True)
    bm = bmesh.from_edit_mesh(cube().data)
    for f in bm.faces:
        f.select_set(False)
    for f in bm.faces:
        if f.normal.z > 0.9:
            f.select_set(True)
    bm.select_flush_mode()
    bmesh.update_edit_mesh(cube().data)
    with v3d_ctx():
        bpy.ops.wm.tool_set_by_id(name="builtin.move")
    redraw()


@step
def s_ctrl_e():
    ev('E', 'PRESS', ctrl=True)
    ev('E', 'RELEASE', ctrl=True)


def manip_poll():
    gg = mod(".ui.manipulator")
    cls = next(c for c in gg.classes if getattr(c, "bl_idname", "") == gg.GROUP)
    with v3d_ctx():
        return bool(cls.poll(bpy.context))


@step
def s_extruded():
    with v3d_ctx():
        shown = mod(".ui.in_view").manip_visible(bpy.context)
    check(f"#80 Ctrl+E: extrude manipulator shown, Move manipulator hidden (extrude {shown}, move {manip_poll()})",
          shown and not manip_poll())
    redraw()
    shot("143_extruded.png")
    tap('W')


@step
def s_w():
    with v3d_ctx():
        shown = mod(".ui.in_view").manip_visible(bpy.context)
    rec = mod(".operators.extrude").active(bpy.context)[1]
    check(f"#80 W after Ctrl+E: Move manipulator back, extrude one gone (extrude {shown}, move {manip_poll()})",
          not shown and manip_poll())
    check(f"#80 the extrusion stays in Channel Box INPUTS ({rec and rec.name})", rec is not None)
    redraw()


@step
def s_w_shot():
    shot("143_after_w.png")
    C["before"] = selected_centre()
    C["p"] = cap_point()
    ev('MOUSEMOVE', 'NOTHING', x=C["p"][0], y=C["p"][1])


@step
def s_press_centre():
    ev('LEFTMOUSE', 'PRESS', x=C["p"][0], y=C["p"][1])


@step
def s_drag_1():
    ev('MOUSEMOVE', 'NOTHING', x=C["p"][0] + 20, y=C["p"][1] + 20)


@step
def s_drag_2():
    ev('MOUSEMOVE', 'NOTHING', x=C["p"][0] + 40, y=C["p"][1] + 40)


@step
def s_release_centre():
    ev('LEFTMOUSE', 'RELEASE', x=C["p"][0] + 40, y=C["p"][1] + 40)


@step
def s_moved():
    d = (selected_centre() - C["before"]).length
    check(f"#80 dragging the Move manipulator's centre moves the extruded faces ({d:.3f})", d > 0.05)
    ev('MOUSEMOVE', 'NOTHING', x=C["x"], y=C["y"])
    tap('F9')


@step
def s_f9():
    m = tuple(ts().mesh_select_mode)
    check(f"#80 F9 over the viewport: vertex mode ({bpy.context.mode}, {m})",
          bpy.context.mode == 'EDIT_MESH' and m == (True, False, False))
    tap('F10')


@step
def s_f10():
    m = tuple(ts().mesh_select_mode)
    check(f"#80 F10: edge mode ({m})", m == (False, True, False))
    tap('F11')


@step
def s_f11():
    m = tuple(ts().mesh_select_mode)
    check(f"#80 F11: face mode ({m})", m == (False, False, True))
    with v3d_ctx():
        bpy.ops.object.mode_set(mode='OBJECT')
    tap('F10')


@step
def s_f10_object():
    m = tuple(ts().mesh_select_mode)
    check(f"#80 F10 in object mode: edit mode, edge mode ({bpy.context.mode}, {m})",
          bpy.context.mode == 'EDIT_MESH' and m == (False, True, False))
    bm = bmesh.from_edit_mesh(cube().data)
    for e in bm.edges:
        e.select_set(False)
    bm.edges.ensure_lookup_table()
    bm.edges[0].select_set(True)
    bm.select_flush_mode()
    bmesh.update_edit_mesh(cube().data)
    C["windows"] = len(bpy.context.window_manager.windows)
    ev('MOUSEMOVE', 'NOTHING', x=C["x"], y=C["y"])
    tap('F12')


@step
def s_f12():
    n = len(bpy.context.window_manager.windows)
    print("GUI143 F12:", "sync", ts().use_uv_select_sync, "windows", C["windows"], "->", n, flush=True)
    check(f"#80 F12: Maya UV mode (UV sync off, UV Editor window {C['windows']} -> {n})",
          not ts().use_uv_select_sync and n == C["windows"] + 1)


@step
def s_f12_settle():
    ev('MOUSEMOVE', 'NOTHING', x=C["x"], y=C["y"])


@step
def s_f9_after_f12():
    tap('F9')


@step
def s_f9_after_f12_result():
    bm = bmesh.from_edit_mesh(cube().data)
    nv = sum(v.select for v in bm.verts)
    m = tuple(ts().mesh_select_mode)
    print("GUI143 F9 after F12:", "sync", ts().use_uv_select_sync, "mode", m, "verts", nv, "of", len(bm.verts), flush=True)
    check(f"#80 F9 after F12: vertex mode with UV sync back on ({m}, sync {ts().use_uv_select_sync})",
          m == (True, False, False) and ts().use_uv_select_sync)
    check(f"#80 F9 after F12: the edge selected before F12 is the selection again ({nv} vertices)", nv == 2)


# --- #84 double-click loop pick ---------------------------------------------------------------------------------

@step
def s_loop_pick():
    bm = bmesh.from_edit_mesh(cube().data)
    for e in bm.edges:
        e.select_set(False)
    bmesh.update_edit_mesh(cube().data)
    e = max(bm.edges, key=lambda e: (e.verts[0].co + e.verts[1].co).z)
    area, region = view3d()
    mid = cube().matrix_world @ ((e.verts[0].co + e.verts[1].co) / 2)
    p = view3d_utils.location_3d_to_region_2d(region, area.spaces.active.region_3d, mid)
    C["e"] = (region.x + round(p.x), region.y + round(p.y))
    ev('MOUSEMOVE', 'NOTHING', x=C["e"][0], y=C["e"][1])


@step
def s_loop_pick_invoke():
    area, region = view3d()
    try:
        with bpy.context.temp_override(window=win(), area=area, region=region):
            res = bpy.ops.allset.loop_pick('INVOKE_DEFAULT', between=False)
        err = None
    except Exception as ex:      # #84: TypeError "keyword "ring" unrecognized" on 5.1+
        res, err = None, ex
    n = sum(e.select for e in bmesh.from_edit_mesh(cube().data).edges)
    check(f"#84 double-click loop pick runs without an error ({res}, {err!r}, {n} edges)", err is None and n >= 1)


run()
