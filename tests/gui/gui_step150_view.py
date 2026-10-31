"""Lane A (#96) in a real UI: Maya Workflow Kit layout, pCube1 Translate X / Y keyed, Graph Editor from
Windows > Animation Editors. View > Curve Name > Always writes "pCube1.translateX" / "pCube1.translateY" beside the
last keys in the curve colours (Never: nothing); View > Auto Frame (on by default, like Maya) refits the value axis when
the selection changes to pCube2 (keys at 40 .. 200, values 0 .. 50; the time range stays)."""

import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, run, setup, step, win, load_maya_layout  # noqa: E402

GUI_TIMEOUT = 200
SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "") or bpy.app.tempdir
C = {}


def mod(name):
    return import_module(MODULE + name)


def prefs():
    return mod(".preferences").get(bpy.context)


def shot(name, window):
    path = os.path.join(SHOTS, name)
    with bpy.context.temp_override(window=window):
        bpy.ops.screen.screenshot(filepath=path)
    return path


def editor():
    for w in bpy.context.window_manager.windows:
        for a in w.screen.areas:
            if a.ui_type == 'FCURVES':
                return w, a, next(r for r in a.regions if r.type == 'WINDOW')
    return None, None, None


def redraw():
    for w in bpy.context.window_manager.windows:
        for a in w.screen.areas:
            a.tag_redraw()


def pixels(path):
    import numpy as np
    img = bpy.data.images.load(path)
    w, h = img.size
    px = np.empty(w * h * 4, dtype=np.float32)
    img.pixels.foreach_get(px)
    bpy.data.images.remove(img)
    return px.reshape(h, w, 4)[..., :3]


def view_x(r):
    v = r.view2d
    return v.region_to_view(0, 0)[0], v.region_to_view(r.width, 0)[0]


def select(name):
    for o in bpy.context.scene.objects:
        o.select_set(o.name == name)
    bpy.context.view_layer.objects.active = bpy.data.objects[name]


@step
def s_setup():
    setup()
    bpy.ops.allset.make_maya(open_layout=False)
    load_maya_layout()


@step
def s_scene():
    area = max((a for a in win().screen.areas if a.type == 'VIEW_3D'), key=lambda a: a.width * a.height)
    region = next(r for r in area.regions if r.type == 'WINDOW')
    k = mod(".operators.units").maya_unit()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        for name, keys in (("A", ((0, 1, 0.0), (0, 24, 5.0), (1, 1, 0.0), (1, 24, 3.0))),
                           ("B", ((2, 40, 0.0), (2, 200, 50.0)))):
            bpy.ops.allset.create(kind='CUBE')
            ob = bpy.context.active_object
            for axis, frame, v in keys:
                ob.location[axis] = v * k
                ob.keyframe_insert("location", index=axis, frame=frame)
            C[name] = ob.name
    select(C["A"])
    prefs().graph_curve_names = 'NEVER'
    prefs().graph_auto_frame = True
    with bpy.context.temp_override(window=win(), area=area, region=region):
        bpy.ops.allset.menu_item(item="Windows/Animation Editors/Graph Editor")


@step
def s_frame():
    w, a, r = editor()
    check("Graph Editor window opened", r is not None)
    with bpy.context.temp_override(window=w, area=a, region=r):
        bpy.ops.graph.view_all()
    redraw()


@step
def s_wait():
    redraw()


@step
def s_never_shot():
    w, a, r = editor()
    C["never"] = shot("gui_step150_curve_names_never.png", w)
    prefs().graph_curve_names = 'ALWAYS'
    redraw()


@step
def s_wait2():
    redraw()


@step
def s_always_shot():
    import numpy as np
    gv = mod(".ui.graph_view")
    w, a, r = editor()
    with bpy.context.temp_override(window=w, area=a, region=r):
        items = gv.name_items(bpy.context, r)
    texts = sorted(t for _x, _y, t, _c in items)
    want = sorted([f"{C['A']}.translateX", f"{C['A']}.translateY"])
    check(f"Curve Name > Always names the shown curves the Maya way ({texts})", texts == want)
    C["always"] = shot("gui_step150_curve_names_always.png", w)
    on, off = pixels(C["always"]), pixels(C["never"])
    s = bpy.context.preferences.system.ui_scale
    diffs = []
    for x, y, _t, _c in items:
        x0, y0 = r.x + int(x + 6 * s), r.y + int(y + 3 * s)
        box = (slice(y0, y0 + int(14 * s)), slice(x0, x0 + int(60 * s)))
        diffs.append(round(float(np.abs(on[box] - off[box]).max()), 2))
    check(f"names drawn beside the last keys (max pixel change per label {diffs})", diffs and min(diffs) > 0.2)
    C["x"] = view_x(r)
    select(C["B"])          # Auto Frame (on by default): the selection change reframes the Graph Editor
    redraw()


@step
def s_wait3():
    redraw()


@step
def s_wait4():
    redraw()


@step
def s_auto_frame():
    w, a, r = editor()
    x0, x1 = view_x(r)
    v = r.view2d
    y0, y1 = v.region_to_view(0, 0)[1], v.region_to_view(0, r.height)[1]
    top = 50 * mod(".operators.units").maya_unit()
    # Maya's Auto Frame refits the value axis to the curves shown and keeps the time range
    check(f"Auto Frame: pCube2 selected -> time kept {x0:.1f} .. {x1:.1f} (was {C['x'][0]:.1f} .. {C['x'][1]:.1f}), "
          f"values {y0:.3f} .. {y1:.3f} refit to its keys 0 .. {top:.3f}",
          abs(x0 - C["x"][0]) < 1e-3 and abs(x1 - C["x"][1]) < 1e-3 and y0 < 0 < top < y1 < 2 * top)
    shot("gui_step150_auto_frame.png", w)
    prefs().graph_curve_names = 'NEVER'


run()
