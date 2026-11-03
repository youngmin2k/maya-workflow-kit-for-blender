"""Type Manipulator: single characters of a Type node move, turn and scale about their own middle; a handle object
stands for the picked character while the manipulator is on."""
from importlib import import_module

import bpy
import numpy as np

import kit

tm = import_module(kit.MODULE + ".operators.type_manip")
create = import_module(kit.MODULE + ".operators.create")
cb = import_module(kit.MODULE + ".ui.channel_box")
ae = import_module(kit.MODULE + ".ui.attribute_editor")
menu_map = import_module(kit.MODULE + ".ui.menu_map")


def _type(body="Hi ok"):
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    ob = create.create(bpy.context, 'TEXT')
    ob.data.body = body
    ob.data.extrude = 0.05
    bpy.context.view_layer.objects.active = ob
    ob.select_set(True)
    return ob


def _chars(ob):
    bpy.context.view_layer.update()
    return tm.characters(ob, bpy.context.evaluated_depsgraph_get())


def _verts(ob, modifier_on=True):
    md = tm.modifier(ob)
    if md is not None:
        md.show_viewport = modifier_on
    bpy.context.view_layer.update()
    ev = ob.evaluated_get(bpy.context.evaluated_depsgraph_get())
    mesh = ev.to_mesh()
    co = np.array([v.co[:] for v in mesh.vertices])
    ev.to_mesh_clear()
    if md is not None:
        md.show_viewport = True
    return co


def test_every_visible_character_is_found():
    ob = _type("Hi ok\nAm")
    tm.ensure(ob)
    chars = _chars(ob)
    assert sorted(chars) == [i for i, c in enumerate(ob.data.body) if not c.isspace()], sorted(chars)
    # the modifier alone changes nothing
    assert np.abs(_verts(ob) - _verts(ob, modifier_on=False)).max() < 1e-5
    # characters keep left-to-right order on a line, each pivot inside its own box
    xs = [chars[i][1][0][0] for i in (0, 1, 3, 4)]
    assert xs == sorted(xs), xs
    for pivot, (lo, hi) in chars.values():
        assert lo[0] <= pivot[0] <= hi[0] and lo[1] <= pivot[1] <= hi[1]


def test_text_settings_are_followed():
    ob = _type("Ab cd")
    cu = ob.data
    cu.align_x, cu.space_character, cu.shear, cu.offset_x = 'CENTER', 1.4, 0.25, 0.3
    tm.ensure(ob)
    assert sorted(_chars(ob)) == [0, 1, 3, 4]
    assert np.abs(_verts(ob) - _verts(ob, modifier_on=False)).max() < 1e-5


def test_one_character_moves_turns_and_scales_about_its_middle():
    ob = _type()
    tm.ensure(ob)
    before = _chars(ob)
    tm.set_xform(ob.data, 1, (0.0, 0.5, 0.0, 0.0, 0.0, 0.0, 2.0, 2.0, 1.0))
    tm.sync(ob)
    after = _chars(ob)
    (lo0, hi0), (lo1, hi1) = before[1][1], after[1][1]
    assert np.allclose((lo1 + hi1) / 2, (lo0 + hi0) / 2 + np.array((0.0, 0.5, 0.0)), atol=0.02)
    assert np.allclose((hi1 - lo1)[:2], 2.0 * (hi0 - lo0)[:2], atol=0.02)
    for i in (0, 3, 4):
        assert np.allclose(after[i][1][0], before[i][1][0], atol=1e-5), "other characters stay"
    # a quarter turn about Z swaps the character's width and height
    tm.set_xform(ob.data, 1, (0.0, 0.0, 0.0, 0.0, 0.0, np.pi / 2, 1.0, 1.0, 1.0))
    tm.sync(ob)
    lo2, hi2 = _chars(ob)[1][1]
    assert abs((hi2 - lo2)[0] - (hi0 - lo0)[1]) < 0.02 and abs((hi2 - lo2)[1] - (hi0 - lo0)[0]) < 0.02


def test_editing_the_text_keeps_the_transforms():
    ob = _type("ab")
    tm.ensure(ob)
    tm.set_xform(ob.data, 0, (0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0, 1.0, 1.0))
    tm.sync(ob)
    ob.data.body = "abcdef"
    tm.sync(ob)
    nodes = tm.modifier(ob).node_group.nodes
    assert len(nodes["Offsets"].index_switch_items) == 6
    chars = _chars(ob)
    assert sorted(chars) == [0, 1, 2, 3, 4, 5]
    assert chars[0][1][0][2] > 0.9 and chars[1][1][0][2] < 0.0


def test_manipulator_handle_writes_its_character():
    ob = _type()
    assert bpy.ops.allset.type_manipulator() == {'FINISHED'}
    handle = tm.handle_of(ob)
    assert handle is not None and handle.parent == ob
    assert bpy.context.view_layer.objects.active == handle and handle.select_get() and not ob.select_get()
    assert int(handle[tm.CHAR]) == 0
    start = _chars(ob)[0][1]
    handle.location.x += 1.0
    handle.rotation_euler.z = 0.3
    bpy.context.view_layer.update()          # the depsgraph handler stores the handle's move
    values = tm.xforms(ob.data)[0]
    assert abs(values[0] - 1.0) < 1e-5 and abs(values[5] - 0.3) < 1e-5, values
    now = _chars(ob)[0][1]
    assert abs((now[0][0] + now[1][0]) / 2 - (start[0][0] + start[1][0]) / 2 - 1.0) < 0.05
    # picking another character puts the handle on it, with that character's (empty) transform
    assert bpy.ops.allset.type_char_pick(type_object=ob.name, index=3) == {'FINISHED'}
    assert int(handle[tm.CHAR]) == 3 and tuple(handle.scale) == (1.0, 1.0, 1.0)
    assert abs(handle.location.x - _chars(ob)[3][0][0]) < 1e-5
    assert tm.xforms(ob.data)[0][0] == values[0], "the first character stays where it was moved"
    # off: the handle goes, the transforms (and so the modifier) stay, the text is selected again
    assert bpy.ops.allset.type_manipulator() == {'FINISHED'}
    assert tm.handle_of(ob) is None and tm.modifier(ob) is not None
    assert bpy.context.view_layer.objects.active == ob


def test_reset_puts_characters_back_and_drops_the_modifier():
    ob = _type()
    bpy.ops.allset.type_manipulator()
    handle = tm.handle_of(ob)
    handle.location.y += 0.4
    bpy.context.view_layer.update()
    assert 0 in tm.xforms(ob.data)
    tree = tm.modifier(ob).node_group.name
    assert bpy.ops.allset.type_reset() == {'FINISHED'}
    assert not tm.xforms(ob.data) and abs(handle.location.y - _chars(ob)[0][0][1]) < 1e-5
    bpy.context.view_layer.objects.active = ob
    bpy.ops.allset.type_manipulator()            # off
    assert tm.modifier(ob) is None, "nothing moved: the type is a plain text object again"
    assert tree not in bpy.data.node_groups


def test_modifier_is_part_of_the_type_node():
    ob = _type()
    tm.ensure(ob)
    assert not cb._inputs(ob), "no INPUTS node for the type's own character transforms"
    assert not [t for t in ae.tabs(ob) if t[0].startswith("M:")]


def test_duplicate_gets_its_own_tree():
    ob = _type("ab")
    tm.ensure(ob)
    copy = ob.copy()
    copy.data = ob.data.copy()
    bpy.context.scene.collection.objects.link(copy)
    copy.data.body = "xyz"
    tm.sync(copy)
    assert tm.modifier(copy).node_group != tm.modifier(ob).node_group
    assert tm.modifier(ob).node_group.nodes["Layout"].inputs["String"].default_value == "ab"


def test_hit_picks_the_smallest_box():
    boxes = [(0, (0, 0, 100, 100)), (1, (40, 40, 60, 60))]
    assert tm.hit(boxes, 50, 50) == 1
    assert tm.hit(boxes, 10, 10) == 0
    assert tm.hit(boxes, 200, 10) is None


def test_menu_item_and_keymap():
    assert menu_map.MAP["Modify/Transformation Tools/Type Manipulator"][1] == "allset.type_manipulator"
    kc = kit.maya_kc()
    for km_name in ("3D View", "3D View Tool: Tweak"):
        items = [i.idname for i in kc.keymaps[km_name].keymap_items if i.type == 'LEFTMOUSE']
        assert "allset.type_char_pick" in items, km_name
