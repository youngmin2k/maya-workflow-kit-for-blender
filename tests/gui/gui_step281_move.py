"""#192: in a real UI (Maya Workflow Kit layout, the big view switched to the Graph Editor): Shift+MMB moves
the selected key along time only or value only (the first 3 px decide, that motion is dropped), a single long move
then release moves nothing, Shift+LMB drag on a selected key locks the same way, and with time snap on a key at 10.3
moved by a plain MMB drag lands on frame 10."""

import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, run, step, setup, screenshot, view3d, win, load_maya_layout  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


def region():
    return next(r for r in C["area"].regions if r.type == 'WINDOW')


def curve():
    return import_module(MODULE + ".compat").id_fcurve_collection(bpy.data.objects["pCube1"]).find("location", index=0)


def key10():
    return min(curve().keyframe_points, key=lambda kp: abs(kp.co.x - 10.0))


def win_xy(rx, ry):
    r = region()
    return int(r.x + rx), int(r.y + ry)


def px_per_frame():
    v2d = region().view2d
    return v2d.view_to_region(11, 0, clip=False)[0] - v2d.view_to_region(10, 0, clip=False)[0]


def view_dv(dy):
    """Value change of a vertical drag of dy px in this view."""
    v2d = region().view2d
    return v2d.region_to_view(0, 300 + dy)[1] - v2d.region_to_view(0, 300)[1]


def reset_key(x=10.0, y=0.05):
    for kp in curve().keyframe_points:
        kp.select_control_point = kp.select_left_handle = kp.select_right_handle = False
    kp = key10()
    dx, dy = x - kp.co.x, y - kp.co.y
    kp.co = (x, y)
    kp.handle_left = (kp.handle_left.x + dx, kp.handle_left.y + dy)
    kp.handle_right = (kp.handle_right.x + dx, kp.handle_right.y + dy)
    kp.select_control_point = True
    curve().update()


def shift(value):
    ev('LEFT_SHIFT', value, shift=(value == 'PRESS'))


@step
def s_setup():
    setup()
    load_maya_layout()


@step
def s_scene():
    bpy.ops.allset.keymap_activate()
    area, reg = view3d()
    with bpy.context.temp_override(window=win(), area=area, region=reg):
        bpy.ops.allset.create(kind='CUBE')
    ob = bpy.data.objects["pCube1"]
    for f, v in ((1, 0.0), (10, 0.05), (20, 0.0)):
        ob.location.x = v
        ob.keyframe_insert("location", index=0, frame=f)
    prefs = import_module(MODULE + ".preferences").get()
    prefs.snap_time_to_selection = False
    if hasattr(prefs, "graph_auto_frame"):
        prefs.graph_auto_frame = False
    bpy.context.scene.tool_settings.use_snap_anim = True
    C["area"] = area
    area.ui_type = 'FCURVES'


@step
def s_frame():
    a = C["area"]
    a.spaces.active.use_normalization = False
    with bpy.context.temp_override(window=win(), area=a, region=region()):
        bpy.ops.graph.view_all()
    reset_key()
    r = region()
    ev('MOUSEMOVE', 'NOTHING', x=r.x + r.width // 2, y=r.y + r.height // 3)


@step
def s_measure():
    r = region()
    C["ppf"] = ppf = px_per_frame()
    C["mid"] = (r.width // 2, r.height // 3)          # MMB anywhere: away from the curve
    C["n2"] = int(round(2.3 * ppf))                    # 2.3 frames of drag after the deciding move
    print("GUI ppf", ppf, "region", r.width, r.height, flush=True)
    check(f"Graph Editor view is wide enough for the drags ({ppf:.1f} px / frame)", ppf >= 8)


def _case(name, button, moves_fn, press_fn, expect_fn, mods=True, prep=None):
    seq_state = {}

    def before():
        reset_key()
        if prep:
            prep()
        seq_state["press"] = press_fn()
        seq_state["moves"] = moves_fn()
        seq_state["start"] = tuple(key10().co)

    step(before)
    step(lambda: None)
    if mods:
        step(lambda: shift('PRESS'))

    def press():
        x, y = win_xy(*seq_state["press"])
        ev('MOUSEMOVE', 'NOTHING', x=x, y=y, shift=mods)
    step(press)

    def down():
        x, y = win_xy(*seq_state["press"])
        ev(button, 'PRESS', x=x, y=y, shift=mods)
    step(down)
    for i in range(8):
        def mv(i=i):
            moves = seq_state["moves"]
            if i < len(moves):
                p = seq_state["press"]
                x, y = win_xy(p[0] + moves[i][0], p[1] + moves[i][1])
                ev('MOUSEMOVE', 'NOTHING', x=x, y=y, shift=mods)
        step(mv)
    step(lambda: ev(button, 'RELEASE', shift=mods))
    if mods:
        step(lambda: shift('RELEASE'))
    step(lambda: None)
    step(lambda: None)

    def verify():
        kp = key10()
        ok, text = expect_fn(seq_state["start"], tuple(kp.co))
        check(f"{name}: {text} (key {seq_state['start'][0]:.3f}, {seq_state['start'][1]:.4f} -> "
              f"{kp.co.x:.3f}, {kp.co.y:.4f})", ok)
        if SHOTS:
            screenshot(os.path.join(SHOTS, f"step281_{name.split(':')[0].replace(' ', '_')}.png"))
    step(verify)


def _mid():
    return C["mid"]


def _key_px():
    kp = key10()
    return tuple(int(round(v)) for v in region().view2d.view_to_region(kp.co.x, kp.co.y, clip=False))


_case("shift_mmb_time", 'MIDDLEMOUSE', lambda: [(3, 0), (3 + C["n2"], 0), (3 + C["n2"], -2)], _mid,
      lambda s, e: (e[0] == s[0] + 2 and abs(e[1] - s[1]) < 1e-6, "time only, +2 frames"))

C_DV = {}


def _value_moves():
    C_DV["dv"] = view_dv(-60)
    return [(0, -3), (0, -63), (2, -63)]


_case("shift_mmb_value", 'MIDDLEMOUSE', _value_moves, _mid,
      lambda s, e: (e[0] == s[0] and abs((e[1] - s[1]) - C_DV["dv"]) < 1e-3 * max(1.0, abs(C_DV["dv"])),
                    f"value only, {C_DV.get('dv', 0):.4f} expected"))

_case("shift_mmb_single_move", 'MIDDLEMOUSE', lambda: [(60, 0)], _mid,
      lambda s, e: (e == s, "one 60 px move then release moves nothing"))

def _unselect():
    key10().select_control_point = False      # Shift+press toggles it on, then the drag moves it


_case("shift_lmb_time", 'LEFTMOUSE', lambda: [(6, 1), (6 + C["n2"], 1), (6 + C["n2"], -1)], _key_px,
      lambda s, e: (e[0] == s[0] + 2 and abs(e[1] - s[1]) < 1e-6, "Shift+LMB drag on the key: time only, +2"),
      prep=_unselect)


def _fraction():
    reset_key(10.3)


_case("mmb_snap_fraction", 'MIDDLEMOUSE',
      lambda: [(int(round(0.38 * C["ppf"])), 0), (int(round(0.38 * C["ppf"])), 0)], _mid,
      lambda s, e: (e[0] == 10.0, "time snap: 10.3 + 0.38 f lands on 10"), mods=False, prep=_fraction)

_case("mmb_snap_fraction_up", 'MIDDLEMOUSE',
      lambda: [(int(round(0.62 * C["ppf"])), 0), (int(round(0.62 * C["ppf"])), 0)], _mid,
      lambda s, e: (e[0] == 11.0, "time snap: 10.3 + 0.62 f lands on 11"), mods=False, prep=_fraction)


run()
