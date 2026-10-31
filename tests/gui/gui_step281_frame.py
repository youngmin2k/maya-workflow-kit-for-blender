"""#192: in a real UI: Graph Editor F / A frame Maya's rectangle (operators/graph_frame.py) and View > Auto
Frame refits the value axis only. pCube1 Translate Y keys (1, -10) (30, 40) and Scale X keys (1, 0) (5, 4) (10, 6)
(15, 2) (25, 8), linear: A = time [-1.9, 32.9], value [-22.5, 52.5]; F on Scale X key 25 = time [14, 26], value
[0.5, 9.5]; F with no key selected = A. The canvas between the time ruler strip and the scroll bar shows those
ranges within half a pixel."""

import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, run, screenshot, setup, step, tap, win  # noqa: E402

A = {}
SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
# before the keymap integration: bind F / A here (head of the add-on "Graph Editor" keymap) to try the operator
LOCAL = os.environ.get("ALLSET_281C_LOCAL") == "1"


def gf():
    return import_module(MODULE + ".operators.graph_frame")


def ge():
    a = A["area"]
    return a, next(r for r in a.regions if r.type == 'WINDOW')


def canvas():
    a, r = ge()
    with bpy.context.temp_override(window=win(), area=a, region=r):
        bottom, top = gf().pads(bpy.context, a.spaces.active)
    w, h = gf().span_px(r)
    v = r.view2d
    x0, y0 = v.region_to_view(0.0, bottom)
    x1, y1 = v.region_to_view(float(w), h - top)
    return x0, x1, y0, y1


def near(name, want, px=0.5, got=None):
    a, r = ge()
    got = canvas() if got is None else got
    w, h = gf().span_px(r)
    sx = (want[1] - want[0]) / w
    sy = (want[3] - want[2]) / h
    err = max(abs(g - t) / s for g, t, s in zip(got, want, (sx, sx, sy, sy)))
    print("GUI281", name, "got", tuple(round(v, 4) for v in got), "want", want, "err px", round(err, 4), flush=True)
    check(f"{name}: within {px} px of {want} (err {err:.3f} px)", err <= px)


def hover():
    a, r = ge()
    ev('MOUSEMOVE', 'NOTHING', x=r.x + r.width // 2, y=r.y + r.height // 2)


def select_keys(frames_by_path):
    ob = A["ob"]
    for fc in import_module(MODULE + ".compat").id_fcurves(ob):
        for p in fc.keyframe_points:
            p.select_control_point = (fc.data_path, fc.array_index) in frames_by_path and \
                p.co.x in frames_by_path[(fc.data_path, fc.array_index)]
            p.select_left_handle = p.select_right_handle = False
    for area in win().screen.areas:
        area.tag_redraw()


def set_view(view):
    a, r = ge()
    with bpy.context.temp_override(window=win(), area=a, region=r):
        gf().apply_view(bpy.context, r, view)
    a.tag_redraw()


@step
def s_setup():
    setup()
    scr = win().screen
    area = max(scr.areas, key=lambda a: a.width * a.height)
    area.ui_type = 'FCURVES'
    A["area"] = area
    sc = bpy.context.scene
    sc.timeline_markers.clear()
    ob = bpy.data.objects.get("Cube")
    for f, v in ((1, -10.0), (30, 40.0)):
        ob.location[1] = v
        ob.keyframe_insert("location", index=1, frame=f)
    for f, v in ((1, 0.0), (5, 4.0), (10, 6.0), (15, 2.0), (25, 8.0)):
        ob.scale[0] = v
        ob.keyframe_insert("scale", index=0, frame=f)
    A["ob"] = ob
    select_keys({})
    for o in sc.objects:
        o.select_set(o is ob)
    bpy.context.view_layer.objects.active = ob
    for fc in import_module(MODULE + ".compat").id_fcurves(ob):
        for p in fc.keyframe_points:
            p.interpolation = 'LINEAR'
    import_module(MODULE + ".preferences").get(bpy.context).graph_auto_frame = True
    if LOCAL:
        if not hasattr(bpy.types, "ALLSET_OT_graph_frame"):
            bpy.utils.register_class(gf().ALLSET_OT_graph_frame)
        A["kmi"] = []
        for kc in (bpy.context.window_manager.keyconfigs.addon, bpy.context.window_manager.keyconfigs.user):
            km = kc.keymaps.get("Graph Editor")
            for kmi in (km.keymap_items if km else ()):
                if kmi.idname in ("graph.view_all", "graph.view_selected") and kmi.type in ('A', 'F') \
                        and not (kmi.shift or kmi.ctrl or kmi.alt):
                    old = kmi.idname
                    kmi.idname = "allset.graph_frame"
                    kmi.properties.mode = 'ALL' if old == "graph.view_all" else 'SELECTED'
                    A["kmi"].append((kc.name, kmi.type))
        print("GUI281 local keys", A["kmi"], flush=True)


@step
def s_wait():
    for a in win().screen.areas:
        a.tag_redraw()


@step
def s_view_off():
    set_view((100.0, 160.0, 300.0, 900.0))       # somewhere else, so the keys must move the view
    hover()


@step
def s_press_a():
    tap('A')


@step
def s_check_a():
    near("A frames every curve", gf().maya_rect((1, 30, -10, 40)))
    if SHOTS:
        screenshot(os.path.join(SHOTS, "gui_step281_frame_a.png"))
    select_keys({("scale", 0): (25,)})
    set_view((100.0, 160.0, 300.0, 900.0))
    hover()


@step
def s_press_f_key25():
    tap('F')


@step
def s_check_f_key25():
    near("F on Scale X key 25", (14.0, 26.0, 0.5, 9.5))
    select_keys({("scale", 0): (1,)})
    hover()


@step
def s_press_f_key1():
    tap('F')


@step
def s_check_f_key1():
    near("F on Scale X key 1", (0.6, 5.4, -1.0, 5.0))
    select_keys({})
    set_view((100.0, 160.0, 300.0, 900.0))
    hover()


@step
def s_press_f_none():
    tap('F')


@step
def s_check_f_none():
    near("F with no key selected = A", gf().maya_rect((1, 30, -10, 40)))
    set_view((-4.0, 25.0, -100.0, 100.0))
    A["before"] = gf().current_view(ge()[1])
    A["ob"].select_set(False)                     # Auto Frame: a selection change (timer polls every 0.25 s)


@step
def s_reselect():
    A["ob"].select_set(True)
    bpy.context.view_layer.objects.active = A["ob"]


@step
def s_wait_auto():
    pass


@step
def s_wait_auto_2():
    pass


@step
def s_check_auto():
    x0, x1, _y0, _y1 = gf().current_view(ge()[1])
    b = A["before"]
    check(f"Auto Frame keeps the time range ({x0:.4f}, {x1:.4f})", abs(x0 - b[0]) < 1e-3 and abs(x1 - b[1]) < 1e-3)
    c = canvas()
    near("Auto Frame refits the value axis", (b[0], b[1]) + gf().maya_rect((1, 30, -10, 40))[2:], got=c)


run()
