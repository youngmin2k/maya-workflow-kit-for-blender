# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya's Pose Editor window (Issue #137).

Maya: Windows > Animation Editors > Pose Editor / Deform > Pose Space Deformation > Pose Editor — pose interpolators on
the left, the current interpolator's poses on the right (Add Pose, Add Shape, Edit, Go to Pose, Delete, the pose
weights). The kit's layout = toolbar row, then two columns
(interpolators | poses with their read-only weight), then the interpolation (Linear; Gaussian greyed with a notice).
Logic in ``operators/pose_space_227.py``; the window is ``marked_window`` kind POSE_EDITOR.
"""

import bpy

from . import marked_window

KIND = "POSE_EDITOR"

# greyed rows (notices.PANEL_NOTICES while registered; drawn through allset.menu_unavailable)
NOTICES = {
    "Pose Editor/Interpolation/Gaussian": (
        "Linear", "The kit's pose weights are Maya's Linear interpolation (a shape key driver per pose); Blender "
        "drivers can't solve Maya's Gaussian RBF."),
}


def _ps():
    from ..operators import pose_space_227
    return pose_space_227


def redraw(context):
    marked_window.redraw(context, KIND)


def _grey(layout, key, text):
    row = layout.row()
    row.enabled = False
    row.operator("allset.menu_unavailable", text=text, emboss=False).item = key


def draw_toolbar(layout, context):
    ps = _ps()
    interp, pose = ps.current(context)
    row = layout.row(align=True)
    row.operator("allset.pose_interpolator_create", text="Create Pose Interpolator")
    sub = row.row(align=True)
    sub.enabled = interp is not None
    op = sub.operator("allset.pose_add", text="Add Pose")
    op.interpolator = interp.name if interp is not None else ""
    for idname, text in (("allset.pose_add_shape", "Add Shape"), ("allset.pose_go", "Go to Pose"),
                         ("allset.pose_delete", "Delete")):
        op = sub.operator(idname, text=text)
        op.interpolator = interp.name if interp is not None else ""
        op.pose = pose


def draw_lists(layout, context):
    ps = _ps()
    interp, pose = ps.current(context)
    split = layout.split(factor=0.4)
    left = split.column(align=True)
    left.label(text="Pose Interpolators")
    box = left.box().column(align=True)
    items = ps.interpolators()
    if not items:
        box.label(text="Select a joint, then Create Pose Interpolator")
    for ob in items:
        op = box.operator("allset.pose_pick", text=ob.name, depress=(ob == interp and not pose), emboss=True,
                          icon='DRIVER')
        op.interpolator, op.pose = ob.name, ""
    right = split.column(align=True)
    right.label(text="Poses" + (f" ({interp.name})" if interp is not None else ""))
    box = right.box().column(align=True)
    if interp is None:
        return
    arm, pb = ps.driver_of(interp)
    box.label(text=f"Driver: {pb.name if pb is not None else '(missing)'}", icon='BONE_DATA')
    head = box.row()
    head.label(text="Pose")
    head.label(text="Weight")
    head.label(text="Shape")
    for name in [ps.NEUTRAL, *ps.poses(interp)]:
        row = box.row(align=True)
        op = row.operator("allset.pose_pick", text=name, depress=(name == pose))
        op.interpolator, op.pose = interp.name, name
        row.label(text="" if name == ps.NEUTRAL else f"{ps.weight(interp, name):.3f}")
        if name == ps.NEUTRAL:
            row.label(text="")
            continue
        shapes = ps.shapes_of(interp, name)
        if shapes:
            op = row.operator("allset.pose_edit", text="Edit", depress=ps.editing(interp, name) is not None)
        else:
            op = row.operator("allset.pose_add_shape", text="Add Shape")
        op.interpolator, op.pose = interp.name, name


def draw_settings(layout, context):
    ps = _ps()
    interp, _pose = ps.current(context)
    if interp is None:
        return
    row = layout.row(align=True)
    row.label(text="Interpolation")
    row.operator("allset.pose_pick", text="Linear", depress=True).interpolator = interp.name
    _grey(row, "Pose Editor/Interpolation/Gaussian", "Gaussian")
    axis = ("X", "Y", "Z")[int(interp.get(ps.P_AXIS, 0))]
    layout.label(text=f"Driver twist axis: {axis}")


class ALLSET_PT_pose_editor(bpy.types.Panel):
    """Maya's Pose Editor (a marked Properties Tool tab in its own window)"""
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Tool"            # = drawn by the Properties Tool tab (like Tool Settings)
    bl_label = "Pose Editor"
    bl_options = {'HIDE_HEADER'}
    bl_order = -300

    @classmethod
    def poll(cls, context):
        return marked_window.context_kind(context) == KIND

    def draw(self, context):
        layout = self.layout
        draw_toolbar(layout, context)
        draw_lists(layout, context)
        draw_settings(layout, context)
        layout.operator("allset.marked_window_close", text="Close")


classes = (ALLSET_PT_pose_editor,)
