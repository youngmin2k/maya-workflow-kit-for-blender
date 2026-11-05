# SPDX-License-Identifier: GPL-3.0-or-later
"""Modeless command options using the kit's existing floating Properties editors."""

import json

import bpy
from bpy.props import PointerProperty, StringProperty

from .. import live_refs, undo_steps
from ..operators import menu_extras, option_windows
from . import marked_window, window_places

KIND = 'COMMAND_OPTIONS'
_sessions = {}
_groups = {}


def prepare(key):
    """Allocate a command's RNA fields when its options are first used."""
    if key in _groups:
        return
    spec = option_windows._BY_KEY[key]
    group = type('ALLSET_PG_options_'+key, (bpy.types.PropertyGroup,),
                 {'__annotations__': {field.name: field.prop() for field in spec.fields}})
    bpy.utils.register_class(group)
    setattr(bpy.types.WindowManager, 'allset_options_'+key, PointerProperty(type=group, options={'SKIP_SAVE'}))
    _groups[key] = group


def owner(wm, key):
    return getattr(wm, 'allset_options_'+key)


def session(context):
    return _sessions.get(context.window.as_pointer()) if context.window else None


def find(context, key):
    for pointer, data in list(_sessions.items()):
        window = live_refs.window(pointer)
        if window is None:
            _sessions.pop(pointer, None)
        elif data['key'] == key:
            return window
    return None


def origin(data):
    window, area = live_refs.find_area(data['area'], data['window'])
    if area is None:
        window = live_refs.window(data['window'])
        if window is not None:
            area = max((a for a in window.screen.areas if a.type == data['area_type']),
                       key=lambda a: a.width*a.height, default=None)
    if area is None:
        return None, None, None
    region = next((r for r in area.regions if r.type == 'WINDOW'), None)
    return window, area, region


class ALLSET_OT_option_editor_open(bpy.types.Operator):
    bl_idname = 'allset.option_editor_open'
    bl_label = 'Command Options'
    bl_options = {'INTERNAL'}
    key: StringProperty(options={'SKIP_SAVE'})
    values: StringProperty(default='{}', options={'SKIP_SAVE'})

    def execute(self, context):
        spec = option_windows._BY_KEY.get(self.key)
        if spec is None or context.window is None or bpy.app.background:
            return {'CANCELLED'}
        if find(context, self.key) is not None:
            return {'FINISHED'}
        source = context.area
        if source is None or source.type not in {'VIEW_3D', 'IMAGE_EDITOR', 'GRAPH_EDITOR', 'DOPESHEET_EDITOR', 'NLA_EDITOR'}:
            source = max((a for a in context.window.screen.areas if a.type == 'VIEW_3D'),
                         key=lambda a: a.width*a.height, default=None)
        if source is None:
            self.report({'WARNING'}, 'Open command options from its modeling or animation editor')
            return {'CANCELLED'}
        origin_data = dict(key=self.key, window=context.window.as_pointer(), area=source.as_pointer(),
                           area_type=source.type)
        place_key = 'options:'+self.key
        if window_places.place(place_key) is None:
            scale = context.preferences.system.ui_scale or 1.0
            width = min(source.width, round(spec.width*scale))
            height = min(source.height, round(max(280, 170+26*len(spec.fields))*scale))
            window_places.remember(place_key, (context.window.x+source.x, context.window.y+source.y,
                                               width, height))
        window = menu_extras.open_window(context, source, place_key)
        if window is None:
            return {'FINISHED'} if window_places.deferred() else {'CANCELLED'}
        prepare(self.key)
        holder = owner(context.window_manager, self.key)
        defaults = spec.defaults()
        for name, value in {**defaults, **json.loads(self.values)}.items():
            if name in defaults:
                setattr(holder, name, value)
        _sessions[window.as_pointer()] = origin_data
        area = window.screen.areas[0]
        area.type = 'PROPERTIES'
        if not marked_window.set_kind(area, KIND, window):
            marked_window.set_kind_later(window, area, KIND)
        return {'FINISHED'}


class ALLSET_OT_option_editor_action(bpy.types.Operator):
    bl_idname = 'allset.option_editor_action'
    bl_label = 'Option Window Action'
    bl_options = {'INTERNAL'}
    action: StringProperty(options={'SKIP_SAVE'})

    def execute(self, context):
        data = session(context)
        if data is None:
            return {'CANCELLED'}
        spec = option_windows._BY_KEY[data['key']]
        holder = owner(context.window_manager, spec.key)
        if self.action == 'CLOSE':
            _sessions.pop(context.window.as_pointer(), None)
            marked_window.close_later(context.window)
        elif self.action == 'RESET':
            for field in spec.fields:
                setattr(holder, field.name, field.default)
            option_windows.store(spec.key, None)
        elif self.action == 'SAVE':
            option_windows.store(spec.key, option_windows.values_of(spec, holder))
        elif self.action in {'APPLY', 'RUN'}:
            window, area, region = origin(data)
            if region is None:
                self.report({'WARNING'}, 'The editor that opened these options is no longer available')
                return {'CANCELLED'}
            values = option_windows.values_of(spec, holder)
            with context.temp_override(window=window, area=area, region=region):
                apply_run = getattr(spec, 'apply_run', None) if self.action == 'APPLY' else None
                if apply_run is None:
                    result = getattr(bpy.ops.allset, 'opt_'+spec.key)('EXEC_DEFAULT', **values)
                else:
                    def apply_command():
                        res = apply_run(bpy.context, values)
                        option_windows.store(spec.key, values)
                        if isinstance(res, str):
                            self.report({'WARNING'}, res)
                            return {'CANCELLED'}
                        return {'FINISHED'} if res is None else res
                    result = undo_steps.command(spec.title, apply_command)
            if 'FINISHED' not in result:
                return result
            if self.action == 'RUN':
                _sessions.pop(context.window.as_pointer(), None)
                marked_window.close_later(context.window)
        else:
            return {'CANCELLED'}
        return {'FINISHED'}


class ALLSET_OT_option_editor_key(bpy.types.Operator):
    bl_idname = 'allset.option_editor_key'
    bl_label = 'Command Options Keyboard Action'
    bl_options = {'INTERNAL'}
    action: StringProperty(options={'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        return marked_window.context_kind(context) == KIND and session(context) is not None

    def execute(self, context):
        return bpy.ops.allset.option_editor_action(action=self.action)


class ALLSET_PT_command_options(bpy.types.Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Tool'
    bl_label = 'Command Options'
    bl_options = {'HIDE_HEADER'}
    bl_order = -300

    @classmethod
    def poll(cls, context):
        return marked_window.context_kind(context) == KIND and session(context) is not None

    def draw(self, context):
        spec = option_windows._BY_KEY[session(context)['key']]
        layout = self.layout
        layout.label(text=spec.title)
        row = layout.row(align=True)
        row.operator('allset.option_editor_action', text='Save Settings').action = 'SAVE'
        row.operator('allset.option_editor_action', text='Reset Settings').action = 'RESET'
        layout.separator()
        option_windows.draw_fields(spec, layout.column(), owner(context.window_manager, spec.key))
        layout.separator()
        row = layout.row(align=True)
        for action, text in (('RUN', spec.action), ('APPLY', spec.apply_text), ('CLOSE', 'Close')):
            row.operator('allset.option_editor_action', text=text).action = action


@bpy.app.handlers.persistent
def clear(_dummy=None):
    _sessions.clear()


classes = (ALLSET_OT_option_editor_open, ALLSET_OT_option_editor_action, ALLSET_OT_option_editor_key,
           ALLSET_PT_command_options)


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
    for key, group in reversed(list(_groups.items())):
        delattr(bpy.types.WindowManager, 'allset_options_'+key)
        bpy.utils.unregister_class(group)
    _groups.clear()
