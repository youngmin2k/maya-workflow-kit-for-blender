"""L15 (Issue #137): blendShape in-between and combination targets on shape keys
(operators/blend_shapes_227.py, ui/shape_editor.py).

Expected:
polyPlane w2 h2 sx2 sy2 ``face``; ``smile`` = vtx[0:2] + (0, 1, 0); ``smile_half`` = vtx[0:2] + (0, 0.2, 0.3);
``smile_more`` = vtx[0:2] + (0.5, 0.9, -0.2); in-betweens at 0.5 (``inbetween_one``) / 0.3 + 0.7 (``inbetween_two``),
vertex 0's world position sampled at 37 weights -0.4 ... 1.4. Combinations: combinationShape output weight for
multiplication / lowest / smooth (8 x 8 grid, 2 inputs; 4 rows, 3 inputs). Maya (x, y, z) -> Blender (x, -z, y);
deltas from the base are compared so the axis swap is the only mapping."""

import os
from importlib import import_module

import bpy

import kit

bs = import_module(kit.MODULE + ".operators.blend_shapes_227")
shape_editor = import_module(kit.MODULE + ".ui.shape_editor")
menu_map = import_module(kit.MODULE + ".ui.menu_map")
notices = import_module(kit.MODULE + ".ui.notices")

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
OUT = os.path.join(ROOT, "tmp", "test_step227")
TOL = 1e-4


def _b(v):
    """Maya vector -> Blender."""
    return (v[0], -v[2], v[1])


def _fresh():
    bpy.ops.wm.read_homefile(use_empty=True)
    wm = bpy.context.window_manager
    wm.allset_se_current = ""
    wm.allset_se_edit = ""
    wm.allset_se_picked = ""


def _plane(name, offset=None):
    """Maya's polyPlane w2 h2 sx2 sy2 in Blender axes; ``offset`` (Maya vector) added to vtx[0:2]."""
    verts = []
    for row in range(3):                   # Maya: x fastest, z from +1 to -1
        for col in range(3):
            verts.append(list(_b((-1.0 + col, 0.0, 1.0 - row))))
    if offset is not None:
        d = _b(offset)
        for i in range(3):
            verts[i] = [a + b for a, b in zip(verts[i], d)]
    faces = [(0, 1, 4, 3), (1, 2, 5, 4), (3, 4, 7, 6), (4, 5, 8, 7)]
    me = bpy.data.meshes.new(name + "Shape")
    me.from_pydata(verts, [], faces)
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def _select(*obs):
    for o in bpy.context.scene.objects:
        o.select_set(o in obs)
    bpy.context.view_layer.objects.active = obs[-1] if obs else None


def _face(*targets):
    """face with a blendShape and targets [(name, Maya offset of vtx[0:2])]."""
    face = _plane("face")
    _select(face)
    assert bpy.ops.allset.shape_create() == {'FINISHED'}
    key = face.data.shape_keys
    for name, off in targets:
        src = _plane(name, off)
        _select(face, src)
        bpy.context.view_layer.objects.active = face
        assert bpy.ops.allset.shape_add_selection() == {'FINISHED'}
        bpy.data.objects.remove(src)
        kb = key.key_blocks[name]
        kb.slider_min, kb.slider_max = -2.0, 2.0          # Maya weights are unclamped; the test drives -0.4 ... 1.4
    _select(face)
    return face, key


def _v0(face):
    dg = bpy.context.evaluated_depsgraph_get()
    dg.update()
    ev = face.evaluated_get(dg)
    me = ev.to_mesh()
    co = tuple(me.vertices[0].co)
    ev.to_mesh_clear()
    return co


def _v0_at(face, kb, w):
    kb.value = w
    return _v0(face)


def _simple(key):
    ad = key.animation_data
    assert ad is not None and ad.drivers, "no drivers"
    for fc in ad.drivers:
        assert fc.driver.is_simple_expression, (fc.data_path, fc.driver.expression)
        assert fc.driver.is_valid, (fc.data_path, fc.driver.expression)
        assert not fc.modifiers and not fc.keyframe_points, fc.data_path      # the expression alone is the value


def test_registered_and_menus_mapped():
    for op in ("shape_add_inbetween", "shape_remove_inbetween", "shape_add_combination", "shape_combination_method"):
        assert hasattr(bpy.ops.allset, op), op
    for path in ("Create/Add In-Between Target", "Create/Add Selection as In-Between Target",
                 "Create/Add Combination Target", "Create/Add Selection as Combination Target",
                 "Shapes/Set as Combination Target"):
        full = "Shape Editor/" + path
        assert menu_map.spec(full) is not None, full
        assert full not in notices.NOTICES, full            # mapped now: no "not in Blender" notice


def test_empty_inbetween_keeps_the_shape_and_goes_into_edit():
    """Add In-Between Target without a selection = the shape the target has at that weight, then Edit on it
    (Maya Shape Editor: duplicate the shape at the in-between weight, sculptTarget -ibw)."""
    _fresh()
    face, key = _face(("smile", (0, 1, 0)))
    smile = key.key_blocks["smile"]
    before = [_v0_at(face, smile, w) for w in (-0.4, 0.25, 0.6, 1.3)]
    wm = bpy.context.window_manager
    wm.allset_se_current = f"{key.name}/{key.key_blocks.find('smile')}"
    r = bpy.ops.allset.shape_add_inbetween(weight=0.6)
    assert r == {'FINISHED'}, r
    after = [_v0_at(face, smile, w) for w in (-0.4, 0.25, 0.6, 1.3)]
    for a, b in zip(before, after):
        assert max(abs(x - y) for x, y in zip(a, b)) < 1e-5, (before, after)
    assert shape_editor.editing(key) == "smile_ib600", shape_editor.editing(key)
    # removing it gives the straight line back
    shape_editor.edit_off(bpy.context)
    assert bpy.ops.allset.shape_remove_inbetween(key=key.name, target="smile", weight=0.6) == {'FINISHED'}
    assert not bs.inbetweens(key) and key.key_blocks.get("smile_ib600") is None
    assert key.key_blocks.get("smile_ibfix") is None


def test_fix_key_follows_target_edits():
    _fresh()
    face, key = _face(("smile", (0, 1, 0)))
    bs.add_inbetween(key, "smile", 0.5)
    smile = key.key_blocks["smile"]
    co = smile.data[0].co.copy()
    smile.data[0].co = co + type(co)((0.0, 0.0, 1.0))
    assert bs.sync(key)
    assert tuple(key.key_blocks["smile_ibfix"].data[0].co) == tuple(smile.data[0].co)
    got = _v0_at(face, smile, 1.0)
    assert abs(got[2] - (1.0 + 1.0)) < TOL, got           # the edited target at weight 1
    smile.mute = True
    bs.sync(key)
    assert key.key_blocks["smile_ibfix"].mute and key.key_blocks["smile_ib500"].mute
    # deleting the target in Blender drops its helpers
    face.active_shape_key_index = key.key_blocks.find("smile")
    face.shape_key_remove(smile)
    bs.sync(key)
    assert not bs.inbetweens(key) and [kb.name for kb in key.key_blocks] == ["Basis"], [k.name for k in
                                                                                         key.key_blocks]


def test_set_and_selection_combination():
    _fresh()
    face, key = _face(("smile", (0, 1, 0)), ("blink", (0, 1, 0)), ("both", (0, 0.5, 0)))
    wm = bpy.context.window_manager
    for i, name in enumerate(("smile", "blink", "both")):
        assert bpy.ops.allset.shape_pick(key=key.name, index=key.key_blocks.find(name), extend=i > 0) == {'FINISHED'}
    assert shape_editor.picked_targets(bpy.context, key) == ["smile", "blink", "both"]
    assert bpy.ops.allset.shape_add_combination(mode='SET') == {'FINISHED'}
    assert bs.combinations(key) == {"both": (["smile", "blink"], 'MULTIPLY')}
    # Add Selection as Combination Target: every selected mesh becomes a target, the last the combination
    a, b, c = _plane("lid_l", (0, 0.1, 0)), _plane("lid_r", (0, 0.2, 0)), _plane("lids", (0, 0.3, 0))
    _select(face, a, b, c)
    bpy.context.view_layer.objects.active = face
    assert bpy.ops.allset.shape_add_combination(key=key.name, mode='SELECTION', method='LOWEST') == {'FINISHED'}
    assert bs.combinations(key)["lids"] == (["lid_l", "lid_r"], 'LOWEST')
    _simple(key)


def test_undo_restores():
    _fresh()
    face, key = _face(("smile", (0, 1, 0)))
    bpy.ops.ed.undo_push(message="before in-between")
    r = bpy.ops.allset.shape_add_inbetween('EXEC_DEFAULT', True, key=key.name, target="smile", weight=0.5)
    assert r == {'FINISHED'}, r
    assert bpy.data.shape_keys[0].key_blocks.get("smile_ib500") is not None
    bpy.ops.ed.undo()
    key = bpy.data.objects["face"].data.shape_keys
    assert key.key_blocks.get("smile_ib500") is None and not bs.inbetweens(key)


def _channels(path):
    """{BlendShape deformer name: {channel name: (shape names in order, FullWeights)}} of an FBX file."""
    fbx_rig = import_module(kit.MODULE + ".operators.fbx_rig")
    tree, _v = fbx_rig.load(path)
    objs, conns = tree.first(b"Objects"), tree.first(b"Connections")
    ids = {e.props[0]: e for e in objs.elems if e.props}
    kids = {}
    for c in conns.elems:
        if c.props[0] == b"OO":
            kids.setdefault(c.props[2], []).append(c.props[1])
    out = {}
    for d in [e for e in objs.find(b"Deformer") if e.props[2] == b"BlendShape"]:
        chans = {}
        for u in kids.get(d.props[0], ()):
            ch = ids[u]
            shapes = [fbx_rig.name_of(ids[x]) for x in kids.get(u, ()) if x in ids and ids[x].props[2] == b"Shape"]
            fw = ch.first(b"FullWeights")
            chans[fbx_rig.name_of(ch)] = (shapes, [round(x, 3) for x in fw.props[0]] if fw is not None else None)
        out[fbx_rig.name_of(d)] = chans
    return out


def test_fbx_export_writes_maya_blend_shapes():
    """Kit File > Export All (FBX): Maya's blendShape layout — one channel per target, an in-between is a
    second shape of its target's channel (FullWeights 50 / 100, items 5500 / 6000), the helper keys are
    not channels; a combination target is a plain target (Maya FBX writes the combo the same way)."""
    _fresh()
    face, key = _face(("smile", (0, 1, 0)), ("blink", (0, 1, 0)))
    bs.add_inbetween(key, "smile", 0.5)
    assert bpy.ops.allset.shape_add_combination(key=key.name, targets="smile	blink") == {'FINISHED'}
    targets = [kb.name for kb in bs.target_blocks(key)]
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, "blend227.fbx")
    for ob in bpy.context.selected_objects:
        ob.select_set(False)
    r = bpy.ops.allset.file_export_all('EXEC_DEFAULT', filepath=path, export_type='FBX')
    assert r == {'FINISHED'}, r
    got = _channels(path)
    print(f"FBX blend shapes: {got}")
    (name, chans), = got.items()
    assert sorted(chans) == sorted(targets), (sorted(chans), targets)
    assert chans["smile"] == (["smile_ib500", "smile"], [50.0, 100.0]), chans["smile"]
    assert all(v == ([k], [100.0]) for k, v in chans.items() if k != "smile"), chans


def test_fbx_blend_shapes_next_to_a_cluster():
    """A cluster (Hook) on the mesh no longer drops the blend shapes from the FBX."""
    _fresh()
    face, key = _face(("smile", (0, 1, 0)), ("blink", (0, 1, 0)))
    bs.add_inbetween(key, "smile", 0.5)
    e = bpy.data.objects.new("cluster1Handle", None)
    bpy.context.scene.collection.objects.link(e)
    md = face.modifiers.new("cluster1", 'HOOK')
    md.object = e
    md.vertex_indices_set([0])
    path = os.path.join(OUT, "blend227_hook.fbx")
    for ob in bpy.context.selected_objects:
        ob.select_set(False)
    assert bpy.ops.allset.file_export_all('EXEC_DEFAULT', filepath=path, export_type='FBX') == {'FINISHED'}
    (name, chans), = _channels(path).items()
    assert sorted(chans) == ["blink", "smile"], chans
    assert chans["smile"][1] == [50.0, 100.0]
    assert md.show_viewport and md.show_render


def test_unregister_removes_handler():
    assert bs._on_depsgraph in bpy.app.handlers.depsgraph_update_post
    kit.disable()
    assert all(getattr(h, "__name__", "") != "_on_depsgraph" or "blend_shapes_227" not in getattr(h, "__module__", "")
               for h in bpy.app.handlers.depsgraph_update_post)
    assert not hasattr(bpy.types.WindowManager, "allset_se_picked")
    kit.enable()
