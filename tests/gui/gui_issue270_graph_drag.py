"""Graph Editor key drags past the last key (#270) in a real UI (Maya Workflow Kit layout, the big view switched to
the Graph Editor): a left drag and a middle drag that carry a key past its neighbour keep the key count, land the
key where the mouse went and come back with one undo; r / e / w over the Graph Editor pick the key tools."""

import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, run, step, setup, screenshot, view3d, win, load_maya_layout  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}
FRAMES = ((1, 0.0), (10, 0.05), (20, 0.02))


def region():
    return next(r for r in C["area"].regions if r.type == 'WINDOW')


def fcurves():
    return list(import_module(MODULE + ".compat").id_fcurves(bpy.data.objects["pCube1"]))


def curve():
    return import_module(MODULE + ".compat").id_fcurve_collection(bpy.data.objects["pCube1"]).find("location", index=0)


def state():
    return [(fc.data_path, fc.array_index, tuple((round(kp.co.x, 4), round(kp.co.y, 5)) for kp in fc.keyframe_points))
            for fc in fcurves()]


def win_xy(rx, ry):
    r = region()
    return int(r.x + rx), int(r.y + ry)


def key_px(frame):
    kp = min(curve().keyframe_points, key=lambda k: abs(k.co.x - frame))
    return tuple(int(round(v)) for v in region().view2d.view_to_region(kp.co.x, kp.co.y, clip=False))


def frame_px(frame):
    return region().view2d.view_to_region(frame, 0.0, clip=False)[0]


def select_only(frames, every=False):
    for fc in fcurves():
        fc.select = every or (fc.data_path == "location" and fc.array_index == 0)
        for kp in fc.keyframe_points:
            on = fc.select and any(abs(kp.co.x - f) < 1e-3 for f in frames)
            kp.select_control_point = on
            kp.select_left_handle = kp.select_right_handle = False


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
    scene = bpy.context.scene
    for f, v in FRAMES:
        scene.frame_set(f)
        ob.location.x = v
        with bpy.context.temp_override(window=win(), area=area, region=reg):
            bpy.ops.allset.set_key()            # the kit's S: every keyable channel, the kit's tangents
    scene.frame_set(1)
    p = import_module(MODULE + ".preferences").get()
    p.snap_time_to_selection = False
    p.graph_auto_frame = False
    p.graph_auto_frame_time = False
    p.graph_unconstrained_drag = True
    bpy.context.window_manager.allset_graph_key_tool = 'MOVE'
    C["area"] = area
    area.ui_type = 'FCURVES'


def frame_view():
    a = C["area"]
    a.spaces.active.use_normalization = False
    with bpy.context.temp_override(window=win(), area=a, region=region()):
        bpy.ops.graph.view_all()


def zoom_out():
    # room on the right of frame 20 for the drag
    a = C["area"]
    with bpy.context.temp_override(window=win(), area=a, region=region()):
        bpy.ops.view2d.zoom_in(zoomfacx=-0.25, zoomfacy=0.0)
    r = region()
    ev('MOUSEMOVE', 'NOTHING', x=r.x + r.width // 2, y=r.y + r.height // 3)


step(frame_view)
step(zoom_out)


def _values(st):
    return [(c[0], c[1], sorted(v for _f, v in c[2])) for c in st]


def _drag_case(name, button, frame_to, auto_key=False, current=1, frames=(10,), every=False):
    st = {}
    for _ in range(10):
        step(lambda: None)
    step(frame_view)
    step(zoom_out)

    def before():
        bpy.context.scene.tool_settings.use_snap_anim = True
        bpy.context.scene.allset_auto_key = auto_key
        bpy.context.scene.frame_set(current)
        select_only(frames, every)
        bpy.ops.ed.undo_push(message=f"{name} select")
        st["before"] = state()
        st["press"] = key_px(10)
        st["count"] = sum(len(fc.keyframe_points) for fc in fcurves())
        st["to"] = int(round(frame_px(frame_to)))
    step(before)

    def hover():
        ev('MOUSEMOVE', 'NOTHING', x=win_xy(*st["press"])[0], y=win_xy(*st["press"])[1])
    step(hover)
    step(lambda: ev(button, 'PRESS', x=win_xy(*st["press"])[0], y=win_xy(*st["press"])[1]))
    n = 8
    for i in range(1, n + 1):
        def mv(i=i):
            px0 = st["press"][0]
            x = px0 + (st["to"] - px0) * i / n
            ev('MOUSEMOVE', 'NOTHING', x=win_xy(x, st["press"][1])[0], y=win_xy(x, st["press"][1])[1])
        step(mv)
    step(lambda: ev(button, 'RELEASE'))
    for _ in range(4):
        step(lambda: None)

    def verify():
        after = state()
        count = sum(len(fc.keyframe_points) for fc in fcurves())
        xs = [kp.co.x for kp in curve().keyframe_points]
        check(f"{name}: no key added or lost ({st['count']} -> {count})", count == st["count"])
        check(f"{name}: the dragged key landed past the last key ({xs})", len(xs) == 3 and xs[2] > 20.5)
        check(f"{name}: every curve keeps its key values, no two keys on one frame",
              _values(after) == _values(st["before"])
              and all(len({f for f, _v in c[2]}) == len(c[2]) for c in after))
        if not every and frames == (10,):
            others = [c for c in after if not (c[0] == "location" and c[1] == 0)]
            check(f"{name}: other curves untouched", others == [c for c in st["before"]
                                                                if not (c[0] == "location" and c[1] == 0)])
        if SHOTS:
            screenshot(os.path.join(SHOTS, f"issue270_{name}.png"))
        x, y = win_xy(region().width // 2, region().height // 3)
        ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
    step(verify)

    def undo():
        ev('LEFT_CTRL', 'PRESS', ctrl=True)
        ev('Z', 'PRESS', ctrl=True)
        ev('Z', 'RELEASE', ctrl=True)
        ev('LEFT_CTRL', 'RELEASE')
    step(undo)
    step(lambda: None)
    step(lambda: None)

    def verify_undo():
        check(f"{name}: one undo puts every key back ({state()[0][2]})", state() == st["before"])
    step(verify_undo)


_drag_case("lmb_past_last", 'LEFTMOUSE', 26)
_drag_case("mmb_past_last", 'MIDDLEMOUSE', 26)
# with Auto Key on and the current time inside the curve part the drag changes: no key at the current time
_drag_case("lmb_auto_key", 'LEFTMOUSE', 26, auto_key=True, current=15)
_drag_case("mmb_auto_key", 'MIDDLEMOUSE', 26, auto_key=True, current=15)
# several keys on every curve slid past the last key
_drag_case("lmb_columns_auto", 'LEFTMOUSE', 26, frames=(1, 10), every=True, auto_key=True, current=15)
_drag_case("mmb_columns_auto", 'MIDDLEMOUSE', 26, frames=(1, 10), every=True, auto_key=True, current=15)


@step
def s_r():
    x, y = win_xy(region().width // 2, region().height // 3)
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
    ev('R', 'PRESS')
    ev('R', 'RELEASE')


@step
def s_r_check():
    check("r over the Graph Editor picks the Scale Keys tool",
          bpy.context.window_manager.allset_graph_key_tool == 'SCALE')
    bpy.context.window_manager.allset_graph_key_tool = 'MOVE'


run()
