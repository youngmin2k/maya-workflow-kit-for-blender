"""#172: Maya UV Shell selection (operators/uv_shell_select.py), like Maya.
Maya: polyCube with the four edges of the top face cut = 3 shells A = f[0] f[4]
f[5] (front, right, left), B = f[1] (top), C = f[2] f[3] (back, bottom). The kit cube has Maya's face order,
so the face indices of the tables apply as they are."""

from importlib import import_module

import bmesh
import bpy

import kit

uss = import_module(kit.MODULE + ".operators.uv_shell_select")
uv_tools = import_module(kit.MODULE + ".operators.uv_tools")
uv_arrays = import_module(kit.MODULE + ".operators.uv_arrays")

A, B, C = {0, 4, 5}, {1}, {2, 3}


def _cube():
    if bpy.context.object and bpy.context.object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    bpy.ops.allset.create(kind='CUBE')
    ob = bpy.context.view_layer.objects.active
    bpy.ops.object.mode_set(mode='EDIT')
    bm = bmesh.from_edit_mesh(ob.data)
    bm.faces.ensure_lookup_table()
    uv = bm.loops.layers.uv.active
    uv_tools.cut(bm, uv, list(bm.faces[1].edges))       # Maya polyMapCut on the top face's edges
    bmesh.update_edit_mesh(ob.data)
    uv_tools.set_component(bpy.context, 'SHELL')
    return ob


def _sel(ob):
    return {f.index for f in bmesh.from_edit_mesh(ob.data).faces if f.select}


def _labels(ob):
    bm = bmesh.from_edit_mesh(ob.data)
    a = uv_arrays.read(ob, bm, bm.loops.layers.uv.active, bpy.context.evaluated_depsgraph_get())
    return uss.shell_labels(a)


def test_shells_of_the_cut_cube():
    ob = _cube()
    lab = _labels(ob)
    groups = {}
    for f, l in enumerate(lab.tolist()):
        groups.setdefault(l, set()).add(f)
    assert sorted(map(sorted, groups.values())) == sorted(map(sorted, (A, B, C))), groups


def test_entering_shell_mode():
    ob = _cube()
    ts = bpy.context.scene.tool_settings
    assert uss.active(bpy.context)
    assert tuple(ts.mesh_select_mode) == (False, False, True) and ts.use_uv_select_sync
    assert _sel(ob) == set()                      # Maya: switching to the mask clears the selection


def test_click_rules_match_maya():
    ob = _cube()
    ctx = bpy.context
    steps = [  # (face clicked, shift, ctrl, expected selected faces), rows 1-6
        (0, False, False, A),                     # click front -> f[0] f[4:5]
        (1, True, False, A | B),                  # Shift+click top -> adds B
        (4, True, False, B),                      # Shift+click right (A selected) -> A removed
        (4, True, False, A | B),                  # again -> A back
        (1, False, True, A),                      # Ctrl+click top -> B removed
        (1, True, True, A | B),                   # Ctrl+Shift+click top -> add
        (1, True, True, A | B),                   # twice: still add
    ]
    for face, shift, ctrl, want in steps:
        uss.pick(ctx, ob, face, shift, ctrl)
        assert _sel(ob) == want, (face, shift, ctrl, _sel(ob), want)
    uss.pick(ctx, None, None, False, False)       # click on empty space -> []
    assert _sel(ob) == set()


def test_box_rules_match_maya():
    ob = _cube()
    ctx = bpy.context

    def box(picked_by_blender, shift=False, ctrl=False, start=frozenset()):
        uss.write_selection(ob, bmesh.from_edit_mesh(ob.data), set(start))
        before = uss._face_sets(ctx)
        bm = bmesh.from_edit_mesh(ob.data)
        if shift and not ctrl:
            now = set(start) | picked_by_blender
        elif ctrl and not shift:
            now = set(start) - picked_by_blender
        else:
            now = set(picked_by_blender)
        uss.write_selection(ob, bm, now)          # what Blender's box left
        uss.grow_box(ctx, before, shift, ctrl)
        return _sel(ob)
    assert box({1, 2, 4}) == A | B | C            # box inside the top face: faces of all three shells under it
                                                  # (occluded back / walls too) -> f[0:5]
    assert box({0, 4, 2}) == A | C                # thin strip across front + right (+ occluded back) -> A + C
    assert box({1}, ctrl=True, start=A | B | C) == A | C      # Ctrl+box over the top face removes its shell
    assert box({0}, shift=True, start=B) == A | B             # Shift+box adds (UV Editor; 3D: from empty)


def test_uv_editor_point_pick():
    ob = _cube()
    bm = bmesh.from_edit_mesh(ob.data)
    bm.faces.ensure_lookup_table()
    uv = bm.loops.layers.uv.active
    a = uv_arrays.read(ob, bm, uv, bpy.context.evaluated_depsgraph_get())
    for f in range(6):
        cu = sum(l[uv].uv.x for l in bm.faces[f].loops) / 4
        cv = sum(l[uv].uv.y for l in bm.faces[f].loops) / 4
        hit = uss.uv_faces_at(a, ~a.face_hide, cu, cv).tolist()
        assert hit == [f], (f, hit)
    assert uss.uv_faces_at(a, ~a.face_hide, 5.0, 5.0).tolist() == []    # empty UV space


def test_current_uv_set_only():
    ob = _cube()
    me = ob.data
    bpy.ops.object.mode_set(mode='OBJECT')
    second = me.uv_layers.new(name="set2")      # a fresh set: copies map1 -> cut later by giving each face its own UVs
    for poly in me.polygons:
        for k, li in enumerate(range(poly.loop_start, poly.loop_start + poly.loop_total)):
            second.data[li].uv = (poly.index * 2 + (k in (1, 2)), (k in (2, 3)))
    me.uv_layers.active = second
    bpy.ops.object.mode_set(mode='EDIT')
    lab = _labels(ob)
    assert len(set(lab.tolist())) == 6            # every face its own shell in set2 (Maya: f[0] alone)
    bpy.ops.object.mode_set(mode='OBJECT')
    me.uv_layers.active = me.uv_layers[0]
    bpy.ops.object.mode_set(mode='EDIT')
    assert len(set(_labels(ob).tolist())) == 3    # back on map1


def test_other_component_mode_ends_the_mask():
    _cube()
    assert uss.flag(bpy.context)
    uv_tools.set_component(bpy.context, 'VERTEX')
    assert not uss.flag(bpy.context) and not uss.active(bpy.context)
    uv_tools.set_component(bpy.context, 'SHELL')
    uv_tools.leave_uv_mode(bpy.context)           # F9 / F10 / F11 (allset.component_mode)
    assert not uss.flag(bpy.context)


def test_move_uv_shell_keeps_blender_islands():
    ob = _cube()
    uv_tools.set_component(bpy.context, 'ISLAND')
    ts = bpy.context.scene.tool_settings
    assert not ts.use_uv_select_sync and not uss.flag(bpy.context)


def _uv_sel(ob):
    return {f.index for f in bmesh.from_edit_mesh(ob.data).faces if f.uv_select}


def test_uv_editor_selection_follows_shell_picks():
    # #245: faces picked in the UV Editor with UV Sync on leave a UV selection of its own; entering UV Shell mode and
    # picking a shell must show in the UV Editor too, not only in the viewport
    ob = _cube()
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.mode_set(mode='EDIT')
    ts = bpy.context.scene.tool_settings
    ts.use_uv_select_sync = True
    bm = bmesh.from_edit_mesh(ob.data)
    bm.faces.ensure_lookup_table()
    for f in bm.faces:
        f.select_set(f.index == 2)
    bm.select_flush_mode()
    bm.uv_select_sync_from_mesh()          # what a UV Editor face pick leaves with sync on
    bmesh.update_edit_mesh(ob.data)
    assert bmesh.from_edit_mesh(ob.data).uv_select_sync_valid
    uv_tools.set_component(bpy.context, 'SHELL')
    assert _sel(ob) == set() and _uv_sel(ob) == set()
    uss.pick(bpy.context, ob, 1, False, False)
    assert _sel(ob) == B and _uv_sel(ob) == B
    uss.pick(bpy.context, ob, 0, True, False)
    assert _sel(ob) == A | B and _uv_sel(ob) == A | B
