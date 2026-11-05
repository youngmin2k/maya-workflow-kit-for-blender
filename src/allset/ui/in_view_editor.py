# SPDX-License-Identifier: GPL-3.0-or-later
"""In-View attribute selection, editor layout and transactional viewport dragging."""

import json
import os
import tempfile
import time
from pathlib import Path

import bpy
from bpy.props import BoolProperty, FloatProperty, IntProperty, StringProperty
from bpy_extras.view3d_utils import location_3d_to_region_2d

from .. import preferences
from ..operators import extrude
from . import attribute_edit, cb_entry, node_attributes

_views = {}
_model_targets = {}
_generation = 0


def view_key(context):
    return context.window.as_pointer(), context.area.as_pointer()


def tool(context):
    current = context.workspace.tools.from_space_view3d_mode(context.mode, create=False)
    return current.idname if current else None


def state(context, node):
    key = view_key(context)
    current = _views.get(key)
    if current is None or current['identity'] != node.identity:
        live = {(window.as_pointer(), area.as_pointer()) for window in context.window_manager.windows
                for area in window.screen.areas}
        for stale in set(_views)-live:
            _views.pop(stale, None)
            _model_targets.pop(stale, None)
        saved = settings(context, node)
        current = dict(identity=node.identity, field=node.spec.fields[0], armed=True, tool=tool(context),
                       position=saved.get('position'), width=saved.get('width') or 180.0,
                       height=saved.get('height'), scroll=0, reveal=False)
        _views[key] = current
    return current


def settings(context, node):
    try:
        saved = json.loads(preferences.get(context).inview_layouts).get(node.spec.node_type, {})
        return saved if isinstance(saved, dict) else {}
    except (ValueError, TypeError, AttributeError):
        return {}


def layout_file(create=False):
    package = __package__.rsplit('.', 1)[0]
    try:
        folder = Path(bpy.utils.extension_path_user(package, create=create))
    except (AttributeError, ValueError):
        folder = Path(__file__).resolve().parents[1]/'user_data'
        if create:
            folder.mkdir(parents=True, exist_ok=True)
    return folder/'in_view_editors.json'


def persist_layouts(context, prefs=None):
    """The kit user folder keeps editor layouts across sessions, including preference auto-save being off."""
    path = layout_file(create=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                         prefix='.inview-', delete=False) as stream:
            stream.write((prefs if prefs is not None else preferences.get(context)).inview_layouts)
            temporary = Path(stream.name)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def save_settings(context, node, values):
    prefs = preferences.get(context)
    try:
        all_settings = json.loads(prefs.inview_layouts)
        if not isinstance(all_settings, dict):
            all_settings = {}
    except (ValueError, TypeError):
        all_settings = {}
    all_settings[node.spec.node_type] = values
    prefs.inview_layouts = json.dumps(all_settings)
    try:
        persist_layouts(context)
    except OSError as error:
        from . import notices
        notices.show(f'Unable to save In-View Editor settings: {error}')


def available_fields(node):
    hidden = getattr(node.spec, 'hidden', ())
    return [name for name in getattr(node.spec, 'all_fields', node.spec.fields) if name not in hidden]


def fields(context, node):
    saved = settings(context, node)
    available = available_fields(node)
    order = [name for name in saved.get('order', ()) if name in available]
    order += [name for name in available if name not in order]
    hidden = set(saved.get('hidden', set(available)-set(node.spec.fields)))
    return [name for name in order if name not in hidden]


def model_target(context, fresh=False):
    """Share expensive display validation within a frame; edit entry points always validate afresh."""
    ob = context.edit_object
    if ob is None or context.window is None or context.area is None:
        return None
    record = extrude.RECORDS.get(ob.name)
    if record is None or record.pre is None or record.dismissed:
        return None
    key = view_key(context)
    identity = (ob.session_uid, ob.data.session_uid, id(record), tuple(record.params.items()))
    cached = _model_targets.get(key)
    now = time.perf_counter()
    if not fresh and cached is not None and cached[0] == identity and now-cached[1] < 1/120:
        return cached[2]
    record = extrude.current(ob)
    node = (node_attributes.ModelingNode(ob, record)
            if record is not None and extrude.caps_selected(ob, record) else None)
    _model_targets[key] = identity, time.perf_counter(), node
    return node


def target(context, fresh=False):
    if (context.window is None or context.area is None or context.area.type != 'VIEW_3D'
            or context.region is None or context.region.type != 'WINDOW'
            or not preferences.get(context).inview_editors):
        return None
    from .toolbox import is_toolbox
    if is_toolbox(context.space_data):
        return None
    ob = context.active_object
    if ob is None or context.mode not in {'OBJECT', 'EDIT_MESH'}:
        return None
    if context.mode == 'EDIT_MESH':
        node = model_target(context, fresh)
        if node is None:
            return None
        record = node.record
        saved = _views.get(view_key(context))
        forced = saved is not None and saved.get('forced') and saved['identity'][0] == ob.session_uid
        if not record.spec.in_view and not forced:
            return None
        return node
    saved = _views.get(view_key(context))
    if saved is None or saved['identity'][0] != ob.session_uid or saved['tool'] != tool(context):
        return None
    node = node_attributes.target(context, ob)
    return node if node is not None and node.identity == saved['identity'] else None


def show(context):
    node = node_attributes.target(context)
    if node is None:
        return False
    if isinstance(node, node_attributes.ModelingNode):
        node.record.dismissed = False
    current = state(context, node)
    current.update(tool=tool(context), armed=True, forced=True)
    context.area.tag_redraw()
    return True


def select(context, node, field):
    if field not in fields(context, node):
        saved = settings(context, node)
        hidden = set(saved.get('hidden', set(available_fields(node))-set(node.spec.fields)))
        hidden.discard(field)
        saved['hidden'] = sorted(hidden)
        save_settings(context, node, saved)
    current = state(context, node)
    current.update(field=field, armed=True, tool=tool(context), reveal=True)
    from . import channel_box
    channel_box.disarm_slider()
    context.area.tag_redraw()


def armed(context, node):
    current = state(context, node)
    return current['armed'] and current['tool'] == tool(context)


def disarm(context):
    if context.window is not None and context.area is not None:
        current = _views.get(view_key(context))
        if current is not None:
            current['armed'] = False


def disarm_window(context):
    if context.window is not None:
        pointer = context.window.as_pointer()
        for (window, _area), current in _views.items():
            if window == pointer:
                current['armed'] = False


def current_layout(context, fresh=False):
    from . import in_view
    node = target(context, fresh)
    if node is None or context.region_data is None:
        return None, None
    if isinstance(node, node_attributes.ModelingNode):
        anchor = in_view.anchor(context, node.ob, node.record)
    else:
        point = location_3d_to_region_2d(context.region, context.region_data, node.ob.matrix_world.translation)
        anchor = tuple(point) if point is not None else None
    if anchor is None:
        return None, None
    current = state(context, node)
    visible = fields(context, node)
    scale = context.preferences.system.ui_scale or 1.0
    row_height = in_view.ROW_H * scale
    max_height = context.region.height-8*scale
    requested_height = current['height'] or (len(visible)+1)*row_height/scale
    capacity = max(1, int(min(requested_height*scale, max_height)/row_height)-1)
    offset = max(0, min(current['scroll'], len(visible)-capacity))
    if current.pop('reveal', False) and current['field'] in visible:
        index = visible.index(current['field'])
        offset = min(offset, index) if index < offset else max(offset, index-capacity+1)
    current['scroll'] = offset
    shown = visible[offset:offset+capacity]
    width = max(150.0, min(float(current['width']), context.region.width / scale - 8))
    lay = in_view.layout(context.region, anchor, scale, visible)
    position = current['position']
    height = row_height * (len(shown) + 1)
    x0 = position[0] * scale if position else lay['box'][0]
    top = position[1] * scale if position else lay['box'][3]
    x0 = max(4 * scale, min(x0, context.region.width - width * scale - 4 * scale))
    top = max(height + 4 * scale, min(top, context.region.height - 4 * scale))
    rows = [(field, x0, top - (i + 2) * row_height, x0 + width * scale, top - (i + 1) * row_height)
            for i, field in enumerate(shown)]
    lay = dict(box=(x0, top-height, x0+width*scale, top),
               title=(x0, top-row_height, x0+width*scale, top), rows=rows,
               offset=offset, capacity=capacity, total=len(visible))
    return node, lay


def draw():
    from ..marking import draw as marking_draw
    from . import in_view
    context = bpy.context
    node, lay = current_layout(context)
    if node is None or marking_draw.menu_up():
        return
    import blf
    import gpu
    scale = context.preferences.system.ui_scale or 1.0
    pad, size = 5 * scale, 11 * scale
    gpu.state.blend_set('ALPHA')
    try:
        in_view._rect(*lay['box'], in_view.BG)
        in_view._rect(*lay['title'], in_view.TITLE_BG)
        x0, y0, x1, _y1 = lay['title']
        in_view._text(x0+pad, y0+4*scale, node.name, in_view.TEXT, size)
        in_view._text(x1-16*scale, y0+4*scale, '+', in_view.TEXT, size)
        if lay['total'] > len(lay['rows']):
            in_view._text(x1-72*scale, y0+4*scale,
                          f"{lay['offset']+1}-{lay['offset']+len(lay['rows'])}/{lay['total']}", in_view.TEXT, 9*scale)
        active = state(context, node)['field']
        params = node.params
        for name, x0, y0, x1, _y1 in lay['rows']:
            colour = in_view.HOT if name == active else in_view.TEXT
            in_view._text(x0+pad, y0+4*scale, node.spec.labels[name], colour, size)
            kind = node.spec.kinds[name]
            value = params[name]
            if kind == 'ENUM':
                labels, values = node.choices(name)
                text = labels[values.index(value)] if value in values else str(value)
            elif kind == 'BOOL':
                text = 'On' if value else 'Off'
            else:
                text = cb_entry.fmt_number(value)
            blf.size(0, size)
            in_view._text(x1-pad-blf.dimensions(0, text)[0], y0+4*scale, text, in_view.TEXT, size)
        x1, y0 = lay['box'][2], lay['box'][1]
        in_view._text(x1-8*scale, y0, '/', in_view.TEXT, 9*scale)
    finally:
        gpu.state.blend_set('NONE')


def hit(context, event, lay):
    x, y = event.mouse_region_x, event.mouse_region_y
    x0, y0, x1, y1 = lay['box']
    reach = 10 * context.preferences.system.ui_scale
    if x1-reach <= x <= x1 and y0 <= y <= y0+reach:
        return 'RESIZE', None
    for field, x0, y0, x1, y1 in lay['rows']:
        if x0 <= x <= x1 and y0 <= y <= y1:
            return 'ROW', field
    x0, y0, x1, y1 = lay['box']
    if lay['title'][0] <= x <= x1 and lay['title'][1] <= y <= y1:
        return ('MENU' if x >= x1-24*context.preferences.system.ui_scale else 'MOVE'), None
    return None, None


def apply(context, node, params):
    return bpy.ops.allset.node_attribute_apply('EXEC_DEFAULT', True, object_name=node.ob.name,
                                              node_name=node.name, values=json.dumps(params))


def attribute_menu(context):
    node = target(context)
    if node is None:
        return False
    from ..marking import menus
    menu = menus.MENUS['INVIEW_ATTRIBUTES']
    entries = [(node.spec.labels[name], ('allset.inview_select', {'field': name}))
               for name in fields(context, node)]
    menu.radial.clear()
    menu.radial.update(zip(menus.RADIALS, entries[:8]))
    menu.items[:] = entries[8:]
    return True


class ALLSET_OT_node_attribute_apply(bpy.types.Operator):
    """Commit modeling attributes as one undoable edit from any attribute UI"""
    bl_idname = 'allset.node_attribute_apply'
    bl_label = 'Edit Node Attributes'
    bl_options = {'INTERNAL', 'UNDO'}
    object_name: StringProperty(options={'SKIP_SAVE'})
    node_name: StringProperty(options={'SKIP_SAVE'})
    values: StringProperty(options={'SKIP_SAVE'})

    def execute(self, context):
        ob = bpy.data.objects.get(self.object_name)
        if ob is None:
            return {'CANCELLED'}
        node = node_attributes.target(context, ob)
        if node is None or node.name != self.node_name:
            return {'CANCELLED'}
        params = json.loads(self.values)
        try:
            node.commit(context, params)
        finally:
            node.finish()
        return {'FINISHED'}


def invoke_drag(operator, context, event):
    node, lay = current_layout(context, fresh=True)
    if node is None or attribute_edit.busy(context) or event.alt or event.oskey:
        return {'PASS_THROUGH'}
    role, field = hit(context, event, lay)
    if operator.row >= 0:
        if operator.row >= len(lay['rows']):
            return {'CANCELLED'}
        role, field = 'ROW', lay['rows'][operator.row][0]
    if event.type == 'RIGHTMOUSE':
        if role is None:
            return {'PASS_THROUGH'}
        if field is not None:
            select(context, node, field)
        bpy.ops.wm.call_menu(name=ALLSET_MT_inview_attributes.__name__)
        return {'CANCELLED'}
    if event.type == 'LEFTMOUSE' and role is None:
        return {'PASS_THROUGH'}
    if event.type == 'MIDDLEMOUSE' and role is None:
        if not armed(context, node):
            return {'PASS_THROUGH'}
        if state(context, node)['field'] not in fields(context, node):
            return {'PASS_THROUGH'}
        field, role = state(context, node)['field'], 'ROW'
    if role == 'MENU':
        bpy.ops.wm.call_menu(name=ALLSET_MT_inview_attributes.__name__)
        return {'CANCELLED'}
    operator._node = node
    operator._view = view_key(context)
    operator._generation = _generation
    operator._scene = context.scene
    operator._frame = context.scene.frame_current
    operator._tool = tool(context)
    operator._role = role
    operator._button = event.type
    operator._last = event.mouse_x, event.mouse_y
    operator._origin = event.mouse_x, event.mouse_y
    operator._moved = False
    operator._last_preview = 0.0
    operator._start = dict(node.params)
    operator._pending = dict(operator._start)
    operator._layout = lay
    current = state(context, node)
    operator._box_start = current['position'], current['width'], current['height']
    if role == 'ROW':
        select(context, node, field)
        if not node_attributes.editable(node, field):
            return {'CANCELLED'}
        operator._field = field
        kind = node.spec.kinds[field]
        if kind == 'BOOL':
            if event.type == 'LEFTMOUSE':
                apply(context, node, dict(node.params, **{field: not node.params[field]}))
            return {'CANCELLED'}
        if kind == 'ENUM':
            bpy.ops.wm.call_menu(name=ALLSET_MT_inview_choices.__name__)
            return {'CANCELLED'}
        operator._drag = attribute_edit.Drag(node.params[field], node.descriptor(field, soft=True))
        operator._type_on_click = (event.type == 'LEFTMOUSE' and
                                  event.mouse_region_x > (lay['box'][0]+lay['box'][2])*0.5)
    if not attribute_edit.claim(context, operator):
        return {'CANCELLED'}
    operator._finished = False
    operator._timer = context.window_manager.event_timer_add(1/30, window=context.window)
    context.window_manager.modal_handler_add(operator)
    return {'RUNNING_MODAL'}


def _preview(operator, context):
    if operator._node.params != operator._pending:
        operator._node.preview(context, operator._pending)
        operator._last_preview = time.perf_counter()
        context.area.tag_redraw()


def finish_drag(operator, context, cancel=False):
    if getattr(operator, '_finished', True):
        return {'CANCELLED'}
    operator._finished = True
    node = operator._node
    try:
        if operator._role == 'ROW' and node.valid():
            try:
                if cancel or not operator._moved or operator._pending == operator._start:
                    node.preview(context, operator._start)
                else:
                    _preview(operator, context)
                    # Reuse each backend's normal commit path and one Blender undo step.
                    apply(context, node, operator._pending)
            finally:
                node.finish()
        elif operator._role in {'MOVE', 'RESIZE'}:
            current = state(context, node)
            if cancel:
                current['position'], current['width'], current['height'] = operator._box_start
            else:
                saved = settings(context, node)
                saved.update(position=current['position'], width=current['width'], height=current['height'])
                save_settings(context, node, saved)
    except (ReferenceError, RuntimeError, AttributeError, TypeError, ValueError) as error:
        operator.report({'WARNING'}, str(error))
        cancel = True
    finally:
        context.window_manager.event_timer_remove(operator._timer)
        attribute_edit.release(operator._view[0], operator)
        if context.area:
            context.area.tag_redraw()
    if (not cancel and not operator._moved and operator._role == 'ROW'
            and operator._type_on_click):
        if isinstance(node, node_attributes.ModelingNode) and operator._field in node.spec.fields:
            bpy.ops.allset.inview_type('INVOKE_DEFAULT', row=node.spec.fields.index(operator._field))
        else:
            bpy.ops.allset.inview_number('INVOKE_DEFAULT')
    return {'CANCELLED'} if cancel else {'FINISHED'}


def modal_drag(operator, context, event):
    try:
        if (operator._generation != _generation or context.window is None or context.area is None
                or view_key(context) != operator._view or context.scene != operator._scene
                or context.scene.frame_current != operator._frame or context.active_object != operator._node.ob
                or tool(context) != operator._tool or not operator._node.valid()):
            return finish_drag(operator, context, cancel=True)
        if event.type in {'ESC', 'RIGHTMOUSE', 'WINDOW_DEACTIVATE'}:
            return finish_drag(operator, context, cancel=True)
        if event.type in {'MOUSEMOVE', 'INBETWEEN_MOUSEMOVE'}:
            dx = event.mouse_x-operator._last[0]
            operator._last = event.mouse_x, event.mouse_y
            scale = context.preferences.system.ui_scale or 1.0
            operator._moved |= abs(event.mouse_x-operator._origin[0]) > 3*scale
            if operator._role == 'ROW':
                prefs = preferences.get(context)
                from .channel_box import SPEED_FACTOR
                value = operator._drag.move(dx/scale, SPEED_FACTOR[prefs.cb_speed], event.ctrl,
                                            event.shift, prefs.cb_hyperbolic)
                operator._pending[operator._field] = value
                if operator._moved and time.perf_counter()-operator._last_preview >= 1/30:
                    _preview(operator, context)
            else:
                x0, _y0, x1, top = operator._layout['box']
                current = state(context, operator._node)
                current['position'] = [(x0+event.mouse_x-operator._origin[0])/scale,
                                       (top+event.mouse_y-operator._origin[1])/scale]
                if operator._role == 'RESIZE':
                    current['position'] = [x0/scale, top/scale]
                    current['width'] = max(150, (x1-x0+event.mouse_x-operator._origin[0])/scale)
                    current['height'] = max(32, (operator._layout['box'][3]-operator._layout['box'][1]
                                                -event.mouse_y+operator._origin[1])/scale)
                context.area.tag_redraw()
        elif (event.type == 'TIMER' and operator._moved and operator._role == 'ROW'
              and time.perf_counter()-operator._last_preview >= 1/30):
            _preview(operator, context)
        elif event.type == operator._button and event.value == 'RELEASE':
            return finish_drag(operator, context)
        elif event.value == 'PRESS' and event.type in {'Q', 'W', 'E', 'R', 'T', 'Z'}:
            finish_drag(operator, context, cancel=True)
            return {'CANCELLED', 'PASS_THROUGH'}
    except (ReferenceError, RuntimeError, AttributeError, TypeError, ValueError) as error:
        operator.report({'WARNING'}, str(error))
        return finish_drag(operator, context, cancel=True)
    return {'RUNNING_MODAL'}


class ALLSET_OT_inview_select(bpy.types.Operator):
    """Choose the attribute driven by middle-dragging in the viewport"""
    bl_idname = 'allset.inview_select'
    bl_label = 'Select In-View Attribute'
    bl_options = {'INTERNAL'}
    field: StringProperty(options={'SKIP_SAVE'})
    reverse: BoolProperty(options={'SKIP_SAVE'})

    def execute(self, context):
        node = target(context)
        if node is None:
            return {'CANCELLED'}
        visible = fields(context, node)
        if self.field:
            name = self.field
        elif visible:
            current = state(context, node)['field']
            index = visible.index(current) if current in visible else -1
            name = visible[(index+(-1 if self.reverse else 1)) % len(visible)]
        else:
            return {'CANCELLED'}
        if name not in available_fields(node):
            return {'CANCELLED'}
        select(context, node, name)
        return {'FINISHED'}


class ALLSET_OT_inview_cycle(bpy.types.Operator):
    bl_idname = 'allset.inview_cycle'
    bl_label = 'Cycle In-View Attribute'
    bl_options = {'INTERNAL'}
    reverse: BoolProperty(options={'SKIP_SAVE'})

    def invoke(self, context, event):
        if target(context) is None or attribute_edit.busy(context):
            return {'PASS_THROUGH'}
        return bpy.ops.allset.inview_select(reverse=self.reverse)


class ALLSET_OT_inview_scroll(bpy.types.Operator):
    bl_idname = 'allset.inview_scroll'
    bl_label = 'Scroll In-View Attributes'
    bl_options = {'INTERNAL'}
    direction: IntProperty(default=1)

    def invoke(self, context, event):
        node, lay = current_layout(context)
        if node is None:
            return {'PASS_THROUGH'}
        x0, y0, x1, y1 = lay['box']
        if not (x0 <= event.mouse_region_x <= x1 and y0 <= event.mouse_region_y <= y1):
            return {'PASS_THROUGH'}
        current = state(context, node)
        current['scroll'] = max(0, min(lay['total']-lay['capacity'], current['scroll']+self.direction))
        current['reveal'] = False
        context.area.tag_redraw()
        return {'FINISHED'}


class ALLSET_OT_inview_number(bpy.types.Operator):
    """Enter an attribute value using the same units and relative entry as the Channel Box"""
    bl_idname = 'allset.inview_number'
    bl_label = 'Edit Attribute'
    bl_options = {'INTERNAL'}
    text: StringProperty(name='Value', options={'SKIP_SAVE'})

    def invoke(self, context, event):
        node = target(context)
        if node is None:
            return {'CANCELLED'}
        self._identity = node.identity
        self._field = state(context, node)['field']
        self.text = str(node.params[self._field])
        return context.window_manager.invoke_props_dialog(self, title=node.spec.labels[self._field])

    def execute(self, context):
        node = target(context)
        if node is None or node.identity != self._identity or not node_attributes.editable(node, self._field):
            return {'CANCELLED'}
        field = self._field
        try:
            value = cb_entry.parse_entry(self.text, node.params[field], node.spec.kinds[field], context.scene)
            value = node.descriptor(field).limit(value)
        except (ValueError, SyntaxError, TypeError) as error:
            self.report({'WARNING'}, str(error))
            return {'CANCELLED'}
        return apply(context, node, dict(node.params, **{field: value}))


class ALLSET_OT_inview_setting(bpy.types.Operator):
    bl_idname = 'allset.inview_setting'
    bl_label = 'In-View Editor Settings'
    bl_options = {'INTERNAL'}
    action: StringProperty(options={'SKIP_SAVE'})
    field: StringProperty(options={'SKIP_SAVE'})
    value: FloatProperty(options={'SKIP_SAVE'})

    def execute(self, context):
        node = target(context)
        if node is None:
            return {'CANCELLED'}
        name = self.field or state(context, node)['field']
        if name not in available_fields(node) and self.action != 'RESET':
            return {'CANCELLED'}
        saved = settings(context, node)
        if self.action in {'DEFAULT', 'VALUE'}:
            if not node_attributes.editable(node, name):
                return {'CANCELLED'}
            value = node.spec.defaults[name] if self.action == 'DEFAULT' else self.value
            return apply(context, node, dict(node.params, **{name: value}))
        if self.action == 'RESET':
            saved = {}
            state(context, node).update(position=None, width=180.0, height=None, scroll=0,
                                       field=node.spec.fields[0])
        elif self.action == 'TOGGLE':
            hidden = set(saved.get('hidden', set(available_fields(node))-set(node.spec.fields)))
            hidden.symmetric_difference_update({name})
            saved['hidden'] = sorted(hidden)
        elif self.action in {'UP', 'DOWN'}:
            order = [f for f in saved.get('order', ()) if f in available_fields(node)]
            order += [f for f in available_fields(node) if f not in order]
            index = order.index(name)
            other = max(0, min(len(order)-1, index+(-1 if self.action == 'UP' else 1)))
            order[index], order[other] = order[other], order[index]
            saved['order'] = order
        save_settings(context, node, saved)
        visible = fields(context, node)
        if state(context, node)['field'] not in visible:
            state(context, node)['field'] = visible[0] if visible else None
        context.area.tag_redraw()
        return {'FINISHED'}


class ALLSET_MT_inview_choices(bpy.types.Menu):
    bl_label = 'Attribute Values'

    def draw(self, context):
        node = target(context)
        if node is None:
            return
        name = state(context, node)['field']
        labels, values = node.choices(name)
        for label, value in zip(labels, values):
            op = self.layout.operator('allset.inview_setting', text=label)
            op.action, op.field, op.value = 'VALUE', name, value


class ALLSET_MT_inview_attributes(bpy.types.Menu):
    bl_label = 'In-View Editor'

    def draw(self, context):
        node = target(context)
        if node is None:
            return
        prefs = preferences.get(context)
        self.layout.prop(prefs, 'cb_speed', text='Slider Speed')
        self.layout.prop(prefs, 'cb_hyperbolic', text='Hyperbolic')
        self.layout.separator()
        for field in available_fields(node):
            op = self.layout.operator('allset.inview_select', text=node.spec.labels[field],
                                      icon='RADIOBUT_ON' if state(context, node)['field'] == field else 'RADIOBUT_OFF')
            op.field = field
        self.layout.separator()
        for action, label in [('DEFAULT', 'Reset Attribute'), ('TOGGLE', 'Hide Active Attribute'),
                              ('UP', 'Move Attribute Up'), ('DOWN', 'Move Attribute Down'), ('RESET', 'Reset Editor')]:
            self.layout.operator('allset.inview_setting', text=label).action = action
        self.layout.menu('ALLSET_MT_inview_visible', text='Displayed Attributes')


class ALLSET_MT_inview_visible(bpy.types.Menu):
    bl_label = 'Displayed Attributes'

    def draw(self, context):
        node = target(context)
        if node is None:
            return
        visible = fields(context, node)
        for field in available_fields(node):
            op = self.layout.operator('allset.inview_setting', text=node.spec.labels[field],
                                      icon='CHECKBOX_HLT' if field in visible else 'CHECKBOX_DEHLT')
            op.action, op.field = 'TOGGLE', field


@bpy.app.handlers.persistent
def clear(_dummy=None):
    global _generation
    _generation += 1
    _views.clear()
    _model_targets.clear()
    attribute_edit.clear()


classes = (ALLSET_OT_node_attribute_apply, ALLSET_OT_inview_select, ALLSET_OT_inview_cycle, ALLSET_OT_inview_scroll,
           ALLSET_OT_inview_number,
           ALLSET_OT_inview_setting, ALLSET_MT_inview_choices, ALLSET_MT_inview_visible,
           ALLSET_MT_inview_attributes)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    load_layouts()
    for handler in (bpy.app.handlers.load_pre, bpy.app.handlers.undo_pre, bpy.app.handlers.redo_pre):
        handler.append(clear)


def unregister():
    clear()
    for handler in (bpy.app.handlers.load_pre, bpy.app.handlers.undo_pre, bpy.app.handlers.redo_pre):
        if clear in handler:
            handler.remove(clear)
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


def load_layouts():
    try:
        path = layout_file()
        if path.is_file():
            text = path.read_text(encoding='utf-8')
            if isinstance(json.loads(text), dict):
                preferences.get().inview_layouts = text
    except (OSError, ValueError):
        pass
