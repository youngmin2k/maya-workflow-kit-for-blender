"""L17 / L15b: Maya reorderDeformers on the modifier stack, Key > Set Blend Shape Target Weight Keys.
Maya 2026 deformer order."""

from importlib import import_module

import bpy

import kit

order_mod = import_module(kit.MODULE + ".operators.deformer_order")
menu_map = import_module(kit.MODULE + ".ui.menu_map")
notices = import_module(kit.MODULE + ".ui.notices")

# Maya: evaluation order c1 c2 c3 (Maya lists output first: c3 c2 c1)
MAYA = {("c3", "c1"): ["c2", "c1", "c3"], ("c1", "c3"): ["c3", "c1", "c2"], ("c1", "c2"): ["c2", "c1", "c3"]}


def _clear():
    if bpy.context.active_object is not None and bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)


def _cube_with_three():
    _clear()
    bpy.ops.mesh.primitive_cube_add()
    ob = bpy.context.active_object
    for n in ("c1", "c2", "c3"):
        ob.modifiers.new(n, 'DISPLACE')
    return ob


def test_pure_rule_matches_maya():
    for (a, b), want in MAYA.items():
        assert order_mod.reorder(["c1", "c2", "c3"], a, b) == want, (a, b)
    try:
        order_mod.reorder(["c1", "c2", "c3"], "c2", "c1")
    except order_mod.AlreadyInOrder as ex:
        assert str(ex) == "c1 and c2 are already in the specified order." or "already in the specified order" in str(ex)
    else:
        raise AssertionError("no warning for an order that is already right")


def test_operator_moves_the_stack_and_undoes():
    for (a, b), want in MAYA.items():
        name = _cube_with_three().name
        bpy.ops.ed.undo_push(message="before")
        res = bpy.ops.allset.reorder_deformers('EXEC_DEFAULT', True, object=name, first=a, second=b)
        assert res == {'FINISHED'}
        got = [m.name for m in bpy.data.objects[name].modifiers]
        assert got == want, (got, a, b)
    name = _cube_with_three().name
    bpy.ops.ed.undo_push(message="before")
    bpy.ops.allset.reorder_deformers('EXEC_DEFAULT', True, object=name, first="c3", second="c1")
    bpy.ops.ed.undo()
    ob = bpy.data.objects[name]
    assert [m.name for m in ob.modifiers] == ["c1", "c2", "c3"]


def test_already_in_order_changes_nothing():
    ob = _cube_with_three()
    res = bpy.ops.allset.reorder_deformers('EXEC_DEFAULT', object=ob.name, first="c2", second="c1")
    assert res == {'CANCELLED'} and [m.name for m in ob.modifiers] == ["c1", "c2", "c3"]


def test_smooth_preview_stays_last():
    """The kit's display-only smooth preview modifiers are not Maya history: reordering never passes them."""
    display = import_module(kit.MODULE + ".operators.display")
    ob = _cube_with_three()
    preview = ob.modifiers.new(sorted(display.PREVIEW_NAMES)[0], 'SUBSURF')
    names = [m.name for m in ob.modifiers]
    assert names[-1] == preview.name
    order_mod.reorder_deformers(ob, "c3", "c1")
    assert [m.name for m in ob.modifiers] == ["c2", "c1", "c3", preview.name]


def test_new_cluster_goes_last_blend_shapes_first():
    """Maya 2026: Deform > Cluster (Default) lands at the end of the chain; Blend Shape (automatic) before the skin
    = Blender shape keys, always evaluated before every modifier."""
    _clear()
    bpy.ops.mesh.primitive_cube_add()
    ob = bpy.context.active_object
    ob.modifiers.new("skinCluster1", 'ARMATURE')
    ob.select_set(True)
    res = bpy.ops.allset.cluster('EXEC_DEFAULT')
    assert 'FINISHED' in res
    hooks = [i for i, m in enumerate(ob.modifiers) if m.type == 'HOOK']
    arm = [i for i, m in enumerate(ob.modifiers) if m.type == 'ARMATURE']
    assert hooks and arm and hooks[0] > arm[0], [m.name for m in ob.modifiers]


def test_blend_shape_weight_keys():
    _clear()
    bpy.ops.mesh.primitive_cube_add()
    ob = bpy.context.active_object
    ob.shape_key_add(name="Basis")
    smile = ob.shape_key_add(name="smile")
    frown = ob.shape_key_add(name="frown")
    smile.value, frown.value = 0.25, 0.5
    bpy.context.scene.frame_set(7)
    assert bpy.ops.allset.key_blend_shape_weights('EXEC_DEFAULT') == {'FINISHED'}
    key = ob.data.shape_keys
    paths = sorted(fc.data_path for fc in kit.fcurves(key))
    assert paths == ['key_blocks["frown"].value', 'key_blocks["smile"].value'], paths
    for fc in kit.fcurves(key):
        assert [tuple(p.co) for p in fc.keyframe_points][0][0] == 7.0
    for o in bpy.context.selected_objects:
        o.select_set(False)
    try:
        bpy.ops.allset.key_blend_shape_weights('EXEC_DEFAULT')
    except RuntimeError as ex:
        assert "No shape was selected." in str(ex)
    else:
        raise AssertionError("Maya's error for an empty selection")


def test_menu_row():
    assert menu_map.MAP["Key/Set Blend Shape Target Weight Keys"] == "allset.key_blend_shape_weights"
    assert "Key/Set Blend Shape Target Weight Keys" not in notices.NOTICES
