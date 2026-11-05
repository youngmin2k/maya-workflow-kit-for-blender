"""Option editors reuse every existing field schema and store UI values outside scene history."""
from importlib import import_module
import json

import bpy
import kit

editor = import_module(kit.MODULE+'.ui.option_editor')
options = import_module(kit.MODULE+'.operators.option_windows')
fields = import_module(kit.MODULE+'.ui.attribute_fields')
repeat = import_module(kit.MODULE+'.operators.repeat_maya')


def test_all_option_schemas_have_equivalent_numeric_owners():
    assert not editor._groups
    for spec in options.WINDOWS:
        editor.prepare(spec.key)
        owner = editor.owner(bpy.context.window_manager, spec.key)
        for field in spec.fields:
            setattr(owner, field.name, field.default)
        values = options.values_of(spec, owner)
        assert set(values) == set(spec.defaults())
        json.dumps(values)
        for field in spec.fields:
            if field.kind in {'int', 'float', 'length'}:
                path = 'allset_options_'+spec.key+'.'+field.name
                numeric = fields.NumericField(bpy.context.window_manager, path, -1)
                assert numeric.writable() and not numeric.undoable()


def test_options_ui_does_not_replace_the_repeat_command():
    assert not repeat.repeatable('ALLSET_OT_option_editor_open')
    assert not repeat.repeatable('ALLSET_OT_option_editor_action')


def test_changed_origin_editor_is_not_used_as_a_viewport():
    window = bpy.context.window
    area = next(a for a in window.screen.areas if a.type == 'VIEW_3D')
    data = dict(window=window.as_pointer(), area=area.as_pointer(), area_type='VIEW_3D')
    try:
        area.type = 'IMAGE_EDITOR'
        _window, source, _region = editor.origin(data)
        assert source is None or source.type == 'VIEW_3D'
    finally:
        area.type = 'VIEW_3D'


def test_disable_releases_lazy_option_schemas():
    keys = list(editor._groups)
    kit.disable()
    assert not editor._groups
    assert all(not hasattr(bpy.types.WindowManager, 'allset_options_'+key) for key in keys)
    kit.enable()
    assert not editor._groups
