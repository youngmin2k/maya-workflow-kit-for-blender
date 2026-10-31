"""Lane B (Issue #155): rig polish — root joint Translate, Outliner name, Orient Joint / Ghost Selected output,
menu items that left pose mode, the Channel Box joint hint.

Maya: a new root joint is ``joint1`` in
the Outliner and the Channel Box, its Translate = its position; Orient Joint after success = only the command echo;
Ghost Selected prints nothing on success, "Nothing selected can be ghosted using the current settings." when nothing
can be ghosted). Kit axes: the kit shows Blender's Z-up values (Maya Translate Y = kit Z).
"""

import json
from importlib import import_module

import bpy

import kit

joints = import_module(kit.MODULE + ".operators.joints")
joint_edit = import_module(kit.MODULE + ".operators.joint_edit")
units = import_module(kit.MODULE + ".operators.units")
cb = import_module(kit.MODULE + ".ui.channel_box")
command_line = import_module(kit.MODULE + ".command_line")

# Blender position of the root joint (Maya (3, 2, 1) in Y-up = Blender (3, -1, 2))
ROOT = (3.0, -1.0, 2.0)
CHAIN = [ROOT, (3.0, -1.0, 6.0), (5.0, -1.0, 9.0)]


def _reset():
    if bpy.context.object is not None and bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    for arm in list(bpy.data.armatures):
        bpy.data.armatures.remove(arm)
    joint_edit.rebase()


def _skeleton():
    """Joint Tool with three points (no clicks): pose mode, joint1 selected, like the #155 session."""
    _reset()
    k = units.maya_unit(bpy.context.scene)
    pts = [[c * k for c in p] for p in CHAIN]
    assert bpy.ops.allset.joint_tool(points=json.dumps(pts)) == {'FINISHED'}
    ob = bpy.context.object
    assert ob.type == 'ARMATURE' and ob.mode == 'POSE', (ob.type, ob.mode)
    return ob, k


def _numbers(scene):
    c = scene.allset_cb
    return [float(c.tx_text), float(c.ty_text), float(c.tz_text)]


def _close(a, b, tol=1e-3):
    return all(abs(x - y) < tol for x, y in zip(a, b))


# --- 1. root joint Translate ------------------------------------------------------------------------------------------

def test_root_joint_translate_shows_its_position():
    ob, k = _skeleton()
    scene = bpy.context.scene
    assert cb.lead().name == "joint1"
    assert _close(_numbers(scene), ROOT), _numbers(scene)


def test_root_joint_translate_entry_moves_it():
    ob, k = _skeleton()
    scene = bpy.context.scene
    scene.allset_cb.tz_text = "5"
    scene.allset_cb.ty_text = "+=1"
    bpy.context.view_layer.update()
    head = ob.matrix_world @ ob.pose.bones["joint1"].head
    assert _close(head / k, (3.0, 0.0, 5.0)), head / k
    assert _close(_numbers(scene), (3.0, 0.0, 5.0)), _numbers(scene)
    # the children come along (their joint offsets unchanged)
    j2 = ob.matrix_world @ ob.pose.bones["joint2"].head
    assert _close(j2 / k, (3.0, 0.0, 9.0)), j2 / k


def test_root_joint_translate_keys_and_edit_mode_agree():
    ob, k = _skeleton()
    scene = bpy.context.scene
    pb = ob.pose.bones["joint1"]
    assert cb.keyframe(pb, "tx")
    fc = cb.fcurve(pb, "tx")
    assert fc is not None
    scene.allset_cb.tx_text = "4"
    assert _close(_numbers(scene), (4.0, -1.0, 2.0)), _numbers(scene)
    # the same rule in Edit mode (the Channel Box Translate): the root joint's rest position, kit axes
    for p in ob.pose.bones:
        p.location = (0.0, 0.0, 0.0)
    bpy.ops.object.mode_set(mode='EDIT')
    ob.data.edit_bones.active = ob.data.edit_bones["joint1"]
    shown = [float(scene.allset_joint_tx), float(scene.allset_joint_ty), float(scene.allset_joint_tz)]
    assert _close(shown, ROOT), shown
    scene.allset_joint_tz = "3"
    assert _close(ob.data.edit_bones["joint1"].head / k, (3.0, -1.0, 3.0)), ob.data.edit_bones["joint1"].head
    bpy.ops.object.mode_set(mode='POSE')


def test_child_joint_translate_unchanged():
    """Pose-mode child joints keep showing the pose offset — only the root changed."""
    ob, k = _skeleton()
    cbm = joints._cb()
    for p in ob.pose.bones:
        cbm.set_bone_selected(p, p.name == "joint2")
    ob.data.bones.active = ob.data.bones["joint2"]
    assert cb.lead().name == "joint2"
    assert _close(_numbers(bpy.context.scene), (0.0, 0.0, 0.0)), _numbers(bpy.context.scene)


# --- 2. Outliner name -------------------------------------------------------------------------------------------------

def test_outliner_label_is_root_joint():
    ob, _k = _skeleton()
    ol = import_module(kit.MODULE + ".ui.outliner_joints")
    assert ol.label(ob) == "joint1"
    cube = bpy.data.objects.new("pCube1", bpy.data.meshes.new("pCubeShape1"))
    bpy.context.scene.collection.objects.link(cube)
    assert ol.label(cube) is None
    # a renamed root joint renames the row
    ob.data.bones["joint1"].name = "hip"
    assert ol.label(ob) == "hip"


# --- 3. Orient Joint output -------------------------------------------------------------------------------------------

def test_orient_joint_prints_no_result():
    ob, _k = _skeleton()
    command_line._result["text"] = "previous"
    assert bpy.ops.allset.orient_joint() == {'FINISHED'}
    assert command_line._result["text"] == "", command_line._result


# --- 4. Ghost Selected output -----------------------------------------------------------------------------------------

def test_ghost_selected_prints_nothing():
    _reset()
    me = bpy.data.meshes.new("pCubeShape1")
    cube = bpy.data.objects.new("pCube1", me)
    bpy.context.scene.collection.objects.link(cube)
    cube.select_set(True)
    bpy.context.view_layer.objects.active = cube
    command_line._result["text"] = "previous"
    assert bpy.ops.allset.ghost(action="GHOST") == {'FINISHED'}
    assert cube.allset_ghost.enabled
    assert command_line._result["text"] == "", command_line._result


def test_ghost_selected_nothing_selected_error():
    _reset()
    try:
        bpy.ops.allset.ghost(action="GHOST")
    except RuntimeError as ex:
        assert "Nothing selected can be ghosted using the current settings." in str(ex), str(ex)
    else:
        raise AssertionError("Ghost Selected with nothing selected must report Maya's error")


# --- 5. menu items keep pose mode -------------------------------------------------------------------------------------

# the #155 session — Maya has no modes: none of these changes what is selected
MENU_ITEMS = (
    "Key/Hold Current Keys",
    "Key/IK/FK Keys/Move IK to FK",
    "Key/Set Blend Shape Target Weight Keys",
    "Visualize/Ghost Selected",
    "Visualize/Create Animation Snapshot",
    "Windows/Animation Editors/Time Editor",
    "Windows/LookdevX Graph Editor",
    "Windows/Bifrost Graph Editor",
)


def test_menu_items_keep_pose_mode():
    left = []
    for path in MENU_ITEMS:
        ob, _k = _skeleton()
        try:
            bpy.ops.allset.menu_item(item=path)
        except RuntimeError:
            pass            # a Maya error is fine; leaving pose mode is not
        if bpy.context.object is not ob or ob.mode != 'POSE' or cb.lead() is None or cb.lead().name != "joint1":
            left.append((path, ob.mode))
    assert not left, left


def test_snapshot_on_joints_keeps_pose_mode():
    ob, _k = _skeleton()
    try:
        bpy.ops.allset.animation_snapshot()
    except RuntimeError as ex:
        assert "No geometry found to create snapshot." in str(ex), str(ex)
    assert ob.mode == 'POSE' and bpy.context.object is ob


# --- 5b. Channel Box hint -----------------------------------------------------------------------------------------------

def test_joint_hint_fits_the_dock():
    import blf
    toolbox = import_module(kit.MODULE + ".ui.toolbox")
    for scale in (1.0, 1.25):
        blf.size(0, 11.0 * scale)
        w = blf.dimensions(0, cb.POSE_HINT)[0]
        room = toolbox.dock_width(scale, kind="CHANNEL_BOX") - 60 * scale   # panel margins + tab strip
        assert w < room, (scale, w, room, cb.POSE_HINT)
