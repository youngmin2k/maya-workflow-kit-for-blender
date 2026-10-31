"""Maya animation layers on NLA (operators/anim_layers.py) like Maya:
the same base keys, the same layer keys set like Maya's setKeyframe -v (the value is the result), raw layer curves and
translateX / rotateX / rotateY / rotateZ / scaleX at frames 1..10, then weight, mute, solo, override and the key that
the selected layer receives."""

import math
import os
from importlib import import_module

import bpy

import kit

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
al = import_module(kit.MODULE + ".operators.anim_layers")
cb = import_module(kit.MODULE + ".ui.channel_box")
PATH = {"translateX": ("location", 0, 1.0), "rotateX": ("rotation_euler", 0, math.pi / 180),
        "rotateY": ("rotation_euler", 1, math.pi / 180), "rotateZ": ("rotation_euler", 2, math.pi / 180),
        "scaleX": ("scale", 0, 1.0)}
TOL = 1e-5          # Blender keeps rotations in float32 radians: ~3e-6 deg at 116 deg (max 4e-6)


def linear(ob):
    for act in bpy.data.actions:
        for fc in _fcs(act):
            for kp in fc.keyframe_points:
                kp.interpolation = 'LINEAR'


def _fcs(act):
    compat = import_module(kit.MODULE + ".compat")
    return compat.action_fcurves(act)


def scene():
    sc = bpy.context.scene
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    for a in list(bpy.data.actions):
        bpy.data.actions.remove(a)
    sc.allset_anim_layers.clear()
    sc.allset_anim_layer_index = 0
    ob = bpy.data.objects.new("pCube1", bpy.data.meshes.new("pCubeShape1"))
    sc.collection.objects.link(ob)
    ob.rotation_mode = 'XYZ'
    for f, tx, ry, sx in ((1, 0, 0, 1), (10, 10, 90, 2)):
        sc.frame_set(f)
        ob.location.x, ob.rotation_euler.y, ob.scale.x = tx, math.radians(ry), sx
        ob.keyframe_insert("location", index=0, frame=f)
        ob.keyframe_insert("rotation_euler", index=1, frame=f)
        ob.keyframe_insert("scale", index=0, frame=f)
    ob.rotation_euler.x = math.radians(30)
    ob.keyframe_insert("rotation_euler", index=0, frame=1)
    linear(ob)
    for o in sc.objects:
        o.select_set(o == ob)
    bpy.context.view_layer.objects.active = ob
    return sc, ob


def mkey(sc, ob, layer, attr, frame, value):
    """Maya setKeyframe -animLayer <layer> -t <frame> -v <value> (linear tangents)."""
    sc.allset_anim_layer_index = [e.name for e in sc.allset_anim_layers].index(layer)
    path, idx, k = PATH[attr]
    sc.frame_set(frame)
    assert al.key(ob, path, idx, frame=frame, value=value * k, scene=sc)
    linear(ob)


def new_layer(sc, override=False):
    bpy.ops.allset.anim_layer_create(from_selected=True)
    e = sc.allset_anim_layers[sc.allset_anim_layer_index]
    e.override = override
    return e.name


def values(sc, ob, frames):
    out = {}
    for attr, (path, idx, k) in PATH.items():
        vals = []
        for f in frames:
            sc.frame_set(f)
            vals.append(getattr(ob, path)[idx] / k)
        out[attr] = vals
    return out


def assert_values(name, got, want):
    for attr in want:
        for f, (g, w) in enumerate(zip(got[attr], want[attr])):
            assert abs(g - w) < TOL, (name, attr, f, g, w)


def raw_curves(ob):
    out = {}
    for name, tr in al.tracks(ob).items():
        d = {}
        for attr, (path, idx, k) in PATH.items():
            fc = al._fcurve(tr.strips[0].action, path, idx)
            if fc is not None and len(fc.keyframe_points):
                d[attr] = [[kp.co[0], kp.co[1] / k] for kp in fc.keyframe_points]
        out[name] = d
    return out


def two_additive():
    sc, ob = scene()
    l1, l2 = new_layer(sc), new_layer(sc)
    assert (l1, l2) == ("AnimLayer1", "AnimLayer2")
    mkey(sc, ob, l1, "translateX", 1, 5); mkey(sc, ob, l1, "translateX", 10, 5)
    mkey(sc, ob, l1, "rotateY", 1, 10); mkey(sc, ob, l1, "rotateY", 10, 30)
    mkey(sc, ob, l1, "rotateX", 1, 20)
    mkey(sc, ob, l1, "scaleX", 1, 2); mkey(sc, ob, l1, "scaleX", 10, 2)
    mkey(sc, ob, l2, "translateX", 1, 0); mkey(sc, ob, l2, "translateX", 10, 4)
    mkey(sc, ob, l2, "rotateY", 5, 45)
    mkey(sc, ob, l2, "rotateZ", 1, 15)
    return sc, ob


def test_locked_layer_takes_no_keys():
    sc, ob = scene()
    l1 = new_layer(sc)
    sc.allset_anim_layers[l1].lock = True
    sc.frame_set(5)
    ob.location.x = 7
    assert not al.key(ob, "location", 0, scene=sc)
    assert al.tracks(ob)[l1].lock


def test_layer_list_and_delete():
    sc, ob = scene()
    bpy.ops.allset.anim_layer_create(from_selected=False)
    assert [e.name for e in sc.allset_anim_layers] == ["BaseAnimation", "AnimLayer1"]
    assert not al.has_layers(ob)             # an empty layer has no members (Maya: attribute list empty)
    bpy.ops.allset.anim_layer_members(add=True)
    assert list(al.tracks(ob)) == ["BaseAnimation", "AnimLayer1"]
    bpy.ops.allset.anim_layer_delete()
    assert [e.name for e in sc.allset_anim_layers] == ["BaseAnimation"]
    assert list(al.tracks(ob)) == ["BaseAnimation"]
    sc.frame_set(10)
    assert abs(ob.location.x - 10.0) < TOL     # the base animation still plays

