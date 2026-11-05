# SPDX-License-Identifier: GPL-3.0-or-later
"""Bridge path controls and a transactional scalar taper graph."""

import json

import bpy
from bpy.props import BoolProperty, StringProperty

from ..operators import bridge_curve
from . import attribute_edit, in_view_editor, node_attributes, option_editor

_generation = 0
_editors = []
MODES = ('None', 'Linear', 'Smooth', 'Spline')


def active(context):
    return any(editor._area == context.area.as_pointer() and editor._window == context.window.as_pointer()
               for editor in _editors)


def draw_controls(layout, node):
    column = layout.column(align=True)
    column.enabled = bool(node.params.get('curve_type'))
    column.operator('allset.bridge_ramp', text='Edit Taper Curve')
    if node.params.get('curve_type') == 2:
        row = column.row(align=True)
        row.operator('allset.bridge_path', text='Choose Path').edit = False
        row.operator('allset.bridge_path', text='Edit Path').edit = True


class ALLSET_OT_bridge_path(bpy.types.Operator):
    bl_idname = 'allset.bridge_path'
    bl_label = 'Bridge Path Curve'
    bl_options = {'INTERNAL'}
    edit: BoolProperty(options={'SKIP_SAVE'})
    curve: StringProperty(name='Curve', options={'SKIP_SAVE'})

    def invoke(self, context, event):
        node = node_attributes.target(context)
        if node is None or node.spec.kind != 'BRIDGE':
            return {'CANCELLED'}
        self.curve = node.params.get('input_curve', '')
        return self.execute(context) if self.edit else context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        self.layout.prop_search(self, 'curve', bpy.data, 'objects')

    def execute(self, context):
        node = node_attributes.target(context)
        if node is None or node.spec.kind != 'BRIDGE':
            return {'CANCELLED'}
        try:
            if not self.edit:
                return in_view_editor.apply(context, node, dict(node.params, input_curve=self.curve))
            curve = bridge_curve.curve_object(node.ob, node.params)
            if context.mode != 'OBJECT':
                bpy.ops.object.mode_set(mode='OBJECT')
            bpy.ops.object.select_all(action='DESELECT')
            curve.select_set(True)
            context.view_layer.objects.active = curve
            bpy.ops.object.mode_set(mode='EDIT')
            return {'FINISHED'}
        except (ValueError, RuntimeError) as error:
            self.report({'WARNING'}, str(error))
            return {'CANCELLED'}


def graph_value(box, maximum, x, y):
    x0, y0, x1, y1 = box
    return max(0, min(1, (x-x0)/(x1-x0))), max(0, min(maximum, (y-y0)/(y1-y0)*maximum))


class ALLSET_OT_bridge_ramp(bpy.types.Operator):
    """Click to add, drag to move, X to delete, 1-4 to interpolate, Enter to apply, Esc to cancel"""
    bl_idname = 'allset.bridge_ramp'
    bl_label = 'Bridge Taper Curve'
    bl_options = {'INTERNAL', 'BLOCKING'}
    options: BoolProperty(options={'SKIP_SAVE'})

    def invoke(self, context, event):
        if context.area.type != 'VIEW_3D' or context.region.type != 'WINDOW':
            data = option_editor.session(context) if self.options else None
            if data is not None:
                window, area, region = option_editor.origin(data)
            else:
                window = context.window
                area = next((a for a in window.screen.areas if a.type == 'VIEW_3D'), None)
                region = next((r for r in area.regions if r.type == 'WINDOW'), None) if area else None
            if region is None:
                self.report({'WARNING'}, 'Open a 3D viewport to edit the taper curve')
                return {'CANCELLED'}
            with context.temp_override(window=window, area=area, region=region):
                return bpy.ops.allset.bridge_ramp('INVOKE_DEFAULT', options=self.options)
        self._node = None if self.options else node_attributes.target(context)
        if not self.options and (self._node is None or self._node.spec.kind != 'BRIDGE'):
            return {'CANCELLED'}
        if not attribute_edit.claim(context, self):
            return {'CANCELLED'}
        self._window = context.window.as_pointer()
        self._area = context.area.as_pointer()
        self._mode = context.mode
        self._generation = _generation
        self._start = dict(self._node.params) if self._node else None
        self._holder = option_editor.owner(context.window_manager, 'bridge') if self.options else None
        text = self._holder.taper_curve if self.options else self._start.get('taper_curve', bridge_curve.RAMP_DEFAULT)
        try:
            self._points = [list(point) for point in bridge_curve.ramp_points(text)]
        except ValueError as error:
            attribute_edit.release(self._window, self)
            self.report({'WARNING'}, str(error))
            return {'CANCELLED'}
        self._selected, self._dragging, self._pending = 0, False, False
        self._maximum = max(2.0, max(point[1] for point in self._points)*1.2)
        scale = context.preferences.system.ui_scale or 1
        width, height = min(370*scale, context.region.width-32), min(250*scale, context.region.height-32)
        x, y = max(16, (context.region.width-width)/2), max(16, (context.region.height-height)/2)
        self._box = x, y, x+width, y+height
        self._graph = x+28, y+65, x+width-18, y+height-40
        self._finished = False
        self._handler = bpy.types.SpaceView3D.draw_handler_add(self.draw_graph, (), 'WINDOW', 'POST_PIXEL')
        self._timer = context.window_manager.event_timer_add(.05, window=context.window)
        _editors.append(self)
        context.window_manager.modal_handler_add(self)
        context.area.tag_redraw()
        return {'RUNNING_MODAL'}

    def text(self):
        return json.dumps(sorted(self._points), separators=(',', ':'))

    def preview(self, context):
        if self._node is not None:
            self._node.preview(context, dict(self._start, taper_curve=self.text()))
        self._pending = False

    def finish(self, context, cancel=False):
        if getattr(self, '_finished', True):
            return {'CANCELLED'}
        self._finished = True
        try:
            if self._node is not None and self._node.valid():
                if cancel:
                    self._node.preview(context, self._start)
                else:
                    in_view_editor.apply(context, self._node, dict(self._start, taper_curve=self.text()))
                self._node.finish()
            elif not cancel and self._holder is not None:
                self._holder.taper_curve = self.text()
        except (ValueError, RuntimeError, ReferenceError) as error:
            self.report({'WARNING'}, str(error))
            cancel = True
        finally:
            bpy.types.SpaceView3D.draw_handler_remove(self._handler, 'WINDOW')
            context.window_manager.event_timer_remove(self._timer)
            attribute_edit.release(self._window, self)
            if self in _editors:
                _editors.remove(self)
            if context.area:
                context.area.tag_redraw()
        return {'CANCELLED'} if cancel else {'FINISHED'}

    def cancel(self, context):
        self.finish(context, cancel=True)

    def modal(self, context, event):
        if (self._generation != _generation or context.mode != self._mode
                or (self._node is not None and not self._node.valid())):
            return self.finish(context, cancel=True)
        if event.type in {'ESC', 'RIGHTMOUSE'} and event.value == 'PRESS':
            return self.finish(context, cancel=True)
        if event.type in {'RET', 'NUMPAD_ENTER'} and event.value == 'PRESS':
            return self.finish(context)
        x, y = event.mouse_x-context.region.x, event.mouse_y-context.region.y
        if event.type == 'LEFTMOUSE':
            if event.value == 'PRESS':
                x0, y0, x1, y1 = self._graph
                if not (x0 <= x <= x1 and y0 <= y <= y1):
                    return {'RUNNING_MODAL'}
                nearest = min(range(len(self._points)), key=lambda i: self.distance(self._points[i], x, y))
                if self.distance(self._points[nearest], x, y) > 12**2 and len(self._points) < 256:
                    t, value = graph_value(self._graph, self._maximum, x, y)
                    self._points.append([t, value, 1])
                    nearest = len(self._points)-1
                self._selected, self._dragging = nearest, True
                self._pending = True
            else:
                self._dragging = False
        elif event.type == 'MOUSEMOVE' and self._dragging:
            self._points[self._selected][:2] = graph_value(self._graph, self._maximum, x, y)
            self._pending = True
        elif event.type in {'X', 'DEL'} and event.value == 'PRESS' and len(self._points) > 1:
            self._points.pop(self._selected)
            self._selected = min(self._selected, len(self._points)-1)
            self._pending = True
        elif event.type in {'ONE', 'TWO', 'THREE', 'FOUR'} and event.value == 'PRESS':
            self._points[self._selected][2] = ('ONE', 'TWO', 'THREE', 'FOUR').index(event.type)
            self._pending = True
        elif event.type in {'WHEELUPMOUSE', 'WHEELDOWNMOUSE'}:
            factor = 1.25 if event.type == 'WHEELUPMOUSE' else .8
            self._maximum = max(.1, min(1e6, self._maximum*factor))
        if event.type == 'TIMER' and self._pending:
            try:
                self.preview(context)
            except (ValueError, RuntimeError, ReferenceError) as error:
                self.report({'WARNING'}, str(error))
                return self.finish(context, cancel=True)
        context.area.tag_redraw()
        return {'RUNNING_MODAL'}

    def point(self, point):
        x0, y0, x1, y1 = self._graph
        return x0+point[0]*(x1-x0), y0+point[1]/self._maximum*(y1-y0)

    def distance(self, point, x, y):
        px, py = self.point(point)
        return (px-x)**2+(py-y)**2

    def draw_graph(self):
        context = bpy.context
        if context.area.as_pointer() != self._area or context.window.as_pointer() != self._window:
            return
        import gpu
        from gpu_extras.batch import batch_for_shader
        from .in_view import _rect, _text
        gpu.state.blend_set('ALPHA')
        try:
            x0, y0, x1, y1 = self._box
            _rect(x0, y0, x1, y1, (.08, .08, .08, .98))
            _rect(*self._graph, (.03, .03, .03, 1))
            white = (.85, .85, .85, 1)
            _text(x0+12, y1-24, 'Bridge Taper Curve', white, 13)
            points = sorted(self._points)
            line = [self.point((i/128, bridge_curve.ramp_value(points, i/128))) for i in range(129)]
            shader = gpu.shader.from_builtin('UNIFORM_COLOR')
            shader.bind()
            shader.uniform_float('color', (1, .75, .1, 1))
            batch_for_shader(shader, 'LINE_STRIP', {'pos': line}).draw(shader)
            for index, point in enumerate(self._points):
                x, y = self.point(point)
                color = (1, .75, .1, 1) if index == self._selected else white
                _rect(x-4, y-4, x+4, y+4, color)
            point = self._points[self._selected]
            _text(x0+12, y0+45, f'Position {point[0]:.3f}   Value {point[1]:.3f}   {MODES[point[2]]}', white, 11)
            _text(x0+12, y0+26, 'Click / drag points   X delete   1-4 interpolation', white, 11)
            _text(x0+12, y0+9, f'Wheel value range {self._maximum:.2f}   Enter apply   Esc cancel', white, 11)
        finally:
            gpu.state.blend_set('NONE')


@bpy.app.handlers.persistent
def clear(_dummy=None):
    global _generation
    _generation += 1
    for editor in tuple(_editors):
        editor.finish(bpy.context, cancel=True)


classes = (ALLSET_OT_bridge_path, ALLSET_OT_bridge_ramp)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    for handlers in (bpy.app.handlers.load_pre, bpy.app.handlers.undo_pre, bpy.app.handlers.redo_pre):
        handlers.append(clear)


def unregister():
    clear()
    for handlers in (bpy.app.handlers.load_pre, bpy.app.handlers.undo_pre, bpy.app.handlers.redo_pre):
        if clear in handlers:
            handlers.remove(clear)
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
