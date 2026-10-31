"""Smart Extrude (Shift+manipulator on faces/edges), taking back a copy or
extrusion that didn't move, only the transform manipulator, hold-menu check boxes.
The drag itself: tests/gui/gui_step26_smart_extrude.py.
"""

from importlib import import_module
from types import SimpleNamespace

import bmesh
import bpy

import kit

manip = import_module(kit.MODULE + ".operators.manip")
engine = import_module(kit.MODULE + ".marking.engine")
draw = import_module(kit.MODULE + ".marking.draw")
mm = import_module(kit.MODULE + ".marking.menus")
preferences = import_module(kit.MODULE + ".preferences")


def _cube(mode, faces=(0,)):
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    bpy.ops.mesh.primitive_cube_add()
    ob = bpy.context.active_object
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_mode(type=mode)
    bpy.ops.mesh.select_all(action='DESELECT')
    bm = bmesh.from_edit_mesh(ob.data)
    seq = bm.faces if mode == 'FACE' else bm.edges if mode == 'EDGE' else bm.verts
    seq.ensure_lookup_table()
    for i in faces:
        seq[i].select = True
    bm.select_flush_mode()
    bmesh.update_edit_mesh(ob.data)
    return ob


def _counts(ob):
    bm = bmesh.from_edit_mesh(ob.data)
    return len(bm.verts), len(bm.edges), len(bm.faces)


class _Gizmo:
    def __init__(self, on):
        self.on = on

    def __enter__(self):
        self.saved = manip.from_xform_gizmo
        manip.from_xform_gizmo = lambda _c: self.on

    def __exit__(self, *exc):
        manip.from_xform_gizmo = self.saved


def test_kind_by_mode_and_gizmo():
    ob = _cube('FACE')
    with _Gizmo(True):
        assert manip.kind(bpy.context) == 'EXTRUDE'
        bpy.ops.mesh.select_mode(type='VERT')
        assert manip.kind(bpy.context) == 'EXTRUDE', "vertex mode: Smart Extrude too (Maya 2026, #183)"
        bpy.ops.mesh.select_mode(type='EDGE')
        assert manip.kind(bpy.context) == 'EXTRUDE'
        preferences.get().smart_extrude = False
        assert manip.kind(bpy.context) is None, "option off"
        preferences.get().smart_extrude = True
    with _Gizmo(False):
        assert manip.kind(bpy.context) is None, "not the transform manipulator"
    bpy.ops.object.mode_set(mode='OBJECT')
    assert ob.name in bpy.data.objects


def test_xform_gizmo_check_reads_the_gizmo_group():
    ctx = SimpleNamespace(gizmo_group=SimpleNamespace(bl_idname="VIEW3D_GGT_xform_gizmo"))
    assert manip.from_xform_gizmo(ctx)
    ctx.gizmo_group.bl_idname = "VIEW3D_GGT_light_spot"
    assert not manip.from_xform_gizmo(ctx)
    assert not manip.from_xform_gizmo(SimpleNamespace())


def test_extrude_face_then_take_back():
    ob = _cube('FACE')
    state = manip.start_extrude(bpy.context)
    assert _counts(ob) == (12, 20, 10), _counts(ob)    # one face extruded in place
    assert not manip.moved(state)
    manip.revert(state)                                 # cancelled drag
    assert _counts(ob) == (8, 12, 6), _counts(ob)
    manip.cleanup(state)
    assert not any(name in bpy.data.meshes for name in state["saved"].values()), "saved copy removed"
    bpy.ops.object.mode_set(mode='OBJECT')


def test_extrude_kept_when_moved():
    ob = _cube('FACE')
    state = manip.start_extrude(bpy.context)
    bpy.ops.transform.translate(value=(0, 0, 0.5))
    assert manip.moved(state)
    manip.cleanup(state)
    assert _counts(ob) == (12, 20, 10)
    bpy.ops.object.mode_set(mode='OBJECT')


def test_extrude_edge_strip():
    ob = _cube('EDGE', faces=(0,))
    manip.cleanup(manip.start_extrude(bpy.context))
    assert _counts(ob) == (10, 15, 7), _counts(ob)     # one edge -> 2 verts, 3 edges, 1 quad
    bpy.ops.object.mode_set(mode='OBJECT')


def _vertices(ob):
    bm = bmesh.from_edit_mesh(ob.data)
    return [v.co.copy() for v in bm.verts if v.select]


def test_extrude_vertex():
    """#183: Shift+drag with one cube corner selected = polyExtrudeVertex (Width 0.5,
    Length 0): 8/12/6 -> 11/18/9, and the corner plus its three new base vertices are selected for the drag."""
    ob = _cube('VERT', faces=(0,))
    corner = _vertices(ob)[0]
    state = manip.start_extrude(bpy.context)
    assert _counts(ob) == (11, 18, 9), _counts(ob)
    sel = _vertices(ob)
    assert len(sel) == 4 and any((v - corner).length < 1e-6 for v in sel), sel    # Length 0: the tip stays
    assert not manip.moved(state)
    manip.revert(state)
    assert _counts(ob) == (8, 12, 6), _counts(ob)
    manip.cleanup(state)
    bpy.ops.object.mode_set(mode='OBJECT')


def test_extrude_two_vertices():
    """Two corners of one edge -> 14/24/12."""
    ob = _cube('VERT', faces=(0,))
    bm = bmesh.from_edit_mesh(ob.data)
    v0 = next(v for v in bm.verts if v.select)
    v0.link_edges[0].other_vert(v0).select = True
    bmesh.update_edit_mesh(ob.data)
    manip.cleanup(manip.start_extrude(bpy.context))
    assert _counts(ob) == (14, 24, 12), _counts(ob)
    assert len(_vertices(ob)) == 8, len(_vertices(ob))
    bpy.ops.object.mode_set(mode='OBJECT')


def test_duplicate_taken_back_when_not_moved():
    _cube('FACE')
    bpy.ops.object.mode_set(mode='OBJECT')
    ob = bpy.context.active_object
    state = manip.start_duplicate(bpy.context)
    assert len(bpy.data.objects) == 2 and not manip.moved(state)
    manip.revert(state)
    assert [o.name for o in bpy.data.objects] == [ob.name] and ob.select_get()
    assert bpy.context.view_layer.objects.active is ob


def test_hold_menu_check_boxes():
    for menu in (mm.OPT_MOVE, mm.OPT_ROTATE, mm.OPT_SCALE):
        for label, action in (i for i in menu.items if i != mm.DIVIDER):
            if label in ("Shift Extrude", "Shift Duplicate", "Preserve UVs", "Preserve Children"):
                assert engine.is_toggle(action), (menu.name, label)
                assert engine.Layout._text(label, action).endswith("    "), "room for the box"
    prefs = preferences.get()
    action = ("allset.manip_option", {"option": 'SMART_EXTRUDE'})
    assert draw.checked(action) is True
    prefs.smart_extrude = False
    assert draw.checked(action) is False
    prefs.smart_extrude = True
    ts = bpy.context.scene.tool_settings
    uv = ("wm.context_toggle", {"data_path": "scene.tool_settings.use_transform_correct_face_attributes"})
    assert draw.checked(uv) is ts.use_transform_correct_face_attributes
    assert draw.checked(("allset.editor_toggle", {"editor": 'TOOL_SETTINGS'})) is None
