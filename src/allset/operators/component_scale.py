# SPDX-License-Identifier: GPL-3.0-or-later
"""Non-negative component scaling in the Maya Scale tool.

The manipulator's own drag (``manip_scale``) stops every handle at zero; this operator is the single-axis
route for MMB scaling and scripts.

Each preview restores the original coordinates/UVs and executes Blender's native
transform without nested undo steps. Thus zero is reversible within a gesture,
and proportional editing, mesh symmetry and UV correction stay in Blender.
"""
import math

import bmesh
import bpy
from bpy_extras import view3d_utils
from mathutils import Matrix, Vector

from . import hold

DRAG = None
STEP = .1


def enabled(context):
    from .. import preferences
    return (context.mode == 'EDIT_MESH' and preferences.get(context).maya_mode
            and preferences.get(context).prevent_negative_scale and not hold.COMPONENT.on)


def start(context, kwargs, button='LEFTMOUSE'):
    """Route constrained MMB scaling through the same operator as axis handles."""
    if enabled(context) and sum(kwargs.get('constraint_axis', ())) == 1:
        return bpy.ops.allset.component_scale('INVOKE_DEFAULT', release_event=button, **kwargs)
    return bpy.ops.transform.resize('INVOKE_DEFAULT', **kwargs)


class Snapshot:
    def __init__(self, context):
        self.entries = []
        ts = context.tool_settings
        for ob in context.objects_in_mode_unique_data:
            if ob.type != 'MESH':
                continue
            bm = bmesh.from_edit_mesh(ob.data)
            bm.verts.ensure_lookup_table()
            all_points = ts.use_proportional_edit or any((ob.data.use_mirror_x, ob.data.use_mirror_y, ob.data.use_mirror_z))
            coords = [(i, v.co.copy()) for i, v in enumerate(bm.verts) if all_points or v.select]
            shapes = {layer.name: [(i, bm.verts[i][layer].copy()) for i, _ in coords]
                      for layer in bm.verts.layers.shape.values()} if ob.data.shape_keys else {}
            uvs = {layer.name: [lp[layer].uv.copy() for f in bm.faces for lp in f.loops]
                   for layer in bm.loops.layers.uv.values()} if ts.use_transform_correct_face_attributes else {}
            self.entries.append((ob, coords, shapes, uvs))

    def restore(self):
        for ob, coords, shapes, uvs in self.entries:
            bm = bmesh.from_edit_mesh(ob.data)
            bm.verts.ensure_lookup_table()
            for i, co in coords:
                bm.verts[i].co = co
            for name, values in shapes.items():
                layer = bm.verts.layers.shape.get(name)
                for i, co in values:
                    bm.verts[i][layer] = co
            for name, values in uvs.items():
                layer = bm.loops.layers.uv.get(name)
                for lp, uv in zip((lp for f in bm.faces for lp in f.loops), values):
                    lp[layer].uv = uv
            bm.normal_update()
            bmesh.update_edit_mesh(ob.data, loop_triangles=False, destructive=False)


class ALLSET_OT_prevent_negative_scale(bpy.types.Operator):
    """Stop component scaling at zero on every Scale handle; Object Mode is unaffected"""
    bl_idname = "allset.prevent_negative_scale"
    bl_label = "Prevent Negative Scale"
    bl_options = {'INTERNAL'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'EDIT_MESH'

    def execute(self, context):
        from .. import preferences
        prefs = preferences.get(context)
        prefs.prevent_negative_scale = not prefs.prevent_negative_scale
        hold._redraw()
        return {'FINISHED'}


class ALLSET_OT_component_scale(bpy.types.Operator):
    """Scale components along one axis, stopping at zero without flipping"""
    bl_idname = "allset.component_scale"
    bl_label = "Scale Components"
    bl_options = {'REGISTER', 'UNDO', 'BLOCKING'}

    constraint_axis: bpy.props.BoolVectorProperty(size=3, default=(False, False, False), options={'HIDDEN', 'SKIP_SAVE'})
    orient_type: bpy.props.StringProperty(default='GLOBAL', options={'HIDDEN', 'SKIP_SAVE'})
    orient_matrix_type: bpy.props.StringProperty(default='GLOBAL', options={'HIDDEN', 'SKIP_SAVE'})
    orient_matrix: bpy.props.FloatVectorProperty(size=(3, 3), subtype='MATRIX', default=((1, 0, 0), (0, 1, 0), (0, 0, 1)), options={'HIDDEN', 'SKIP_SAVE'})
    value: bpy.props.FloatVectorProperty(name="Scale", size=3, default=(1, 1, 1), options={'HIDDEN', 'SKIP_SAVE'})
    release_confirm: bpy.props.BoolProperty(default=True, options={'HIDDEN', 'SKIP_SAVE'})
    release_event: bpy.props.EnumProperty(items=(('LEFTMOUSE', "Left", ""), ('MIDDLEMOUSE', "Middle", "")),
                                        default='LEFTMOUSE', options={'HIDDEN', 'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        return context.mode == 'EDIT_MESH' and context.edit_object is not None

    def _capture(self, context):
        from ..ui import manipulator
        axes = [i for i, on in enumerate(self.constraint_axis) if on]
        if len(axes) != 1:
            raise ValueError("Choose one scale axis")
        self._axis = axes[0]
        self._centre, _, _ = manipulator.pivot_frame(context, 'RESIZE')
        if self._centre is None:
            raise ValueError("Select components first")
        self._frame = (Matrix(self.orient_matrix) if self.orient_type == 'GLOBAL' and self.properties.is_property_set('orient_matrix')
                       else manipulator.axes_of(context, self.orient_type, context.region_data))
        if not all(math.isfinite(v) for row in self._frame for v in row) or abs(self._frame.determinant()) < 1e-10:
            raise ValueError("Choose a usable scale orientation")
        self._snapshot = Snapshot(context)
        self._individual = context.tool_settings.transform_pivot_point == 'INDIVIDUAL_ORIGINS'
        # Serialize the actual frozen frame for registered-op handle memory and
        # redo. Gizmo bindings use an identity matrix placeholder for LOCAL/NORMAL.
        self.orient_type = self.orient_matrix_type = 'GLOBAL'
        self.orient_matrix = self._frame

    def apply(self, context, factor):
        if not math.isfinite(factor):
            raise ValueError("Scale must be finite")
        factor = max(0., factor)
        self._snapshot.restore()
        ts = context.tool_settings
        values = [1., 1., 1.]
        values[self._axis] = factor
        kwargs = dict(value=values, constraint_axis=self.constraint_axis,
                      orient_type='GLOBAL', orient_matrix_type='GLOBAL', orient_matrix=self._frame,
                      use_proportional_edit=ts.use_proportional_edit,
                      proportional_edit_falloff=ts.proportional_edit_falloff, proportional_size=ts.proportional_size,
                      use_proportional_connected=ts.use_proportional_connected,
                      use_proportional_projected=ts.use_proportional_projected, snap=False)
        if not self._individual:
            kwargs['center_override'] = self._centre
        if bpy.ops.transform.resize('EXEC_DEFAULT', False, **kwargs) != {'FINISHED'}:
            raise ValueError("Blender could not scale this selection")
        self.value = values

    def execute(self, context):
        try:
            self._capture(context)
            self.apply(context, self.value[self._axis])
        except (ValueError, RuntimeError) as ex:
            if hasattr(self, '_snapshot'):
                self._snapshot.restore()
            self.report({'WARNING'}, str(ex))
            return {'CANCELLED'}
        finally:
            if hasattr(self, '_snapshot'):
                self._snapshot.entries.clear()
        return {'FINISHED'}

    def invoke(self, context, event):
        global DRAG
        try:
            self._capture(context)
        except (ValueError, RuntimeError) as ex:
            self.report({'WARNING'}, str(ex))
            return {'CANCELLED'}
        region, rv = context.region, context.region_data
        a = view3d_utils.location_3d_to_region_2d(region, rv, self._centre)
        b = view3d_utils.location_3d_to_region_2d(region, rv, self._centre+self._frame.col[self._axis])
        direction = b-a if a is not None and b is not None else Vector((0, 0))
        self._direction = direction.normalized() if direction.length > 1e-4 else Vector((0, 1))
        self._mouse = Vector((event.mouse_region_x, event.mouse_region_y))
        distance = abs((self._mouse-a).dot(self._direction)) if a is not None else 0
        self._sensitivity = 1/max(24., distance)
        self._factor, self._text = 1., ''
        self._step_held, self._baseline_step = hold.step_state(context.tool_settings, 'RESIZE')
        from . import manip
        manip.HANDLES['RESIZE'] = dict(constraint_axis=tuple(self.constraint_axis), orient_type='GLOBAL',
                                      orient_matrix=self._frame.copy(), orient_matrix_type='GLOBAL')
        DRAG = self
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def _update(self, context, event):
        factor = self._factor
        if self._step_held or (self._baseline_step != event.ctrl):
            factor = round(factor/STEP)*STEP
        if self._text:
            try:
                factor = float(self._text)
            except ValueError:
                return
        self.apply(context, factor)
        context.area.header_text_set(f"Scale {'XYZ'[self._axis]}: {self.value[self._axis]:.4f} · "
                                     "Prevent Negative Scale · J: 0.1 steps · Type: Value · Esc: Cancel")
        context.area.tag_redraw()

    def _end(self, context, cancel=False):
        global DRAG
        if cancel:
            self._snapshot.restore()
        DRAG = None
        self._snapshot.entries.clear()
        context.area.header_text_set(None)
        context.area.tag_redraw()
        return {'CANCELLED'} if cancel else {'FINISHED'}

    def cancel(self, context):
        self._end(context, True)

    def modal(self, context, event):
        if event.type in {'ESC', 'RIGHTMOUSE'} and event.value == 'PRESS':
            return self._end(context, True)
        if ((event.type == self.release_event and event.value == 'RELEASE')
                or (event.type in {'RET', 'NUMPAD_ENTER'} and event.value == 'PRESS')):
            return self._end(context)
        try:
            if event.type == 'MOUSEMOVE':
                mouse = Vector((event.mouse_region_x, event.mouse_region_y))
                if not self._text:
                    delta = (mouse-self._mouse).dot(self._direction)*self._sensitivity*(.1 if event.shift else 1.)
                    self._factor = max(0., self._factor+delta)
                self._mouse = mouse
                self._update(context, event)
            elif event.type == 'J' and event.value in {'PRESS', 'RELEASE'}:
                if not event.is_repeat:
                    self._step_held = event.value == 'PRESS'
                    self._update(context, event)
            elif event.value == 'PRESS' and event.type == 'BACK_SPACE':
                self._text = self._text[:-1]
                self._update(context, event)
            elif event.value == 'PRESS' and getattr(event, 'unicode', '') and event.unicode in '0123456789.-':
                self._text += event.unicode
                self._update(context, event)
            elif event.type in {'LEFT_CTRL', 'RIGHT_CTRL'}:
                self._update(context, event)
        except (ValueError, RuntimeError) as ex:
            self.report({'WARNING'}, str(ex))
            return self._end(context, True)
        return {'RUNNING_MODAL'}


classes = (ALLSET_OT_prevent_negative_scale, ALLSET_OT_component_scale)
