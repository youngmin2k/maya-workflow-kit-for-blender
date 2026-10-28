# SPDX-License-Identifier: GPL-3.0-or-later
"""Rotate the custom pivot's frame directly so its arrows follow during the drag.

Maya's combined custom-pivot manipulator edits a frame, not the object's rotation.
Keeping this as pivot metadata avoids a delayed origin-transform rewrite and keeps
geometry, children and transform channels unchanged throughout the gesture.
"""
import math

import bpy
from bpy_extras import view3d_utils
from mathutils import Matrix, Vector

from . import hold, pivot


class ALLSET_OT_pivot_rotate(bpy.types.Operator):
    """Rotate the pivot axes live without rotating the object"""
    bl_idname = "allset.pivot_rotate"
    bl_label = "Rotate Custom Pivot"
    bl_options = {'REGISTER', 'UNDO', 'BLOCKING'}

    axis: bpy.props.EnumProperty(items=tuple((a, a, "") for a in 'XYZ'))
    angle: bpy.props.FloatProperty(name="Angle", subtype='ANGLE')

    @classmethod
    def poll(cls, context):
        return (pivot.pivot_mode(context) and context.active_object is not None
                and bool(context.selected_objects))

    def _capture(self, context):
        self._frame = pivot.axes_for(context.active_object)
        self._axis = self._frame.col['XYZ'.index(self.axis)].normalized()
        self._origin = context.active_object.matrix_world.translation.copy()
        self._objects = {ob.name: (tuple(ob[pivot.PROP]) if pivot.PROP in ob else None, pivot.axes_for(ob))
                         for ob in context.selected_objects}
        self._slot_types = tuple(slot.type for slot in context.scene.transform_orientation_slots)
        orientation = pivot._orientation(context.scene)
        self._previous_axes = orientation.matrix.copy() if orientation is not None else None
        self._step_held, self._baseline_step = hold.step_state(context.tool_settings, 'ROTATE')

    def _drag_value(self, context, event):
        angle = self._drag_angle
        if self._step_held or (self._baseline_step != event.ctrl):
            increment = context.tool_settings.snap_angle_increment_3d
            if increment > 1e-6:
                angle = round(angle/increment)*increment
        return angle

    def _apply(self, context, angle):
        self.angle = angle
        delta = Matrix.Rotation(angle, 3, self._axis)
        for name, (_saved, frame) in self._objects.items():
            ob = bpy.data.objects.get(name)
            if ob is not None:
                ob[pivot.PROP] = tuple(ob.matrix_world.to_quaternion().inverted() @ (delta @ frame).to_quaternion())
        pivot.set_custom_orientation(context, delta @ self._frame)
        hold._redraw()

    def _restore(self, context):
        for name, (saved, _frame) in self._objects.items():
            ob = bpy.data.objects.get(name)
            if ob is None:
                continue
            if saved is None:
                if pivot.PROP in ob:
                    del ob[pivot.PROP]
            else:
                ob[pivot.PROP] = saved
        orientation = pivot._orientation(context.scene)
        if orientation is not None:
            if self._previous_axes is not None:
                orientation.matrix = self._previous_axes
            else:
                context.scene.transform_orientation_slots[0].type = pivot.ORIENT_NAME
                bpy.ops.transform.delete_orientation()
        for slot, saved in zip(context.scene.transform_orientation_slots, self._slot_types):
            slot.type = saved
        hold._redraw()

    def _vector(self, context, event):
        mouse = (event.mouse_region_x, event.mouse_region_y)
        origin = view3d_utils.region_2d_to_origin_3d(context.region, context.region_data, mouse)
        direction = view3d_utils.region_2d_to_vector_3d(context.region, context.region_data, mouse)
        denominator = direction.dot(self._axis)
        if abs(denominator) < 1e-5:
            return None
        vector = origin + direction*((self._origin-origin).dot(self._axis)/denominator) - self._origin
        return vector.normalized() if vector.length > 1e-6 else None

    def execute(self, context):
        self._capture(context)
        self._apply(context, self.angle)
        return {'FINISHED'}

    def invoke(self, context, event):
        self._capture(context)
        self._last = self._vector(context, event)
        self._mouse = (event.mouse_region_x, event.mouse_region_y)
        self._drag_angle = 0.0
        self._text = ""
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type in {'ESC', 'RIGHTMOUSE'} and event.value == 'PRESS':
            self._restore(context)
            return {'CANCELLED'}
        if event.type in {'RET', 'NUMPAD_ENTER'} and event.value == 'PRESS':
            return {'FINISHED'}
        if event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
            return {'FINISHED'}
        if event.type == 'D':
            # Like a native transform, consume D until the gesture ends. The
            # hold timer restores temporary pivot mode after the mouse release.
            return {'RUNNING_MODAL'}
        if event.type == 'J' and event.value in {'PRESS', 'RELEASE'}:
            if not event.is_repeat:
                self._step_held = event.value == 'PRESS'
                if not self._text:
                    self._apply(context, self._drag_value(context, event))
            return {'RUNNING_MODAL'}
        if event.type == 'MOUSEMOVE':
            mouse = (event.mouse_region_x, event.mouse_region_y)
            if mouse == self._mouse:
                return {'RUNNING_MODAL'}
            vector = self._vector(context, event)
            if vector is not None and self._last is not None:
                step = math.atan2(self._axis.dot(self._last.cross(vector)), self._last.dot(vector))
            else:
                step = ((mouse[0]-self._mouse[0])+(mouse[1]-self._mouse[1]))*.01
            self._last, self._mouse = vector, mouse
            self._drag_angle += step * (.1 if event.shift else 1.0)
            if not self._text:
                self._apply(context, self._drag_value(context, event))
            return {'RUNNING_MODAL'}
        if event.value == 'PRESS':
            char = getattr(event, 'unicode', '')
            if (char and char in '0123456789.-') or event.type == 'BACK_SPACE':
                self._text = self._text[:-1] if event.type == 'BACK_SPACE' else self._text+char
                try:
                    self._apply(context, math.radians(float(self._text)))
                except ValueError:
                    pass
                return {'RUNNING_MODAL'}
        return {'PASS_THROUGH'}


classes = (ALLSET_OT_pivot_rotate,)
