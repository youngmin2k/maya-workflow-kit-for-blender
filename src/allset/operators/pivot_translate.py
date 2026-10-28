# SPDX-License-Identifier: GPL-3.0-or-later
"""Move pivot handles with momentary J steps, including J pressed during a drag."""
import bpy
from bpy_extras import view3d_utils
from mathutils import Vector
from mathutils.geometry import intersect_line_line, intersect_line_plane

from . import freeze, hold, pivot, snap_align, units


class ALLSET_OT_pivot_translate(bpy.types.Operator):
    """Move the pivot only; hold J for discrete steps and release J to move freely"""
    bl_idname = "allset.pivot_translate"
    bl_label = "Move Custom Pivot"
    bl_options = {'REGISTER', 'UNDO', 'BLOCKING'}

    constraint_axis: bpy.props.BoolVectorProperty(size=3, default=(False, False, False))
    value: bpy.props.FloatVectorProperty(name="Offset", size=3, subtype='TRANSLATION')

    @classmethod
    def poll(cls, context):
        return ((pivot.pivot_mode(context) and context.active_object is not None)
                or (context.mode == 'EDIT_MESH' and hold.COMPONENT.on))

    def _capture(self, context):
        self._component = context.mode == 'EDIT_MESH'
        self._frame = context.scene.cursor.matrix.to_3x3() if self._component else pivot.axes_for(context.active_object)
        self._origin = (context.scene.cursor.location.copy() if self._component
                        else context.active_object.matrix_world.translation.copy())
        self._origins = {ob.name: ob.matrix_world.translation.copy() for ob in context.selected_objects} if not self._component else {}
        self._step_held, self._baseline_step = hold.step_state(context.tool_settings, 'TRANSLATE')
        self._unit = units.maya_unit(context.scene)
        self._absolute = (context.tool_settings.use_snap_grid_absolute
                          and snap_align.absolute_offered(context.scene, 'TRANSLATE'))

    def _apply(self, context, delta):
        self.value = delta
        if self._component:
            context.scene.cursor.location = self._origin + delta
        else:
            objects = [ob for name in self._origins if (ob := bpy.data.objects.get(name)) is not None]
            for ob in freeze.parents_first(objects):
                context.view_layer.update()
                pivot.match_pivot(ob, self._origins[ob.name] + delta)
            context.view_layer.update()
        hold._redraw()

    def _drag_value(self, context, event):
        local = self._frame.transposed() @ self._raw_delta
        mask = tuple(self.constraint_axis)
        for i in range(3):
            if any(mask) and not mask[i]:
                local[i] = 0
        if self._step_held or (self._baseline_step != event.ctrl):
            offset = self._frame.transposed() @ self._origin if self._absolute else Vector()
            for i in range(3):
                if not any(mask) or mask[i]:
                    local[i] = round((local[i]+offset[i])/self._unit)*self._unit-offset[i]
        return self._frame @ local

    def _point(self, context, event):
        mouse = (event.mouse_region_x, event.mouse_region_y)
        region, rv = context.region, context.region_data
        origin = view3d_utils.region_2d_to_origin_3d(region, rv, mouse)
        direction = view3d_utils.region_2d_to_vector_3d(region, rv, mouse)
        enabled = [i for i, value in enumerate(self.constraint_axis) if value]
        if len(enabled) == 1:
            axis = self._frame.col[enabled[0]]
            points = intersect_line_line(origin, origin+direction, self._origin, self._origin+axis)
            if points is not None and abs(direction.dot(axis)) < .9999:
                return points[1]
        if len(enabled) == 2:
            normal = self._frame.col[next(i for i in range(3) if i not in enabled)]
            point = intersect_line_plane(origin, origin+direction, self._origin, normal)
            if point is not None:
                return point
        return view3d_utils.region_2d_to_location_3d(region, rv, mouse, self._origin)

    def execute(self, context):
        self._capture(context)
        self._apply(context, Vector(self.value))
        return {'FINISHED'}

    def invoke(self, context, event):
        # Keep Blender's geometry snapping for X/C/V and persistent surface snaps.
        # J-only gestures use our frame so snap can change during the modal drag.
        if snap_align.other_snaps_on(context.tool_settings):
            frame = context.scene.cursor.matrix.to_3x3() if context.mode == 'EDIT_MESH' else pivot.axes_for(context.active_object)
            bpy.ops.transform.translate('INVOKE_DEFAULT', constraint_axis=self.constraint_axis,
                    orient_type='GLOBAL', orient_matrix_type='GLOBAL', orient_matrix=frame,
                    cursor_transform=context.mode == 'EDIT_MESH', release_confirm=True)
            return {'FINISHED'}
        self._capture(context)
        self._start = self._point(context, event)
        self._raw_delta = Vector()
        self._text = ""
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type in {'ESC', 'RIGHTMOUSE'} and event.value == 'PRESS':
            self._apply(context, Vector())
            return {'CANCELLED'}
        if event.type in {'RET', 'NUMPAD_ENTER'} and event.value == 'PRESS':
            return {'FINISHED'}
        if event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
            return {'FINISHED'}
        if event.type == 'D':
            return {'RUNNING_MODAL'}
        if event.type == 'J' and event.value in {'PRESS', 'RELEASE'}:
            if not event.is_repeat:
                self._step_held = event.value == 'PRESS'
                if not self._text:
                    self._apply(context, self._drag_value(context, event))
            return {'RUNNING_MODAL'}
        if event.type == 'MOUSEMOVE':
            if not self._text:
                self._raw_delta = self._point(context, event)-self._start
                self._apply(context, self._drag_value(context, event))
            return {'RUNNING_MODAL'}
        if event.value == 'PRESS':
            char = getattr(event, 'unicode', '')
            if (char and char in '0123456789.-') or event.type == 'BACK_SPACE':
                self._text = self._text[:-1] if event.type == 'BACK_SPACE' else self._text+char
                try:
                    axis = next((i for i, value in enumerate(self.constraint_axis) if value), 0)
                    self._apply(context, self._frame.col[axis]*(float(self._text)*self._unit))
                except ValueError:
                    pass
                return {'RUNNING_MODAL'}
        return {'PASS_THROUGH'}


classes = (ALLSET_OT_pivot_translate,)
