"""Maya Ctrl+D duplicate names copies pCube2 / pCubeShape2 (not pCube1.001),
in place, with the subtree; Shift+D after it repeats the move."""

from importlib import import_module

import bpy
from mathutils import Vector

import kit

menu_map = import_module(kit.MODULE + ".ui.menu_map")


def _fresh():
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o)
    for m in list(bpy.data.meshes):
        bpy.data.meshes.remove(m)


def _only(*obs):
    for o in bpy.context.view_layer.objects:
        o.select_set(o in obs)
    bpy.context.view_layer.objects.active = obs[-1]


def _create(kind):
    assert bpy.ops.allset.create(kind=kind) == {'FINISHED'}
    return bpy.context.active_object


def test_ctrl_d_binding():
    km = kit.maya_kc().keymaps["Object Mode"]
    items = [k for k in km.keymap_items if k.active and k.type == 'D' and k.ctrl and not k.shift
             and not k.alt and k.value == 'PRESS']
    assert [k.idname for k in items] == ["allset.duplicate"], [k.idname for k in items]
    assert menu_map.MAP["Edit/Duplicate"] == "allset.duplicate"


def test_three_duplicates_count_up():
    _fresh()
    cube = _create('CUBE')
    cube.location = (1, 2, 3)
    assert cube.name == "pCube1" and cube.data.name == "pCubeShape1"
    names = []
    for _ in range(3):
        assert bpy.ops.allset.duplicate() == {'FINISHED'}
        dup = bpy.context.active_object
        names.append((dup.name, dup.data.name))
        assert (dup.location - Vector((1, 2, 3))).length < 1e-6, "in place"
        assert bpy.context.selected_objects == [dup], "only the copy is selected"
    assert names == [("pCube2", "pCubeShape2"), ("pCube3", "pCubeShape3"), ("pCube4", "pCubeShape4")], names
    assert bpy.data.objects["pCube2"].data is not cube.data, "geometry copied, not shared"


def test_group_duplicate_renames_children():
    _fresh()
    cube, sphere = _create('CUBE'), _create('SPHERE')
    _only(cube, sphere)
    bpy.ops.allset.group()
    grp = bpy.data.objects["group1"]
    sphere.location = (3, 0, 0)
    bpy.context.view_layer.update()
    _only(grp)
    bpy.ops.allset.duplicate()
    new = bpy.context.active_object
    assert new.name == "group2", new.name
    kids = sorted(c.name for c in new.children)
    assert kids == ["pCube2", "pSphere2"], kids
    bpy.context.view_layer.update()
    assert (bpy.data.objects["pSphere2"].matrix_world.translation - Vector((3, 0, 0))).length < 1e-5
    assert bpy.data.objects["pSphere2"].data.name == "pSphereShape2"


def test_shift_d_repeats_after_ctrl_d():
    _fresh()
    cube = _create('CUBE')
    bpy.ops.allset.duplicate()
    dup = bpy.context.active_object
    dup.location.x += 2.0
    bpy.context.view_layer.update()
    bpy.ops.allset.duplicate_with_transform()
    third = bpy.context.active_object
    assert third.name == "pCube3", third.name
    assert abs(third.location.x - 4.0) < 1e-5, third.location


def test_blender_names_renumber():
    _fresh()
    me = bpy.data.meshes.new("Cube")
    ob = bpy.data.objects.new("Cube", me)
    bpy.context.scene.collection.objects.link(ob)
    bpy.context.view_layer.update()
    _only(ob)
    bpy.ops.allset.duplicate()
    assert bpy.context.active_object.name == "Cube1", bpy.context.active_object.name
