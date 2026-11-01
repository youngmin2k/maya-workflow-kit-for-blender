"""Issue #271: blendShape weights in animation layers, like Maya. Channel Box > Channels > Add to Selected Layers
with a weight selected puts the weight (on the mesh's blendShape node = its Key datablock) into the selected layer;
a key then goes onto that layer, solved so the result is the shown value; the layer weight scales it; the Channel Box
marks the weight as a layer member; Remove From Selected Layers takes it out again."""

from importlib import import_module

import bpy

import kit

al = import_module(kit.MODULE + ".operators.anim_layers")
cb = import_module(kit.MODULE + ".ui.channel_box")


def _scene():
    sc = bpy.context.scene
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    for coll in (bpy.data.actions, bpy.data.meshes, bpy.data.shape_keys):
        for d in list(coll):
            if d.users == 0:
                try:
                    coll.remove(d)
                except (AttributeError, RuntimeError):
                    pass
    sc.allset_anim_layers.clear()
    sc.allset_anim_layer_index = 0
    bpy.ops.mesh.primitive_cube_add()
    ob = bpy.context.active_object
    ob.shape_key_add(name="Basis")
    ob.shape_key_add(name="smile")
    for o in sc.objects:
        o.select_set(o == ob)
    bpy.context.view_layer.objects.active = ob
    key = ob.data.shape_keys
    sc.frame_set(1)
    key.key_blocks["smile"].value = 0.2
    key.keyframe_insert('key_blocks["smile"].value', frame=1)
    sc.frame_set(10)
    key.key_blocks["smile"].value = 0.4
    key.keyframe_insert('key_blocks["smile"].value', frame=10)
    return sc, ob, key


def _new_layer(sc):
    bpy.ops.allset.anim_layer_create(from_selected=False)
    return sc.allset_anim_layers[sc.allset_anim_layer_index].name


def _value(sc, key, frame):
    sc.frame_set(frame + 1)
    sc.frame_set(frame)
    return key.key_blocks["smile"].value


def test_weight_joins_the_layer_on_its_blendshape_node():
    sc, ob, key = _scene()
    l1 = _new_layer(sc)
    cb.set_selected_channels(["bw:smile"])
    assert bpy.ops.allset.anim_layer_attrs(add=True) == {'FINISHED'}
    assert l1 in al.tracks(key) and al.BASE in al.tracks(key)
    assert l1 not in al.tracks(ob), "the mesh's transform stays out of the layer"
    assert al.member_keys(key, l1) == ["bw:smile"]
    assert cb.channel_state(ob, "bw:smile") == 'LAYERED'
    assert abs(_value(sc, key, 5) - (0.2 + 0.2 * 4 / 9)) < 0.02     # BaseAnimation still plays


def test_key_on_the_layer_solves_the_shown_weight():
    sc, ob, key = _scene()
    l1 = _new_layer(sc)
    cb.set_selected_channels(["bw:smile"])
    bpy.ops.allset.anim_layer_attrs(add=True)
    sc.frame_set(10)
    key.key_blocks["smile"].value = 0.9
    assert cb.keyframe(ob, "bw:smile")
    fc = al._fcurve(al.tracks(key)[l1].strips[0].action, 'key_blocks["smile"].value', 0)
    assert fc is not None and abs(fc.evaluate(10) - 0.5) < 1e-4, fc and fc.evaluate(10)   # 0.9 - base 0.4
    base = al.base_curve(key, 'key_blocks["smile"].value', -1)
    assert [round(k.co.y, 4) for k in base.keyframe_points] == [0.2, 0.4], "BaseAnimation keeps its keys"
    assert abs(_value(sc, key, 10) - 0.9) < 1e-4
    sc.allset_anim_layers[l1].weight = 0.5                        # Maya layer weight: half the layer's offset
    assert abs(_value(sc, key, 10) - 0.65) < 1e-4, key.key_blocks["smile"].value


def test_remove_from_selected_layers_drops_the_weight():
    sc, ob, key = _scene()
    l1 = _new_layer(sc)
    cb.set_selected_channels(["bw:smile"])
    bpy.ops.allset.anim_layer_attrs(add=True)
    sc.frame_set(10)
    key.key_blocks["smile"].value = 0.9
    assert cb.keyframe(ob, "bw:smile")
    cb.set_selected_channels(["bw:smile"])
    assert bpy.ops.allset.anim_layer_attrs(add=False) == {'FINISHED'}
    assert l1 not in al.tracks(key)
    assert abs(_value(sc, key, 10) - 0.4) < 1e-4
    assert cb.channel_state(ob, "bw:smile") in ('KEYED', 'ANIMATED')


def test_delete_layer_removes_the_weight_track():
    sc, ob, key = _scene()
    l1 = _new_layer(sc)
    cb.set_selected_channels(["bw:smile"])
    bpy.ops.allset.anim_layer_attrs(add=True)
    assert bpy.ops.allset.anim_layer_delete(layer=l1) == {'FINISHED'}
    assert l1 not in al.tracks(key)
