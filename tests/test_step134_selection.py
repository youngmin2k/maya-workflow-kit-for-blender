"""Maya selection colours without a theme — the object wire uses kit-fixed colours
(lead #43ffa3, other selected #ffffff) and mesh edit mode gets Maya-style component colours (ui/component_colors.py)."""

from importlib import import_module

import bmesh
import bpy
import numpy as np

import kit

sw = import_module(kit.MODULE + ".ui.selection_wire")
cc = import_module(kit.MODULE + ".ui.component_colors")


def _close(a, b, tol=1e-4):
    return all(abs(x - y) < tol for x, y in zip(a, b))


def _cube(name="pCube1"):
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    me = bpy.data.meshes.new(name + "Shape")
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=2.0)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    bpy.context.view_layer.update()
    for o in bpy.context.scene.objects:      # view_layer.objects can yield None after removals
        o.select_set(o is ob)
    bpy.context.view_layer.objects.active = ob
    return ob


def test_maya_wire_colors_fixed():
    from mathutils import Color
    lead, other = sw.wire_colors()
    want = Color((0x43 / 255, 1.0, 0xa3 / 255)).from_srgb_to_scene_linear()
    assert _close(lead, (want.r, want.g, want.b, 1.0)), lead
    assert _close(other, (1.0, 1.0, 1.0, 1.0)), other
    assert sw.LEAD == "#43ffa3" and sw.OTHER == "#ffffff"


def test_wire_colors_ignore_the_theme():
    """The kit ships no theme: Blender's factory theme is orange, the wire must still be Maya's."""
    theme = bpy.context.preferences.themes[0].view_3d
    before = sw.wire_colors()
    old = tuple(theme.object_active), tuple(theme.object_selected)
    theme.object_active = (1.0, 0.5, 0.0)          # this test process only (factory startup, never saved)
    theme.object_selected = (0.9, 0.3, 0.0)
    try:
        assert sw.wire_colors() == before
    finally:
        theme.object_active, theme.object_selected = old


def test_component_color_values():
    assert cc.srgb(cc.HILITE) == (0x64 / 255, 0xdc / 255, 1.0)
    assert (cc.VERT, cc.VERT_SEL, cc.EDGE_SEL, cc.FACE_SEL) == ("#c800c8", "#fdff88", "#e3ac79", "#e3ac79")
    assert (cc.VERT_PX, cc.VERT_SEL_PX) == (3.0, 4.0)


def test_vertex_size_follows_theme():
    """The kit's vertices use the theme's Vertex Size (selected one larger); it never writes the theme."""
    assert cc.point_sizes(3) == (3.0, 4.0)
    assert cc.point_sizes(8) == (8.0, 9.0)
    assert cc.point_sizes(0) == (3.0, 4.0) and cc.point_sizes(None) == (3.0, 4.0)
    theme = bpy.context.preferences.themes[0].view_3d
    old = theme.vertex_size
    try:
        theme.vertex_size = 8
        assert cc.theme_point_sizes(bpy.context) == (8.0, 9.0)
        bpy.ops.mesh.primitive_cube_add()
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.object.mode_set(mode='OBJECT')
        assert theme.vertex_size == 8
    finally:
        theme.vertex_size = old


def test_fan_triangles():
    # a quad (0..3), a triangle (4..6) and a pentagon (7..11)
    ls, lt = [0, 4, 7], [4, 3, 5]
    cv = list(range(12))
    tri = cc.fan_triangles(ls, lt, cv, np.array([True, True, True]))
    assert tri.tolist() == [[0, 1, 2], [0, 2, 3], [4, 5, 6], [7, 8, 9], [7, 9, 10], [7, 10, 11]]
    assert cc.fan_triangles(ls, lt, cv, np.array([False, True, False])).tolist() == [[4, 5, 6]]
    assert cc.fan_triangles(ls, lt, cv, np.zeros(3, bool)).shape == (0, 3)


def test_layers_follow_select_mode_and_hide():
    co = np.zeros((4, 3))
    edges = [(0, 1), (1, 2), (2, 3), (3, 0)]
    m = cc.MeshArrays(co, edges, vsel=[1, 0, 0, 1], vhide=[0, 0, 1, 0], esel=[0, 0, 0, 1], ehide=[0, 1, 1, 0],
                      fsel=[1], fhide=[0], loop_start=[0], loop_total=[4], corner_vert=[0, 1, 2, 3])
    lay = cc.layers(m, (True, False, False))
    assert lay["edges"].tolist() == [[0, 1], [3, 0]]                 # hidden edges never drawn
    assert lay["verts"].tolist() == [1] and lay["verts_sel"].tolist() == [0, 3]   # vertex 2 hidden
    assert "edges_sel" not in lay and "tris" not in lay
    lay = cc.layers(m, (False, True, False))
    assert lay["edges_sel"].tolist() == [[3, 0]] and "verts" not in lay
    lay = cc.layers(m, (False, False, True))
    assert lay["tris"].tolist() == [[0, 1, 2], [0, 2, 3]]
    m.fhide[:] = True
    assert cc.layers(m, (False, False, True))["tris"].shape == (0, 3)


def test_read_paths_and_rules():
    ob = _cube()
    assert cc.use_evaluated(ob.modifiers)
    bpy.ops.object.mode_set(mode='EDIT')
    try:
        bm = bmesh.from_edit_mesh(ob.data)
        bm.verts.ensure_lookup_table()
        bm.faces.ensure_lookup_table()
        for v in bm.verts:
            v.select = False
        for e in bm.edges:
            e.select = False
        for f in bm.faces:
            f.select = False
        bm.verts[0].select = True
        bm.faces[2].select_set(True)
        bm.verts[7].hide = True
        bmesh.update_edit_mesh(ob.data)
        dg = bpy.context.evaluated_depsgraph_get()
        fast = cc.read_evaluated(ob, dg)
        slow = cc.read_bmesh(bmesh.from_edit_mesh(ob.data))
        assert len(fast.co) == len(slow.co) == 8 and len(fast.edges) == len(slow.edges) == 12
        assert np.allclose(fast.co, slow.co)
        for name in ("vsel", "vhide", "esel", "ehide", "fsel", "fhide"):
            assert getattr(fast, name).tolist() == getattr(slow, name).tolist(), name
        assert fast.vhide[7] and fast.fsel.sum() == 1 and fast.vsel[0]
        # state(): the evaluated read without edit-mode modifiers
        st = cc.state(ob, dg)
        assert st is not None and len(st.arrays.co) == 8
        # Smooth Preview style Subsurf shown in edit mode: the evaluated mesh isn't the cage -> BMesh cage
        md = ob.modifiers.new("Maya Smooth Preview", 'SUBSURF')
        md.show_in_editmode, md.show_on_cage = True, False
        assert not cc.use_evaluated(ob.modifiers)
        cc._dirty.add(ob.name)
        st = cc.state(ob, bpy.context.evaluated_depsgraph_get())
        assert st is not None and len(st.arrays.co) == 8 and len(st.arrays.edges) == 12
        ob.modifiers.remove(md)
    finally:
        bpy.ops.object.mode_set(mode='OBJECT')
    assert cc.readable(10 ** 6, True) and cc.readable(cc.BMESH_LIMIT, False) and not cc.readable(cc.BMESH_LIMIT + 1, False)


def test_option_and_disable():
    prefs = bpy.context.preferences.addons[kit.MODULE].preferences
    assert prefs.maya_component_colors and prefs.maya_selection_wire        # on by default, like Maya
    prefs.maya_component_colors = False
    assert not cc._enabled()
    prefs.maya_component_colors = True
    assert cc._handle and cc._on_depsgraph in bpy.app.handlers.depsgraph_update_post
    kit.disable()
    try:
        assert not cc._handle and cc._on_depsgraph not in bpy.app.handlers.depsgraph_update_post
        assert not cc._cache
    finally:
        kit.enable()
