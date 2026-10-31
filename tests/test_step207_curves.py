"""Curves 3, like Maya.
Pure maths on the expected numbers first (1e-6), then the kit operators on
Blender objects built from the same CVs (Maya Y-up -> Blender (X, -Z, Y))."""

import json
import os
from importlib import import_module

import bpy

import kit

cm = import_module(kit.MODULE + ".operators.curves_math")
sm = import_module(kit.MODULE + ".operators.surfaces_math")
cmaya = import_module(kit.MODULE + ".operators.curves_maya")
smaya = import_module(kit.MODULE + ".operators.surfaces_maya")
c207 = import_module(kit.MODULE + ".operators.curves_207")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORST = {}


# --- pure maths -----------------------------------------------------------------------------------------------


def test_keep_leg_lengths():
    old = [(0, 0, 0), (1, 0, 0), (2, 0.5, 0), (3, 0, 0), (4, 0, 0)]
    new = list(old)
    new[2] = (2, 2.0, 0.5)
    out = cm.keep_leg_lengths(old, new)
    assert out[2] == new[2]
    legs = lambda P: [cm.norm(cm.sub(P[i + 1], P[i])) for i in range(len(P) - 1)]
    assert max(abs(a - b) for a, b in zip(legs(out), legs(old))) < 1e-9
    assert cm.keep_leg_lengths(old, old) == old


# --- kit operators --------------------------------------------------------------------------------------------

def _clear():
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)


def _sel(*obs):
    for o in bpy.context.selected_objects:
        o.select_set(False)
    for o in obs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = obs[-1]


def _bl(pts):
    return [c207.from_maya(p) for p in pts]


def _curve(name, maya_cvs, degree=3):
    c = cmaya.MCurve(_bl(maya_cvs), cm.clamped_uniform(len(maya_cvs), degree), degree)
    ob = cmaya._new_curve_object(bpy.context, name, [c])
    ob.name = name
    return ob


def _cvs(ob):
    return cmaya.read_spline(ob.data.splines[0]).cvs


def test_lock_length():
    _clear()
    ob = _curve("curveA", [(0, 0, 0), (1, 0, -3), (4, 0, -4), (6, 0, -1), (8, 0, 2)])
    _sel(ob)
    assert bpy.ops.allset.curve_lock_length(lock=True) == {'FINISHED'}
    assert ob.data[c207.LOCK]
    legs = lambda P: [cm.norm(cm.sub(P[i + 1], P[i])) for i in range(len(P) - 1)]
    before = legs(_cvs(ob))
    sp = ob.data.splines[0]
    sp.points[2].co = (5.0, 2.0, 1.0, 1.0)
    assert c207.apply_lock(ob.data)
    after = _cvs(ob)
    assert tuple(after[2]) == (5.0, 2.0, 1.0)
    assert max(abs(x - y) for x, y in zip(legs(after), before)) < 1e-6
    assert bpy.ops.allset.curve_lock_length(lock=False) == {'FINISHED'}
    sp.points[0].co = (9.0, 9.0, 9.0, 1.0)
    bpy.context.view_layer.update()
    assert tuple(_cvs(ob)[0]) == (9.0, 9.0, 9.0)        # unlocked: nothing follows


def test_report_worst():
    print("WORST", json.dumps({k: v for k, v in sorted(WORST.items())}, indent=0, default=str))


