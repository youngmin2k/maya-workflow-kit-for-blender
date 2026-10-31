"""Maya double-click component selection — double-click = loop (Blender's loop pick at the
mouse), Shift+double-click a second component = the run between the two picks along their common loop
(edge / vertex / face), on the "Mesh" keymap's LEFTMOUSE DOUBLE_CLICK."""

from importlib import import_module

import bmesh
import bpy

import kit

loop_pick = import_module(kit.MODULE + ".operators.loop_pick")


def _grid_object(n=6):
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    me = bpy.data.meshes.new("grid")
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=n, y_segments=n, size=1.0)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new("grid", me)
    bpy.context.scene.collection.objects.link(ob)
    bpy.context.view_layer.objects.active = ob
    ob.select_set(True)
    return ob


def _bm_grid(n=6):
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=n, y_segments=n, size=1.0)
    for seq in (bm.verts, bm.edges, bm.faces):
        seq.ensure_lookup_table()
    return bm


def _row_edges(bm, y):
    """Horizontal edges at height y, sorted by x."""
    es = [e for e in bm.edges if all(abs(v.co.y - y) < 1e-5 for v in e.verts)]
    return sorted(es, key=lambda e: sum(v.co.x for v in e.verts))


def test_edge_run_along_loop():
    bm = _bm_grid()
    row = _row_edges(bm, bm.verts[0].co.y + 2 * (2.0 / 6))      # an inner row
    run = loop_pick.edge_run(row[1], row[4])
    assert run is not None and set(run) == set(row[1:5]), run
    col = [e for e in bm.edges if all(abs(v.co.x - bm.verts[0].co.x - 2.0 / 6) < 1e-5 for v in e.verts)]
    assert loop_pick.edge_run(row[1], col[2]) is None             # different loops


def test_face_run_along_loop():
    bm = _bm_grid()
    y = sorted({round(f.calc_center_median().y, 5) for f in bm.faces})[2]
    row = sorted((f for f in bm.faces if abs(f.calc_center_median().y - y) < 1e-4),
                 key=lambda f: f.calc_center_median().x)
    run = loop_pick.face_run(row[0], row[3])
    assert run is not None and set(run) == set(row[:4]), [f.index for f in run or []]


def test_vert_run_along_loop():
    bm = _bm_grid()
    y = sorted({round(v.co.y, 5) for v in bm.verts})[3]
    row = sorted((v for v in bm.verts if abs(v.co.y - y) < 1e-5), key=lambda v: v.co.x)
    run = loop_pick.vert_run(row[1], row[5])
    assert run is not None and set(run[0]) == set(row[1:6]), run


def test_shift_double_click_selects_between_edges():
    ob = _grid_object()
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.context.tool_settings.mesh_select_mode = (False, True, False)
    bm = bmesh.from_edit_mesh(ob.data)
    for e in bm.edges:
        e.select = False
    for v in bm.verts:
        v.select = False
    bm.edges.ensure_lookup_table()
    ys = sorted({round(v.co.y, 5) for v in bm.verts})
    row = _row_edges(bm, ys[2])
    a, b = row[0], row[3]
    for e in (a, b):          # pick one, then Shift+click the second (select history: a then b)
        e.select_set(True)
        bm.select_history.add(e)
    bmesh.update_edit_mesh(ob.data)
    assert bpy.ops.allset.loop_pick(between=True) == {'FINISHED'}
    bm = bmesh.from_edit_mesh(ob.data)
    sel = {e.index for e in bm.edges if e.select}
    want = {e.index for e in _row_edges(bm, ys[2])[0:4]}
    assert sel == want, (sorted(sel), sorted(want))
    assert isinstance(bm.select_history.active, bmesh.types.BMEdge)
    bpy.ops.object.mode_set(mode='OBJECT')


def test_mesh_keymap_double_click():
    km = kit.maya_kc().keymaps["Mesh"]
    items = [k for k in km.keymap_items if k.idname == "allset.loop_pick" and k.type == 'LEFTMOUSE'
             and k.value == 'DOUBLE_CLICK' and not k.ctrl and not k.alt]
    by_shift = {k.shift: k.properties.between for k in items}
    assert by_shift == {False: False, True: True}, by_shift


def _face_row(bm, k):
    y = sorted({round(f.calc_center_median().y, 5) for f in bm.faces})[k]
    return sorted((f for f in bm.faces if abs(f.calc_center_median().y - y) < 1e-4),
                  key=lambda f: f.calc_center_median().x)


def test_neighbour_faces_take_the_whole_loop():
    # Maya 2026 (#222): pick a face, Shift+double-click its neighbour = the whole face loop through both;
    # two faces further apart = only the faces between them
    bm = _bm_grid()
    row = _face_row(bm, 2)
    assert set(loop_pick.face_loop(row[2], row[3])) == set(row)
    for f in bm.faces:
        f.select = False
    for f in (row[2], row[3]):
        f.select_set(True)
        bm.select_history.add(f)
    assert loop_pick.select_run(bm) == len(row)
    assert {f.index for f in bm.faces if f.select} == {f.index for f in row}
    for f in bm.faces:
        f.select = False
    bm.select_history.clear()
    for f in (row[2], row[4]):
        f.select_set(True)
        bm.select_history.add(f)
    assert loop_pick.select_run(bm) == 3
    assert {f.index for f in bm.faces if f.select} == {f.index for f in row[2:5]}


def test_double_click_picks_shell_for_vertices_and_faces():
    # Maya 2026 (#222): a vertex or face double-click selects its whole shell, an edge double-click its loop
    assert loop_pick.shell_mode((False, False, True))
    assert loop_pick.shell_mode((True, False, False))
    assert not loop_pick.shell_mode((False, True, False))
    assert not loop_pick.shell_mode((True, True, True))
