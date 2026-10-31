"""Shape Editor (Issue #119) — Maya blendShape editing on Blender shape keys (ui/shape_editor.py).
Maya rules: Create Blend Shape = blendShape1, blendShape2 (one
past the highest); Add Target = pCube2, pCube3 (duplicate name, next free alias; after renaming pCube2 the next is
pCube2 again), weight 1.0, zero delta, the new target in Edit; weight w blends base + w * delta."""

from importlib import import_module

import bpy

import kit

shape_editor = import_module(kit.MODULE + ".ui.shape_editor")
compat = import_module(kit.MODULE + ".compat")

CUBE = [(x, y, z) for x in (-0.5, 0.5) for y in (-0.5, 0.5) for z in (-0.5, 0.5)]
FACES = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]


def _cube(name):
    me = bpy.data.meshes.new(name.replace("pCube", "pCubeShape"))
    me.from_pydata(CUBE, [], FACES)
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def _select(*obs):
    for o in bpy.context.scene.objects:
        o.select_set(o in obs)
    bpy.context.view_layer.objects.active = obs[-1] if obs else None


def _fresh():
    bpy.ops.wm.read_homefile(use_empty=True)
    wm = bpy.context.window_manager
    wm.allset_se_current = ""
    wm.allset_se_edit = ""


def _ok(r):
    assert r == {'FINISHED'}, r


def _targets(ob):
    return [kb.name for kb in ob.data.shape_keys.key_blocks[1:]]


def test_registered():
    assert hasattr(bpy.types, "ALLSET_PT_shape_editor")
    for op in ("shape_editor", "shape_create", "shape_add_target", "shape_add_selection", "shape_edit", "shape_key",
               "shape_reset", "shape_duplicate", "shape_flip", "shape_mirror", "shape_pick"):
        assert compat.has_op(bpy.ops.allset, op), op


def test_create_blend_shape_names():
    _fresh()
    a, b = _cube("pCube1"), _cube("pCube2")
    _select(a)
    _ok(bpy.ops.allset.shape_create())
    assert a.data.shape_keys is not None and a.data.shape_keys.name == "blendShape1"
    assert len(a.data.shape_keys.key_blocks) == 1, "SE4: no targets, only Blender's Basis"
    _select(b)
    _ok(bpy.ops.allset.shape_create())
    assert b.data.shape_keys.name == "blendShape2", b.data.shape_keys.name
    a.data.shape_keys.name = "blendShape7"
    c = _cube("pCube3")
    _select(c)
    _ok(bpy.ops.allset.shape_create())
    assert c.data.shape_keys.name == "blendShape8", "Maya: one past the highest"
    # a mesh that already has one: Blender has one Key per mesh
    _select(a)
    r = bpy.ops.allset.shape_create()
    assert r == {'CANCELLED'} and a.data.shape_keys.name == "blendShape7"


def test_add_target_names_weight_delta():
    _fresh()
    ob = _cube("pCube1")
    _select(ob)
    _ok(bpy.ops.allset.shape_create())
    key = ob.data.shape_keys
    bpy.context.window_manager.allset_se_current = key.name
    _ok(bpy.ops.allset.shape_add_target())
    _ok(bpy.ops.allset.shape_add_target())
    assert _targets(ob) == ["pCube2", "pCube3"], _targets(ob)
    kb = key.key_blocks["pCube2"]
    assert abs(kb.value - 1.0) < 1e-6, "SE5: weight 1.0"
    assert all((p.co - v.co).length < 1e-6 for p, v in zip(kb.data, ob.data.vertices)), "zero delta"
    # the last added target is in Edit
    assert ob.active_shape_key_index == 2 and shape_editor.editing(key) == "pCube3"
    kb.name = "smile"
    _ok(bpy.ops.allset.shape_add_target())
    assert _targets(ob) == ["smile", "pCube3", "pCube2"], "Maya: after a rename pCube2 again"
    # an object pCube4 in the scene raises the number (the duplicate's node name)
    _cube("pCube4")
    _ok(bpy.ops.allset.shape_add_target())
    assert _targets(ob)[-1] == "pCube5", _targets(ob)


def test_add_target_needs_a_blend_shape():
    _fresh()
    ob = _cube("pCube1")
    _select(ob)
    assert not bpy.ops.allset.shape_add_target.poll()
    _ok(bpy.ops.allset.shape_create())
    assert bpy.ops.allset.shape_add_target.poll(), "the selected mesh has a blendShape"


def test_edit_one_target_at_a_time():
    _fresh()
    a, b = _cube("pCube1"), _cube("pSphere1")
    for ob in (a, b):
        _select(ob)
        _ok(bpy.ops.allset.shape_create())
        bpy.context.window_manager.allset_se_current = ob.data.shape_keys.name
        _ok(bpy.ops.allset.shape_add_target())
    ka, kb_ = a.data.shape_keys, b.data.shape_keys
    assert shape_editor.editing(kb_) and not shape_editor.editing(ka), "only the last added target edits"
    assert a.active_shape_key_index == 0
    _ok(bpy.ops.allset.shape_edit(key=ka.name, target="pCube2"))
    assert a.active_shape_key_index == 1 and a.use_shape_key_edit_mode
    assert b.active_shape_key_index == 0 and not shape_editor.editing(kb_), "Maya: one target in Edit"
    _ok(bpy.ops.allset.shape_edit(key=ka.name, target="pCube2"))
    assert a.active_shape_key_index == 0 and not shape_editor.editing(ka), "Edit off = back to the Basis"


def _evaluated_co(ob, i):
    dg = bpy.context.evaluated_depsgraph_get()
    dg.update()
    return ob.evaluated_get(dg).data.vertices[i].co.copy()


def test_weight_blends_linearly_and_reset():
    _fresh()
    ob = _cube("pCube1")
    _select(ob)
    _ok(bpy.ops.allset.shape_create())
    bpy.context.window_manager.allset_se_current = ob.data.shape_keys.name
    _ok(bpy.ops.allset.shape_add_target())
    key = ob.data.shape_keys
    kb = key.key_blocks["pCube2"]
    assert abs(ob.data.vertices[0].co.y + 0.5) < 1e-6
    kb.data[0].co.y += 0.5          # SE6: the sculpted delta (0, 0.5, 0) on vtx[0]
    kb.value = 0.5
    assert abs(_evaluated_co(ob, 0).y + 0.25) < 1e-5, "SE7: w 0.5 -> half the move"
    kb.value = 0.0
    assert abs(_evaluated_co(ob, 0).y + 0.5) < 1e-5, "SE7: w 0 -> base"
    kb.value = 0.7
    bpy.context.window_manager.allset_se_current = f"{key.name}/1"
    _ok(bpy.ops.allset.shape_reset())
    assert kb.value == 0.0, "SE8: Reset -> 0"


def test_key_weight():
    _fresh()
    ob = _cube("pCube1")
    _select(ob)
    _ok(bpy.ops.allset.shape_create())
    key = ob.data.shape_keys
    bpy.context.window_manager.allset_se_current = key.name
    _ok(bpy.ops.allset.shape_add_target())
    bpy.context.scene.frame_set(5)
    bpy.context.window_manager.allset_se_current = f"{key.name}/1"
    _ok(bpy.ops.allset.shape_key())
    paths = {fc.data_path for fc in compat.id_fcurves(key)}
    assert 'key_blocks["pCube2"].value' in paths, paths
    fc = next(fc for fc in compat.id_fcurves(key) if fc.data_path == 'key_blocks["pCube2"].value')
    assert [tuple(k.co) for k in fc.keyframe_points] == [(5.0, 1.0)]


def test_add_selection_as_target():
    _fresh()
    base, t = _cube("pCube1"), _cube("pCube2")
    t.data.vertices[0].co.y += 1.0
    _select(base)
    _ok(bpy.ops.allset.shape_create())
    bpy.context.window_manager.allset_se_current = base.data.shape_keys.name
    _select(t, base)
    _ok(bpy.ops.allset.shape_add_selection())
    key = base.data.shape_keys
    assert _targets(base) == ["pCube2"], _targets(base)
    kb = key.key_blocks["pCube2"]
    assert kb.value == 0.0, "doBlendShapeAddSelectionAsTarget ... 0 1: reset weight, no Edit"
    assert abs(kb.data[0].co.y - 0.5) < 1e-6
    assert not shape_editor.editing(key)


def test_duplicate_flip_mirror():
    _fresh()
    ob = _cube("pCube1")
    _select(ob)
    _ok(bpy.ops.allset.shape_create())
    key = ob.data.shape_keys
    bpy.context.window_manager.allset_se_current = key.name
    _ok(bpy.ops.allset.shape_add_target())
    kb = key.key_blocks["pCube2"]
    kb.data[0].co.y += 0.5          # vtx 0 is on the -X side; its mirror partner is vtx 4
    bpy.context.window_manager.allset_se_current = f"{key.name}/1"
    _ok(bpy.ops.allset.shape_duplicate())
    _ok(bpy.ops.allset.shape_duplicate())
    assert _targets(ob) == ["pCube2", "pCube2_Copy", "pCube2_Copy1"], _targets(ob)
    dup = key.key_blocks["pCube2_Copy"]
    assert abs(dup.data[0].co.y) < 1e-6, "a copy of the target's points"
    _ok(bpy.ops.allset.shape_flip())
    assert abs(kb.data[0].co.y + 0.5) < 1e-6 and abs(kb.data[4].co.y) < 1e-6, "Flip: the move goes to the other side"
    _ok(bpy.ops.allset.shape_mirror(direction='POSITIVE'))
    assert abs(kb.data[4].co.y) < 1e-6 and abs(kb.data[0].co.y) < 1e-6, "+X -> -X: the -X side gets the +X move"
    kb.data[4].co.y += 0.25
    _ok(bpy.ops.allset.shape_mirror(direction='POSITIVE'))
    assert abs(kb.data[0].co.y - 0.25) < 1e-6, "+X move (0, 0.75, 0) copied onto -X"


class _Layout:
    """Accepts every UILayout call (headless: no real layout) and records them."""

    def __init__(self, log):
        object.__setattr__(self, "_log", log)

    def __getattr__(self, name):
        def call(*args, **kw):
            self._log.append((name, args, kw))
            return _Layout(self._log)
        return call

    def __setattr__(self, name, value):
        pass


def test_tree_draws_rows():
    _fresh()
    ob = _cube("pCube1")
    _select(ob)
    _ok(bpy.ops.allset.shape_create())
    _ok(bpy.ops.allset.shape_add_target())
    log = []
    shape_editor.draw_toolbar(_Layout(log), bpy.context)
    shape_editor.draw_tree(_Layout(log), bpy.context)
    texts = [kw.get("text") for name, _a, kw in log if name in ("operator", "label")]
    assert "blendShape1" in texts and "1.000" in texts, texts
    edits = [a for name, a, kw in log if name == "operator" and a[0] == "allset.shape_edit" and kw.get("depress")]
    assert edits, "the new target's Edit button is pressed"


def test_unregister_clean():
    kit.disable()
    assert not hasattr(bpy.types.WindowManager, "allset_se_current")
    assert not hasattr(bpy.types, "ALLSET_PT_shape_editor")
    kit.enable()
    assert hasattr(bpy.types.WindowManager, "allset_se_current")
