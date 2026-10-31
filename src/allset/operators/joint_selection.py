# SPDX-License-Identifier: GPL-3.0-or-later
"""Bridge Maya joint objects to Blender pose bones without a manual mode switch."""

import bpy
import numpy as np

from .. import compat
from .preselect import project, segment_distance


def clear(context):
    """Clear latent bone selections too, so reselecting a rig cannot revive them."""
    from ..ui.channel_box import set_bone_selected
    for ob in context.view_layer.objects:
        if ob is None or ob.type != 'ARMATURE':
            continue
        if ob.mode == 'EDIT':
            for bone in ob.data.edit_bones:
                bone.select = bone.select_head = bone.select_tail = False
            ob.data.edit_bones.active = None
        for pb in ob.pose.bones:
            set_bone_selected(pb, False)
        ob.data.bones.active = None


def _collection_hidden(bone):
    return bool(bone.collections) and not any(c.is_visible_effectively for c in bone.collections)


def root_joints(ob):
    """Pose bones of the skeleton's top joints: shown bones with no shown ancestor, in bone order."""
    out = []
    for pb in ob.pose.bones:
        if compat.bone_hidden(pb) or _collection_hidden(pb.bone):
            continue
        up = pb.bone.parent
        while up is not None and (up.hide or _collection_hidden(up)):
            up = up.parent
        if up is None:
            out.append(pb)
    return out


def select_roots_if_empty(ob):
    """Maya: picking a skeleton picks its root joint (the Channel Box shows
    the root's channels, Select > All = every root, lead = the last). When the automatic Pose mode shows
    a rig with no shown bone selected, select its root joints, the last one active. True when it selected."""
    from ..ui.channel_box import bone_selected, set_bone_selected
    if ob is None or ob.type != 'ARMATURE' or ob.pose is None:
        return False
    if ob.mode == 'EDIT':
        # an unskinned skeleton is shown in Edit mode; its root joints are picked with their subtrees
        ebs = ob.data.edit_bones
        if any(eb.select or eb.select_head or eb.select_tail for eb in ebs):
            return False
        roots = [ebs[pb.name] for pb in root_joints(ob) if pb.name in ebs]
        for eb in roots:
            for b in _subtree(eb):
                _set_edit(b, True)
        if roots:
            ebs.active = roots[-1]
        return bool(roots)
    if any(bone_selected(pb) and not compat.bone_hidden(pb) and not _collection_hidden(pb.bone)
           for pb in ob.pose.bones):
        return False
    roots = root_joints(ob)
    for pb in roots:
        set_bone_selected(pb, True)
    if roots:
        ob.data.bones.active = roots[-1].bone
    return bool(roots)


def pick(context, ob, mouse, radius):
    """Pick a visible, selectable joint, preferring its head over the connecting shaft."""
    from .select_priority import BONE_WIDTH, bone_width
    editing = ob.mode == 'EDIT'
    bones = ob.data.edit_bones if editing else ob.pose.bones
    candidates = []
    persp = np.asarray(context.region_data.perspective_matrix, dtype=np.float64)
    region = context.region
    for item in bones:
        bone = item if editing else item.bone
        hidden = bone.hide if editing else compat.bone_hidden(item)
        if (hidden or bone.hide_select or (bone.collections and
                not any(c.is_visible_effectively for c in bone.collections))):
            continue
        points = np.asarray([ob.matrix_world @ item.head, ob.matrix_world @ item.tail])
        screen, front = project(points, persp, region.width, region.height)
        if not all(front):
            continue
        distance, t = segment_distance(mouse, screen[:1], screen[1:])
        width = BONE_WIDTH * np.linalg.norm(screen[1] - screen[0]) if ob.data.display_type == 'OCTAHEDRAL' else 0
        shaft = max(0.0, float(distance[0] - bone_width(t, width)[0]))
        head = float(np.linalg.norm(screen[0] - mouse))
        if min(head, shaft) <= radius:
            candidates.append((head > radius, head if head <= radius else shaft, item.name))
    return min(candidates)[2] if candidates else None


# --- Edit or Pose (Issue #156) ------------------------------------
# Maya moves a placed joint with W at any time (translate; the children follow). Blender can't translate a connected
# bone in Pose mode, so while the **Move tool** is on, a skeleton that drives no mesh is shown in Edit mode (the rest
# = where Maya's joints are); with any other tool joints are picked in Pose mode as before (Channel Box
# channels, S keys, pick walk). A skinned (or animated) skeleton is posed with every tool, and Skin > Move Skinned
# Joints puts it in Edit mode for the move (the Armature modifier deforms by pose x rest^-1: a new rest at the rest
# pose leaves the mesh where it is = Maya's moveJointsMode rewriting bindPreMatrix). Entering Edit mode on every pick would
# lose the Channel Box / S / pick walk of unskinned joints.

MOVE_SKINNED = "allset_move_skinned"
AUTO_EDIT = "allset_joint_move_edit"      # Edit mode entered because of the Move tool (sync_tool_mode leaves it)
POSE_PIN = "allset_joint_pose_pin"        # F8 chose Pose while the Move tool is on


def move_tool_active(context):
    try:
        tools = context.workspace.tools
        return any((t := tools.from_space_view3d_mode(m, create=False)) is not None and t.idname == "builtin.move"
                   for m in {context.mode, 'POSE'} if m in {'POSE', 'EDIT_ARMATURE', 'OBJECT'})
    except (AttributeError, RuntimeError, TypeError):
        return False


def sync_tool_mode(context):
    """Move tool on an unskinned skeleton's picked joints -> Edit mode with the picked subtrees; another tool -> back
    to Pose with the same joints picked. Returns the mode switched to (None: nothing done). tool_keys watch, 0.25 s."""
    ob = context.active_object
    if ob is None or ob.type != 'ARMATURE' or not ob.select_get() or ob.get(MOVE_SKINNED):
        return None
    moving = move_tool_active(context)
    if ob.get(POSE_PIN):            # F8 went back to Pose with the Move tool on: stay until another tool is picked
        if not moving:
            ob.pop(POSE_PIN, None)
        return None
    if ob.mode == 'POSE' and moving and joint_mode(ob) == 'EDIT':
        from ..ui.channel_box import bone_selected
        picked = [pb.name for pb in ob.pose.bones if bone_selected(pb)]
        active = ob.data.bones.active.name if ob.data.bones.active else None
        if not picked or any(ob.pose.bones[n].custom_shape is not None for n in picked):
            return None     # controls (custom shapes) are animated in Pose, never repositioned (#171)
        bpy.ops.object.mode_set(mode='EDIT')
        ob[AUTO_EDIT] = True
        ebs = ob.data.edit_bones
        for eb in ebs:
            _set_edit(eb, False)
        for name in picked:
            for b in _subtree(ebs[name]):
                _set_edit(b, True)
        ebs.active = ebs.get(active) if active in picked else ebs[picked[-1]]
        sync_joint_pivot(context)
        return 'EDIT'
    if ob.mode == 'EDIT' and ob.get(AUTO_EDIT) and not moving:
        picked = [eb.name for eb in _edit_picked(ob)]
        active = ob.data.edit_bones.active.name if ob.data.edit_bones.active else None
        ob.pop(AUTO_EDIT, None)
        bpy.ops.object.mode_set(mode='POSE')
        from ..ui.channel_box import set_bone_selected
        for pb in ob.pose.bones:
            set_bone_selected(pb, pb.name in picked)
        if picked:
            ob.data.bones.active = ob.data.bones[active if active in picked else picked[-1]]
        return 'POSE'
    return None


def is_skinned(ob):
    """An Armature modifier of some mesh uses ``ob`` (Maya: a skinCluster influence)."""
    return any(o.type == 'MESH' and any(m.type == 'ARMATURE' and m.object == ob for m in o.modifiers)
               for o in bpy.data.objects)


def is_animated(ob):
    ad = ob.animation_data
    if ad is None:
        return False
    if ad.nla_tracks:
        return True
    return any(fc.data_path.startswith("pose.bones") for fc in compat.id_fcurves(ob))


def joint_mode(ob):
    """'EDIT' where moving a joint repositions its rest (unskinned, unanimated, or Move Skinned Joints on), else
    'POSE' (used with the Move tool, see sync_tool_mode)."""
    if ob.get(MOVE_SKINNED):
        return 'EDIT'
    return 'POSE' if is_skinned(ob) or is_animated(ob) else 'EDIT'


def sync_joint_pivot(context):
    """E / R on picked joints in Edit mode turn / scale about the lead joint (Maya rotates a joint about itself).
    Blender's Active Element pivot of an edit bone is its middle, so the Edit Armature pivot is the 3D cursor kept on
    the lead joint (pivot.MAYA_PIVOT_POINT; the Maya layout doesn't draw the cursor). Called on a pick and from
    tool_keys' 0.25 s watch (the joint moves with W)."""
    ob = context.active_object
    if ob is None or ob.type != 'ARMATURE' or ob.mode != 'EDIT':
        return False
    eb = ob.data.edit_bones.active
    if eb is None or not eb.select:
        return False
    from .pivot import MAYA_PIVOT_POINT
    ts = context.scene.tool_settings
    if ts.transform_pivot_point != 'CURSOR' and ts.transform_pivot_point in {*MAYA_PIVOT_POINT.values(), 'MEDIAN_POINT'}:
        # only from a Maya pivot value (or Blender's default Median), and put back when Edit Armature ends (restore_joint_pivot): a user's cursor
        # pivot in mesh editing is never touched (test_step59_pivot_snap)
        _PIVOT["prev"] = ts.transform_pivot_point
        ts.transform_pivot_point = 'CURSOR'
    head = ob.matrix_world @ eb.head
    cursor = context.scene.cursor
    if (cursor.location - head).length > 1e-9:
        cursor.location = head
    return True


_PIVOT = {"prev": None}


def restore_joint_pivot(context):
    """Outside Edit Armature mode, give back the pivot sync_joint_pivot replaced. tool_keys watch."""
    prev = _PIVOT["prev"]
    if prev is None or context.mode == 'EDIT_ARMATURE':
        return False
    _PIVOT["prev"] = None
    ts = context.scene.tool_settings
    if ts.transform_pivot_point == 'CURSOR':
        ts.transform_pivot_point = prev
        return True
    return False


def _subtree(bone):
    return [bone, *bone.children_recursive]


def _edit_selected(eb):
    return eb.select and eb.select_head and eb.select_tail


def _set_edit(eb, state):
    eb.select = eb.select_head = eb.select_tail = state


def _edit_picked(ob):
    """Picked joints in Edit mode: bones whose head is selected and whose parent isn't wholly selected (a picked joint
    is its whole subtree, or only its head with Preserve Children)."""
    return [eb for eb in ob.data.edit_bones if eb.select_head
            and (_edit_selected(eb) or not eb.select_tail)
            and not (eb.parent is not None and _edit_selected(eb.parent))]


def _pick_shape(eb, state, preserve):
    """Select joint ``eb`` for W: its bone and subtree, or (Maya Preserve Children) only its head, so the
    children stay — a connected head is the parent's tail point."""
    if not preserve:
        for b in _subtree(eb):
            _set_edit(b, state)
        return
    eb.select_head = state
    eb.select = eb.select_tail = False
    if eb.use_connect and eb.parent is not None and not _edit_selected(eb.parent):
        eb.parent.select_tail = state


def reshape(context, ob, preserve):
    """Re-select the picked joints of ``ob`` (edit mode) in the subtree / head-only shape; the active stays."""
    if ob is None or ob.type != 'ARMATURE' or ob.mode != 'EDIT':
        return False
    ebs = ob.data.edit_bones
    picked = [eb.name for eb in _edit_picked(ob)]
    active = ebs.active
    for eb in ebs:
        _set_edit(eb, False)
    for name in picked:
        _pick_shape(ebs[name], True, preserve)
    ebs.active = active
    return bool(picked)


def select_edit(context, ob, name, shift=False, ctrl=False):
    """Maya replace / toggle / subtract / add on joints of a skeleton in Edit mode: a picked joint selects its bone
    and the subtree below it (W moves them together, like Maya's children following their parent)."""
    if context.mode != 'OBJECT' and (context.active_object != ob or ob.mode != 'EDIT'):
        bpy.ops.object.mode_set(mode='OBJECT')
    if not shift and not ctrl:
        clear(context)
        for other in context.selected_objects:
            if other != ob:
                other.select_set(False)
    ob.select_set(True)
    context.view_layer.objects.active = ob
    if ob.mode != 'EDIT':
        bpy.ops.object.mode_set(mode='EDIT')
        if not shift and not ctrl:
            for eb in ob.data.edit_bones:
                _set_edit(eb, False)
    ebs = ob.data.edit_bones
    eb = ebs[name]
    from .joint_edit import preserve_children
    preserve = preserve_children(context)
    selected = eb.select_head and (_edit_selected(eb) or preserve)
    remove = (ctrl and not shift) or (shift and not ctrl and selected)
    if not shift and not ctrl:
        for other in ebs:
            _set_edit(other, False)
    _pick_shape(eb, not remove, preserve)
    if remove:
        if ebs.active == eb:
            picked = _edit_picked(ob)
            ebs.active = picked[-1] if picked else None
        if not _edit_picked(ob):
            bpy.ops.object.mode_set(mode='OBJECT')
            ob.select_set(False)
            if context.view_layer.objects.active == ob:
                context.view_layer.objects.active = next(iter(context.selected_objects), None)
        return False
    ebs.active = eb
    sync_joint_pivot(context)
    return True


def select(context, ob, name, shift=False, ctrl=False):
    """Maya replace / toggle / subtract / add on individual joints."""
    # a bone with a custom shape is a control (control = bone Custom Shape), not a Maya joint: picking it
    # keeps Pose mode with the Move tool too (#171: an unkeyed Rigify rig went to Edit mode on a W click)
    control = name in ob.pose.bones and ob.pose.bones[name].custom_shape is not None
    if ob.get(MOVE_SKINNED) or (joint_mode(ob) == 'EDIT' and not control and not ob.get(POSE_PIN)
                                and move_tool_active(context)):
        r = select_edit(context, ob, name, shift, ctrl)
        if not ob.get(MOVE_SKINNED) and ob.mode == 'EDIT':
            ob[AUTO_EDIT] = True
        return r
    from ..ui.channel_box import bone_selected, set_bone_selected
    pb = ob.pose.bones[name]
    selected = bone_selected(pb)
    remove = (ctrl and not shift) or (shift and not ctrl and selected)
    if remove:
        set_bone_selected(pb, False)
        if ob.data.bones.active == pb.bone:
            ob.data.bones.active = next((b.bone for b in ob.pose.bones if bone_selected(b)), None)
        if not any(bone_selected(b) for b in ob.pose.bones):
            if context.active_object == ob and ob.mode == 'POSE':
                bpy.ops.object.mode_set(mode='OBJECT')
            ob.select_set(False)
            if context.view_layer.objects.active == ob:
                context.view_layer.objects.active = next(iter(context.selected_objects), None)
        return False
    if context.mode != 'OBJECT' and context.active_object != ob:
        bpy.ops.object.mode_set(mode='OBJECT')
    if not shift and not ctrl:
        clear(context)
        for other in context.selected_objects:
            if other != ob:
                other.select_set(False)
    ob.select_set(True)
    context.view_layer.objects.active = ob
    if ob.mode != 'POSE':
        bpy.ops.object.mode_set(mode='POSE')
    set_bone_selected(ob.pose.bones[name], True)
    ob.data.bones.active = ob.data.bones[name]
    return True


def leave(context, clear_selection=False):
    if clear_selection:
        clear(context)
    if context.mode != 'OBJECT' and context.active_object is not None:
        bpy.ops.object.mode_set(mode='OBJECT')


def select_object_at(context, mouse, shift=False, ctrl=False):
    """Native object picking after releasing Blender's pose/edit selection lock."""
    leave(context, clear_selection=not (shift or ctrl))
    result = bpy.ops.view3d.select(location=tuple(map(int, mouse)),
                                  deselect_all=not (shift or ctrl),
                                  toggle=shift and not ctrl,
                                  deselect=ctrl and not shift,
                                  extend=shift and ctrl)
    if not context.selected_objects:
        context.view_layer.objects.active = None
    return result
