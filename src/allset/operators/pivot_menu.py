# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya pivot-edit RMB marking menu actions (docs/steps/step_94.md 「계획」 1).

RMB held while editing a pivot (D / Insert) shows RMB_EMPTY's pivot-edit menu
(research/maya/marking_menus.json menus.RMB_EMPTY; research/maya/interaction.md:81, :127-130):
Pin Component Pivot / Snap Pivot Position / Snap Pivot Orientation are Move tool options (check boxes, Maya defaults
off / on / on, research/maya/workflows/pivot_snap.md P13), Reset Pivot (Position / Orientation) and Exit are commands.
Object pivot edit = ``tool_settings.use_transform_data_origin`` (operators/pivot.py), component pivot edit =
``hold.COMPONENT`` (the 3D cursor is the pivot, step 77).
"""

import bpy
from bpy.props import BoolProperty, EnumProperty

# (option, WindowManager property, Maya default)
OPTIONS = (("PIN", "allset_pin_pivot", False), ("SNAP_POS", "allset_snap_pivot_pos", True),
           ("SNAP_ORI", "allset_snap_pivot_ori", True))
_PROP = {o: p for o, p, _d in OPTIONS}


def option(name, context=None):
    """Current value of a pivot option (Maya default when the property isn't there)."""
    context = context or bpy.context
    prop = _PROP[name]
    default = next(d for o, _p, d in OPTIONS if o == name)
    return bool(getattr(context.window_manager, prop, default))


def pivot_editing(context):
    """True while a pivot is being edited: objects (D / Insert) or components (hold.COMPONENT)."""
    from . import hold
    if context.mode == hold.EDIT_MODE:
        return hold.COMPONENT.on
    scene = getattr(context, "scene", None)
    return context.mode == 'OBJECT' and scene is not None and scene.tool_settings.use_transform_data_origin


class ALLSET_OT_pivot_option(bpy.types.Operator):
    """Turn a Move tool pivot option on or off (Maya pivot edit RMB menu check box)"""
    bl_idname = "allset.pivot_option"
    bl_label = "Pivot Option"
    bl_options = {'REGISTER'}

    option: EnumProperty(items=(("PIN", "Pin Component Pivot", "The custom component pivot stays when the selection "
                                 "changes"),
                                ("SNAP_POS", "Snap Pivot Position", "Clicking a component puts the pivot on it"),
                                ("SNAP_ORI", "Snap Pivot Orientation", "Clicking a component orients the pivot to it")))

    def execute(self, context):
        from . import hold
        wm = context.window_manager
        prop = _PROP[self.option]
        setattr(wm, prop, not option(self.option, context))
        if self.option != "PIN" and hold.COMPONENT.on:
            hold.apply_cursor_options(context)
        return {'FINISHED'}


class ALLSET_OT_pivot_reset(bpy.types.Operator):
    """Put the pivot back: objects on their own origin, components on the selection's centre (Maya Reset Pivot)"""
    bl_idname = "allset.pivot_reset"
    bl_label = "Reset Pivot"
    bl_options = {'REGISTER', 'UNDO'}

    position: BoolProperty(name="Position", default=True, options={'SKIP_SAVE'})
    orientation: BoolProperty(name="Orientation", default=True, options={'SKIP_SAVE'})

    def execute(self, context):
        from . import hold
        if context.mode == hold.EDIT_MODE:
            hold.COMPONENT.reset(context, self.position, self.orientation)
            return {'FINISHED'}
        if not bpy.ops.allset.reset_pivot.poll():      # no selected object in Object Mode: no pivot to put back
            return {'CANCELLED'}
        return bpy.ops.allset.reset_pivot(position=self.position, orientation=self.orientation)


class ALLSET_OT_pivot_exit(bpy.types.Operator):
    """Leave pivot edit (Maya pivot edit RMB menu > Exit)"""
    bl_idname = "allset.pivot_exit"
    bl_label = "Exit Pivot Edit"
    bl_options = {'REGISTER'}

    def execute(self, context):
        from . import hold
        if context.mode == hold.EDIT_MODE:
            hold.COMPONENT.finish(context)
        elif context.scene.tool_settings.use_transform_data_origin:
            hold.toggle_object_pivot(context.scene.tool_settings)
        hold._redraw()
        return {'FINISHED'}


classes = (ALLSET_OT_pivot_option, ALLSET_OT_pivot_reset, ALLSET_OT_pivot_exit)


def register_props():
    wm = bpy.types.WindowManager
    for name, prop, default in OPTIONS:
        setattr(wm, prop, BoolProperty(name=name.replace("_", " ").title(), default=default, options={'SKIP_SAVE'}))


def unregister_props():
    wm = bpy.types.WindowManager
    for _name, prop, _default in OPTIONS:
        if hasattr(wm, prop):
            delattr(wm, prop)
