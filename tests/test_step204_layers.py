"""Animation layers 4 (Issue #111) — Extract Selected Objects, Duplicate Layer, Empty / Delete Empty Layers,
Zero / Full Weight key, Layer Editor Ctrl / Shift multi-selection and the Graph Editor lines of the other selected
layers (operators/anim_layers_204.py, ui/graph_layers.py). Maya behaviour of the Layer Editor:
extraction keeps the result, a duplicate adds its layer again, each command is
one undo step."""

from importlib import import_module

import bpy

import kit

al = import_module(kit.MODULE + ".operators.anim_layers")
a4 = import_module(kit.MODULE + ".operators.anim_layers_204")
gl = import_module(kit.MODULE + ".ui.graph_layers")
le = import_module(kit.MODULE + ".ui.layer_editor")
compat = import_module(kit.MODULE + ".compat")
FRAMES = (-5, 1, 3, 6, 9, 12, 15, 18, 21, 24, 30)
TOL = 1e-5
CH = (("location", 0), ("location", 1), ("rotation_euler", 1))


def _obj(sc, name, offset):
    ob = bpy.data.objects.new(name, bpy.data.meshes.new(name + "Shape"))
    sc.collection.objects.link(ob)
    for f, x in ((1, 0.0), (12, 5.0), (24, 0.0)):
        ob.location.x = x + offset
        ob.keyframe_insert("location", index=0, frame=f)
    for f, r in ((1, 0.0), (24, 1.5708)):
        ob.rotation_euler.y = r
        ob.keyframe_insert("rotation_euler", index=1, frame=f)
    return ob


def _select(sc, obs):
    for o in sc.objects:
        o.select_set(o in obs)
    bpy.context.view_layer.objects.active = obs[0] if obs else None


def _layered():
    """pCube1 + pSphere1 (base tx 0@1 5@12 0@24, ry 0 -> 90 deg), AnimLayer1 from both, layer tx +2@6 -1@18 on the
    cube and +1@6 on the sphere, ty +3@12 on the cube (two objects)."""
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    for act in list(bpy.data.actions):
        bpy.data.actions.remove(act)
    sc = bpy.context.scene
    sc.allset_anim_layers.clear()
    sc.allset_anim_layer_index = 0
    sc.frame_set(1)
    cube, sphere = _obj(sc, "pCube1", 0.0), _obj(sc, "pSphere1", 1.0)
    _select(sc, [cube, sphere])
    bpy.ops.allset.anim_layer_create(from_selected=True)
    for ob, keys in ((cube, ((6, 0, 2.0), (18, 0, -1.0), (12, 1, 3.0))), (sphere, ((6, 0, 1.0),))):
        for f, idx, d in keys:
            base = al.base_curve(ob, "location", idx)
            v = (base.evaluate(f) if base is not None else 0.0) + d
            assert al.key(ob, "location", idx, frame=f, value=v, scene=sc)
    return sc, cube, sphere


def _names(sc):
    return [e.name for e in sc.allset_anim_layers]


def _evaluated(sc, ob):
    out = []
    for f in FRAMES:
        sc.frame_set(f)
        e = ob.evaluated_get(bpy.context.evaluated_depsgraph_get())
        out.append([e.location[0], e.location[1], e.rotation_euler[1]])
    sc.frame_set(1)
    return out


def _same(a, b, tol=TOL):
    d = max(abs(x - y) for r1, r2 in zip(a, b) for x, y in zip(r1, r2))
    assert d < tol, d


def _check_kit_is_nla(sc, ob):
    """The kit's own composition (anim_layers.result) equals Blender's NLA at every frame (channels some layer has a
    curve for; an unanimated channel keeps its property value)."""
    got = [[al.result(ob, p, i, frame=f, scene=sc) for p, i in CH] for f in FRAMES]
    ev = _evaluated(sc, ob)
    d = max(abs(x - y) for r1, r2 in zip(got, ev) for x, y in zip(r1, r2) if x is not None)
    assert d < TOL, d


def _value(ob, layer, path, index, frame):
    fc = al._fcurve(al._strip(al.tracks(ob)[layer]).action, path, index)
    return fc.evaluate(frame) if fc is not None else 0.0


def _undo_start():
    bpy.ops.ed.undo_push(message="layers test start")


def _op(name, **kw):
    """A command run like a UI button (undo depth 0): one undo step."""
    return getattr(bpy.ops.allset, name)('EXEC_DEFAULT', True, **kw)


def _undo_restores(names_before, members_before):
    bpy.ops.ed.undo()
    sc = bpy.context.scene
    assert _names(sc) == names_before, _names(sc)
    for name, obs in members_before.items():
        assert sorted(o.name for o in al.members(sc, name)) == obs, (name, al.members(sc, name))


# --- Extract Selected Objects ----------------------------------------------------------------------------------

def test_extract_selected_objects_keeps_the_result():
    sc, cube, sphere = _layered()
    before = {o.name: _evaluated(sc, o) for o in (cube, sphere)}
    layer_tx = [kp.co[:] for kp in al._fcurve(al._strip(al.tracks(cube)["AnimLayer1"]).action, "location", 0)
                .keyframe_points]
    _select(sc, [cube])
    _undo_start()
    assert _op("anim_layer_extract") == {'FINISHED'}
    sc = bpy.context.scene
    cube, sphere = bpy.data.objects["pCube1"], bpy.data.objects["pSphere1"]
    # Maya: <layer>_extract right above the layer, same settings, the selected objects' attributes and curves moved
    assert _names(sc) == [al.BASE, "AnimLayer1", "AnimLayer1_extract"], _names(sc)
    assert set(al.tracks(cube)) == {al.BASE, "AnimLayer1_extract"}, set(al.tracks(cube))
    assert set(al.tracks(sphere)) == {al.BASE, "AnimLayer1"}
    moved = al._fcurve(al._strip(al.tracks(cube)["AnimLayer1_extract"]).action, "location", 0)
    assert [kp.co[:] for kp in moved.keyframe_points] == layer_tx
    assert [tr.name for tr in cube.animation_data.nla_tracks] == [al.BASE, "AnimLayer1_extract"]
    for o in (cube, sphere):
        _same(_evaluated(sc, o), before[o.name])
        _check_kit_is_nla(sc, o)
    _undo_restores([al.BASE, "AnimLayer1"], {"AnimLayer1": ["pCube1", "pSphere1"]})


def test_extract_keeps_mode_not_weight():
    """Maya: the extract layer keeps Additive / Override but has weight 1.0 without L's
    weight keys, so the result changes when L's weight isn't 1 (Maya extract case)."""
    sc, cube, sphere = _layered()
    e = sc.allset_anim_layers[1]
    e.override = True
    e.weight = 0.5
    a4.key_weight(sc, ["AnimLayer1"], 0.25, frame=6)
    before = _evaluated(sc, cube)
    _select(sc, [cube])
    a4.extract(sc, [cube], "AnimLayer1")
    new = sc.allset_anim_layers["AnimLayer1_extract"]
    assert new.override and abs(new.weight - 1.0) < 1e-9, (new.override, new.weight)
    st = al._strip(al.tracks(cube)["AnimLayer1_extract"])
    assert not st.use_animated_influence or abs(st.influence - 1.0) < 1e-9     # full weight, no keys
    st = al._strip(al.tracks(sphere)["AnimLayer1"])         # L keeps its weight keys for its other members
    assert st.use_animated_influence and len(st.fcurves.find("influence").keyframe_points) == 1
    assert before != _evaluated(sc, cube)
    _check_kit_is_nla(sc, cube)


def test_extract_from_base_animation():
    """BaseAnimation selected (or Extract Non-Layered Animation): an Override layer BaseAnimation_extract right above
    BaseAnimation takes the objects' base curves."""
    sc, cube, sphere = _layered()
    before = _evaluated(sc, cube)
    base_tx = [kp.co[:] for kp in al.base_curve(cube, "location", 0).keyframe_points]
    sc.allset_anim_layer_index = 0
    _select(sc, [cube])
    _undo_start()
    assert _op("anim_layer_extract") == {'FINISHED'}
    sc = bpy.context.scene
    cube = bpy.data.objects["pCube1"]
    assert _names(sc) == [al.BASE, "BaseAnimation_extract", "AnimLayer1"], _names(sc)
    assert sc.allset_anim_layers[1].override
    assert al.base_curve(cube, "location", 0) is None
    got = al._fcurve(al._strip(al.tracks(cube)["BaseAnimation_extract"]).action, "location", 0)
    assert [kp.co[:] for kp in got.keyframe_points] == base_tx
    _same(_evaluated(sc, cube), before)
    _check_kit_is_nla(sc, cube)
    _undo_restores([al.BASE, "AnimLayer1"], {"AnimLayer1": ["pCube1", "pSphere1"]})


# --- Duplicate Layer -------------------------------------------------------------------------------------------

def test_duplicate_layer_adds_it_again():
    sc, cube, sphere = _layered()
    base = [[_value(cube, al.BASE, p, i, f) for p, i in CH] for f in FRAMES]
    layer = [[_value(cube, "AnimLayer1", p, i, f) for p, i in CH] for f in FRAMES]
    _undo_start()
    assert _op("anim_layer_duplicate") == {'FINISHED'}
    sc = bpy.context.scene
    cube = bpy.data.objects["pCube1"]
    assert _names(sc) == [al.BASE, "AnimLayer1", "AnimLayer1_copy"], _names(sc)
    assert sorted(o.name for o in al.members(sc, "AnimLayer1_copy")) == ["pCube1", "pSphere1"]
    # Additive twice: base + 2 x layer
    want = [[b + 2 * x for b, x in zip(rb, rl)] for rb, rl in zip(base, layer)]
    _same(_evaluated(sc, cube), want)
    _check_kit_is_nla(sc, cube)
    # a second copy gets Maya's number suffix
    sc.allset_anim_layer_index = 1
    a4.duplicate(sc, "AnimLayer1")
    assert _names(sc) == [al.BASE, "AnimLayer1", "AnimLayer1_copy1", "AnimLayer1_copy"], _names(sc)
    _undo_restores([al.BASE, "AnimLayer1"], {"AnimLayer1": ["pCube1", "pSphere1"]})


def test_duplicate_layer_no_animation():
    """Maya: an additive copy without animation adds nothing; an override one holds L's value at the current time
    (copy without animation, L1 / L2)."""
    sc, cube, sphere = _layered()
    before = _evaluated(sc, cube)
    assert _op("anim_layer_duplicate", no_animation=True) == {'FINISHED'}
    sc = bpy.context.scene
    cube = bpy.data.objects["pCube1"]
    assert al.layer_curves(cube, "AnimLayer1_copy") == []
    _same(_evaluated(sc, cube), before)
    sc.allset_anim_layer_index = 1
    sc.allset_anim_layers[1].override = True
    sc.frame_set(9)
    a4.duplicate(sc, "AnimLayer1", with_curves=False)
    copy = sc.allset_anim_layers["AnimLayer1_copy1"]
    assert copy.override and copy.weight == 1.0
    assert sorted(o.name for o in al.members(sc, "AnimLayer1_copy1")) == ["pCube1", "pSphere1"]
    held = {(fc.data_path, fc.array_index): fc for fc in al.layer_curves(cube, "AnimLayer1_copy1")}
    assert set(held) == {("location", 0), ("location", 1)}, set(held)
    for (path, idx), fc in held.items():
        assert len(fc.keyframe_points) == 1 and fc.keyframe_points[0].interpolation == 'CONSTANT'
        assert abs(fc.keyframe_points[0].co.y - _value(cube, "AnimLayer1", path, idx, 9)) < TOL
    ev = _evaluated(sc, cube)
    assert all(abs(r[0] - _value(cube, "AnimLayer1", "location", 0, 9)) < TOL for r in ev)
    _check_kit_is_nla(sc, cube)


def test_duplicate_base_animation():
    """Maya (copy_base): an Override BaseAnimation_copy on top; members = the layered attributes, curves = copies of
    the base curves; it overrides every layer below."""
    sc, cube, sphere = _layered()
    sc.allset_anim_layer_index = 0
    assert _op("anim_layer_duplicate") == {'FINISHED'}
    sc = bpy.context.scene
    cube = bpy.data.objects["pCube1"]
    assert _names(sc) == [al.BASE, "AnimLayer1", "BaseAnimation_copy"], _names(sc)
    copy = sc.allset_anim_layers["BaseAnimation_copy"]
    assert copy.override and copy.weight == 1.0
    tx = al._fcurve(al._strip(al.tracks(cube)["BaseAnimation_copy"]).action, "location", 0)
    assert [kp.co[:] for kp in tx.keyframe_points] == [kp.co[:] for kp in al.base_curve(cube, "location", 0)
                                                       .keyframe_points]
    for f, r in zip(FRAMES, _evaluated(sc, cube)):
        assert abs(r[0] - al.base_curve(cube, "location", 0).evaluate(f)) < TOL, (f, r)
    _check_kit_is_nla(sc, cube)


# --- Empty / Delete Empty Layers ----------------------------------------------------------------------------------

def test_empty_and_delete_empty_layers():
    sc, cube, sphere = _layered()
    bpy.ops.allset.anim_layer_create(from_selected=False)          # AnimLayer2, empty
    assert _names(sc) == [al.BASE, "AnimLayer1", "AnimLayer2"]
    sc.allset_anim_layer_index = 1
    _undo_start()
    assert _op("anim_layer_delete_empty") == {'FINISHED'}
    sc = bpy.context.scene
    assert _names(sc) == [al.BASE, "AnimLayer1"], _names(sc)
    assert sc.allset_anim_layers[sc.allset_anim_layer_index].name == "AnimLayer1"
    _undo_restores([al.BASE, "AnimLayer1", "AnimLayer2"], {"AnimLayer1": ["pCube1", "pSphere1"]})
    sc = bpy.context.scene
    sc.allset_anim_layer_index = 1
    _undo_start()
    assert _op("anim_layer_empty") == {'FINISHED'}
    sc = bpy.context.scene
    assert al.members(sc, "AnimLayer1") == [] and "AnimLayer1" in _names(sc)
    cube = bpy.data.objects["pCube1"]
    _check_kit_is_nla(sc, cube)
    assert abs(_evaluated(sc, cube)[3][0] - al.base_curve(cube, "location", 0).evaluate(6)) < TOL
    bpy.ops.allset.anim_layer_delete_empty()
    assert _names(sc) == [al.BASE], _names(sc)
    assert sc.allset_anim_layer_index == 0


# --- Zero / Full Weight key -------------------------------------------------------------------------------------

def test_zero_and_full_weight_keys():
    sc, cube, sphere = _layered()
    sc.frame_set(1)
    _undo_start()
    assert _op("anim_layer_key_weight", weight=0.0) == {'FINISHED'}
    sc = bpy.context.scene
    sc.frame_set(12)
    assert _op("anim_layer_key_weight", weight=1.0) == {'FINISHED'}
    sc = bpy.context.scene
    cube = bpy.data.objects["pCube1"]
    for ob in (cube, bpy.data.objects["pSphere1"]):
        fc = al._strip(al.tracks(ob)["AnimLayer1"]).fcurves.find("influence")
        assert [(round(kp.co.x), round(kp.co.y, 6)) for kp in fc.keyframe_points] == [(1, 0.0), (12, 1.0)]
    assert sc.allset_anim_layers[1].weight == 1.0
    _check_kit_is_nla(sc, cube)
    ev = _evaluated(sc, cube)
    base6 = al.base_curve(cube, "location", 0).evaluate(6)
    fc = al._strip(al.tracks(cube)["AnimLayer1"]).fcurves.find("influence")
    assert abs(ev[3][0] - (base6 + fc.evaluate(6) * 2.0)) < TOL, (ev[3][0], base6, fc.evaluate(6))
    assert abs(ev[1][0] - al.base_curve(cube, "location", 0).evaluate(1)) < TOL      # weight 0 at frame 1
    # weight keys survive the track rebuild of a later layer edit
    _select(sc, [cube])
    bpy.ops.allset.anim_layer_create(from_selected=True)
    fc = al._strip(al.tracks(cube)["AnimLayer1"]).fcurves.find("influence")
    assert fc is not None and len(fc.keyframe_points) == 2
    _check_kit_is_nla(sc, cube)
    # undo: one step per command
    bpy.ops.ed.undo()      # the create above was a nested call: undo the full weight key
    bpy.ops.ed.undo()      # and the zero weight key
    sc = bpy.context.scene
    st = al._strip(al.tracks(bpy.data.objects["pCube1"])["AnimLayer1"])
    assert not st.use_animated_influence or not len(st.fcurves.find("influence").keyframe_points)


def test_weight_keys_on_base_animation():
    """Maya (zero_weight_base): BaseAnimation's weight isn't changed but keyed; the kit keys its strips at 1.0."""
    sc, cube, sphere = _layered()
    sc.allset_anim_layer_index = 0
    before = _evaluated(sc, cube)
    sc.frame_set(10)
    assert bpy.ops.allset.anim_layer_key_weight(weight=0.0) == {'FINISHED'}
    st = al._strip(al.tracks(cube)[al.BASE])
    fc = st.fcurves.find("influence")
    assert [tuple(kp.co) for kp in fc.keyframe_points] == [(10.0, 1.0)], [tuple(kp.co) for kp in fc.keyframe_points]
    _same(_evaluated(sc, cube), before)
    # the Weight row's K button keys the current weight
    sc.allset_anim_layer_index = 1
    sc.allset_anim_layers[1].weight = 0.5
    sc.frame_set(10)
    assert bpy.ops.allset.anim_layer_key_weight(current=True) == {'FINISHED'}
    fc = al._strip(al.tracks(cube)["AnimLayer1"]).fcurves.find("influence")
    assert [tuple(kp.co) for kp in fc.keyframe_points] == [(10.0, 0.5)]


def test_menu_greys_with_base_animation():
    """Maya greys Add / Remove Selected Objects, Delete, Empty, Delete Empty Layers while BaseAnimation is among the
    selected layers; Extract / Duplicate / Merge stay enabled."""
    sc, cube, sphere = _layered()
    bpy.ops.allset.anim_layer_select(index=1)
    assert not a4.base_selected(sc)
    bpy.ops.allset.anim_layer_select(index=0, toggle=True)
    assert a4.base_selected(sc)
    assert set(le.GREY_WITH_BASE) <= {e[1] for e in le.ANIM_LAYER_MENU if e is not None}
    for label in ("Extract Selected Objects", "Duplicate Layer", "Merge Layers", "Zero Key Layer"):
        assert label not in le.GREY_WITH_BASE
    # row right-click menu: an unselected row acts on that row only
    a4.pick(sc, 1)
    assert _op("anim_layer_duplicate", layer=al.BASE) == {'FINISHED'}
    sc = bpy.context.scene
    assert "BaseAnimation_copy" in _names(sc) and "AnimLayer1_copy" not in _names(sc), _names(sc)


# --- Layer Editor multi-selection ---------------------------------------------------------------------------------

def test_ctrl_shift_selection_model():
    sc, cube, sphere = _layered()
    bpy.ops.allset.anim_layer_create(from_selected=False)
    bpy.ops.allset.anim_layer_create(from_selected=False)     # Base, AnimLayer1, AnimLayer2, AnimLayer3
    sel = lambda: [e.name for e in al.selected_layers(sc)]    # noqa: E731
    bpy.ops.allset.anim_layer_select(index=1)
    assert sel() == ["AnimLayer1"]
    bpy.ops.allset.anim_layer_select(index=0, toggle=True)
    assert sel() == [al.BASE, "AnimLayer1"] and sc.allset_anim_layer_index == 0
    bpy.ops.allset.anim_layer_select(index=3, toggle=True)
    assert sel() == [al.BASE, "AnimLayer1", "AnimLayer3"] and sc.allset_anim_layer_index == 3
    bpy.ops.allset.anim_layer_select(index=3, toggle=True)          # Ctrl again: removed, another stays last
    assert sel() == [al.BASE, "AnimLayer1"] and sc.allset_anim_layer_index in (0, 1)
    bpy.ops.allset.anim_layer_select(index=1)
    bpy.ops.allset.anim_layer_select(index=3, extend_range=True)    # Shift: the range
    assert sel() == ["AnimLayer1", "AnimLayer2", "AnimLayer3"] and sc.allset_anim_layer_index == 3
    bpy.ops.allset.anim_layer_select(index=2, toggle=True)
    bpy.ops.allset.anim_layer_select(index=2, toggle=True)
    assert sel() == ["AnimLayer1", "AnimLayer2", "AnimLayer3"]
    sc.allset_anim_layer_index = 0               # a direct write = a plain single selection
    assert sel() == [al.BASE]
    # commands act on every selected layer
    bpy.ops.allset.anim_layer_select(index=1)
    bpy.ops.allset.anim_layer_select(index=2, toggle=True)
    bpy.ops.allset.anim_layer_duplicate()
    assert _names(sc) == [al.BASE, "AnimLayer1", "AnimLayer1_copy", "AnimLayer2", "AnimLayer2_copy", "AnimLayer3"], \
        _names(sc)
    assert sel() == ["AnimLayer1", "AnimLayer2"]


def test_layer_editor_menu_in_maya_order():
    labels = [e[1] for e in le.ANIM_LAYER_MENU if e is not None]
    order = ["Create Empty Layer", "Create Layer from Selected", "Add Selected Objects", "Remove Selected Objects",
             "Extract Selected Objects", "Duplicate Layer", "Duplicate Layer (No Animation)", "Merge Layers",
             "Extract Non-Layered Animation for Selected Objects", "Extract Non-Layered Animation for All Objects",
             "Delete", "Empty", "Delete Empty Layers"]
    assert [x for x in labels if x in order] == order, labels
    for e in le.ANIM_LAYER_MENU + le.ANIM_TOOLBAR:
        if e is not None:
            assert compat.has_op(bpy.ops.allset, e[0].split(".")[1]), e[0]


# --- Graph Editor: the other selected layers ---------------------------------------------------------------------

def test_graph_lines_for_two_selected_layers():
    sc, cube, sphere = _layered()
    bpy.ops.allset.anim_layer_select(index=1)
    assert gl.extra_curves(sc, cube) == [] and gl.lines(sc, [cube], 1, 24, 23) == []
    bpy.ops.allset.anim_layer_select(index=0, toggle=True)
    bpy.ops.allset.anim_layer_select(index=1, toggle=True)
    bpy.ops.allset.anim_layer_select(index=1, toggle=True)          # BaseAnimation + AnimLayer1, last = AnimLayer1
    assert sc.allset_anim_layer_index == 1
    assert cube.animation_data.action.get(al.MARK) == "AnimLayer1"  # Blender's editable curves = the last picked
    extra = gl.extra_curves(sc, cube)
    assert {(n, fc.data_path, fc.array_index) for n, fc in extra} == \
        {(al.BASE, "location", 0), (al.BASE, "rotation_euler", 1)}, extra
    items = gl.lines(sc, [cube, sphere], 1.0, 24.0, 23)
    assert len(items) == 4, len(items)          # base tx + ry of both objects
    for rgba, ob, name, pts in items:
        assert name == al.BASE and len(pts) == 24 and rgba[3] < 1.0
        assert any(all(abs(y - f.evaluate(x) * gl.value_factor(sc, f)) < 1e-4 for x, y in pts)
                   for _n, f in gl.extra_curves(sc, ob)), (ob.name, pts[:3])
    # the kit outliner rows: a BaseAnimation row and its curves under each object
    rows = gl.outliner_rows(sc, cube)
    assert [r[0] for r in rows] == ["LAYER", "LAYER_ATTR", "LAYER_ATTR"], rows
    assert gl.layer_of_row(rows[0]) == al.BASE and gl.layer_of_row(rows[1]) == al.BASE
    assert len({gl.row_id(r) for r in rows}) == 3
    # picking a drawn curve / row makes that layer the last picked one, the selection stays
    got = gl.hit(items, lambda x, y: (x * 10.0, y * 10.0), items[0][3][5][0] * 10.0, items[0][3][5][1] * 10.0 + 3)
    assert got == (items[0][1], al.BASE), got
    assert gl.activate_row(bpy.context, rows[0])
    assert sc.allset_anim_layer_index == 0
    assert [e.name for e in al.selected_layers(sc)] == [al.BASE, "AnimLayer1"]
    assert cube.animation_data.action.get(al.MARK) == al.BASE
    assert {n for n, _fc in gl.extra_curves(sc, cube)} == {"AnimLayer1"}
    # an object only in BaseAnimation shows its base, no extra lines
    _check_kit_is_nla(sc, cube)


def test_normalized_lines_span_minus_one_to_one():
    sc, cube, sphere = _layered()
    bpy.ops.allset.anim_layer_select(index=1)
    bpy.ops.allset.anim_layer_select(index=0, toggle=True)
    bpy.ops.allset.anim_layer_select(index=1, toggle=True)
    bpy.ops.allset.anim_layer_select(index=1, toggle=True)
    items = gl.lines(sc, [cube], 1.0, 24.0, 230, normalize=True)
    for _rgba, _ob, _n, pts in items:
        ys = [y for _x, y in pts]
        assert min(ys) >= -1.0001 and max(ys) <= 1.0001, (min(ys), max(ys))


def test_layer_curves_use_axis_colours():
    """A layer's transform curves draw X / Y / Z red / green / blue like Maya (not AUTO_RAINBOW)."""
    sc, cube, _sphere = _layered()
    act = al._strip(al.tracks(cube)["AnimLayer1"]).action
    for idx in (0, 1):
        fc = al._fcurve(act, "location", idx)
        assert fc is not None and fc.color_mode == 'AUTO_RGB', (idx, fc and fc.color_mode)
