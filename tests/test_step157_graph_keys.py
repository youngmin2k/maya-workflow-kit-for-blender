"""Graph Editor keys in Maya terms — key windows on the selected keys, Add / Remove Inbetween on the
editor's curves, per-key Mute / Unmute (Maya holds), Select masks, Default In / Out Tangent."""

from importlib import import_module

import bpy

import kit

gkm = import_module(kit.MODULE + ".operators.graph_key_menu")
option_windows = import_module(kit.MODULE + ".operators.option_windows")
menu_map = import_module(kit.MODULE + ".ui.menu_map")
preferences = import_module(kit.MODULE + ".preferences")


def _scene():
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    bpy.ops.mesh.primitive_cube_add()
    ob = bpy.context.active_object
    for frame, x in ((1, 0.0), (10, 5.0), (20, 0.0), (30, 8.0)):
        ob.location.x = x
        ob.keyframe_insert("location", index=0, frame=frame)
    ob.location.y = 1.0
    ob.keyframe_insert("location", index=1, frame=1)
    for fc in kit.fcurves(ob):
        for kp in fc.keyframe_points:
            kp.interpolation = 'LINEAR'
            kp.select_control_point = kp.select_left_handle = kp.select_right_handle = False
    bpy.context.scene.frame_set(1)
    return ob


def _tx(ob):
    return next(fc for fc in kit.fcurves(ob) if fc.data_path == "location" and fc.array_index == 0)


def _select(ob, times, index=0):
    fc = next(fc for fc in kit.fcurves(ob) if fc.array_index == index)
    for kp in fc.keyframe_points:
        kp.select_control_point = any(abs(kp.co.x - t) < 1e-4 for t in times)


class Editor:
    """A Graph Editor (or Dope Sheet) in the first area for the duration of a with block."""

    def __init__(self, ui_type='FCURVES'):
        self.ui_type = ui_type

    def __enter__(self):
        self.area = bpy.context.window_manager.windows[0].screen.areas[0]
        self.old = self.area.ui_type
        self.area.ui_type = self.ui_type
        region = next(r for r in self.area.regions if r.type == 'WINDOW')
        self.ctx = bpy.context.temp_override(area=self.area, region=region)
        self.ctx.__enter__()
        return self

    def __exit__(self, *exc):
        self.ctx.__exit__(*exc)
        self.area.ui_type = self.old


# --- Mute / Unmute Key -------------------------------------------------------------------------------------


# --- Add / Remove Inbetween ---------------------------------------------------------------------------------

def test_inbetween_moves_keys_after_current_time_on_editor_curves():
    ob = _scene()
    bpy.context.scene.frame_set(10)
    with Editor():
        assert bpy.ops.allset.graph_inbetween(delta="ADD") == {'FINISHED'}
        assert [kp.co.x for kp in _tx(ob).keyframe_points] == [1, 11, 21, 31]
        bpy.ops.allset.graph_inbetween(delta="REMOVE")
        bpy.ops.allset.graph_inbetween(delta="REMOVE")
        assert [kp.co.x for kp in _tx(ob).keyframe_points] == [1, 9, 19, 29]
    ty = next(f for f in kit.fcurves(ob) if f.array_index == 1)
    assert [kp.co.x for kp in ty.keyframe_points] == [1], "keys before the current time stay"


# --- key windows from the editor ----------------------------------------------------------------------------

def _window(path):
    w = option_windows.find_path(path)
    assert w is not None, path
    return w


def test_key_windows_bound_to_editor_edit_menus():
    for ed in ("Graph Editor", "Dope Sheet"):
        for edit, key in (("Delete", "delete_keys"), ("Cut", "cut_keys"), ("Copy", "copy_keys"),
                          ("Paste", "paste_keys"), ("Scale", "scale_keys"), ("Snap", "snap_keys")):
            assert _window(f"{ed}/Edit/{edit}").key == key, (ed, edit)


def test_delete_keys_window_selected_keys_vs_nodes():
    ob = _scene()
    _select(ob, (10,))
    w = _window("Graph Editor/Edit/Delete")
    with Editor():
        option_windows.run(w, bpy.context, w.defaults())
        assert [kp.co.x for kp in _tx(ob).keyframe_points] == [1, 20, 30], "selected key only"
        for fc in kit.fcurves(ob):
            for kp in fc.keyframe_points:
                kp.select_control_point = False
        option_windows.run(w, bpy.context, w.defaults())     # no keys selected: Maya's time range on the nodes
    assert not kit.fcurves(ob) or all(not len(fc.keyframe_points) for fc in kit.fcurves(ob))


def test_delete_keys_from_main_menu_uses_nodes():
    ob = _scene()
    _select(ob, (10,))
    w = _window("Key/Delete Keys")
    option_windows.run(w, bpy.context, w.defaults())       # 3D View context: not from the Graph Editor
    assert not kit.fcurves(ob) or all(not len(fc.keyframe_points) for fc in kit.fcurves(ob))


def test_scale_and_snap_windows_on_selected_keys():
    ob = _scene()
    _select(ob, (10, 20))
    w = _window("Graph Editor/Edit/Scale")
    with Editor():
        v = dict(w.defaults(), time_scale=2.0, time_pivot=0.0, value_scale=1.0)
        option_windows.run(w, bpy.context, v)
        xs = sorted(round(kp.co.x, 4) for kp in _tx(ob).keyframe_points)
        assert xs == [1, 20, 30, 40], ("1 and 30 unselected", xs)
        _select(ob, (20,))
        _tx(ob).keyframe_points[1].co.x = 20.4
        s = _window("Graph Editor/Edit/Snap")
        option_windows.run(s, bpy.context, s.defaults())
        assert round(_tx(ob).keyframe_points[1].co.x, 4) == 20.0


def test_copy_paste_windows_use_the_editor_buffer():
    ob = _scene()
    _select(ob, (10,))
    with Editor():
        c = _window("Graph Editor/Edit/Copy")
        option_windows.run(c, bpy.context, c.defaults())
        assert gkm.editor_clipboard()
        bpy.context.scene.frame_set(15)
        p = _window("Graph Editor/Edit/Paste")
        option_windows.run(p, bpy.context, dict(p.defaults(), value_offset=1.0))
    xs = {round(kp.co.x, 3): round(kp.co.y, 3) for kp in _tx(ob).keyframe_points}
    assert xs.get(15.0) == 6.0, xs


# --- Select masks -------------------------------------------------------------------------------------------

def test_select_masks_filter_new_selection():
    ob = _scene()
    sc = bpy.context.scene
    fc = _tx(ob)
    gkm._mask["last"] = None
    # Only Curve: a newly picked key selects its whole curve, its handles are dropped
    gkm.mask_step(sc, True, False, False, False)          # baseline
    kp = fc.keyframe_points[1]
    kp.select_control_point = kp.select_left_handle = kp.select_right_handle = True
    assert gkm.mask_step(sc, True, False, False, False) == 1
    assert all(k.select_control_point for k in fc.keyframe_points), "the curve"
    assert not fc.keyframe_points[1].select_left_handle and not fc.keyframe_points[1].select_right_handle
    # keys off, curves off: a new key pick is dropped; in tangents allowed
    for k in fc.keyframe_points:
        k.select_control_point = False
    gkm.mask_step(sc, False, False, True, False)
    fc.keyframe_points[2].select_control_point = True
    fc.keyframe_points[2].select_left_handle = True
    gkm.mask_step(sc, False, False, True, False)
    assert not fc.keyframe_points[2].select_control_point and fc.keyframe_points[2].select_left_handle
    # an existing selection isn't touched when a mask changes
    fc.keyframe_points[0].select_control_point = True
    gkm._mask["last"] = None
    gkm.mask_step(sc, False, False, False, False)
    assert fc.keyframe_points[0].select_control_point
    # all on: nothing to do
    assert gkm.mask_step(sc, True, True, True, True) == 0 and gkm._mask["last"] is None


def test_select_type_presets():
    p = preferences.get()
    bpy.ops.allset.graph_select_type(preset="ONLY_CURVE")
    assert (p.graph_select_curve, p.graph_select_key, p.graph_select_in, p.graph_select_out) == \
        (True, False, False, False)
    bpy.ops.allset.graph_select_type(preset="ALL")
    assert gkm.masks() == (True, True, True, True)


# --- Default In / Out Tangent -------------------------------------------------------------------------------

def test_default_tangents_apply_to_kit_keys():
    p = preferences.get()
    try:
        for ob in list(bpy.data.objects):
            bpy.data.objects.remove(ob)
        bpy.ops.mesh.primitive_cube_add()
        ob = bpy.context.active_object
        p.default_in_tangent, p.default_out_tangent = 'FLAT', 'STEPPED'
        sc = bpy.context.scene
        sc.frame_set(1)
        bpy.ops.allset.set_key(channels="TRANSLATE")
        ob.location.x = 3.0
        sc.frame_set(10)
        ob.location.x = 3.0
        bpy.ops.allset.set_key(channels="TRANSLATE")
        fc = _tx(ob)
        k0, k1 = fc.keyframe_points
        assert k1.interpolation == 'CONSTANT' and k0.interpolation == 'CONSTANT',             ("Stepped out tangent", k0.interpolation, k1.interpolation)
        assert k1.handle_left_type == 'FREE' and abs(k1.handle_left.y - k1.co.y) < 1e-6, "Flat in tangent"
        # Auto / Auto = Blender's own new key
        p.default_in_tangent = p.default_out_tangent = 'AUTO'
        sc.frame_set(20)
        bpy.ops.allset.set_key(channels="TRANSLATE")
        k2 = _tx(ob).keyframe_points[2]
        assert k2.handle_left_type == 'AUTO_CLAMPED', "Auto / Auto = Blender's own new key (untouched)"
        # same values on both sides = one apply_tangent
        p.default_in_tangent = p.default_out_tangent = 'LINEAR'
        sc.frame_set(30)
        bpy.ops.allset.set_key(channels="TRANSLATE")
        assert _tx(ob).keyframe_points[3].interpolation == 'LINEAR'
    finally:
        p.default_in_tangent = p.default_out_tangent = 'AUTO'


# --- menus ---------------------------------------------------------------------------------------------------

def test_menu_items_mapped():
    m = menu_map.MAP
    for ed in ("Graph Editor", "Dope Sheet"):
        assert m[f"{ed}/Keys/Mute Key"] == ("allset.mute_key", {"mute": True})
        assert m[f"{ed}/Keys/Unmute Key"] == ("allset.mute_key", {"mute": False})
        assert m[f"{ed}/Keys/Add Inbetween"][0] == "allset.graph_inbetween"
    for ed in ("Graph Editor",):    # Maya's Dope Sheet has no Tangents menu
        assert m[f"{ed}/Tangents/Default In Tangent/Flat"] == ("prop", "addon_prefs.default_in_tangent",
                                                               {"value": 'FLAT'})
        assert m[f"{ed}/Tangents/Default Out Tangent/Stepped"][2] == {"value": 'STEPPED'}
        assert f"{ed}/Tangents/Default In Tangent/Stepped" not in m
    for label in ("Curve", "Key", "In Tangent", "Out Tangent"):
        assert m[f"Graph Editor/Select/{label}"][0] == "prop"
    assert m["Graph Editor/Select/Only Curve"] == ("allset.graph_select_type", {"preset": "ONLY_CURVE"})
    assert m["Key/Set Key on Translate"] == ("allset.set_key", {"channels": "TRANSLATE"})
