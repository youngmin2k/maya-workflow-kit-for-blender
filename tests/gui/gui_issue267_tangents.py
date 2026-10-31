"""Non-weighted tangents in a real UI (Maya Workflow Kit layout, the big view switched to the Graph Editor): dragging
a tangent handle of a non-weighted curve only turns it (the arm keeps a third of its key interval in time while the
mouse moves and after the release), Esc puts it back, one Ctrl+Z undoes the drag, and a weighted curve's handle still
follows the mouse in length."""

import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, run, step, setup, view3d, win, load_maya_layout  # noqa: E402

C = {}
THIRD = 10.0 / 3.0          # key 10's right interval (10 -> 20) / 3


def region():
    return next(r for r in C["area"].regions if r.type == 'WINDOW')


def curve():
    return import_module(MODULE + ".compat").id_fcurve_collection(bpy.data.objects["pCube1"]).find("location", index=0)


def key10():
    return curve().keyframe_points[1]


def arm():
    kp = key10()
    return kp.handle_right[0] - kp.co[0], kp.handle_right[1] - kp.co[1]


def reset(weighted):
    gw = import_module(MODULE + ".operators.graph_weights")
    fc = curve()
    gw.set_weighted(fc, weighted)
    for kp in fc.keyframe_points:
        kp.select_control_point = kp.select_left_handle = kp.select_right_handle = False
    kp = key10()
    kp.handle_left_type = kp.handle_right_type = 'ALIGNED'
    kp.co = (10.0, 0.05)
    kp.handle_left = (10.0 - THIRD, 0.055)
    kp.handle_right = (10.0 + THIRD, 0.045)
    kp.select_right_handle = True
    fc.update()
    C["area"].tag_redraw()


def modals():
    return [op.bl_idname for op in win().modal_operators if op.bl_idname.startswith("TRANSFORM_OT")]


def handle_px():
    kp = key10()
    x, y = region().view2d.view_to_region(kp.handle_right[0], kp.handle_right[1], clip=False)
    r = region()
    return int(round(r.x + x)), int(round(r.y + y))


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
    bpy.context.scene.tool_settings.use_snap_anim = False
    C["area"] = area
    area.ui_type = 'FCURVES'


@step
def s_frame():
    a = C["area"]
    a.spaces.active.use_normalization = False
    with bpy.context.temp_override(window=win(), area=a, region=region()):
        bpy.ops.graph.view_all()


def drag(name, weighted, button, finish, moves=((40, -25), (80, -50), (120, -80), (150, -60))):
    """Press on key 10's right handle with ``button``, move one step per tick (the arm read after each), then
    ``finish`` = 'RELEASE' / 'ESC'."""
    st = {"samples": []}

    def before():
        reset(weighted)
        st["start"] = arm()
        st["types"] = []

    step(before)
    step(lambda: None)

    def hover():
        st["p"] = handle_px()
        ev('MOUSEMOVE', 'NOTHING', x=st["p"][0], y=st["p"][1])
    step(hover)
    step(lambda: ev(button, 'PRESS', x=st["p"][0], y=st["p"][1]))
    for i, (dx, dy) in enumerate(moves):
        def mv(dx=dx, dy=dy, first=(i == 0)):
            if not first:
                st["samples"].append(arm())
                st["types"].append(modals())
            ev('MOUSEMOVE', 'NOTHING', x=st["p"][0] + dx, y=st["p"][1] + dy)
        step(mv)

    def last():
        st["samples"].append(arm())
        st["types"].append(modals())
        if finish == 'ESC':
            ev('ESC', 'PRESS')
            ev('ESC', 'RELEASE')
        else:
            ev(button, 'RELEASE')
    step(last)
    step(lambda: None)

    def verify():
        end = arm()
        print("GUI", name, "start", st["start"], "samples", st["samples"], "end", end, "modals", st["types"],
              flush=True)
        st["end"] = end
        moved = any(abs(s[1] - st["start"][1]) > 1e-4 for s in st["samples"])
        check(f"{name}: the drag reached the handle (a modal ran: {st['types'][0]}, arm moved: {moved})",
              bool(st["types"][0]) and moved)
        if finish == 'ESC':
            check(f"{name}: Esc puts the handle back ({end} vs {st['start']})",
                  abs(end[0] - st["start"][0]) < 1e-5 and abs(end[1] - st["start"][1]) < 1e-6)
            return
        if weighted:
            check(f"{name}: a weighted handle follows the mouse in length (dx {end[0]:.4f})",
                  abs(end[0] - THIRD) > 0.05)
            return
        mid = [s[0] for s in st["samples"]]
        check(f"{name}: while dragging the arm stays a third of the interval in time ({mid})",
              all(abs(x - THIRD) < 1e-4 for x in mid))
        s0, s1 = st["start"][1] / st["start"][0], end[1] / end[0]       # slope (value per frame)
        check(f"{name}: after the release the arm is a third in time ({end[0]:.5f}) and turned (slope {s0:.6f} -> "
              f"{s1:.6f})", abs(end[0] - THIRD) < 1e-4 and abs(s1 - s0) > 0.1 * abs(s0))
    step(verify)
    return st


LMB = drag("lmb_non_weighted", False, 'LEFTMOUSE', 'RELEASE')


def undo():
    r = region()
    ev('MOUSEMOVE', 'NOTHING', x=r.x + r.width // 2, y=r.y + r.height // 2)
    ev('LEFT_CTRL', 'PRESS', ctrl=True)
    ev('Z', 'PRESS', ctrl=True)
    ev('Z', 'RELEASE', ctrl=True)
    ev('LEFT_CTRL', 'RELEASE')


step(undo)
step(lambda: None)


@step
def s_undo_check():
    a = arm()
    check(f"one Ctrl+Z undoes the handle drag ({a} vs {LMB['start']})",
          abs(a[0] - LMB["start"][0]) < 1e-5 and abs(a[1] - LMB["start"][1]) < 1e-6)


drag("lmb_cancel", False, 'LEFTMOUSE', 'ESC')
drag("mmb_non_weighted", False, 'MIDDLEMOUSE', 'RELEASE')
drag("lmb_weighted", True, 'LEFTMOUSE', 'RELEASE')


@step
def s_watch_with_listeners():
    """The kit's click listeners stay up in the Maya layout; the 0.25 s watch still runs."""
    gw = import_module(MODULE + ".operators.graph_weights")
    listeners = [op.bl_idname for op in win().modal_operators]
    check(f"watch is not held up by the listener modals ({listeners})", gw._busy() is False)
    reset(False)
    handlers = bpy.app.handlers.depsgraph_update_post
    live = [fn for fn in handlers if getattr(fn, "__module__", "").endswith("graph_weights")]
    for fn in live:
        handlers.remove(fn)
    try:
        kp = key10()
        kp.handle_right = (kp.co[0] + 6.0, kp.co[1] - 0.006)
        n = gw.watch(bpy.context)
    finally:
        for fn in live:
            handlers.append(fn)
    check(f"watch puts a long arm back to a third ({n} arm(s), dx {arm()[0]:.5f})",
          n >= 1 and abs(arm()[0] - THIRD) < 1e-4)


@step
def s_blender_keying():
    """Blender's own Insert Keyframe on a new object: its curves get the Default Tangent Weight (non-weighted)."""
    C["area"].ui_type = 'VIEW_3D'
    area, reg = view3d()
    with bpy.context.temp_override(window=win(), area=area, region=reg):
        bpy.ops.allset.create(kind='SPHERE')
        bpy.ops.anim.keyframe_insert(type='Location')
    C["sphere"] = bpy.context.view_layer.objects.active.name


@step
def s_blender_keying_check():
    gw = import_module(MODULE + ".operators.graph_weights")
    ob = bpy.data.objects[C["sphere"]]
    fcs = list(import_module(MODULE + ".compat").id_fcurves(ob))
    check(f"Blender's Insert Keyframe makes non-weighted curves ({len(fcs)} curves)",
          len(fcs) >= 3 and all(not gw.is_weighted(fc) for fc in fcs))


run()
