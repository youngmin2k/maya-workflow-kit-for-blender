"""#66: in a real UI: the Maya Workflow Kit layout (cm shown, scale_length 1), pCube1 Translate X keyed
0 -> 5 cm at 1 / 24, Windows > Animation Editors > Graph Editor, View All. With the mouse over the curve area the
value numbers read 0 .. 5 (display units) instead of Blender's 0.00 .. 0.05, on Blender's own grid lines and in
Blender's label boxes only; over the channel list Blender's numbers show (draw-cursor limit); a rotation curve shown
with it keeps Blender's numbers (mixed units)."""

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
    """Screenshot as rows bottom-up (window pixel y), RGB 0..1."""
    import numpy as np
    img = bpy.data.images.load(path)
    w, h = img.size
    px = np.empty(w * h * 4, dtype=np.float32)
    img.pixels.foreach_get(px)
    bpy.data.images.remove(img)
    return px.reshape(h, w, 4)[..., :3]


def hover(window, x, y):
    window.event_simulate(type='MOUSEMOVE', value='NOTHING', x=x, y=y)


@step
def s_setup():
    setup()
    bpy.ops.allset.make_maya(open_layout=False)
    load_maya_layout()


@step
def s_scene():
    area = max((a for a in win().screen.areas if a.type == 'VIEW_3D'), key=lambda a: a.width * a.height)
    region = next(r for r in area.regions if r.type == 'WINDOW')
    with bpy.context.temp_override(window=win(), area=area, region=region):
        bpy.ops.allset.create(kind='CUBE')
        ob = bpy.context.active_object
        k = mod(".operators.units").maya_unit()
        C["k"] = k
        for frame, x in ((1, 0.0), (24, 5.0)):
            ob.location.x = x * k
            ob.keyframe_insert("location", index=0, frame=frame)
        C["ob"] = ob.name
        bpy.ops.allset.menu_item(item="Windows/Animation Editors/Graph Editor")


@step
def s_frame():
    w, a, r = editor()
    check("Graph Editor window opened", r is not None)
    with bpy.context.temp_override(window=w, area=a, region=r):
        bpy.ops.graph.view_all()
    ch = next(x for x in a.regions if x.type == 'CHANNELS')
    hover(w, ch.x + ch.width // 2, ch.y + ch.height // 3)     # Blender's numbers first
    redraw()


@step
def s_wait():
    redraw()


@step
def s_blender_shot():
    w, a, r = editor()
    C["blender"] = shot("gui_step137_graph_blender_numbers.png", w)
    hover(w, r.x + r.width // 2, r.y + r.height // 2)
    redraw()


@step
def s_wait2():
    redraw()


@step
def s_kit_shot():
    gu = mod(".ui.graph_units")
    w, a, r = editor()
    snap = gu._SNAP.get(r.as_pointer())
    check(f"Translate X only, cm scene (maya_unit {C['k']}) -> the Graph Editor gets display-unit labels",
          snap is not None and C["k"] == 0.01)
    if snap is None:
        return
    texts = [it[4] for it in snap["items"]]
    nums = [float(t) for t in texts]
    check(f"labels are cm values 0 .. 5 like the Channel Box / Maya ({texts})",
          "0" in texts and "5" in texts and all(-1 <= v <= 6 for v in nums) and "0.05" not in texts
          and all(t == str(int(v)) for t, v in zip(texts, nums)))
    C["kit"] = shot("gui_step137_graph_cm_numbers.png", w)
    C["items"] = snap["items"]
    C["snap"] = snap
    C["rect"] = (r.x, r.y, r.width, r.height)


@step
def s_pixels():
    import numpy as np
    gu = mod(".ui.graph_units")
    if "kit" not in C:
        return
    kit, bl = pixels(C["kit"]), pixels(C["blender"])
    rx, ry, rw, rh = C["rect"]
    s = bpy.context.preferences.system.ui_scale
    y_off = None
    import blf
    gu._font(s)
    y_off = blf.dimensions(0, "0")[1] / 2.0 - bpy.context.preferences.system.pixel_size
    # grid lines: rows of the curve area (x = 3/4 of the region, away from curve and labels) brighter than the back
    col = kit[ry:ry + rh, rx + int(rw * 0.75)].mean(axis=1)
    back = np.median(col)
    lines = [y for y in range(1, rh - 1) if abs(col[y] - back) > 0.015]
    off = []
    for x, base, w, h, t in C["items"]:
        yc = base + y_off
        d = min((abs(y - yc) for y in lines), default=99)
        off.append(round(d, 1))
    check(f"every display label sits on a Blender grid line (distance px {off}, lines {len(lines)})",
          off and max(off) <= 1.0)
    # Blender's wider "0.05" glyphs are gone right of the short cm label: there the window shows the region pixels
    # from before Blender's overlay (the snapshot), where Blender's shot had its text
    snap = C["snap"]
    bx0, by0, _bx1, _by1 = snap["box"]
    pre = snap["pixels"][..., :3]
    pad = snap["pad"]
    same, was = [], []
    for x, base, w, h, t in C["items"]:
        tw = blf.dimensions(0, t)[0]
        x0, x1 = int(x + tw + pad + 1), int(x + w)
        y0, y1 = int(base), int(base + h)
        if x1 > x0:
            k = kit[ry + y0:ry + y1, rx + x0:rx + x1]
            p = pre[y0 - by0:y1 - by0, x0 - bx0:x1 - bx0]
            same.append(round(float(np.abs(k - p).max()), 3))
            was.append(round(float(bl[ry + y0:ry + y1, rx + x0:rx + x1].max()), 2))
    check(f"Blender's long numbers covered right of the cm label: window = pre-overlay pixels (max diff {same}; "
          f"Blender's shot max brightness there {was})", same and max(same) < 0.02 and min(was) > 0.6)
    # outside the label boxes the strip is untouched: compare a column between the labels and the canvas
    xs = rx + int(max(x + w for x, _b, w, _h, _t in C["items"]) + 8 * s)
    diff = float(np.abs(kit[ry + int(20 * s):ry + rh - int(30 * s), xs] - bl[ry + int(20 * s):ry + rh - int(30 * s), xs]).max())
    check(f"nothing else covered: the column right of the labels is identical (max diff {diff:.3f})", diff < 0.02)


@step
def s_mixed():
    ob = bpy.data.objects[C["ob"]]
    for frame, r in ((1, 0.0), (24, 1.0)):
        ob.rotation_euler.z = r
        ob.keyframe_insert("rotation_euler", index=2, frame=frame)
    w, a, r = editor()
    with bpy.context.temp_override(window=w, area=a, region=r):
        bpy.ops.graph.view_all()
    redraw()


@step
def s_mixed_wait():
    redraw()


@step
def s_mixed_check():
    gu = mod(".ui.graph_units")
    w, a, r = editor()
    check("Translate X + Rotate Z shown (mixed units) -> Blender's numbers stay",
          gu._SNAP.get(r.as_pointer()) is None)
    shot("gui_step137_graph_mixed.png", w)


run()
