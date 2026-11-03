"""Move tool Transform Constraint (Edge / Surface slide) and Ctrl+Shift+MMB edge slide. GUI:
tests/gui/gui_issue262_slide.py."""
import types
from importlib import import_module

import bpy

import kit

xc = import_module(kit.MODULE + ".operators.xform_constraint")
prefs = import_module(kit.MODULE + ".preferences")
menus = import_module(kit.MODULE + ".marking.menus")
draw = import_module(kit.MODULE + ".marking.draw")
ts_ui = import_module(kit.MODULE + ".ui.tool_settings")


def _edit_cube():
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    bpy.ops.mesh.primitive_cube_add()
    bpy.ops.object.mode_set(mode='EDIT')


def test_default_off_and_setting():
    p = prefs.get(bpy.context)
    assert p.bl_rna.properties["transform_constraint"].default == 'NONE'
    _edit_cube()
    p.transform_constraint = 'NONE'
    assert not xc.active(bpy.context)
    assert bpy.ops.allset.xform_constraint(mode='EDGE') == {'FINISHED'}
    assert p.transform_constraint == 'EDGE' and xc.active(bpy.context)
    bpy.ops.object.mode_set(mode='OBJECT')
    assert not xc.active(bpy.context), "object mode moves objects as before"
    p.transform_constraint = 'NONE'


def test_vertex_only():
    assert xc.vertex_only((True, False, False))
    assert not xc.vertex_only((True, True, False))
    assert not xc.vertex_only((False, False, True))


def test_marking_menu_radio_items():
    p = prefs.get(bpy.context)
    sub = dict(menus._constraints())["Transform Constraints"]
    labels = [label for label, _action in sub.items]
    assert labels == ["Off", "Edge Slide", "Surface Slide", "Along Normals"]
    p.transform_constraint = 'SURFACE'
    states = [draw.checked(action) for _label, action in sub.items]
    assert states == [False, False, True, False], states
    assert bpy.ops.allset.xform_constraint(mode='NORMAL') == {'FINISHED'}
    assert [draw.checked(action) for _label, action in sub.items] == [False, False, False, True]
    p.transform_constraint = 'NONE'


def test_reset_tool_turns_it_off():
    p = prefs.get(bpy.context)
    p.transform_constraint = 'EDGE'
    ts_ui.reset_maya_options(bpy.context, 'TRANSLATE')
    assert p.transform_constraint == 'NONE'


def test_ctrl_shift_mmb_in_move_tool():
    km = kit.maya_kc().keymaps["3D View Tool: Move"]
    items = [k for k in km.keymap_items if k.idname == "allset.component_slide" and k.active]
    assert len(items) == 1
    k = items[0]
    assert (k.type, k.value, k.ctrl, k.shift, k.alt) == ('MIDDLEMOUSE', 'PRESS', True, True, False)
    assert k.properties.mode == 'EDGE'


class _Layout:
    """Records `prop` calls with whether the row holding them is enabled."""

    def __init__(self, log, enabled=True):
        self.log, self.enabled = log, enabled

    def prop(self, data, name, **_kw):
        self.log.append((name, self.enabled))

    def operator(self, *_a, **_kw):
        return types.SimpleNamespace()

    def __getattr__(self, _name):
        def sub(*_a, **_kw):
            return _Layout(self.log, self.enabled)
        return sub

    def __setattr__(self, name, value):
        if name == "enabled" and "enabled" in self.__dict__:
            value = self.__dict__["enabled"] and value
        object.__setattr__(self, name, value)


def test_move_settings_row_live_in_object_mode():
    """#280: the Move tool's Transform Constraint is a stored setting that can be picked in object mode too (it
    acts once components are moved), not a greyed row."""
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    log = []
    ts_ui.draw_settings(_Layout(log), bpy.context, 'TRANSLATE')
    rows = [enabled for name, enabled in log if name == "transform_constraint"]
    assert rows == [True], log


def test_surface_slide_follows_the_handle():
    """#280: the Move handle's axis reaches the Surface slide (an X arrow drag keeps to X on the surface)."""
    props = bpy.ops.allset.component_slide.get_rna_type().properties
    assert {"constraint_axis", "orient_type", "orient_matrix"} <= set(props.keys())
