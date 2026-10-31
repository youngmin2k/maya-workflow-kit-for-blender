"""Maya Status Line input line (Abs / Rel transform, Rename, Select by name) and the greyed
Construction History toggle. GUI: tests/gui/gui_step75_input_line.py."""

from importlib import import_module

import bmesh
import bpy
from mathutils import Vector

import kit

il = import_module(kit.MODULE + ".ui.input_line")
notices = import_module(kit.MODULE + ".ui.notices")


def _scene_cm():
    sc = bpy.context.scene
    sc.unit_settings.system = 'METRIC'
    sc.unit_settings.length_unit = 'CENTIMETERS'
    sc.unit_settings.scale_length = 1.0
    return sc


def _clear():
    if bpy.context.active_object is not None and bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    for me in list(bpy.data.meshes):
        bpy.data.meshes.remove(me)


def _cube(name):
    bpy.ops.mesh.primitive_cube_add()
    ob = bpy.context.active_object
    ob.name = name
    ob.data.name = name.replace("pCube", "pCubeShape")
    return ob


def _inp():
    return bpy.context.scene.allset_input


def test_abs_move_in_display_units():
    _clear()
    _scene_cm()
    ob = _cube("pCube1")
    inp = _inp()
    inp.mode = 'ABS'
    inp.x, inp.y, inp.z = "1", "2", "3"          # cm in a cm scene
    assert (ob.matrix_world.translation - Vector((0.01, 0.02, 0.03))).length < 1e-6
    inp.x = "5 m"                                 # units still work
    assert abs(ob.location.x - 5.0) < 1e-6 and abs(ob.location.y - 0.02) < 1e-6
    assert inp.x == "" and inp.y == ""            # the fields clear (Maya)


def test_abs_move_keeps_empty_axes_and_pivot_delta():
    _clear()
    _scene_cm()
    ob = _cube("pCube1")
    ob.delta_location = (0.0, 0.0, 0.5)
    ob.location = (0.1, 0.2, 0.0)
    bpy.context.view_layer.update()
    il.transform(bpy.context, ["", "10", ""], relative=False)
    bpy.context.view_layer.update()
    w = ob.matrix_world.translation
    assert abs(w.x - 0.1) < 1e-6 and abs(w.y - 0.10) < 1e-6 and abs(w.z - 0.5) < 1e-6
    assert abs(ob.delta_location.z - 0.5) < 1e-9


def test_rel_and_tools():
    _clear()
    _scene_cm()
    ob = _cube("pCube1")
    il.transform(bpy.context, ["10", "", "-5"], relative=True)
    assert (ob.location - Vector((0.10, 0.0, -0.05))).length < 1e-6
    orig = il.tool_kind
    try:
        il.tool_kind = lambda _c: 'ROTATE'
        il.transform(bpy.context, ["", "", "90"], relative=False)
        il.transform(bpy.context, ["", "", "45"], relative=True)
        assert abs(ob.rotation_euler.z - 2.356194) < 1e-5
        il.tool_kind = lambda _c: 'SCALE'
        il.transform(bpy.context, ["2", "", ""], relative=False)
        il.transform(bpy.context, ["3", "", ""], relative=True)
        assert abs(ob.scale.x - 6.0) < 1e-6 and abs(ob.scale.y - 1.0) < 1e-6
    finally:
        il.tool_kind = orig


def test_edit_mode_move_components():
    _clear()
    _scene_cm()
    ob = _cube("pCube1")
    bpy.ops.object.mode_set(mode='EDIT')
    bm = bmesh.from_edit_mesh(ob.data)
    for v in bm.verts:
        v.select = v.co.z > 0
    bm.select_flush(True)
    il.transform(bpy.context, ["", "", "300"], relative=False)     # top face centre -> z = 3 m
    bm = bmesh.from_edit_mesh(ob.data)
    tops = [v.co.z for v in bm.verts if v.select]
    assert len(tops) == 4 and all(abs(z - 3.0) < 1e-6 for z in tops), tops
    assert all(abs(v.co.z + 1.0) < 1e-6 for v in bm.verts if not v.select)
    bpy.ops.object.mode_set(mode='OBJECT')


def test_rename_rules():
    assert il.clean_name(" my box ") == "my_box"
    assert il.clean_name("1box") is None and il.clean_name("bad-name") is None
    assert il.rename_plan("box", ["a", "b", "c"], {"box1"}) == ["box", "box2", "box3"]
    assert il.rename_plan("box", ["a"], {"box"}) == ["box1"]
    assert il.shape_name("box") == "boxShape" and il.shape_name("box12") == "boxShape12"


def test_rename_selection_and_field_shows_lead():
    _clear()
    a, b = _cube("pCube1"), _cube("pCube2")
    a.select_set(True)
    b.select_set(True)
    bpy.context.view_layer.objects.active = b
    inp = _inp()
    inp.mode = 'RENAME'
    assert inp.text == "pCube2"                   # Maya shows the lead's name
    inp.text = "crate"
    assert b.name == "crate" and a.name == "crate1"
    assert b.data.name == "crateShape" and a.data.name == "crateShape1"
    assert inp.text == "crate"
    inp.text = "2bad"                             # invalid: nothing renamed
    assert b.name == "crate"
    assert "not a valid name" in notices.current()


def test_select_by_name_wildcards():
    _clear()
    for n in ("pCube1", "pCube2", "pSphere1"):
        _cube(n)
    inp = _inp()
    inp.mode = 'SELECT'
    inp.text = "pCube*"
    assert sorted(o.name for o in bpy.context.selected_objects) == ["pCube1", "pCube2"]
    assert bpy.context.view_layer.objects.active.name == "pCube2"
    assert inp.text == "" and "pCube1 pCube2" in notices.current()
    inp.text = "p?phere1"
    assert [o.name for o in bpy.context.selected_objects] == ["pSphere1"]
    inp.text = "nothing*"
    assert [o.name for o in bpy.context.selected_objects] == ["pSphere1"]   # selection kept
    assert inp.text == "nothing*" and "no object matches" in notices.current()


def test_history_notice_and_groups():
    sl = import_module(kit.MODULE + ".ui.status_line")
    groups = [g for g, _d in sl.GROUPS]
    assert groups.index("HISTORY") < groups.index("RENDER") < groups.index("INPUT") < groups.index("EDITORS")
    # Construction History is Maya's toggle now, not a greyed widget with a notice
    assert il.HISTORY_PATH not in notices.PANEL_NOTICES
    assert bpy.context.window_manager.allset_construction_history is True
    assert isinstance(bpy.context.scene.bl_rna.properties["allset_input"], bpy.types.PointerProperty)
