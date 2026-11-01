# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya's Transform Constraint for the Move tool in mesh edit mode.

Edge: dragging a Move handle (or MMB anywhere) slides the selection along its edges — vertices with Blender's
Vertex Slide, edges / faces with Edge Slide (Vertex Slide when Blender finds no edge loop to slide). Surface:
the drag moves the selection with each point snapped to the nearest surface of the mesh. Along Normals: the drag
moves each point along its own normal (Blender's Shrink / Fatten). Off: the Move tool as before. Ctrl+Shift+MMB slides along edges whatever the setting (Maya's quick edge slide).
"""
import bpy

MODES = (('NONE', "Off", "Move components freely"),
         ('EDGE', "Edge Slide", "Slide components along their edges"),
         ('SURFACE', "Surface Slide", "Move components along the surface of the mesh"),
         ('NORMAL', "Along Normals", "Move each component along its own normal"))


def mode(context):
    from .. import preferences
    try:
        return preferences.get(context).transform_constraint
    except AttributeError:
        return 'NONE'


def active(context):
    """The Move tool slides instead of moving (mesh edit mode, Maya mode, a constraint set)."""
    from .. import preferences
    try:
        prefs = preferences.get(context)
    except AttributeError:
        return False
    if context.mode != 'EDIT_MESH' or not prefs.maya_mode or prefs.transform_constraint == 'NONE':
        return False
    from . import hold
    return not hold.COMPONENT.on


def vertex_only(select_mode):
    """Vertex select mode alone: vertices slide on their own (Vertex Slide)."""
    return bool(select_mode[0]) and not select_mode[1] and not select_mode[2]


def slide(context, kind, release_confirm=True):
    """Start the slide drag (INVOKE). Returns the operator result set."""
    if kind == 'NORMAL':
        return bpy.ops.transform.shrink_fatten('INVOKE_DEFAULT', release_confirm=release_confirm)
    if kind == 'SURFACE':
        return bpy.ops.transform.translate('INVOKE_DEFAULT', release_confirm=release_confirm, snap=True,
                                           snap_elements={'FACE_NEAREST'}, snap_target='CLOSEST',
                                           use_snap_self=True, use_snap_edit=True, use_snap_nonedit=True)
    if not vertex_only(context.tool_settings.mesh_select_mode):
        try:
            res = bpy.ops.transform.edge_slide('INVOKE_DEFAULT', release_confirm=release_confirm)
        except RuntimeError:
            res = {'CANCELLED'}
        if res & {'RUNNING_MODAL', 'FINISHED'}:
            return res
    return bpy.ops.transform.vert_slide('INVOKE_DEFAULT', release_confirm=release_confirm)


class ALLSET_OT_xform_constraint(bpy.types.Operator):
    """Set the Move tool's Transform Constraint (Off / Edge Slide / Surface Slide / Along Normals)"""
    bl_idname = "allset.xform_constraint"
    bl_label = "Transform Constraint"
    bl_options = {'INTERNAL'}

    mode: bpy.props.EnumProperty(items=MODES, default='NONE', options={'SKIP_SAVE'})

    def execute(self, context):
        from .. import preferences
        preferences.get(context).transform_constraint = self.mode
        from . import hold
        hold._redraw()
        return {'FINISHED'}


class ALLSET_OT_component_slide(bpy.types.Operator):
    """Slide the selected components along their edges or the surface (Maya Transform Constraint)"""
    bl_idname = "allset.component_slide"
    bl_label = "Slide Components"
    bl_options = {'INTERNAL'}

    mode: bpy.props.EnumProperty(items=(('AUTO', "Setting", "Use the Transform Constraint setting"),) + MODES[1:],
                                 default='AUTO', options={'SKIP_SAVE'})
    release_confirm: bpy.props.BoolProperty(default=True, options={'HIDDEN', 'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        return context.mode == 'EDIT_MESH' and context.area is not None and context.area.type == 'VIEW_3D'

    def invoke(self, context, _event):
        kind = mode(context) if self.mode == 'AUTO' else self.mode
        if kind == 'NONE':
            return {'PASS_THROUGH'}
        try:
            res = slide(context, kind, self.release_confirm)
        except RuntimeError:
            return {'CANCELLED'}
        return {'FINISHED'} if res & {'RUNNING_MODAL', 'FINISHED'} else {'CANCELLED'}

    def execute(self, context):
        return {'CANCELLED'}


classes = (ALLSET_OT_xform_constraint, ALLSET_OT_component_slide)
