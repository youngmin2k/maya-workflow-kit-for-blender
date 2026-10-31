# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya pivot-edit RMB marking menu actions.

RMB held while editing a pivot (D / Insert) shows RMB_EMPTY's pivot-edit menu:
Pin Component Pivot / Snap Pivot Position / Snap Pivot Orientation are Move tool options (check boxes, off / on / on
by default, like Maya), Reset Pivot (Position / Orientation) and Exit are commands.
Object pivot edit = ``tool_settings.use_transform_data_origin`` (operators/pivot.py), component pivot edit =
``hold.COMPONENT`` (the 3D cursor is the pivot).
"""

import bpy
from bpy.props import BoolProperty, EnumProperty

# (option, WindowManager property, default like Maya)
OPTIONS = (("PIN", "allset_pin_pivot", False), ("SNAP_POS", "allset_snap_pivot_pos", True),
           ("SNAP_ORI", "allset_snap_pivot_ori", True))
_PROP = {o: p for o, p, _d in OPTIONS}
# Where Reset Pivot Position puts an object pivot: the bounding box centre (default, like Maya) or the object's
# own origin (Zero Position on Reset). Components always go back to the selection's centre.
RESET_MODES = ("RESET_CENTER", "RESET_ZERO")
RESET_PROP = "allset_pivot_reset_zero"


def option(name, context=None):
    """Current value of a pivot option (the default, like Maya, when the property isn't there)."""
    context = context or bpy.context
    if name in RESET_MODES:
        return getattr(context.window_manager, RESET_PROP, False) == (name == "RESET_ZERO")
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
                                ("SNAP_ORI", "Snap Pivot Orientation", "Clicking a component orients the pivot to it"),
                                ("RESET_CENTER", "Center Position on Reset", "Reset Pivot Position puts an object "
                                 "pivot on the centre of its bounding box"),
                                ("RESET_ZERO", "Zero Position on Reset", "Reset Pivot Position puts an object pivot "
                                 "on the object's own origin")))

    def execute(self, context):
        from . import hold
        wm = context.window_manager
        if self.option in RESET_MODES:          # a pair of radio items: picking one sets it
            setattr(wm, RESET_PROP, self.option == "RESET_ZERO")
            return {'FINISHED'}
        prop = _PROP[self.option]
        setattr(wm, prop, not option(self.option, context))
        if self.option != "PIN" and hold.COMPONENT.on:
            hold.apply_cursor_options(context)
        return {'FINISHED'}


class ALLSET_OT_pivot_reset(bpy.types.Operator):
    """Put the pivot back: objects on their bounding box centre (or their own origin with Zero Position on Reset),
    components on the selection's centre (Maya Reset Pivot)"""
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
        if self.position and not option("RESET_ZERO", context):
            from . import freeze
            obs = list(context.selected_objects)
            if self.orientation:
                bpy.ops.allset.reset_pivot(position=False, orientation=True)
            freeze.center_pivot(context, obs)
            return {'FINISHED'}
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


CUSTOM_AXIS = "Custom"
_DEFAULT_AXIS = {1: 'GLOBAL', 2: 'LOCAL', 3: 'LOCAL'}     # Move = World, Rotate / Scale = Object, like Maya


class ALLSET_OT_custom_axis(bpy.types.Operator):
    """Maya Custom axis of the Move / Rotate / Scale tool (tool option marking menu > Custom): set it from the
    selection or the object, use it, or reset the tool to its default axis"""
    bl_idname = "allset.custom_axis"
    bl_label = "Custom Axis"
    bl_options = {'REGISTER', 'UNDO'}

    slot: bpy.props.IntProperty(min=1, max=3, default=1, options={'SKIP_SAVE'})
    action: EnumProperty(items=(("SELECTION", "Set to Selection", "Axis from the selected components (or object)"),
                                ("OBJECT", "Set to Object", "Axis of the active object"),
                                ("USE", "Custom", "Use the custom axis"),
                                ("RESET", "Reset", "Back to the tool's default axis")), options={'SKIP_SAVE'})

    def execute(self, context):
        from . import pivot
        scene = context.scene
        slot = scene.transform_orientation_slots[self.slot]
        if self.action == "RESET":
            slot.type = _DEFAULT_AXIS[self.slot]
            return {'FINISHED'}
        if self.action == "USE":
            try:
                slot.type = CUSTOM_AXIS
            except TypeError:
                self.report({'WARNING'}, "No custom axis is set: use Set to Component or Set To Object first.")
                return {'CANCELLED'}
            return {'FINISHED'}
        window, area, region = pivot._find_view3d(context)
        kw = {"window": window, "area": area, "region": region} if area is not None else {}
        main = scene.transform_orientation_slots[0]
        prev = main.type
        try:
            with context.temp_override(**kw):
                bpy.ops.transform.create_orientation(name=CUSTOM_AXIS, use=True, overwrite=True)
        except RuntimeError:
            self.report({'WARNING'}, "Select a component or an object to take the axis from.")
            return {'CANCELLED'}
        custom = main.custom_orientation
        ob = context.active_object
        if self.action == "OBJECT" and custom is not None and ob is not None:
            custom.matrix = ob.matrix_world.to_3x3().normalized()
        main.type = prev
        slot.type = CUSTOM_AXIS
        return {'FINISHED'}


classes = (ALLSET_OT_pivot_option, ALLSET_OT_pivot_reset, ALLSET_OT_pivot_exit, ALLSET_OT_custom_axis)


def register_props():
    wm = bpy.types.WindowManager
    for name, prop, default in OPTIONS:
        setattr(wm, prop, BoolProperty(name=name.replace("_", " ").title(), default=default, options={'SKIP_SAVE'}))
    wm.allset_pivot_reset_zero = BoolProperty(name="Zero Position on Reset", default=False, options={'SKIP_SAVE'})


def unregister_props():
    wm = bpy.types.WindowManager
    for prop in [p for _n, p, _d in OPTIONS] + [RESET_PROP]:
        if hasattr(wm, prop):
            delattr(wm, prop)
