"""Issue #271 follow-up: blendShape weight channels picked in the Channel Box (INPUTS > blendShape1 > target) work
where other picked channels do — Create Character Set From Channel Box / Add to Character Set (S keys them on the
blendShape node) and Set Driven Key Load Driver / Load Driven (the blendShape node with that weight)."""
from importlib import import_module

import bpy

import kit

cb = import_module(kit.MODULE + ".ui.channel_box")
sdk = import_module(kit.MODULE + ".operators.driven_key")
chars = import_module(kit.MODULE + ".operators.character_sets")
compat = import_module(kit.MODULE + ".compat")


def _scene():
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ks in list(bpy.context.scene.keying_sets):
        bpy.context.scene.keying_sets.active = ks
        bpy.ops.anim.keying_set_remove()
    for coll in (bpy.data.objects, bpy.data.meshes, bpy.data.actions):
        for idb in list(coll):
            coll.remove(idb)
    me = bpy.data.meshes.new("pSphere1")
    me.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)])
    head = bpy.data.objects.new("pSphere1", me)
    bpy.context.scene.collection.objects.link(head)
    head.shape_key_add(name="Basis")
    head.shape_key_add(name="smile").value = 0.0
    me.shape_keys.name = "blendShape1"
    for o in bpy.context.scene.objects:
        o.select_set(False)
    head.select_set(True)
    bpy.context.view_layer.objects.active = head
    bpy.context.scene.frame_set(1)
    return head, me.shape_keys


def test_character_set_from_channel_box_keys_the_weight():
    head, key = _scene()
    cb.set_selected_channels(["bw:smile"])
    assert bpy.ops.allset.character_create(attributes='CHANNEL_BOX') == {'FINISHED'}
    ks = chars.current(bpy.context.scene)
    paths = [(p.id, p.data_path, p.array_index) for p in ks.paths]
    assert paths == [(key, 'key_blocks["smile"].value', 0)], paths
    key.key_blocks["smile"].value = 0.7
    assert chars.key_current(bpy.context) == 1
    fcs = [fc.data_path for fc in compat.id_fcurves(key)]
    assert fcs == ['key_blocks["smile"].value'], fcs


def test_add_weight_to_a_character_set():
    head, key = _scene()
    cb.set_selected_channels(["tx"])
    assert bpy.ops.allset.character_create(attributes='CHANNEL_BOX') == {'FINISHED'}
    cb.set_selected_channels(["bw:smile"])
    assert bpy.ops.allset.character_edit(add=True) == {'FINISHED'}
    ks = chars.current(bpy.context.scene)
    assert {(p.id.name, p.data_path) for p in ks.paths} == {("pSphere1", "location"),
                                                            ("blendShape1", 'key_blocks["smile"].value')}
    cb.set_selected_channels(["bw:smile"])
    assert bpy.ops.allset.character_edit(add=False) == {'FINISHED'}
    assert [p.data_path for p in ks.paths] == ["location"]


def test_set_driven_key_loads_picked_weights():
    head, key = _scene()
    ctl = bpy.data.objects.new("ctrl", None)
    bpy.context.scene.collection.objects.link(ctl)
    bpy.ops.allset.sdk_window()
    st = bpy.context.window_manager.allset_sdk
    # driven: the picked weight shows the blendShape node with that attribute
    cb.set_selected_channels(["bw:smile"])
    assert bpy.ops.allset.sdk_load(which='DRIVEN') == {'FINISHED'}
    assert sdk.driven_nodes(st)[st.driven_index] == key, (sdk.driven_nodes(st), st.driven_index)
    assert sdk.driven_keys(st) == ["bs:smile"]
    # driver: a picked weight makes the blendShape node the driver
    st2_head, _key2 = head, key
    assert bpy.ops.allset.sdk_load(which='DRIVER') == {'FINISHED'}
    assert sdk.driver_node(st) == key and st.driver_attr == "bs:smile", (sdk.driver_node(st), st.driver_attr)
    # a picked object channel still loads the object
    for o in bpy.context.scene.objects:
        o.select_set(o == ctl)
    bpy.context.view_layer.objects.active = ctl
    cb.set_selected_channels(["tx"])
    assert bpy.ops.allset.sdk_load(which='DRIVER') == {'FINISHED'}
    assert sdk.driver_node(st) == ctl and st.driver_attr == "tx"
    assert st2_head
    st.open = False
