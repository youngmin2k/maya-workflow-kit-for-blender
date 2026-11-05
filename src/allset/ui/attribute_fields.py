# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya Ctrl+mouse numeric-field gestures in the kit's editors."""

import ast
from types import SimpleNamespace

import bpy

from .. import switch
from . import attribute_edit, cb_entry, node_attributes

_hover = {}
_watching = set()
_generation = 0


class NumericField:
    def __init__(self, root, path, index):
        self.root, self.path, self.index = root, path, index
        custom_at = max(path.rfind('["'), path.rfind("['")) if path.endswith(']') else -1
        if custom_at >= 0:
            owner_path, self.name = path[:custom_at], path[custom_at:]
            separator = bool(owner_path)
        else:
            owner_path, separator, self.name = path.rpartition('.')
        self.owner = root.path_resolve(owner_path) if separator else root
        self.property = self.owner.bl_rna.properties.get(self.name)
        self.custom_key = None
        if self.property is None and self.name.startswith('[') and self.name.endswith(']'):
            self.custom_key = ast.literal_eval(self.name[1:-1])
            value = self.owner[self.custom_key]
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError('The custom attribute is not a number')
            ui = self.owner.id_properties_ui(self.custom_key).as_dict()
            self.property = SimpleNamespace(type='INT' if isinstance(value, int) else 'FLOAT',
                                            subtype='NONE', is_readonly=False, is_array=False,
                                            hard_min=ui.get('min', -2147483648 if isinstance(value, int) else -3.4e38),
                                            hard_max=ui.get('max', 2147483647 if isinstance(value, int) else 3.4e38))
        if self.property is None or self.property.type not in {'FLOAT', 'INT'} or self.property.is_readonly:
            raise ValueError('The field is not an editable number')
        if self.property.is_array and (index < 0 or index >= self.property.array_length):
            raise ValueError('Choose a numeric vector component')
        self.kind = ('INT' if self.property.type == 'INT' else
                     'ROTATION' if self.property.subtype in {'ANGLE', 'EULER'} else
                     'LENGTH' if self.property.subtype in {'DISTANCE', 'TRANSLATION'} else 'NONE')

    def read(self):
        if self.custom_key is not None:
            return self.owner[self.custom_key]
        value = getattr(self.owner, self.name)
        return value[self.index] if self.property.is_array and self.index >= 0 else value

    def writable(self):
        if self.custom_key is None and self.owner.is_property_readonly(self.name):
            return False
        id_data = self.owner.id_data
        if isinstance(self.owner, bpy.types.NodeSocket) and self.owner.is_linked:
            return False
        if id_data is not None and not id_data.is_editable:
            return False
        animation = getattr(id_data, 'animation_data', None)
        if animation is not None:
            path = self.owner.path_from_id(self.name)
            if animation.drivers.find(path, index=max(self.index, 0)) is not None:
                return False
        if isinstance(self.owner, (bpy.types.Object, bpy.types.PoseBone)):
            locks = {'location': 'lock_location', 'rotation_euler': 'lock_rotation', 'scale': 'lock_scale'}
            if self.name in locks and self.index >= 0:
                return not getattr(self.owner, locks[self.name])[self.index]
        return True

    def descriptor(self, context):
        step = 0.1 if self.kind == 'INT' else 0.5 if self.kind == 'ROTATION' else 0.01
        return attribute_edit.Field(self.kind, step,
                                    cb_entry.to_display(self.property.hard_min, self.kind, context.scene),
                                    cb_entry.to_display(self.property.hard_max, self.kind, context.scene))

    def write(self, value):
        if self.custom_key is not None:
            self.owner[self.custom_key] = value
            self.owner.id_data.update_tag()
        elif self.property.is_array:
            getattr(self.owner, self.name)[self.index] = value
        else:
            setattr(self.owner, self.name, value)

    def confirm(self, context):
        from .. import compat
        from ..operators import auto_key
        if not self.undoable() or not auto_key.enabled(context.scene):
            return
        owner = self.owner.id_data
        curves = compat.id_fcurve_collection(owner) if owner is not None else None
        if curves is None:
            return
        path = self.owner.path_from_id(self.name)
        index = max(self.index, 0)
        if curves is not None and curves.find(path, index=index) is not None:
            self.owner.keyframe_insert(self.name, index=self.index if self.property.is_array else -1)

    def undoable(self):
        return not isinstance(self.owner.id_data, bpy.types.WindowManager)


class NodeField:
    def __init__(self, context, name):
        self.node = node_attributes.target(context)
        self.name = name
        if self.node is None or name not in self.node.params or self.node.spec.kinds[name] in {'ENUM', 'BOOL'}:
            raise ValueError('The history field is not an editable number')
        self.kind = self.node.spec.kinds[name]

    def read(self):
        return self.node.to_entry(self.name, self.node.params[self.name])

    def writable(self):
        from . import channel_box
        key = (channel_box.model_key(self.node.record, self.name) if hasattr(self.node, 'record') else
               channel_box.HISTORY_PREFIX+self.name)
        return self.node.valid() and not channel_box.is_locked(self.node.ob, key)

    def descriptor(self, context):
        return node_attributes.display_descriptor(self.node, self.name, context)

    def write(self, value):
        value = self.node.from_entry(self.name, value)
        self.node.preview(bpy.context, dict(self.node.params, **{self.name: value}))


def under_pointer(context):
    prop = getattr(context, 'property', None)
    if not prop:
        return None
    root, path, index = prop
    # Existing Channel Box fields own range selection and their field gestures.
    from . import channel_box, maya_dock
    role = maya_dock.area_role(context)
    channel_box_area = role == 'CHANNEL_BOX' or (role == 'STACK' and context.window_manager.allset_dock == 'CHANNEL_BOX')
    cell = channel_box.cell_key(path, root) if isinstance(root, bpy.types.Scene) else None
    if cell is not None:
        if channel_box_area:
            return None
        key, role = cell
        if role == 'VALUE' and key in channel_box.MAIN_BY_KEY:
            ob = channel_box.lead(context)
            data_path, component, kind = channel_box.channel_path(key)
            if ob is not None and kind in {'LOC', 'ROT', 'SCALE'}:
                if channel_box.is_locked(ob, key) or channel_box._non_euler_rot(ob, kind):
                    return None
                return NumericField(ob, data_path, component)
    if path.startswith(('allset_history.', 'allset_creation.')) and path.endswith('_text'):
        return NodeField(context, path.rsplit('.', 1)[1][:-5])
    return NumericField(root, path, index)


def kit_region(context):
    if context.area is None:
        return False
    if context.area.type == 'PROPERTIES':
        from . import marked_window, maya_dock
        space = context.area.spaces.active
        return (maya_dock.role(context.area) is not None or marked_window.kind_of(context.area) is not None
                or (space.show_properties_tool and not space.show_region_header))
    return context.area.type == 'VIEW_3D' and context.region.type == 'UI'


class ALLSET_OT_attribute_field_hover(bpy.types.Operator):
    bl_idname = 'allset.attribute_field_hover'
    bl_label = 'Attribute Field Hover'
    bl_options = {'INTERNAL'}

    def invoke(self, context, event):
        if not switch.is_on() or context.window is None:
            return {'PASS_THROUGH'}
        key = context.window.as_pointer()
        try:
            field = under_pointer(context)
            owner = getattr(field, 'owner', None)
            own_control = (isinstance(field, NodeField)
                           or (owner is not None and owner.bl_rna.identifier.startswith('ALLSET_')))
            if not kit_region(context) and not own_control:
                field = None
            if field is None or not field.writable():
                _hover.pop(key, None)
                return {'PASS_THROUGH'}
            _hover[key] = (field, context.area.as_pointer(), context.region.as_pointer(),
                           event.mouse_x, event.mouse_y)
        except (ReferenceError, RuntimeError, AttributeError, TypeError, ValueError):
            _hover.pop(key, None)
            return {'PASS_THROUGH'}
        if key not in _watching:
            bpy.ops.allset.attribute_field_watch('INVOKE_DEFAULT')
        return {'PASS_THROUGH'}


_handoff = {}


class ALLSET_OT_attribute_field_watch(bpy.types.Operator):
    bl_idname = 'allset.attribute_field_watch'
    bl_label = 'Attribute Field Gestures'
    bl_options = {'INTERNAL'}

    def invoke(self, context, event):
        self._window = context.window.as_pointer()
        self._generation = _generation
        _watching.add(self._window)
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if self._generation != _generation or not switch.is_on():
            _watching.discard(self._window)
            return {'CANCELLED', 'PASS_THROUGH'}
        entry = _hover.get(self._window)
        if entry is None:
            _watching.discard(self._window)
            return {'FINISHED', 'PASS_THROUGH'}
        field, area, region, x, y = entry
        if (event.type == 'WINDOW_DEACTIVATE' or (event.type in {'MOUSEMOVE', 'INBETWEEN_MOUSEMOVE'}
                and (context.area is None or context.area.as_pointer() != area
                     or context.region is None or context.region.as_pointer() != region
                     or abs(event.mouse_x-x) > 8 or abs(event.mouse_y-y) > 8))):
            self.cancel(context)
            return {'FINISHED', 'PASS_THROUGH'}
        if (event.type not in {'LEFTMOUSE', 'MIDDLEMOUSE', 'RIGHTMOUSE'} or event.value != 'PRESS'
                or not event.ctrl or event.alt or attribute_edit.busy(context)):
            return {'PASS_THROUGH'}
        if (context.area is None or context.area.as_pointer() != area or context.region is None
                or context.region.as_pointer() != region
                or abs(event.mouse_x-x) > 8 or abs(event.mouse_y-y) > 8):
            return {'PASS_THROUGH'}
        _handoff[self._window] = field, event.type, event.mouse_x
        try:
            result = bpy.ops.allset.attribute_field_drag('INVOKE_DEFAULT', True)
        finally:
            _handoff.pop(self._window, None)
        return {'RUNNING_MODAL'} if 'RUNNING_MODAL' in result else {'PASS_THROUGH'}

    def cancel(self, context):
        _watching.discard(self._window)
        _hover.pop(self._window, None)


class ALLSET_OT_attribute_field_drag(bpy.types.Operator):
    bl_idname = 'allset.attribute_field_drag'
    bl_label = 'Adjust Attribute Value'
    bl_options = {'INTERNAL', 'BLOCKING'}

    def invoke(self, context, event):
        if context.window is None:
            return {'CANCELLED'}
        self._window = context.window.as_pointer()
        entry = _handoff.get(self._window)
        if entry is None:
            return {'PASS_THROUGH'}
        self._field, self._button, self._x = entry
        if not self._field.writable() or not attribute_edit.claim(context, self):
            return {'CANCELLED'}
        self._start = self._field.read()
        self._scene, self._frame = context.scene, context.scene.frame_current
        self._object = context.active_object
        self._generation = _generation
        self._finished = False
        self._factor = {'LEFTMOUSE': .1, 'MIDDLEMOUSE': 1.0, 'RIGHTMOUSE': 10.0}[self._button]
        self._drag = attribute_edit.Drag(cb_entry.to_display(self._start, self._field.kind, context.scene),
                                         self._field.descriptor(context))
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def _finish(self, context, cancel=False):
        if getattr(self, '_finished', True):
            return {'CANCELLED'}
        self._finished = True
        value = self._start
        try:
            value = self._field.read()
            if cancel and value != self._start:
                self._field.write(self._start)
            if isinstance(self._field, NodeField):
                if not cancel and value != self._start:
                    self._field.node.commit(context, self._field.node.params)
                self._field.node.finish()
            elif not cancel and value != self._start:
                self._field.confirm(context)
        except (ReferenceError, RuntimeError, AttributeError, TypeError, ValueError):
            cancel = True
        finally:
            attribute_edit.release(self._window, self)
            _hover.pop(self._window, None)
        if not cancel and value != self._start and (isinstance(self._field, NodeField) or self._field.undoable()):
            from .. import undo_steps
            undo_steps.push('Edit Attribute Value')
        return {'CANCELLED'} if cancel or value == self._start else {'FINISHED'}

    def modal(self, context, event):
        try:
            if (self._generation != _generation or context.scene != self._scene
                    or context.scene.frame_current != self._frame or context.active_object != self._object
                    or not self._field.writable()):
                return self._finish(context, cancel=True)
            if event.type in {'MOUSEMOVE', 'INBETWEEN_MOUSEMOVE'}:
                dx, self._x = event.mouse_x-self._x, event.mouse_x
                value = self._drag.move(dx/(context.preferences.system.ui_scale or 1.0), speed=self._factor)
                value = cb_entry.from_display(value, self._field.kind, context.scene)
                if self._field.kind == 'INT':
                    value = attribute_edit.nearest_integer(value)
                if self._field.read() != value:
                    self._field.write(value)
                    context.area.tag_redraw()
            elif event.type == self._button and event.value == 'RELEASE':
                return self._finish(context)
            elif event.type in {'ESC', 'WINDOW_DEACTIVATE'}:
                return self._finish(context, cancel=True)
        except (ReferenceError, RuntimeError, AttributeError, TypeError, ValueError) as error:
            self.report({'WARNING'}, str(error))
            return self._finish(context, cancel=True)
        return {'RUNNING_MODAL'}

    def cancel(self, context):
        self._finish(context, cancel=True)


@bpy.app.handlers.persistent
def clear(_dummy=None):
    global _generation
    _generation += 1
    _hover.clear()
    _watching.clear()
    _handoff.clear()


classes = (ALLSET_OT_attribute_field_hover, ALLSET_OT_attribute_field_watch, ALLSET_OT_attribute_field_drag)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.app.handlers.load_pre.append(clear)


def unregister():
    clear()
    if clear in bpy.app.handlers.load_pre:
        bpy.app.handlers.load_pre.remove(clear)
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
