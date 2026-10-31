"""Key batch 2 — Graph Editor 1/2/3, Shift+Q / Alt+Q select marking menus, Ctrl+Alt+Left/Right
Spin Edge, Shift+G repeat at the mouse, Ctrl+Shift+C camera from view. GUI: tests/gui/gui_step78_key_batch.py."""

from importlib import import_module

import bpy
from mathutils import Matrix, Vector

import kit

kb = import_module(kit.MODULE + ".operators.key_batch")
display = import_module(kit.MODULE + ".operators.display")
graph_keys = import_module(kit.MODULE + ".operators.graph_keys")
menus = import_module(kit.MODULE + ".marking.menus")
taphold = import_module(kit.MODULE + ".operators.taphold")


def _items(km, key, **mods):
    kc = kit.maya_kc()
    want = {m: mods.get(m, False) for m in ("shift", "ctrl", "alt")}
    return [k for k in kc.keymaps[km].keymap_items if k.active and k.type == key and k.value == 'PRESS'
            and all(getattr(k, m) == v for m, v in want.items())]


def test_keymap_items():
    for key, mode in (("ONE", "ABSOLUTE"), ("TWO", "STACKED"), ("THREE", "NORMALIZED")):
        it = _items("Graph Editor", key)
        assert [k.idname for k in it] == ["allset.graph_view_mode"], (key, it)
        assert it[0].properties.mode == mode
    for km in ("Object Mode", "Mesh"):
        for mods, binding in (({"shift": True}, "select_component"), ({"alt": True}, "select_polygon")):
            it = _items(km, "Q", **mods)
            assert [k.idname for k in it] == ["allset.tap_hold"], (km, mods, it)
            assert it[0].properties.binding == binding
    for key, ccw in (("LEFT_ARROW", True), ("RIGHT_ARROW", False)):
        it = _items("Mesh", key, ctrl=True, alt=True)
        assert [k.idname for k in it] == ["mesh.edge_rotate"] and it[0].properties.use_ccw == ccw, key
    assert [k.idname for k in _items("3D View", "G", shift=True)] == ["allset.repeat_at_mouse"]
    assert [k.idname for k in _items("Object Mode", "C", shift=True, ctrl=True)] == ["allset.camera_from_view"]
    assert {"select_component", "select_polygon"} <= set(taphold.binding_names())


def test_menus_registered():
    assert "SELECT_COMPONENT" in menus.MENUS and "SELECT_POLYGON" in menus.MENUS
    poly = menus.MENUS["SELECT_POLYGON"].radial
    assert [poly[d][0] for d in ("N", "E", "S", "W")] == ["Vertices", "Edges", "Faces", "UVs"]
    comp = menus.MENUS["SELECT_COMPONENT"].radial
    assert comp["SE"][1] == ("allset.component_mask", {"kind": "FACE"})


def test_toggled_mask():
    t = display.toggled_mask
    assert t((True, False, False), "EDGE") == (True, True, False)
    assert t((True, True, False), "VERT") == (False, True, False)
    assert t((True, False, False), "VERT") == (True, False, False), "Blender keeps one mode on"
    assert t((False, True, False), "ALL") == (True, True, True)


def _cube():
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o)
    bpy.ops.mesh.primitive_cube_add()
    return bpy.context.active_object


def test_component_mask_operator():
    _cube()
    ts = bpy.context.scene.tool_settings
    bpy.ops.allset.component_mask(kind="EDGE")
    assert bpy.context.mode == 'EDIT_MESH'
    first = tuple(ts.mesh_select_mode)
    assert first[1], first
    bpy.ops.allset.component_mask(kind="ALL")
    assert tuple(ts.mesh_select_mode) == (True, True, True)
    bpy.ops.object.mode_set(mode='OBJECT')


def test_ground_point():
    gp = kb.ground_point
    assert (gp(Vector((0, -10, 10)), Vector((0, 1, -1)).normalized()) - Vector((0, 0, 0))).length < 1e-6
    assert (gp(Vector((3, 0, 5)), Vector((0, 0, -1))) - Vector((3, 0, 0))).length < 1e-6
    assert gp(Vector((0, 0, 5)), Vector((1, 0, 0))) is None, "along the plane"
    assert gp(Vector((0, 0, 5)), Vector((0, 0, 1))) is None, "looking away"


def test_move_to_keeps_children_with_parent():
    a = _cube()
    bpy.ops.mesh.primitive_cube_add(location=(2, 0, 0))
    b = bpy.context.active_object
    b.parent = a
    bpy.context.view_layer.update()
    kb.move_to([a, b], Vector((5, 5, 0)))
    bpy.context.view_layer.update()
    assert (a.matrix_world.translation - Vector((5, 5, 0))).length < 1e-6
    assert (b.matrix_world.translation - Vector((7, 5, 0))).length < 1e-6, "the child keeps its offset"


def test_camera_matrix_inverts_view():
    view = Matrix.Translation((0, 0, -10)) @ Matrix.Rotation(0.3, 4, 'X')
    cam = kb.camera_matrix(view)
    assert ((cam @ view) - Matrix.Identity(4)).to_3x3().to_quaternion().angle < 1e-6
    assert ((view @ cam.translation)).length < 1e-6, "camera at the view's eye"


def test_graph_view_mode_requires_graph_editor():
    assert not bpy.ops.allset.graph_view_mode.poll()
    names = [m[0] for m in graph_keys.VIEW_MODES]
    assert names == ["ABSOLUTE", "STACKED", "NORMALIZED"]
