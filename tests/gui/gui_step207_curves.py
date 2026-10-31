"""In a real UI: a CV curve in the Maya layout, Curves > Bend / Curl / Scale Curvature / Duplicate Surface
Curves / Intersect from the menu map; Lock Length keeps every CV leg while a CV is moved with the Move tool's transform
in edit mode; shot of the viewport."""

import os
import sys
from importlib import import_module

import bpy
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, load_maya_layout, run, screenshot, setup, step, view3d, win  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}
PTS = [(0, 0, 0), (1, 1, -3), (4, -1, -4), (6, 2, -1), (8, 0, 2), (11, 1, 1), (12, 0, -2)]


def override():
    a, region = view3d()
    return bpy.context.temp_override(window=win(), screen=win().screen, area=a, region=region)


def run_item(path):
    with override():
        return bpy.ops.allset.menu_item(item=path)


def cvs(ob):
    return [Vector(p.co[:3]) for p in ob.data.splines[0].points]


def make_curve(name, pts):
    cmaya = import_module(MODULE + ".operators.curves_maya")
    cm = import_module(MODULE + ".operators.curves_math")
    c207 = import_module(MODULE + ".operators.curves_207")
    u = import_module(MODULE + ".operators.units").maya_unit()
    bl = [tuple(x * u for x in c207.from_maya(p)) for p in pts]
    ob = cmaya._new_curve_object(bpy.context, name, [cmaya.MCurve(bl, cm.clamped_uniform(len(bl), 3), 3)])
    ob.name = name
    return ob


def sel(*obs):
    for o in bpy.context.selected_objects:
        o.select_set(False)
    for o in obs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = obs[-1]


@step
def s_setup():
    setup()
    load_maya_layout()


@step
def s_scene():
    bpy.ops.allset.keymap_activate()
    ob = make_curve("curveA", PTS)
    sel(ob)
    C["ob"] = ob.name
    with override():
        bpy.ops.view3d.view_selected()


@step
def s_modify():
    ob = bpy.data.objects[C["ob"]]
    for path in ("Curves/Bend", "Curves/Curl", "Curves/Scale Curvature"):
        before = cvs(ob)
        res = run_item(path)
        moved = max((a - b).length for a, b in zip(before, cvs(ob)))
        check(f"{path} runs from the menu ({res}) and moves the CVs ({moved:.4f})", res == {'FINISHED'} and moved > 1e-5)


@step
def s_lock():
    ob = bpy.data.objects[C["ob"]]
    sel(ob)
    run_item("Curves/Lock Length")
    legs = lambda P: [(P[i + 1] - P[i]).length for i in range(len(P) - 1)]
    before = legs(cvs(ob))
    with override():
        bpy.ops.object.mode_set(mode='EDIT')
        for i, p in enumerate(ob.data.splines[0].points):
            p.select = i == 3
        bpy.ops.transform.translate(value=(0.0, 0.0, 0.03))
        bpy.ops.object.mode_set(mode='OBJECT')
    after = legs(cvs(ob))
    dev = max(abs(a - b) for a, b in zip(before, after))
    check(f"Lock Length: moving CV 3 keeps every CV leg ({dev:.2e})", dev < 1e-5)
    run_item("Curves/Unlock Length")
    check("Unlock Length clears lockLength", not ob.data.get("allset_lock_length"))


@step
def s_intersect():
    b = make_curve("curveB", [(2, 0, 2), (4, 0, -2), (7, 0, -6), (10, 0, -2), (11, 0, 3)])
    a = make_curve("curveA2", [(0, 0, 0), (1, 0, -3), (4, 0, -4), (6, 0, -1), (8, 0, 2), (11, 0, 1), (12, 0, -2)])
    sel(a, b)
    res = run_item("Curves/Intersect")
    locs = [o for o in bpy.data.objects if o.type == 'EMPTY']
    check(f"Intersect ({res}): {len(locs)} locators (Maya: 2 crossings x 2 curves)", len(locs) == 4)
    sel(a, b, bpy.data.objects[C["ob"]])
    with override():
        bpy.ops.view3d.view_selected()
    for a_ in win().screen.areas:
        a_.tag_redraw()


@step
def s_frame():
    a, region = view3d()
    with bpy.context.temp_override(window=win(), screen=win().screen, area=a, region=region):
        bpy.ops.view3d.view_axis(type='TOP')
        bpy.ops.view3d.view_selected()
    a.tag_redraw()


@step
def s_shot():
    if SHOTS:
        screenshot(os.path.join(SHOTS, "gui_step207_curves.png"))


run()
