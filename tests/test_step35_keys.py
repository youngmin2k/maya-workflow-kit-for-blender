"""Maya key batch — Ctrl+Alt+LMB box zoom, Ctrl+T, Y, Ctrl+Shift+X/Q, Return, F2–F6.
GUI: tests/gui/gui_step35_keys.py."""

from importlib import import_module

import bpy

import kit

tool_keys = import_module(kit.MODULE + ".operators.tool_keys")
preferences = import_module(kit.MODULE + ".preferences")


def _items(km_name, etype, value='PRESS', shift=False, ctrl=False, alt=False):
    km = kit.maya_kc().keymaps[km_name]
    return [(k.idname, {p: getattr(k.properties, p) for p in k.properties.keys()} if k.properties else {})
            for k in km.keymap_items if k.active and k.type == etype and k.value == value
            and k.shift == shift and k.ctrl == ctrl and k.alt == alt and not k.oskey]


def test_bindings():
    assert _items("3D View", 'LEFTMOUSE', ctrl=True, alt=True)[0][0] == "allset.box_zoom"
    for km in ("Object Mode", "Mesh"):
        assert ("wm.tool_set_by_id", {"name": "builtin.transform"}) in [
            (i, {k: v for k, v in p.items() if k == "name"}) for i, p in _items(km, 'T', ctrl=True)], km
        assert [i for i, _p in _items(km, 'Y')] == ["allset.last_tool"], km
        knife = _items(km, 'X', shift=True, ctrl=True)
        quad = _items(km, 'Q', shift=True, ctrl=True)
        assert knife == [("allset.menu_tool", {"tool": "allset.multi_cut_tool", "edit": True})], (km, knife)
        assert quad == [("allset.quad_draw_start", {})], (km, quad)      # the kit Quad Draw


def test_f_keys_are_menu_sets_and_view_keys_kept():
    sets = {}
    for key in ('F2', 'F3', 'F4', 'F5', 'F6'):
        found = _items("Screen", key)
        assert found and found[0][0] == "allset.menu_set", (key, found)
        sets[key] = found[0][1]["set"]
        assert not [i for i, _p in _items("3D View", key)], (key, _items("3D View", key))
    assert sets == {'F2': 'modelingMenuSet', 'F3': 'riggingMenuSet', 'F4': 'animationMenuSet',
                    'F5': 'dynamicsMenuSet', 'F6': 'renderingMenuSet'}, sets
    # F1 = Maya Help (Window keymap); ortho views still on Ctrl+F1-F3.
    assert not _items("3D View", 'F1'), _items("3D View", 'F1')
    for key in ('F1', 'F2', 'F3'):
        assert _items("3D View", key, ctrl=True)[0][0] == "view3d.view_axis", key


def test_return_no_rename_popover_in_3d_view():
    assert not _items("3D View", 'RET'), _items("3D View", 'RET')


def test_menu_set_operator():
    ap = preferences.get()
    for sid in ('riggingMenuSet', 'renderingMenuSet', 'modelingMenuSet'):
        assert bpy.ops.allset.menu_set(set=sid) == {'FINISHED'}
        assert ap.menu_set == sid


def test_last_tool_memory():
    tool_keys.LAST.clear()
    for idname, sacred in (("builtin.select_box", True), ("builtin.move", True), ("builtin.transform", True),
                           ("builtin.knife", False), ("builtin.extrude_region", False)):
        assert tool_keys.is_sacred(idname) == sacred, idname
    tool_keys.remember('EDIT_MESH', "builtin.knife")
    tool_keys.remember('EDIT_MESH', "builtin.move")      # sacred: not remembered
    tool_keys.remember('OBJECT', "builtin.measure")
    assert tool_keys.LAST == {'EDIT_MESH': "builtin.knife", 'OBJECT': "builtin.measure"}
    tool_keys.LAST.clear()
    assert bpy.ops.allset.last_tool() == {'CANCELLED'}, "nothing remembered yet"


def test_box_zoom_direction():
    assert tool_keys.zoom_direction(100, 300) == 'IN'
    assert tool_keys.zoom_direction(300, 100) == 'OUT'
