# SPDX-License-Identifier: GPL-3.0-or-later
"""Control > Tag As Controller / Parent Controller on bones.

Maya's ``controller`` command (menu Tag As Controller) tags nodes as controllers with
an empty parent controller; ``cmds.controller(parent=True)`` (Parent Controller) makes the last selected node the
parent controller of the others. Pick walk then follows the controller hierarchy
(tags alone leave the parent empty, so j3 Up still reaches the hidden j2 until Parent Controller).

Kit translation: a controller tag is the data Bone ID property ``allset_controller`` (True), the parent controller
``allset_controller_parent`` (a bone name in the same armature). Only pose bones carry tags: objects are walked by
Blender's own hierarchy. Walk rules: ``operators/joints.walk_bone``.
"""

import bpy

from .. import results
from .joints import CONTROLLER, CONTROLLER_PARENT

MSG_SELECT = "Select the joints or controls in Pose mode to tag them as controllers."
MSG_PARENT = "Select the child controls, then the parent control last (Pose mode)."


def _cb():
    from ..ui import channel_box
    return channel_box


def _pose_bones(context):
    cb = _cb()
    if cb.pose_armature(context) is None:
        return []
    return [pb for pb in cb.targets(context) if isinstance(pb, bpy.types.PoseBone)]


def tag(bones):
    """Tag data Bones as controllers (the parent controller is left as it is). Returns the count."""
    for b in bones:
        b[CONTROLLER] = True
    return len(bones)


def _controller_ancestors(bone):
    seen, cur = set(), bone
    while cur is not None and cur.name not in seen:
        seen.add(cur.name)
        name = cur.get(CONTROLLER_PARENT)
        cur = cur.id_data.bones.get(name) if name else None
    return seen


def parent_controllers(parent, children):
    """Maya ``cmds.controller(parent=True)``: ``parent`` becomes the parent controller of ``children`` (all tagged).

    Children of another armature or that would make a loop are skipped. Returns the number parented."""
    tag([parent])
    above = _controller_ancestors(parent)
    n = 0
    for b in children:
        if b.id_data != parent.id_data or b.name in above:
            continue
        tag([b])
        b[CONTROLLER_PARENT] = parent.name
        n += 1
    return n


class ALLSET_OT_tag_controller(bpy.types.Operator):
    """Tag the selected joints / controls as controllers: pick walk (arrow keys) then follows controllers (Maya)"""
    bl_idname = "allset.tag_controller"
    bl_label = "Tag As Controller"
    bl_options = {'UNDO'}

    def execute(self, context):
        pbs = _pose_bones(context)
        if not pbs:
            self.report({'WARNING'}, MSG_SELECT)
            return {'CANCELLED'}
        n = tag([pb.bone for pb in pbs])
        results.result(self, f"Tagged {n} controller(s)")
        return {'FINISHED'}


class ALLSET_OT_parent_controller(bpy.types.Operator):
    """Make the last selected control the parent controller of the other selected controls (Maya controller -p)"""
    bl_idname = "allset.parent_controller"
    bl_label = "Parent Controller"
    bl_options = {'UNDO'}

    def execute(self, context):
        cb = _cb()
        pbs = _pose_bones(context)
        lead = cb.lead(context) if pbs else None
        others = [pb for pb in pbs if pb != lead]
        if lead is None or not isinstance(lead, bpy.types.PoseBone) or not others:
            self.report({'WARNING'}, MSG_PARENT)
            return {'CANCELLED'}
        n = parent_controllers(lead.bone, [pb.bone for pb in others])
        results.result(self, f"Parented {n} controller(s) to {lead.name}")
        return {'FINISHED'}


classes = (ALLSET_OT_tag_controller, ALLSET_OT_parent_controller)
