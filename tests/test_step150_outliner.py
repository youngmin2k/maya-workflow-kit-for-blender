"""Lane B (#96): the kit's Maya Graph Editor outliner — Maya attribute names (Visibility, not Hide
Viewport), joints and blendShape nodes as their own rows, Maya's highlight rule (only picked rows, not every
attribute of a selected node), scrolling, a click on a joint row shows only its curves."""

import types
from importlib import import_module

import bpy

import kit

chrome = import_module(kit.MODULE + ".ui.editor_chrome")


def _clear():
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    for coll in (bpy.data.meshes, bpy.data.armatures, bpy.data.actions):     # their shape keys go with them
        for d in list(coll):
            coll.remove(d)
    chrome._expanded.clear()
    chrome._scroll.clear()
    chrome._picked["ids"], chrome._picked["sig"] = set(), None


def _space(only_selected=False):
    return types.SimpleNamespace(dopesheet=types.SimpleNamespace(show_only_selected=only_selected,
                                                                 show_hidden=False, filter_text=""))


def _ctx(space=None):
    return types.SimpleNamespace(scene=bpy.context.scene, space_data=space or _space(), area=None)


def _cube(name="pCube1"):
    ob = bpy.data.objects.new(name, bpy.data.meshes.new(name + "Shape"))
    bpy.context.scene.collection.objects.link(ob)
    return ob


def _rig():
    """pCube1 keyed on translateX + visibility, joint1 / joint2 keyed (joint3 not), a blendShape1 on pSphere1."""
    _clear()
    cube = _cube()
    cube.keyframe_insert("location", index=0, frame=1)
    cube.keyframe_insert("hide_viewport", frame=1)
    arm = bpy.data.objects.new("skeleton1", bpy.data.armatures.new("skeleton1"))
    bpy.context.scene.collection.objects.link(arm)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode='EDIT')
    for i, name in enumerate(("joint1", "joint2", "joint3")):
        eb = arm.data.edit_bones.new(name)
        eb.head, eb.tail = (0, 0, i), (0, 0, i + 1)
    bpy.ops.object.mode_set(mode='OBJECT')
    for name in ("joint1", "joint2"):
        pb = arm.pose.bones[name]
        pb.keyframe_insert("rotation_euler", index=2, frame=1)     # keyed before translate: listed after it
        pb.keyframe_insert("location", index=1, frame=1)
    sphere = _cube("pSphere1")
    sphere.shape_key_add(name="Basis")
    smile = sphere.shape_key_add(name="smile")
    sphere.data.shape_keys.name = "blendShape1"
    smile.keyframe_insert("value", frame=1)
    for ob in bpy.context.scene.objects:
        ob.select_set(False)
    return cube, arm, sphere


def _labels(rows):
    return [(k, n.name if k != "ATTR" else chrome.attr_label(fc)) for k, n, fc in rows]


def test_maya_names_visibility_not_hide_viewport():
    cube, _arm, _sphere = _rig()
    fcs = chrome.object_curves(cube)
    assert [chrome.attr_label(fc) for fc in fcs] == ["Translate X", "Visibility"], \
        [chrome.attr_label(fc) for fc in fcs]
    cube.keyframe_insert("hide_render", frame=1)
    cube.keyframe_insert("scale", index=2, frame=1)
    labels = [chrome.attr_label(fc) for fc in chrome.object_curves(cube)]
    assert "Primary Visibility" in labels and "Scale Z" in labels, labels
    assert not any("Hide" in s for s in labels), labels


def test_joint_and_blendshape_rows():
    _rig()
    rows = chrome.rows(_ctx(), _space())
    assert _labels(rows) == [
        ("OBJECT", "pCube1"), ("ATTR", "Translate X"), ("ATTR", "Visibility"),
        ("SHAPES", "blendShape1"), ("ATTR", "smile"),
        ("JOINT", "joint1"), ("ATTR", "Translate Y"), ("ATTR", "Rotate Z"),
        ("JOINT", "joint2"), ("ATTR", "Translate Y"), ("ATTR", "Rotate Z")], _labels(rows)
    # the armature has no curves of its own: no "skeleton1" row (Maya: joints are the nodes); joint3 isn't keyed
    chrome._expanded[("JOINT", "skeleton1", "joint1")] = False
    assert ("ATTR", "Translate Y") in _labels(chrome.rows(_ctx(), _space())) and \
        len(chrome.rows(_ctx(), _space())) == len(rows) - 2


def test_only_selected_lists_selected_joints_in_pose_mode():
    _cube_ob, arm, _sphere = _rig()
    arm.select_set(True)
    bpy.context.view_layer.objects.active = arm
    names = [n.name for k, n, _fc in chrome.rows(_ctx(_space(True)), _space(True)) if k != "ATTR"]
    assert names == [], names       # object mode, no joint selected: Blender's filter draws none of their curves
    bpy.ops.object.mode_set(mode='POSE')
    try:
        for pb in arm.pose.bones:
            chrome_cb = import_module(kit.MODULE + ".ui.channel_box")
            chrome_cb.set_bone_selected(pb, pb.name == "joint2")
        names = [n.name for k, n, _fc in chrome.rows(_ctx(_space(True)), _space(True)) if k != "ATTR"]
        assert names == ["joint2"], names
    finally:
        bpy.ops.object.mode_set(mode='OBJECT')


def test_highlight_only_picked_rows():
    cube, _arm, _sphere = _rig()
    cube.select_set(True)
    ctx = _ctx()
    rows = chrome.rows(ctx, ctx.space_data)

    def lit():
        picked = chrome.picked_ids(ctx, rows)
        return [chrome.attr_label(fc) if k == "ATTR" else n.name for k, n, fc in rows
                if chrome.highlighted(k, chrome.row_id((k, n, fc)),
                                      k != "ATTR" and chrome.node_selected(ctx, k, n), picked)]
    # nothing picked: the selected node only (Maya e02_graph_editor_win1.png), never its attribute rows
    assert lit() == ["pCube1"], lit()
    assert all(fc.select for fc in chrome.object_curves(cube))       # Blender: every curve selected
    tx = next(r for r in rows if r[0] == "ATTR" and chrome.attr_label(r[2]) == "Translate X")
    chrome.pick_row(ctx, tx)
    assert lit() == ["Translate X"], lit()
    smile = next(r for r in rows if r[0] == "SHAPES")
    chrome.pick_row(ctx, smile, shift=True)
    assert lit() == ["Translate X", "blendShape1"], lit()
    chrome.pick_row(ctx, tx, ctrl=True)
    assert lit() == ["blendShape1"], lit()
    # a new scene selection = a new load: picks are dropped, the selected nodes light up again
    cube.select_set(False)
    assert lit() == [], lit()


def test_click_joint_row_shows_only_its_curves():
    cube, arm, sphere = _rig()
    ctx = _ctx()
    rows = chrome.rows(ctx, ctx.space_data)
    j2 = next(r for r in rows if r[0] == "JOINT" and r[1].name == "joint2")
    chosen = chrome.pick_row(ctx, j2)
    j2_curves = [fc for fc in chrome.object_curves(arm) if 'pose.bones["joint2"]' in fc.data_path]
    assert len(j2_curves) == 2 and chosen == set(j2_curves)
    for fc in chrome.listed_curves(ctx, ctx.space_data):
        on = fc in j2_curves
        assert fc.select == on and fc.hide == (not on), (fc.data_path, fc.select, fc.hide)
    # the blendShape node: its curve lives in the Key ID's action (compat.id_fcurves), shown alone
    shapes = next(r for r in rows if r[0] == "SHAPES")
    chrome.pick_row(ctx, shapes)
    key_fc = chrome.object_curves(sphere.data.shape_keys)
    assert len(key_fc) == 1 and key_fc[0].select and not key_fc[0].hide
    assert all(fc.hide for fc in chrome.object_curves(arm) + chrome.object_curves(cube))


def test_scroll_offset_clamped():
    assert chrome.clamp_scroll(5, 10, 4) == 5
    assert chrome.clamp_scroll(9, 10, 4) == 6           # the last full page
    assert chrome.clamp_scroll(-3, 10, 4) == 0
    assert chrome.clamp_scroll(3, 3, 8) == 0            # a list that fits doesn't scroll
    _rig()
    ctx = _ctx()
    rows = chrome.rows(ctx, ctx.space_data)
    top_pad, h = chrome.metrics(types.SimpleNamespace(height=0))
    region = types.SimpleNamespace(height=-top_pad + 4 * h)       # room for 4 rows
    assert chrome.visible_rows(region) == 4 and len(rows) == 11
    top = chrome.metrics(region)[0]
    first_row_y = top - h // 2
    assert chrome.row_at(ctx, region, first_row_y) == rows[0]
    chrome._scroll[0] = 3
    assert chrome.row_at(ctx, region, first_row_y) == rows[3]
    chrome._scroll[0] = 99
    assert chrome.scroll_offset(ctx, region, len(rows)) == 7
    assert chrome.row_at(ctx, region, first_row_y) == rows[7]
    chrome._scroll.clear()


def test_scroll_operator_safe_without_graph_editor():
    assert hasattr(bpy.ops.allset, "graph_channel_scroll")
    assert bpy.ops.allset.graph_channel_scroll(delta=3) == {'PASS_THROUGH'}
    assert bpy.ops.allset.graph_channel_scroll(delta=-3) == {'PASS_THROUGH'}
