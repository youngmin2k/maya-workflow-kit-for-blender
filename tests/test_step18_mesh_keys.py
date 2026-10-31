"""Maya mesh component keys — D component pivot, Ctrl+Shift+A / Alt+D,
Ctrl+E / Ctrl+B, Shift+> / Shift+<, Ctrl+F9-F11."""

from importlib import import_module

import bpy

import kit

hold = import_module(kit.MODULE + ".operators.hold")
component = import_module(kit.MODULE + ".operators.component")


def _kmis(km, type, **mods):
    km = kit.maya_kc().keymaps[km]
    want = {"shift": False, "ctrl": False, "alt": False, **mods}
    return [k for k in km.keymap_items if k.active and k.type == type and k.value == 'PRESS'
            and all(getattr(k, m) == v for m, v in want.items()) and not k.oskey]


def _ids(km, type, **mods):
    return [k.idname for k in _kmis(km, type, **mods)]


def test_mesh_bindings():
    d = _kmis("Mesh", "D")
    assert [k.idname for k in d] == ["allset.hold"] and d[0].properties.name == "component_pivot"
    sa = _kmis("Mesh", "A", ctrl=True, shift=True)
    assert [k.idname for k in sa] == ["mesh.select_all"] and sa[0].properties.action == 'SELECT'
    assert _ids("Mesh", "D", alt=True) == ["allset.select_none"]
    assert _ids("Mesh", "E", ctrl=True) == ["allset.extrude"]   # polyExtrudeFace
    assert _ids("Mesh", "B", ctrl=True) == ["allset.bevel"]
    assert _ids("Mesh", "PERIOD", shift=True) == ["mesh.select_more"]
    assert _ids("Mesh", "COMMA", shift=True) == ["mesh.select_less"]
    assert _ids("Mesh", "PERIOD", shift=True, ctrl=True) == ["mesh.select_next_item"]
    assert _ids("Mesh", "COMMA", shift=True, ctrl=True) == ["mesh.select_prev_item"]
    for key, comp in (("F9", "VERT"), ("F10", "EDGE"), ("F11", "FACE")):
        k = _kmis("Mesh", key, ctrl=True)
        assert [i.idname for i in k] == ["allset.convert_selection"], key
        assert k[0].properties.type == comp, key
    # object mode keeps its own D (affect only origins)
    assert _kmis("Object Mode", "D")[0].properties.name == "pivot"


def test_component_pivot_release_rule():
    after = hold.component_pivot_after
    assert after('MEDIAN_POINT', True) == 'CURSOR', "a placed pivot stays"
    assert after('BOUNDING_BOX_CENTER', False) == 'BOUNDING_BOX_CENTER', "tap restores"
    assert after('CURSOR', False) == 'BOUNDING_BOX_CENTER', "tap clears a custom pivot (bbox centre)"
    assert after('CURSOR', True) == 'CURSOR'


def test_component_pivot_group():
    ts = bpy.context.scene.tool_settings
    ts.transform_pivot_point = 'INDIVIDUAL_ORIGINS'
    hold.begin(ts, "component_pivot")
    assert ts.transform_pivot_point == 'CURSOR'
    hold.end(ts, "component_pivot")
    assert ts.transform_pivot_point == 'INDIVIDUAL_ORIGINS'
    ts.transform_pivot_point = 'MEDIAN_POINT'


def test_bevel_affect():
    assert component.bevel_affect((True, False, False)) == 'VERTICES'
    for mode in ((False, True, False), (False, False, True), (True, True, True), (True, True, False)):
        assert component.bevel_affect(mode) == 'EDGES', mode


def _cube():
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o)
    bpy.ops.mesh.primitive_cube_add()
    return bpy.context.active_object


def test_select_none_leaves_edit_mode():
    ob = _cube()
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    assert bpy.ops.allset.select_none() == {'FINISHED'}
    assert bpy.context.mode == 'OBJECT' and not ob.select_get()
    assert not any(v.select for v in ob.data.vertices), "components deselected too"


def test_bevel_exec_vertex_and_edge():
    ob = _cube()
    bpy.ops.object.mode_set(mode='EDIT')
    ts = bpy.context.scene.tool_settings
    ts.mesh_select_mode = (True, False, False)
    bpy.ops.mesh.select_all(action='DESELECT')
    bpy.ops.object.mode_set(mode='OBJECT')
    ob.data.vertices[0].select = True
    bpy.ops.object.mode_set(mode='EDIT')
    assert bpy.ops.allset.bevel() == {'FINISHED'}
    bpy.ops.object.mode_set(mode='OBJECT')
    assert len(ob.data.vertices) == 10, len(ob.data.vertices)   # one corner -> 3 new verts
    bpy.ops.object.mode_set(mode='EDIT')
    ts.mesh_select_mode = (False, False, True)
    bpy.ops.mesh.select_all(action='SELECT')
    n = len(ob.data.polygons)
    bpy.ops.allset.bevel()
    bpy.ops.object.mode_set(mode='OBJECT')
    assert len(ob.data.polygons) > n


def _pick(ob, kind, i, mode):
    import bmesh
    ts = bpy.context.scene.tool_settings
    ts.mesh_select_mode = mode
    b = bmesh.from_edit_mesh(ob.data)
    for seq in (b.verts, b.edges, b.faces):
        for el in seq:
            el.select_set(False)
    seq = getattr(b, kind)
    seq.ensure_lookup_table()
    seq[i].select_set(True)
    b.select_flush_mode()
    bmesh.update_edit_mesh(ob.data)


def _count(ob):
    import bmesh
    b = bmesh.from_edit_mesh(ob.data)
    return sum(v.select for v in b.verts), sum(e.select for e in b.edges), sum(f.select for f in b.faces)


def test_convert_selection_touching():
    ob = _cube()
    bpy.ops.object.mode_set(mode='EDIT')
    ts = bpy.context.scene.tool_settings
    _pick(ob, "verts", 0, (True, False, False))
    bpy.ops.allset.convert_selection(type='FACE')
    assert tuple(ts.mesh_select_mode) == (False, False, True)
    assert _count(ob)[2] == 3, _count(ob)          # a cube corner touches 3 faces
    _pick(ob, "verts", 0, (True, False, False))
    bpy.ops.allset.convert_selection(type='EDGE')
    assert _count(ob)[1] == 3, _count(ob)          # and 3 edges
    _pick(ob, "faces", 0, (False, False, True))
    bpy.ops.allset.convert_selection(type='EDGE')
    assert _count(ob)[1] == 4, _count(ob)          # a face -> its 4 border edges
    _pick(ob, "faces", 0, (False, False, True))
    bpy.ops.allset.convert_selection(type='VERT')
    assert _count(ob)[0] == 4 and tuple(ts.mesh_select_mode) == (True, False, False)
    bpy.ops.allset.convert_selection(type='FACE')   # 4 verts of one face -> 5 faces touch them
    assert _count(ob)[2] == 5, _count(ob)
    bpy.ops.object.mode_set(mode='OBJECT')


def test_bevel_exec_width_is_in_maya_units():
    # exec bevel width = 0.1 Maya units, not 0.1 BU (10 Maya units in a cm scene)
    import bmesh
    units = import_module(kit.MODULE + ".operators.units")
    us = bpy.context.scene.unit_settings
    before = (us.system, us.length_unit, us.scale_length)
    us.system, us.length_unit, us.scale_length = 'METRIC', 'CENTIMETERS', 1.0
    try:
        ob = _cube()
        ob.scale = (0.005, 0.005, 0.005)             # a 1 cm cube, like the Maya Workflow Kit pCube1
        bpy.ops.object.transform_apply(scale=True)
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_mode(type='EDGE')
        bpy.ops.mesh.select_all(action='DESELECT')
        bm = bmesh.from_edit_mesh(ob.data)
        bm.edges.ensure_lookup_table()
        bm.edges[0].select = True
        bmesh.update_edit_mesh(ob.data)
        # Ctrl+B = Maya polyBevel3; an absolute Offset is in Maya units (0.1 cm here, x 0.9999)
        assert bpy.ops.allset.bevel(offset_as_fraction=False, offset=0.1) == {'FINISHED'}
        bm = bmesh.from_edit_mesh(ob.data)
        shortest = min(e.calc_length() for e in bm.edges)
        assert abs(units.maya_unit() - 0.01) < 1e-9
        # chamfer edge of a 0.1 cm bevel = 0.1 cm x sqrt(2); 0.1 BU would clamp at the cube's 0.5 cm
        assert abs(shortest - 0.001 * 2 ** 0.5) < 1e-5, shortest
    finally:
        bpy.ops.object.mode_set(mode='OBJECT')
        us.system, us.length_unit, us.scale_length = before
