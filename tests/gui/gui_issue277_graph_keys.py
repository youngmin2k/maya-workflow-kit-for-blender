"""Graph Editor keys (#277): in the Maya Workflow Kit layout a keyed pCube1's keys read as bigger dots (Key Size
preference) in their own colour, selected keys in the selected colour; Key Size 0 = Blender's own keys."""

import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, load_maya_layout, run, setup, step, win  # noqa: E402

GUI_TIMEOUT = 200
SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "") or bpy.app.tempdir
C = {}


def mod(name):
    return import_module(MODULE + name)


def prefs():
    return mod(".preferences").get(bpy.context)


def redraw():
    for a in win().screen.areas:
        a.tag_redraw()


def graph():
    a = next((a for a in win().screen.areas if a.ui_type == 'FCURVES'), None)
    return a, (next(r for r in a.regions if r.type == 'WINDOW') if a else None)


def shot(name):
    path = os.path.join(SHOTS, name)
    with bpy.context.temp_override(window=win()):
        bpy.ops.screen.screenshot(filepath=path)
    img = bpy.data.images.load(path)
    w, h = img.size
    px = list(img.pixels)
    bpy.data.images.remove(img)
    return w, h, px


def pixel(data, x, y):
    w, _h, px = data
    i = (y * w + x) * 4
    return px[i:i + 3]


def near(c, ref, tol=0.08):
    return all(abs(a - b) <= tol for a, b in zip(c, ref))


def key_win(fc, i):
    _a, r = graph()
    kp = fc.keyframe_points[i]
    x, y = r.view2d.view_to_region(kp.co.x, kp.co.y, clip=False)
    return x + r.x, y + r.y


def tx():
    ob = bpy.data.objects[C["cube"]]
    return next(f for f in mod(".compat").id_fcurves(ob) if f.data_path == "location" and f.array_index == 0)


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
    C["cube"] = ob.name
    u = mod(".operators.units").maya_unit()
    for f, x in ((1, 0), (12, 5), (24, 0)):
        ob.location = (x * u, 0, 0)
        ob.keyframe_insert("location", index=0, frame=f)
    area.ui_type = 'FCURVES'


@step
def s_wait():
    redraw()


@step
def s_frame():
    a, r = graph()
    with bpy.context.temp_override(window=win(), area=a, region=r):
        bpy.ops.graph.view_all()
    for i, kp in enumerate(tx().keyframe_points):
        kp.select_control_point = i == 1
        kp.select_left_handle = kp.select_right_handle = False
    a.spaces.active.show_handles = False
    redraw()


@step
def s_wait2():
    redraw()


@step
def s_big():
    C["big"] = shot("gui_issue277_keys_big.png")
    prefs().graph_key_size = 0
    redraw()


@step
def s_wait3():
    redraw()


@step
def s_check():
    small = shot("gui_issue277_keys_blender.png")
    big = C["big"]
    theme = bpy.context.preferences.themes[0].graph_editor
    scale = bpy.context.preferences.system.ui_scale
    size = 11
    probe = round(size * scale / 2 - 1.5)          # inside the kit dot, outside Blender's own (6 px)
    check(f"probe radius {probe} px is outside Blender's key ({theme.vertex_size * scale / 2:.1f} px)",
          probe > theme.vertex_size * scale / 2 + 0.5)
    sx, sy = key_win(tx(), 1)          # selected key: a flat top, probe straight down
    ux, uy = key_win(tx(), 2)          # unselected key at the end: probe to the right (the curve is flat after it)
    sel_big, sel_small = pixel(big, sx, sy - probe), pixel(small, sx, sy - probe)
    un_big, un_small = pixel(big, ux + probe, uy - probe // 2), pixel(small, ux + probe, uy - probe // 2)
    sel_ref = tuple(theme.vertex_select)[:3]
    un_ref = tuple(theme.vertex)[:3]
    check(f"selected key: kit rim in the selected colour {sel_big} ~ {sel_ref}", near(sel_big, sel_ref))
    check(f"selected key with Key Size 0: no rim {sel_small}", not near(sel_small, sel_ref))
    check(f"unselected key: kit rim in the key colour {un_big} ~ {un_ref}", near(un_big, un_ref))
    check(f"unselected key with Key Size 0: no rim {un_small}", not near(un_small, un_ref))
    centre = pixel(big, sx, sy)
    check(f"Blender's own key still in the middle {centre}", sum(centre) > 0.3)
    prefs().graph_key_size = 11


run()
