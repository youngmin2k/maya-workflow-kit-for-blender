# SPDX-License-Identifier: GPL-3.0-or-later
"""Joint display with Maya's controls (Issue #165): the Channel Box Radius row, Display > Transform Display >
Local Rotation Axes, Display > Animation > Joint Size....

- Radius = the Maya joint radius the kit keeps on each bone (``joints.RADIUS``, Maya units; a joint without one reads
  the default 1). It sizes the joint's click sphere (``joints.joint_sphere_radius``).
- Joint Size = Maya's scene-wide jointDisplayScale (default 1) as ``Scene.allset_joint_size``: it scales every joint's
  click sphere. Blender draws a bone's size from its length only, so the drawn joints keep their size.
- Local Rotation Axes: Maya toggles the selected nodes' displayLocalAxis. Blender shows bone axes per skeleton
  (``Armature.show_axes``) and object axes per object (``Object.show_axis``).
"""

import bpy
from bpy.props import FloatProperty

from .. import results
from . import joints

JOINT_SIZE = "allset_joint_size"
MAYA_RADIUS = 1.0          # Maya joint.radius default


def _get_radius(bone):
    return float(bone.get(joints.RADIUS, MAYA_RADIUS))


def _set_radius(bone, value):
    bone[joints.RADIUS] = max(0.0, float(value))


class ALLSET_OT_local_rotation_axes(bpy.types.Operator):
    """Maya Display > Transform Display > Local Rotation Axes: show / hide the axes of the selected joints or objects"""
    bl_idname = "allset.local_rotation_axes"
    bl_label = "Local Rotation Axes"
    bl_options = {'UNDO'}

    def execute(self, context):
        ob = context.active_object
        if ob is not None and ob.type == 'ARMATURE' and ob.mode in {'POSE', 'EDIT'}:
            arms = [o for o in (getattr(context, "objects_in_mode", None) or [ob]) if o.type == 'ARMATURE']
            on = not ob.data.show_axes
            for arm in arms:
                arm.data.show_axes = on
            results.result(self, f"Joint axes {'on' if on else 'off'}")
            return {'FINISHED'}
        obs = list(context.selected_objects) or ([ob] if ob is not None else [])
        if not obs:
            self.report({'WARNING'}, "Select objects or joints")
            return {'CANCELLED'}
        on = not (ob.show_axis if ob is not None else obs[0].show_axis)
        for o in obs:
            o.show_axis = on
        results.result(self, f"Local rotation axes {'on' if on else 'off'}")
        return {'FINISHED'}


class ALLSET_OT_joint_size(bpy.types.Operator):
    """Maya Display > Animation > Joint Size: the scene's joint display scale (sizes the joints' click spheres)"""
    bl_idname = "allset.joint_size"
    bl_label = "Joint Display Scale"
    bl_options = {'UNDO'}

    size: FloatProperty(name="Joint Size", default=1.0, min=0.01, max=100.0, soft_max=10.0)

    def invoke(self, context, event):
        self.size = getattr(context.scene, JOINT_SIZE, 1.0)
        return context.window_manager.invoke_props_dialog(self, width=300, confirm_text="Close")

    def draw(self, context):
        self.layout.prop(self, "size")
        self.layout.label(text="Blender draws joints by bone length: this sizes where a click picks them.")

    def execute(self, context):
        setattr(context.scene, JOINT_SIZE, self.size)
        results.result(self, f"Joint Size {self.size:g}")
        return {'FINISHED'}


classes = (ALLSET_OT_local_rotation_axes, ALLSET_OT_joint_size)


def register_props():
    bpy.types.Bone.allset_joint_radius = FloatProperty(
        name="Radius", description="Maya joint radius (sizes the joint's click sphere)", min=0.0, soft_max=100.0,
        get=_get_radius, set=_set_radius)
    bpy.types.Scene.allset_joint_size = FloatProperty(
        name="Joint Size", description="Maya joint display scale", default=1.0, min=0.01, max=100.0)


def unregister_props():
    for owner, name in ((bpy.types.Bone, "allset_joint_radius"), (bpy.types.Scene, "allset_joint_size")):
        if hasattr(owner, name):
            delattr(owner, name)
