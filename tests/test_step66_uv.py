"""Maya UV workflow — UV Editor entry, UV components, Cut / Sew / Unfold / Layout, Texel Density, UV marking
menus, UV Toolkit. GUI: tests/gui/gui_step66_uv.py."""

import types
from importlib import import_module

import bmesh
import bpy
from mathutils import Vector

import kit

uvt = import_module(kit.MODULE + ".operators.uv_tools")
marking = import_module(kit.MODULE + ".marking")
mm = import_module(kit.MODULE + ".marking.menus")
compat = import_module(kit.MODULE + ".compat")
menu_map = import_module(kit.MODULE + ".ui.menu_map")
notices = import_module(kit.MODULE + ".ui.notices")


def _clear():
    if bpy.context.active_object is not None and bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)


def _two_quads(size=1.0, name="two"):
    """Two unit quads side by side, UVs in one piece (0..1 x 0..0.5), in edit mode, all selected."""
    me = bpy.data.meshes.new(name)
    s = size
    me.from_pydata([(0, 0, 0), (s, 0, 0), (2 * s, 0, 0), (0, s, 0), (s, s, 0), (2 * s, s, 0)], [],
                   [(0, 1, 4, 3), (1, 2, 5, 4)])
    me.uv_layers.new(name="UVMap")
    ob = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(ob)
    for o in bpy.context.selected_objects:
        o.select_set(False)
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.mode_set(mode='EDIT')
    bm = bmesh.from_edit_mesh(me)
    uv = bm.loops.layers.uv.active
    for f in bm.faces:
        for loop in f.loops:
            loop[uv].uv = (loop.vert.co.x / (2 * s), loop.vert.co.y / (2 * s))
    bmesh.update_edit_mesh(me)
    bpy.context.scene.tool_settings.use_uv_select_sync = True
    return ob


def _bm(ob):
    bm = bmesh.from_edit_mesh(ob.data)
    for seq in (bm.verts, bm.edges, bm.faces):
        seq.ensure_lookup_table()
    return bm, bm.loops.layers.uv.active


def _select_shared_edge(ob):
    bm, _uv = _bm(ob)
    for el in (*bm.verts, *bm.edges, *bm.faces):
        el.select = False
    shared = next(e for e in bm.edges if len(e.link_faces) == 2)
    shared.select = True
    for v in shared.verts:
        v.select = True
    bmesh.update_edit_mesh(ob.data)
    return shared.index


def _blender_islands(ob):
    """How Blender's own pack sees the shells: pack, then count face groups that still share UVs."""
    bm, uv = _bm(ob)
    return len(uvt.islands(bm, uv))


def test_islands_and_seams():
    _clear()
    ob = _two_quads()
    bm, uv = _bm(ob)
    assert len(uvt.islands(bm, uv)) == 1
    next(e for e in bm.edges if len(e.link_faces) == 2).seam = True
    assert len(uvt.islands(bm, uv)) == 1, "Blender islands ignore seams (as pack_islands does)"
    assert len(uvt.islands(bm, uv, seams=True)) == 2


def test_cut_splits_the_shell_in_place():
    _clear()
    ob = _two_quads()
    _select_shared_edge(ob)
    bm, uv = _bm(ob)
    before = {(f.index, l.vert.index): l[uv].uv.copy() for f in bm.faces for l in f.loops}
    assert bpy.ops.allset.uv_cut() == {'FINISHED'}
    bm, uv = _bm(ob)
    assert all(e.seam for e in bm.edges if len(e.link_faces) == 2)
    assert _blender_islands(ob) == 2
    after = {(f.index, l.vert.index): l[uv].uv.copy() for f in bm.faces for l in f.loops}
    assert max((after[k] - before[k]).length for k in before) < 1e-3, "in place"
    # Blender's own island operators now see two shells: pack moves them apart
    bpy.ops.uv.pack_islands(margin=0.05, rotate=False)
    bm, uv = _bm(ob)
    fa, fb = bm.faces
    a = {tuple(round(c, 4) for c in l[uv].uv) for l in fa.loops}
    b = {tuple(round(c, 4) for c in l[uv].uv) for l in fb.loops}
    assert not (a & b), "pack_islands treats the cut as two shells"


def test_sew_moves_the_smaller_shell_onto_the_edge():
    _clear()
    ob = _two_quads()
    _select_shared_edge(ob)
    bpy.ops.allset.uv_cut()
    bm, uv = _bm(ob)
    # move / rotate the second quad's UVs far away (a separate shell somewhere else)
    fb = bm.faces[1]
    for loop in fb.loops:
        x, y = loop[uv].uv
        loop[uv].uv = (0.9 - y, 0.2 + x)      # rotated 90 degrees and moved
    bmesh.update_edit_mesh(ob.data)
    _select_shared_edge(ob)
    assert bpy.ops.allset.uv_sew() == {'FINISHED'}
    bm, uv = _bm(ob)
    assert not any(e.seam for e in bm.edges)
    assert _blender_islands(ob) == 1, "one shell again"
    assert max(abs(uvt._uv_area(f, uv) - 0.25) for f in bm.faces) < 1e-3, "sizes kept (similar shells; Cut nudge aside)"


def test_unfold_keeps_shells_in_place_and_flat():
    _clear()
    bpy.ops.mesh.primitive_cube_add(size=2)
    ob = bpy.context.active_object
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.context.scene.tool_settings.use_uv_select_sync = True
    bpy.ops.mesh.select_all(action='SELECT')
    bm, uv = _bm(ob)
    shells = uvt.islands(bm, uv)
    centres = sorted(tuple(round(c, 3) for c in sum(uvt.uv_bounds(s, uv), Vector((0, 0))) / 2) for s in shells)
    assert bpy.ops.allset.uv_unfold() == {'FINISHED'}
    bm, uv = _bm(ob)
    after = uvt.islands(bm, uv)
    assert len(after) == len(shells), "shell borders kept"
    got = sorted(tuple(round(c, 3) for c in sum(uvt.uv_bounds(s, uv), Vector((0, 0))) / 2) for s in after)
    assert got == centres, (got, centres)
    assert all(uvt._uv_area(f, uv) > 1e-6 for f in bm.faces), "no collapsed faces"
    assert sum(f.select for f in bm.faces) == 6, "selection back"


def test_layout_packs_into_0_1_without_overlap():
    _clear()
    ob = _two_quads()
    _select_shared_edge(ob)
    bpy.ops.allset.uv_cut()
    bm, uv = _bm(ob)
    for i, f in enumerate(bm.faces):       # both shells on the same spot, outside 0-1
        for loop in f.loops:
            x, y = loop[uv].uv
            loop[uv].uv = (1.5 + x - 0.5 * i, 1.2 + y)
    bmesh.update_edit_mesh(ob.data)
    bpy.ops.mesh.select_all(action='DESELECT')
    assert bpy.ops.allset.uv_layout() == {'FINISHED'}, "nothing selected = every shell"
    bm, uv = _bm(ob)
    us = [l[uv].uv for f in bm.faces for l in f.loops]
    assert all(-1e-6 <= u.x <= 1 + 1e-6 and -1e-6 <= u.y <= 1 + 1e-6 for u in us)
    (alo, ahi), (blo, bhi) = (uvt.uv_bounds([f], uv) for f in bm.faces)
    overlap = min(ahi.x, bhi.x) - max(alo.x, blo.x) > 1e-6 and min(ahi.y, bhi.y) - max(alo.y, blo.y) > 1e-6
    assert not overlap


def test_texel_density_get_and_set():
    _clear()
    a = _two_quads(1.0, "small")         # 2 x 1 world, UVs 0..1 x 0..0.5: 1024 px over 2 units = 512 px per unit
    bpy.ops.object.mode_set(mode='OBJECT')
    b = _two_quads(2.0, "big")           # twice as big, same UVs: 256 px per unit
    bpy.ops.object.mode_set(mode='OBJECT')
    s = bpy.context.scene.allset_uv
    assert s.map_size == 1024 and abs(s.shell_padding - 2) < 1e-9
    for ob, want in ((a, 512.0), (b, 256.0)):
        for o in bpy.context.selected_objects:
            o.select_set(False)
        ob.select_set(True)
        bpy.context.view_layer.objects.active = ob
        bpy.ops.object.mode_set(mode='EDIT')
        assert bpy.ops.allset.uv_texel_get() == {'FINISHED'}
        assert abs(s.texel_density - want) < 1e-3, (ob.name, s.texel_density)
        bpy.ops.object.mode_set(mode='OBJECT')
    s.texel_density = 512.0                  # the small one's density onto the big one (Maya Set)
    bpy.ops.object.mode_set(mode='EDIT')     # b is active
    assert bpy.ops.allset.uv_texel_set() == {'FINISHED'}
    bpy.ops.allset.uv_texel_get()
    assert abs(s.texel_density - 512.0) / 512.0 < 0.01


def test_uv_components():
    _clear()
    ob = _two_quads()
    bpy.ops.object.mode_set(mode='OBJECT')
    ts = bpy.context.scene.tool_settings
    ts.use_uv_select_sync = False
    assert bpy.ops.allset.uv_component(mode='EDGE') == {'FINISHED'}
    assert ob.mode == 'EDIT' and ts.use_uv_select_sync and tuple(ts.mesh_select_mode) == (False, True, False)
    # SHELL is Maya's UV Shell mask (sync on, face mode, selection cleared; operators/uv_shell_select.py);
    # Blender's island selection is the internal 'ISLAND' (Move UV Shell)
    assert bpy.ops.allset.uv_component(mode='SHELL') == {'FINISHED'}
    assert ts.use_uv_select_sync and tuple(ts.mesh_select_mode) == (False, False, True)
    assert bpy.context.window_manager.allset_uv_shell_mask and ob.data.total_face_sel == 0
    uvt.set_component(bpy.context, 'ISLAND')
    assert not ts.use_uv_select_sync and compat.uv_island_mode(ts)
    assert ob.data.total_face_sel == 2, "every face selected so the UV Editor draws all UVs"
    assert bpy.ops.allset.uv_component(mode='UV') == {'FINISHED'}
    assert ts.uv_select_mode == 'VERTEX' and not compat.uv_island_mode(ts)
    bpy.ops.object.mode_set(mode='OBJECT')
    assert uvt.prepare(bpy.context) and ob.mode == 'EDIT' and ts.use_uv_select_sync


def _ctx(space_mode='UV', sync=True, island=False):
    ts = bpy.context.scene.tool_settings
    ts.use_uv_select_sync = sync
    ts.mesh_select_mode = (True, False, False)
    ts.uv_select_mode = 'VERTEX'
    compat.set_uv_island_mode(ts, island)
    return types.SimpleNamespace(mode='EDIT_MESH', scene=bpy.context.scene, active_object=None,
                                 window_manager=types.SimpleNamespace(allset_uv_shell_mask=False),
                                 space_data=types.SimpleNamespace(type='IMAGE_EDITOR', mode=space_mode))


def test_uv_editor_marking_menus():
    assert marking.resolve("RMB", _ctx()) == ("pie", marking.idname("UV_EDITOR_RMB"))
    assert marking.resolve("SHIFT_RMB", _ctx()) == ("pie", marking.idname("SHIFT_UV"))
    assert marking.resolve("SHIFT_RMB", _ctx(sync=False, island=True)) == \
        ("pie", marking.idname("SHIFT_UV_SHELL"))
    assert marking.resolve("RMB", _ctx(space_mode='VIEW')) is None, "image viewing: no UV menu"
    rmb = mm.UV_EDITOR_RMB.radial
    assert {p: l for p, (l, _a) in rmb.items()} == {"S": "Face", "N": "Edge", "E": "UV", "W": "Vertex", "NW": "UV Shell"}
    # Maya's UV is a submenu (E UV, S UV Shell; Maya 2022 RMB marking menu)
    label, sub = mm.RMB_MESH.radial["E"]
    assert label == "UV" and sub.radial == {"E": ("UV", ("allset.uv_component", {"mode": 'UV'})),
                                            "S": ("UV Shell", ("allset.uv_component", {"mode": 'SHELL'}))}


def _items(km_name, etype, shift=False, ctrl=False, alt=False):
    km = kit.maya_kc().keymaps[km_name]
    return [(k.idname, {p: getattr(k.properties, p) for p in k.properties.keys()} if k.properties else {})
            for k in km.keymap_items if k.active and k.type == etype and k.value == 'PRESS'
            and k.shift == shift and k.ctrl == ctrl and k.alt == alt and not k.oskey]


def test_keys_and_menus():
    km = "UV Editor"
    assert [i for i, _p in _items(km, 'X', shift=True)] == ["allset.uv_cut"]
    assert [i for i, _p in _items(km, 'S', shift=True)] == ["allset.uv_sew"]
    assert [i for i, _p in _items(km, 'U', ctrl=True)] == ["allset.uv_unfold"]
    assert [i for i, _p in _items(km, 'L', ctrl=True)] == ["allset.uv_layout"], "IC select_linked gone"
    assert _items(km, 'RIGHTMOUSE') == [("allset.marking_menu", {"trigger": 'RMB'})]
    for k in ("Object Mode", "Mesh"):
        assert _items(k, 'F12') == [("allset.uv_component", {"mode": 'UV'})]
        assert _items(k, 'F12', alt=True) == [("allset.uv_component", {"mode": 'SHELL'})]
    assert menu_map.MAP["UV/Cut UV Edges"] == "allset.uv_cut"
    assert menu_map.MAP["UV/Sew UV Edges"] == "allset.uv_sew"
    assert menu_map.MAP["UV/3D Cut and Sew UV Tool"] == "allset.cut_sew_tool_set"   # was a notice
    assert hasattr(bpy.types, "ALLSET_PT_uv_toolkit")


def test_cube_cut_unfold_layout_keeps_world_scale():
    """uv_03: cut the top face out, Unfold, Layout: two shells, equal texel density, inside 0-1."""
    _clear()
    bpy.ops.mesh.primitive_cube_add(size=2)
    ob = bpy.context.active_object
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.context.scene.tool_settings.use_uv_select_sync = True
    bm, _uv = _bm(ob)
    for el in (*bm.verts, *bm.edges, *bm.faces):
        el.select = False
    for e in bm.edges:
        e.select = all(v.co.z > 0.5 for v in e.verts)
    bmesh.update_edit_mesh(ob.data)
    assert bpy.ops.allset.uv_cut() == {'FINISHED'}
    bpy.ops.mesh.select_all(action='SELECT')
    assert bpy.ops.allset.uv_unfold() == {'FINISHED'}
    bpy.ops.mesh.select_all(action='DESELECT')
    assert bpy.ops.allset.uv_layout() == {'FINISHED'}
    bm, uv = _bm(ob)
    shells = uvt.islands(bm, uv)
    assert len(shells) == 2
    d = [uvt.density(s, uv, ob.matrix_world, 1024, 1.0) for s in shells]
    assert abs(d[0] - d[1]) / max(d) < 0.01, d
    us = [l[uv].uv for f in bm.faces for l in f.loops]
    assert all(-1e-5 <= u.x <= 1 + 1e-5 and -1e-5 <= u.y <= 1 + 1e-5 for u in us)
