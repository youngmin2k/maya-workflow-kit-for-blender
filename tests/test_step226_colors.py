"""Lane B (Issue #136): Maya control colours — Display > Wireframe Color... and the Attribute
Editor's Drawing Overrides (operators/wire_color.py).

Maya: the colorIndex palette 1-31
(``colorIndex_gui``), user palette 1-8 = indices 24-31 (``userDefined_gui``), ``color -ud 3`` ->
useObjectColor 1 / objectColor 2, ``color -rgb 1 0 0`` -> useObjectColor 2 / wireColorRGB (``L2_wireframe_color_command``),
override attributes all 0 / off by default (``L2_drawing_override_palette.default_attrs``)."""

from importlib import import_module

import bpy
from mathutils import Color

import kit

wc = import_module(kit.MODULE + ".operators.wire_color")
menu_map = import_module(kit.MODULE + ".ui.menu_map")
ae_layout = import_module(kit.MODULE + ".ui.ae_layout")

# "colorIndex_gui"
MAYA_INDEX = {
    1: [0.0, 0.0, 0.0], 2: [0.25, 0.25, 0.25], 3: [0.6, 0.6, 0.6], 4: [0.608, 0.0, 0.157], 5: [0.0, 0.016, 0.376],
    6: [0.0, 0.0, 1.0], 7: [0.0, 0.275, 0.098], 8: [0.149, 0.0, 0.263], 9: [0.784, 0.0, 0.784], 10: [0.541, 0.282, 0.2],
    11: [0.247, 0.137, 0.122], 12: [0.6, 0.149, 0.0], 13: [1.0, 0.0, 0.0], 14: [0.0, 1.0, 0.0], 15: [0.0, 0.255, 0.6],
    16: [1.0, 1.0, 1.0], 17: [1.0, 1.0, 0.0], 18: [0.392, 0.863, 1.0], 19: [0.263, 1.0, 0.639], 20: [1.0, 0.69, 0.69],
    21: [0.894, 0.675, 0.475], 22: [1.0, 1.0, 0.388], 23: [0.0, 0.6, 0.329], 24: [0.8549, 0.5686, 0.4275],
    25: [0.8784, 0.7843, 0.3059], 26: [0.6353, 0.8118, 0.2784], 27: [0.2314, 0.7569, 0.5804],
    28: [0.2549, 0.8196, 0.7255], 29: [0.2274, 0.6157, 0.8078], 30: [0.6118, 0.4196, 0.8078],
    31: [0.8078, 0.349, 0.6549]}
MAYA_USER = {1: [0.8549, 0.5686, 0.4275], 2: [0.8784, 0.7843, 0.3059], 3: [0.6353, 0.8118, 0.2784],
             4: [0.2314, 0.7569, 0.5804], 5: [0.2549, 0.8196, 0.7255], 6: [0.2274, 0.6157, 0.8078],
             7: [0.6118, 0.4196, 0.8078], 8: [0.8078, 0.349, 0.6549]}


def _close(a, b, tol=1e-4):
    return all(abs(x - y) <= tol for x, y in zip(a, b)) and len(tuple(a)) == len(tuple(b))


def _lin(c):
    lin = Color(c).from_srgb_to_scene_linear()
    return (lin.r, lin.g, lin.b, 1.0)


def _clear():
    if bpy.context.object is not None and bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)


def _curve(name="nurbsCircle1"):
    cu = bpy.data.curves.new(name, 'CURVE')
    sp = cu.splines.new('POLY')
    sp.points.add(3)
    for i, p in enumerate(sp.points):
        p.co = (i * 0.1, 0.0, 0.0, 1.0)
    ob = bpy.data.objects.new(name, cu)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def _select(*obs):
    for o in bpy.context.scene.objects:      # view_layer.objects yields None after removals
        o.select_set(False)
    for o in obs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = obs[0] if obs else None


def _views():
    win = bpy.context.window_manager.windows[0]
    return win, [s for a in win.screen.areas if a.type == 'VIEW_3D' for s in a.spaces if s.type == 'VIEW_3D']


def test_object_color_is_scene_linear():
    # basis for the sRGB -> linear conversion: Object.color is COLOR (linear), bone colours COLOR_GAMMA
    assert bpy.types.Object.bl_rna.properties["color"].subtype == 'COLOR'
    _clear()
    pb = _arm().pose.bones[0]
    assert pb.color.custom.bl_rna.properties["normal"].subtype == 'COLOR_GAMMA'
    bpy.ops.object.mode_set(mode='OBJECT')


def test_menu_maps_to_window():
    act = menu_map.MAP["Display/Wireframe Color..."]
    assert act == ("allset.wireframe_color", {}), act
    kind, target, props = menu_map.normalize(act)
    assert target == "allset.wireframe_color"
    assert "wireframe_color" in dir(bpy.ops.allset)


def test_wireframe_color_on_objects():
    _clear()
    ob, other = _curve(), _curve("nurbsSquare1")
    win, spaces = _views()
    ws = win.workspace
    for s in spaces:
        s.shading.wireframe_color_type = 'THEME'
    # not a Maya workspace: views stay Blender's
    _select(ob)
    assert bpy.ops.allset.wireframe_color(color_type='INDEXED', cell='3') == {'FINISHED'}
    st = ob["allset_object_color"].to_dict()
    assert st["use"] == 1 and st["index"] == 2, st            # Maya: color -ud 3 -> objectColor 2
    assert _close(ob.color, _lin(MAYA_USER[3])), tuple(ob.color)
    assert all(s.shading.wireframe_color_type == 'THEME' for s in spaces)
    assert tuple(other.color) == (1.0, 1.0, 1.0, 1.0) and "allset_object_color" not in other
    # in a Maya workspace the views draw object colours
    ws["allset_template"] = "General"
    try:
        _select(ob, other)
        assert bpy.ops.allset.wireframe_color(color_type='RGB', rgb=(1.0, 0.0, 0.0)) == {'FINISHED'}
        for o in (ob, other):
            st = o["allset_object_color"].to_dict()
            assert st["use"] == 2 and _close(st["rgb"], (1, 0, 0)), st
            assert _close(o.color, (1.0, 0.0, 0.0, 1.0))
        assert spaces and all(s.shading.wireframe_color_type == 'OBJECT' for s in spaces)
        assert win.screen.get("allset_wire_object")
        # Default (Maya ``color``): useObjectColor 0, Blender's white, views back to the theme
        assert bpy.ops.allset.wireframe_color(action='DEFAULT') == {'FINISHED'}
        for o in (ob, other):
            assert o["allset_object_color"]["use"] == 0
            assert tuple(o.color) == (1.0, 1.0, 1.0, 1.0)
            assert "allset_wire_set" not in o
        assert all(s.shading.wireframe_color_type == 'THEME' for s in spaces)
        assert not win.screen.get("allset_wire_object")
        # nothing selected: a warning, nothing changes
        _select()
        assert bpy.ops.allset.wireframe_color(cell='1') == {'CANCELLED'}
    finally:
        del ws["allset_template"]


def _arm():
    arm = bpy.data.objects.new("skeleton1", bpy.data.armatures.new("skeleton1"))
    bpy.context.scene.collection.objects.link(arm)
    _select(arm)
    bpy.ops.object.mode_set(mode='EDIT')
    for name, z in (("joint1", 0.0), ("joint2", 0.1)):
        b = arm.data.edit_bones.new(name)
        b.head, b.tail = (0, 0, z), (0, 0, z + 0.1)
    bpy.ops.object.mode_set(mode='POSE')
    return arm


def _select_bone(arm, name):
    cb = import_module(kit.MODULE + ".ui.channel_box")     # bone selection shim (5.x has no Bone.select)
    for pb in arm.pose.bones:
        cb.set_bone_selected(pb, pb.name == name)
    arm.data.bones.active = arm.data.bones[name]


def test_wireframe_color_on_pose_bones():
    _clear()
    arm = _arm()
    _select_bone(arm, "joint2")
    assert bpy.ops.allset.wireframe_color(color_type='INDEXED', cell='6') == {'FINISHED'}
    pb, other = arm.pose.bones["joint2"], arm.pose.bones["joint1"]
    assert pb.color.palette == 'CUSTOM'
    assert _close(pb.color.custom.normal, MAYA_USER[6]), tuple(pb.color.custom.normal)   # sRGB as is
    assert _close(pb.color.custom.active, (0x43 / 255, 1.0, 0xa3 / 255))                 # Maya lead
    assert pb["allset_object_color"].to_dict()["index"] == 5
    assert other.color.palette == 'DEFAULT'
    assert bpy.ops.allset.wireframe_color(action='DEFAULT') == {'FINISHED'}
    assert pb.color.palette == 'DEFAULT'
    bpy.ops.object.mode_set(mode='OBJECT')


def test_drawing_overrides_object():
    _clear()
    ob = _curve()
    # defaults: overrideEnabled off, overrideColor 0, overrideRGBColors off
    assert not ob.allset_override_enabled and ob.allset_override_index == 0 and ob.allset_override_mode == 'INDEX'
    ob.allset_override_enabled = True
    assert tuple(ob.color) == (1.0, 1.0, 1.0, 1.0)            # index 0 = default colour
    ob.allset_override_index = 13                               # rig convention: right = red 13
    assert _close(ob.color, (1.0, 0.0, 0.0, 1.0))
    assert _close(ob.allset_override_color, MAYA_INDEX[13])
    st = ob["allset_override"].to_dict()
    assert st["enabled"] == 1 and st["index"] == 13 and st["rgb"] == 0, st
    ob.allset_override_index = 18
    assert _close(ob.color, _lin(MAYA_INDEX[18]))
    # the override wins over a Wireframe Color
    wc.color([ob], ud=1)
    assert _close(ob.color, _lin(MAYA_INDEX[18]))
    # editing the colour = RGB colours
    ob.allset_override_color = (0.2, 0.4, 0.6)
    assert ob.allset_override_mode == 'RGB' and _close(ob.color, _lin((0.2, 0.4, 0.6)))
    ob.allset_override_mode = 'INDEX'
    assert _close(ob.color, _lin(MAYA_INDEX[18]))
    # Enable Overrides off: the Wireframe Color shows again; with no Wireframe Color either, Blender's white
    ob.allset_override_enabled = False
    assert _close(ob.color, _lin(MAYA_USER[1]))
    wc.color([ob])
    assert tuple(ob.color) == (1.0, 1.0, 1.0, 1.0) and "allset_wire_set" not in ob


def test_drawing_overrides_pose_bone():
    _clear()
    arm = _arm()
    pb = arm.pose.bones["joint1"]
    pb.allset_override_enabled = True
    pb.allset_override_index = 6                                # left = blue 6
    assert pb.color.palette == 'CUSTOM' and _close(pb.color.custom.normal, MAYA_INDEX[6])
    pb.allset_override_index = 17                               # centre = yellow 17
    assert _close(pb.color.custom.normal, MAYA_INDEX[17])
    assert arm.pose.bones["joint2"].color.palette == 'DEFAULT'
    pb.allset_override_enabled = False
    assert pb.color.palette == 'DEFAULT' and "allset_wire_set" not in pb
    bpy.ops.object.mode_set(mode='OBJECT')


def test_ae_drawing_overrides_rows():
    want = {"allset_override_enabled", "allset_override_mode", "allset_override_index", "allset_override_color"}
    for kind, owner in (("transform", bpy.types.Object), ("joint", bpy.types.PoseBone)):
        sections = ae_layout.BY_KIND[kind][0]
        sec = next(s for _d, s in ae_layout.walk(sections) if s.name == "Drawing Overrides")
        assert not sec.open                                     # Maya collapse=1
        got = {r[2] for r in sec.rows if r[0] == "prop"}
        assert want <= got, (kind, got)
        for name in want:
            assert name in owner.bl_rna.properties, (kind, name)


def test_unregister_removes_props():
    kit.disable()
    try:
        for owner in (bpy.types.Object, bpy.types.PoseBone):
            assert "allset_override_enabled" not in owner.bl_rna.properties
        assert "wireframe_color" not in dir(bpy.ops.allset) or not hasattr(bpy.types, "ALLSET_OT_wireframe_color")
    finally:
        kit.enable()
