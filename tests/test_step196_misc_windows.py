"""Lane B (issue #103): Maya option windows for Create Character Set / Subcharacter Set, Curves Cut / Detach /
Reverse Direction / Smooth (both) / Straighten, the circular arc tools, Merge UVs, Contour Stretch, Set / Assume
Preferred Angle and Add Influence (operators/option_windows_misc196.py).

Window titles / buttons / defaults of Maya's
option windows and the option effects."""

import json
from importlib import import_module

import bmesh
import bpy

import kit

ow = import_module(kit.MODULE + ".operators.option_windows")
menu_sets = import_module(kit.MODULE + ".ui.menu_sets")
cmaya = import_module(kit.MODULE + ".operators.curves_maya")
cm = import_module(kit.MODULE + ".operators.curves_math")
rig = import_module(kit.MODULE + ".operators.rig_maya")

_D = {}


PATHS = {
    "character_set": ("Control/Create Character Set", "Key/Create Character Set"),
    "subcharacter_set": ("Control/Create Subcharacter Set", "Key/Create Subcharacter Set"),
    "cut_curve": ("Curves/Cut",), "detach_curves": ("Curves/Detach",), "reverse_curve": ("Curves/Reverse Direction",),
    "smooth_curves": ("Curves/Smooth", "nHair/Modify Curves/Smooth"), "smooth_curve": ("Curves/Smooth#2",),
    "straighten_curves": ("Curves/Straighten", "nHair/Modify Curves/Straighten"),
    "arc3_tool": ("Create/Curve Tools/Three Point Circular Arc",),
    "arc2_tool": ("Create/Curve Tools/Two Point Circular Arc",),
    "merge_uvs": ("UV/Merge UVs",), "contour_stretch": ("UV/Contour Stretch",),
    "set_preferred_angle": ("Skeleton/Set Preferred Angle",),
    "assume_preferred_angle": ("Skeleton/Assume Preferred Angle",),
    "add_influence": ("Skin/Edit Influences/Add Influence",),
}


def err(got, want):
    assert len(got) == len(want), (len(got), len(want))
    return max(max(abs(a - b) for a, b in zip(g, w)) for g, w in zip(got, want))


def _clear():
    if bpy.context.active_object is not None and bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)


def _sel(*obs):
    for o in bpy.context.scene.objects:
        o.select_set(o in obs)
    bpy.context.view_layer.objects.active = obs[-1] if obs else None


def run(key, **values):
    res = ow.run(ow._BY_KEY[key], bpy.context, values)
    assert not isinstance(res, str), (key, res)
    return res


# --- the windows ---------------------------------------------------------------------------------------


# --- character sets ------------------------------------------------------------------------------------

def cs():
    return import_module(kit.MODULE + ".operators.character_sets")


def _char_scene():
    sc = bpy.context.scene
    _clear()
    while sc.keying_sets:
        cs().remove_character(sc, sc.keying_sets[0])
    if cs().PARENT in sc:
        del sc[cs().PARENT]
    bpy.context.window_manager.allset_character_nodes = ""
    obs = []
    for name in ("pCube1", "pCube2"):
        ob = bpy.data.objects.new(name, bpy.data.meshes.new(name + "Shape"))
        sc.collection.objects.link(ob)
        obs.append(ob)
    obs[1].parent = obs[0]
    obs[0]["custom"] = 0.0
    _sel(obs[0])
    return obs


def _chars():
    sc = bpy.context.scene
    return {ks.bl_label: sorted(cs().member_names(sc, ks)) for ks in sc.keying_sets}


def test_character_window_defaults_equal_the_plain_item():
    _char_scene()
    assert bpy.ops.allset.character_create('EXEC_DEFAULT') == {'FINISHED'}
    plain = _chars()
    _char_scene()
    run("character_set")
    assert _chars() == plain


def test_subcharacter_window():
    obs = _char_scene()
    run("character_set")
    _sel(obs[1])
    assert run("subcharacter_set", name="arms", no_rotate=True) == {'FINISHED'}
    got = _chars()
    assert got["arms"] == sorted(f"pCube2.translate{a}" for a in "XYZ"), got
    assert cs().current(bpy.context.scene).bl_label == "character1"        # Maya keeps the current character
    _sel(obs[1])
    run("subcharacter_set")
    assert "subCharacter1" in _chars()


def test_character_from_channel_box():
    obs = _char_scene()
    cb = import_module(kit.MODULE + ".ui.channel_box")
    cb.set_selected_channels(["tx", "rz"], bpy.context)
    try:
        run("character_set", attributes="From Channel Box")
    finally:
        cb.set_selected_channels([], bpy.context)
    assert _chars() == {"character1": ["pCube1.rotateZ", "pCube1.translateX"]}, _chars()


# --- curves ----------------------------------------------------------------------------------------------

def _crv(c):
    return cmaya.MCurve([tuple(x) for x in c["cvs"]], list(c["knots"]), c["degree"])


def _object(name, c):
    ob = cmaya._new_curve_object(bpy.context, name, [c])
    ob.name = name
    return ob


def _cvs(ob):
    return cmaya.read_spline(ob.data.splines[0]).cvs


def test_arc_tool_settings():
    pts = json.dumps([(0, 0, 0), (2, 2, 0), (4, 0, 0)])
    for degree, sections in ((3, 8), (1, 12), (3, 16)):
        _clear()
        assert bpy.ops.allset.arc3_tool('EXEC_DEFAULT', points=pts, degree=degree, sections=sections) == {'FINISHED'}
        ob = bpy.context.view_layer.objects.active
        want, _knots, deg = cm.arc3((0, 0, 0), (2, 2, 0), (4, 0, 0), sections, degree)
        got = cmaya.read_spline(ob.data.splines[0])
        assert got.degree == deg == degree and err(got.cvs, want) < 1e-5, (degree, sections)
    _clear()
    bpy.ops.allset.arc2_tool('EXEC_DEFAULT', points=json.dumps([(0, 0, 0), (4, 0, 0)]), degree=1, sections=4)
    assert len(cmaya.read_spline(bpy.context.view_layer.objects.active.data.splines[0]).cvs) == 5
    for key in ("arc3_tool", "arc2_tool"):
        assert ow._BY_KEY[key].defaults() == {"degree": "3", "sections": 8}


# --- UVs ------------------------------------------------------------------------------------------------

def _uv_plane(shift):
    """The case: a 2-face plane cut along the middle edge, the right face's UVs shifted by ``shift`` in U."""
    _clear()
    me = bpy.data.meshes.new("pPlaneShape1")
    me.from_pydata([(0, 0, 0), (1, 0, 0), (2, 0, 0), (0, 1, 0), (1, 1, 0), (2, 1, 0)], [], [(0, 1, 4, 3), (1, 2, 5, 4)])
    ob = bpy.data.objects.new("pPlane1", me)
    bpy.context.scene.collection.objects.link(ob)
    _sel(ob)
    bm = bmesh.new()
    bm.from_mesh(me)
    uv = bm.loops.layers.uv.verify()
    for f in bm.faces:
        for lp in f.loops:
            x, y = lp.vert.co.x / 2.0, lp.vert.co.y
            lp[uv].uv = (x + (shift if f.index == 1 else 0.0), y)
    bm.to_mesh(me)
    bm.free()
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.context.scene.tool_settings.use_uv_select_sync = True
    bpy.ops.mesh.select_all(action='SELECT')
    return ob


def _uv_count(ob):
    bm = bmesh.from_edit_mesh(ob.data)
    uv = bm.loops.layers.uv.verify()
    seen = set()
    for f in bm.faces:
        for lp in f.loops:
            seen.add((lp.vert.index, round(lp[uv].uv.x, 6), round(lp[uv].uv.y, 6)))
    return len(seen), sorted({round(lp[uv].uv.x, 6) for f in bm.faces for lp in f.loops})


def test_contour_window_is_the_plain_contour():
    ob = _uv_plane(0.0)
    bpy.ops.object.mode_set(mode='OBJECT')
    _sel(ob)
    assert run("contour_stretch") == {'FINISHED'}
    after_window = [tuple(d.uv) for d in ob.data.uv_layers.active.data]
    assert bpy.ops.allset.uv_contour('EXEC_DEFAULT') == {'FINISHED'}
    assert err(after_window, [tuple(d.uv) for d in ob.data.uv_layers.active.data]) < 1e-6


# --- skeleton / skin ------------------------------------------------------------------------------------


def _pref(arm):
    return {pb.name: round(pb[rig.PREFERRED_PROP][2], 4) if rig.PREFERRED_PROP in pb else 0.0
            for pb in arm.pose.bones}


