"""Maya Dope Sheet > Curves runs the Graph Editor's curve commands (Euler Filter, Resample Curve) on the
curves of the selected keys — the Dope Sheet area turns into a Graph Editor for the call and back — and Dope Sheet
View > Auto Frame frames the Dope Sheet."""

import math
import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, run, setup, step, view3d, win  # noqa: E402

C = {}


def mod(name):
    return import_module(f"{MODULE}.{name}")


def fcurves(ob):
    return list(mod("compat").id_fcurves(ob))


def area():
    return next(a for a in win().screen.areas if a.as_pointer() == C["area"])


@step
def s_setup():
    setup()
    a = view3d()[0]
    C["area"] = a.as_pointer()
    a.ui_type = 'DOPESHEET'


@step
def s_scene():
    ob = bpy.data.objects.get("Cube") or bpy.context.view_layer.objects.active
    C["ob"] = ob.name
    for f, z in ((1, 0.0), (10, math.radians(350)), (20, math.radians(10))):
        ob.rotation_euler.z = z
        ob.keyframe_insert("rotation_euler", index=2, frame=f)
    ob.location.x = 0
    ob.keyframe_insert("location", index=0, frame=1)
    ob.location.x = 1
    ob.keyframe_insert("location", index=0, frame=10)
    for o in bpy.context.view_layer.objects:
        o.select_set(o == ob)
    bpy.context.view_layer.objects.active = ob
    for fc in fcurves(ob):
        for k in fc.keyframe_points:
            k.select_control_point = fc.data_path == "rotation_euler"
    area().tag_redraw()


@step
def s_euler():
    a = area()
    region = next(r for r in a.regions if r.type == 'WINDOW')
    with bpy.context.temp_override(window=win(), area=a, region=region):
        res = bpy.ops.allset.dope_graph_op(command='EULER')
    ob = bpy.data.objects[C["ob"]]
    rz = next(fc for fc in fcurves(ob) if fc.data_path == "rotation_euler")
    vals = [round(math.degrees(k.co.y)) for k in rz.keyframe_points]
    check(f"Dope Sheet > Curves > Euler Filter runs ({res})", res == {'FINISHED'})
    check(f"... and removes the 350° flip ({vals})", vals == [0, -10, 10])
    loc = next(fc for fc in fcurves(ob) if fc.data_path == "location")
    check("curves without selected keys are left alone", [k.co.y for k in loc.keyframe_points] == [0.0, 1.0])
    check(f"the area is a Dope Sheet again ({a.ui_type})", a.ui_type == 'DOPESHEET')


@step
def s_resample():
    a = area()
    region = next(r for r in a.regions if r.type == 'WINDOW')
    ob = bpy.data.objects[C["ob"]]
    for fc in fcurves(ob):
        for k in fc.keyframe_points:
            k.select_control_point = fc.data_path == "location"
    with bpy.context.temp_override(window=win(), area=a, region=region):
        res = bpy.ops.allset.dope_graph_op(command='RESAMPLE')
    loc = next(fc for fc in fcurves(ob) if fc.data_path == "location")
    check(f"Resample Curve keys every frame of the selected curve ({len(loc.keyframe_points)} keys, {res})",
          res == {'FINISHED'} and len(loc.keyframe_points) == 10)
    check("still a Dope Sheet", a.ui_type == 'DOPESHEET')


@step
def s_auto_frame():
    gv = mod("ui.graph_view")
    prefs = mod("preferences").get()
    prefs.dope_auto_frame = True
    try:
        n = gv.auto_frame(bpy.context.scene, prefs)
    finally:
        prefs.dope_auto_frame = False
    check(f"Dope Sheet Auto Frame frames the Dope Sheet ({n})", n >= 1)


run()
