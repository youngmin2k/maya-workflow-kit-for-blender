"""Lane SELECT (quant gap 3): Select menu / Ctrl+RMB (CTRL_CONVERT) conversions — Grow / Shrink Along Loop,
perimeters, To Face Path, To Shell Border, To UV Shell Border, To UVs, To UV Perimeter, To UV Edge Loop
(operators/select_convert.py). Every expected selection is Maya's result on meshes numbered like
Maya's.
GUI: tests/gui/gui_step141_select.py."""

from importlib import import_module

import bmesh
import bpy

import kit

mm = import_module(kit.MODULE + ".marking.menus")
modal = import_module(kit.MODULE + ".marking.modal")
menu_map = import_module(kit.MODULE + ".ui.menu_map")
notices = import_module(kit.MODULE + ".ui.notices")
sc = import_module(kit.MODULE + ".operators.select_convert")
compat = import_module(kit.MODULE + ".compat")

# polyCube: vertex positions, edges, faces (vertex order) and per-corner UV numbers (map index, UV).
CUBE_V = [(-.5, -.5, .5), (.5, -.5, .5), (-.5, .5, .5), (.5, .5, .5), (-.5, .5, -.5), (.5, .5, -.5), (-.5, -.5, -.5),
          (.5, -.5, -.5)]
CUBE_E = [(0, 1), (2, 3), (4, 5), (6, 7), (0, 2), (1, 3), (2, 4), (3, 5), (4, 6), (5, 7), (6, 0), (7, 1)]
CUBE_F = [[(0, 0), (1, 1), (3, 3), (2, 2)], [(2, 2), (3, 3), (5, 5), (4, 4)], [(4, 4), (5, 5), (7, 7), (6, 6)],
          [(6, 6), (7, 7), (1, 9), (0, 8)], [(1, 1), (7, 10), (5, 11), (3, 3)], [(6, 12), (0, 0), (2, 2), (4, 13)]]
CUBE_UV = [(.33, 0), (.6633, 0), (.33, .25), (.6633, .25), (.33, .5), (.6633, .5), (.33, .75), (.6633, .75),
           (.33, 1), (.6633, 1), (1, 0), (1, .25), (0, 0), (0, .25)]


PATHS = {   # Select menu path -> (operator, kind) the step maps
    "Select/Grow Along Loop": 'GROW_LOOP', "Select/Shrink Along Loop": 'SHRINK_LOOP',
    "Select/Convert Selection/To Vertex Perimeter": 'VERTEX_PERIMETER',
    "Select/Convert Selection/To Edge Perimeter": 'EDGE_PERIMETER',
    "Select/Convert Selection/To Face Perimeter": 'FACE_PERIMETER',
    "Select/Convert Selection/To Face Path": 'FACE_PATH', "Select/Convert Selection/To Shell Border": 'SHELL_BORDER',
    "Select/Convert Selection/To UV Shell Border": 'UV_SHELL_BORDER', "Select/Convert Selection/To UVs": 'UVS',
    "Select/Convert Selection/To UV Perimeter": 'UV_PERIMETER',
    "Select/Convert Selection/To UV Edge Loop": 'UV_EDGE_LOOP',
}


# --- meshes numbered like Maya's ------------------------------------------------------------------------

def _clear():
    if bpy.context.active_object is not None and bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    for me in list(bpy.data.meshes):
        bpy.data.meshes.remove(me)


def _plane_bm(n):
    """Maya polyPlane -sx n -sy n numbering: vertex r * (n+1) + c, edges per vertex (right, then down), face r * n + c;
    one UV per vertex (map index = vertex index)."""
    bm = bmesh.new()
    vs = [bm.verts.new((c, -r, 0.0)) for r in range(n + 1) for c in range(n + 1)]
    for i, v in enumerate(vs):
        r, c = divmod(i, n + 1)
        if c < n:
            bm.edges.new((v, vs[i + 1]))
        if r < n:
            bm.edges.new((v, vs[i + n + 1]))
    uv = bm.loops.layers.uv.new("map1")
    for r in range(n):
        for c in range(n):
            i = r * (n + 1) + c
            f = bm.faces.new((vs[i], vs[i + 1], vs[i + n + 2], vs[i + n + 1]))
            for lp in f.loops:
                k = lp.vert.index
                lp[uv].uv = ((k % (n + 1)) / n, 1.0 - (k // (n + 1)) / n)
    return bm


def _cube_bm(open_face=None):
    bm = bmesh.new()
    vs = [bm.verts.new(p) for p in CUBE_V]
    for a, b in CUBE_E:
        bm.edges.new((vs[a], vs[b]))
    uv = bm.loops.layers.uv.new("map1")
    for i, corners in enumerate(CUBE_F):
        if i == open_face:
            continue
        f = bm.faces.new([vs[v] for v, _m in corners])
        for lp, (_v, m) in zip(f.loops, corners):
            lp[uv].uv = CUBE_UV[m]
    return bm


def _make(kind):
    _clear()
    bm = {"plane": lambda: _plane_bm(4), "plane6": lambda: _plane_bm(6), "cube": _cube_bm,
          "open_cube": lambda: _cube_bm(open_face=1)}[kind]()
    for seq in (bm.verts, bm.edges, bm.faces):
        seq.index_update()
    me = bpy.data.meshes.new("pShape1")
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new("p1", me)
    bpy.context.scene.collection.objects.link(ob)
    bpy.context.view_layer.objects.active = ob
    ob.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.context.scene.tool_settings.use_uv_select_sync = True
    return ob


def _bm(ob):
    bm = bmesh.from_edit_mesh(ob.data)
    for seq in (bm.verts, bm.edges, bm.faces):
        seq.ensure_lookup_table()
    return bm


def _seq(bm, kind):
    return {'VERT': bm.verts, 'EDGE': bm.edges, 'FACE': bm.faces}[kind]


def _select(ob, kind, idx):
    ts = bpy.context.scene.tool_settings
    ts.mesh_select_mode = (kind == 'VERT', kind == 'EDGE', kind == 'FACE')
    bm = _bm(ob)
    for seq in (bm.verts, bm.edges, bm.faces):
        for x in seq:
            x.select_set(False)
    for i in idx:
        _seq(bm, kind)[i].select_set(True)
    bmesh.update_edit_mesh(ob.data)


def _map_index(mesh_kind, lp, uv):
    if mesh_kind.startswith("plane"):
        return lp.vert.index
    p = lp[uv].uv
    return next(i for i, q in enumerate(CUBE_UV) if abs(p.x - q[0]) < 1e-4 and abs(p.y - q[1]) < 1e-4)


def _result(ob, mesh_kind, kind):
    bm = _bm(ob)
    if kind == 'UV':
        uv = bm.loops.layers.uv.active
        return sorted({_map_index(mesh_kind, lp, uv) for f in bm.faces if f.select for lp in f.loops
                       if compat.uv_vert_selected(lp, uv)})
    return sorted(x.index for x in _seq(bm, kind) if x.select)


def _mode_kind():
    return sc.mode_kind(bpy.context.scene.tool_settings.mesh_select_mode)


# --- tests ----------------------------------------------------------------------------------------------


def test_menu_paths_mapped():
    for path, kind in PATHS.items():
        assert menu_map.MAP.get(path) == ("allset.select_convert", {"kind": kind}), path
    for path, comp in (("Select/Components/UV", 'UV'), ("Select/Components/UV Shell", 'SHELL')):
        assert menu_map.MAP.get(path) == ("allset.uv_component", {"mode": comp}), path
    for label, t in (("To Vertices", 'VERT'), ("To Edges", 'EDGE'), ("To Faces", 'FACE')):
        assert menu_map.MAP["Select/Convert Selection/" + label] == ("allset.convert_selection", {"type": t})
    # what stays greyed has a notice
    for path in ("Select/Components/Vertex Face", "Select/Convert Selection/To Vertex Faces"):
        assert path not in menu_map.MAP and notices.greyed_notice(path), path
    # the UV Editor's Select menu runs the same conversions
    for label in ("Grow Along Loop", "Convert Selection/To Face Path", "Convert Selection/To UV Perimeter"):
        assert menu_map.MAP["UV Editor/Select/" + label][0] == "allset.select_convert", label


def test_marking_menu_entries():
    entries = {p: a for p, _l, a in mm.label_walk(mm.MENUS["CTRL_CONVERT"], "CTRL_CONVERT")}
    greyed = [p for p, a in entries.items() if mm.is_greyed(a)]
    assert greyed == ["CTRL_CONVERT/Selection Constraints..."], greyed     # Blender has no selection constraints
    for p in ("CTRL_CONVERT/Grow Selection/Grow Along Loop",
              "CTRL_CONVERT/Shrink Selection/Shrink Selection Along Loop", "CTRL_CONVERT/To UVs/To UV Perimeter",
              "CTRL_CONVERT/To UVs/To UVs", "CTRL_CONVERT/To Face Path", "CTRL_CONVERT/To Shell Border",
              "CTRL_CONVERT/To Vertices/To Vertex Perimeter", "CTRL_CONVERT/To Faces/To Face Perimeter",
              "CTRL_CONVERT/To Edges/To Edge Perimeter"):
        a = entries[p]
        assert isinstance(a, tuple) and a[0] == "item" and a[1] in menu_map.MAP, (p, a)
        assert p not in notices.MARKING, p
    ob = _make("plane")
    _select(ob, 'FACE', [5, 6])
    for p, a in entries.items():
        if isinstance(a, tuple) and a[0] == "item":
            assert modal.poll_action(a), p
    # run through the marking-menu path: allset.menu_item -> the Select menu's operator
    modal.run_action(bpy.context, entries["CTRL_CONVERT/Grow Selection/Grow Along Loop"])
    assert _result(ob, "plane", 'FACE') == [4, 5, 6, 7]
    modal.run_action(bpy.context, entries["CTRL_CONVERT/To Vertices/To Vertex Perimeter"])
    assert _mode_kind() == 'VERT' and _result(ob, "plane", 'VERT') == [5, 6, 7, 8, 9, 10, 11, 12, 13, 14]
    modal.run_action(bpy.context, entries["CTRL_CONVERT/To Edges/To Edges"])
    assert _mode_kind() == 'EDGE' and len(_result(ob, "plane", 'EDGE')) == 23, _result(ob, "plane", 'EDGE')


def test_menu_item_runs():
    ob = _make("plane")
    _select(ob, 'EDGE', [13])
    assert bpy.ops.allset.menu_item(item="Select/Convert Selection/To Face Path") == {'FINISHED'}
    assert _mode_kind() == 'FACE' and _result(ob, "plane", 'FACE') == [2, 6, 10, 14]
    # To Edges from vertices = the edges they touch (Maya ConvertSelectionToEdges), not a cleared selection
    _select(ob, 'VERT', [12])
    assert bpy.ops.allset.menu_item(item="Select/Convert Selection/To Edges") == {'FINISHED'}
    assert _mode_kind() == 'EDGE' and _result(ob, "plane", 'EDGE') == [14, 20, 22, 23]
    bpy.ops.object.mode_set(mode='OBJECT')


def test_kit_cube_isolated_vertex():
    """The kit's Maya cube (operators/create.py): an isolated vertex grows along its loops to its 3 neighbours."""
    _clear()
    bpy.ops.allset.create(kind='CUBE')
    ob = bpy.context.active_object
    if bpy.context.mode != 'EDIT_MESH':
        bpy.ops.object.mode_set(mode='EDIT')
    _select(ob, 'VERT', [0])
    bm = _bm(ob)
    want = sorted({0} | {e.other_vert(bm.verts[0]).index for e in bm.verts[0].link_edges})
    print("kit cube", len(bm.verts), [len(v.link_edges) for v in bm.verts], list(ob.modifiers))
    assert bpy.ops.allset.menu_item(item="Select/Grow Along Loop") == {'FINISHED'}
    assert _result(ob, "cube", 'VERT') == want, (_result(ob, "cube", 'VERT'), want)
    bpy.ops.object.mode_set(mode='OBJECT')
