"""UV-only selection in the UV Editor: UV Edge / UV Face components with UV Sync Selection off, and the double-click
(UV edge = its UV loop, Ctrl = its edge ring, UV / UV face = its shell, Shift = add)."""
from importlib import import_module

import bmesh
import bpy

import kit

uv_loop_pick = import_module(kit.MODULE + ".operators.uv_loop_pick")
uv_toolkit = import_module(kit.MODULE + ".ui.uv_toolkit")

N = 4          # faces per side of each grid


def _two_grids():
    """One mesh, two 4 x 4 grids; UV shells: grid A at u 0..1, grid B at u 2..3 (v 0..1)."""
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    me = bpy.data.meshes.new("grids")
    bm = bmesh.new()
    uv = bm.loops.layers.uv.new("map1")
    for shell in range(2):
        x0 = shell * 10.0
        vs = [[bm.verts.new((x0 + i, j, 0.0)) for i in range(N + 1)] for j in range(N + 1)]
        for j in range(N):
            for i in range(N):
                f = bm.faces.new((vs[j][i], vs[j][i + 1], vs[j + 1][i + 1], vs[j + 1][i]))
                for lp in f.loops:
                    lp[uv].uv = (shell * 2.0 + (lp.vert.co.x - x0) / N, lp.vert.co.y / N)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new("grids", me)
    bpy.context.collection.objects.link(ob)
    bpy.context.view_layer.objects.active = ob
    ob.select_set(True)
    return ob


def _uv_mode(mode):
    ob = _two_grids()
    assert bpy.ops.allset.uv_component(mode=mode) == {'FINISHED'}
    bpy.ops.uv.select_all(action='DESELECT')
    return ob


def _selected_uv_edges(ob):
    """Selected UV edges as sorted ((u, v), (u, v)) pairs, one per mesh edge side."""
    bm = bmesh.from_edit_mesh(ob.data)
    uv = bm.loops.layers.uv.active
    out = set()
    for f in bm.faces:
        for lp in f.loops:
            if lp.uv_select_edge:
                a = tuple(round(c, 4) for c in lp[uv].uv)
                b = tuple(round(c, 4) for c in lp.link_loop_next[uv].uv)
                out.add(tuple(sorted((a, b))))
    return out


def _shell_of_selected_corners(ob):
    """{0, 1}: which grids have selected UVs; and the selected corner count."""
    bm = bmesh.from_edit_mesh(ob.data)
    uv = bm.loops.layers.uv.active
    shells, n = set(), 0
    for f in bm.faces:
        for lp in f.loops:
            if lp.uv_select_vert:
                shells.add(int(lp[uv].uv.x >= 1.5))
                n += 1
    return shells, n


def test_uv_edge_and_face_components():
    for mode, select_mode in (('UV_EDGE', 'EDGE'), ('UV_FACE', 'FACE'), ('UV', 'VERTEX')):
        _uv_mode(mode)
        ts = bpy.context.scene.tool_settings
        assert not ts.use_uv_select_sync, mode
        assert not ts.use_uv_select_island, mode
        assert ts.uv_select_mode == select_mode, (mode, ts.uv_select_mode)
        assert uv_toolkit.current_component(bpy.context) == mode
    # the mesh components still turn UV Sync Selection back on
    assert bpy.ops.allset.uv_component(mode='EDGE') == {'FINISHED'}
    assert bpy.context.scene.tool_settings.use_uv_select_sync
    assert uv_toolkit.current_component(bpy.context) == 'EDGE'


def test_pick_kind():
    assert uv_loop_pick.pick_kind('EDGE', False) == 'LOOP'
    assert uv_loop_pick.pick_kind('EDGE', True) == 'RING'
    assert uv_loop_pick.pick_kind('VERTEX', False) == 'SHELL'
    assert uv_loop_pick.pick_kind('FACE', False) == 'SHELL'


def test_double_click_edge_selects_its_uv_loop():
    ob = _uv_mode('UV_EDGE')
    assert bpy.ops.allset.uv_loop_pick(location=(0.375, 0.25)) == {'FINISHED'}
    edges = _selected_uv_edges(ob)
    assert len(edges) == N, edges                              # the whole row of grid A, nothing of grid B
    assert all(a[1] == b[1] == 0.25 and b[0] <= 1.0 for a, b in edges), edges
    assert bpy.context.scene.tool_settings.uv_select_mode == 'EDGE'


def test_ctrl_double_click_selects_the_edge_ring():
    ob = _uv_mode('UV_EDGE')
    assert bpy.ops.allset.uv_loop_pick(location=(0.375, 0.25), ring=True) == {'FINISHED'}
    edges = _selected_uv_edges(ob)
    assert len(edges) == N + 1, edges                          # one column of parallel edges, v 0 .. 1
    assert all(a[1] == b[1] and (a[0], b[0]) == (0.25, 0.5) for a, b in edges), edges


def test_double_click_uv_or_face_selects_its_shell():
    for mode, where in (('UV', (2.25, 0.5)), ('UV_FACE', (2.4, 0.4))):
        ob = _uv_mode(mode)
        assert bpy.ops.allset.uv_loop_pick(location=where) == {'FINISHED'}, mode
        shells, n = _shell_of_selected_corners(ob)
        assert shells == {1} and n == N * N * 4, (mode, shells, n)


def test_shift_adds_and_plain_replaces():
    ob = _uv_mode('UV_EDGE')
    bpy.ops.allset.uv_loop_pick(location=(0.375, 0.25))
    first = _selected_uv_edges(ob)
    assert bpy.ops.allset.uv_loop_pick(location=(0.375, 0.75), extend=True) == {'FINISHED'}
    both = _selected_uv_edges(ob)
    assert first < both and len(both) == 2 * N, both
    # Shift on a loop that is already selected keeps it (adds, never toggles off)
    bpy.ops.allset.uv_loop_pick(location=(0.375, 0.75), extend=True)
    assert _selected_uv_edges(ob) == both
    bpy.ops.allset.uv_loop_pick(location=(0.375, 0.75))
    assert len(_selected_uv_edges(ob)) == N
    # shells: Shift adds the second shell
    ob = _uv_mode('UV')
    bpy.ops.allset.uv_loop_pick(location=(0.5, 0.5))
    bpy.ops.allset.uv_loop_pick(location=(2.5, 0.5), extend=True)
    assert _shell_of_selected_corners(ob)[0] == {0, 1}


def test_mesh_edges_with_uv_sync():
    ob = _two_grids()
    assert bpy.ops.allset.uv_component(mode='EDGE') == {'FINISHED'}
    bpy.ops.mesh.select_all(action='DESELECT')
    assert bpy.ops.allset.uv_loop_pick(location=(0.375, 0.25)) == {'FINISHED'}
    bm = bmesh.from_edit_mesh(ob.data)
    sel = [e for e in bm.edges if e.select]
    assert len(sel) == N and all(abs(v.co.y - 1.0) < 1e-6 and v.co.x <= N for e in sel for v in e.verts), sel
    bpy.ops.allset.uv_loop_pick(location=(2.375, 0.75), extend=True)
    bm = bmesh.from_edit_mesh(ob.data)
    assert sum(e.select for e in bm.edges) == 2 * N


def test_whole_shell_modes_pass():
    _uv_mode('UV')
    bpy.context.scene.tool_settings.use_uv_select_island = True
    assert bpy.ops.allset.uv_loop_pick(location=(0.5, 0.5)) == {'CANCELLED'}


def test_uv_editor_keymap_double_click():
    km = kit.maya_kc().keymaps["UV Editor"]
    items = [k for k in km.keymap_items if k.idname == "allset.uv_loop_pick" and k.type == 'LEFTMOUSE'
             and k.value == 'DOUBLE_CLICK' and not k.alt and k.active]
    got = {(k.shift, k.ctrl): (k.properties.extend, k.properties.ring) for k in items}
    assert got == {(False, False): (False, False), (True, False): (True, False),
                   (False, True): (False, True), (True, True): (True, True)}, got
    blender = [k for k in km.keymap_items if k.idname == "uv.select_loop" and k.value == 'DOUBLE_CLICK' and k.active]
    assert not blender, [(k.shift, k.ctrl) for k in blender]


def test_loop_stops_at_a_uv_seam():
    """Grid A's right half moved apart in UV space (a seam down the middle): the UV loop keeps to its side."""
    ob = _uv_mode('UV_EDGE')
    bm = bmesh.from_edit_mesh(ob.data)
    uv = bm.loops.layers.uv.active
    for f in bm.faces:
        if f.calc_center_median().x < N and f.calc_center_median().x > N / 2:
            for lp in f.loops:
                lp[uv].uv.x += 0.1
    bmesh.update_edit_mesh(ob.data)
    assert bpy.ops.allset.uv_loop_pick(location=(0.125, 0.25)) == {'FINISHED'}
    edges = _selected_uv_edges(ob)
    assert len(edges) == N // 2 and all(b[0] <= 0.5 for _a, b in edges), edges
