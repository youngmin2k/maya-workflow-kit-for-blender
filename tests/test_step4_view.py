"""View history, smooth preview, component modes, keys."""

from importlib import import_module

import bpy

import kit

preferences = import_module(kit.MODULE + ".preferences")
view = import_module(kit.MODULE + ".operators.view")
display = import_module(kit.MODULE + ".operators.display")
maya_patches = import_module(kit.MODULE + ".keymap.maya_patches")

INPUTS = bpy.context.preferences.inputs


def _kmis(km_name, idname, type, shift=False, ctrl=False, alt=False):
    km = kit.maya_kc().keymaps[km_name]
    return [k for k in km.keymap_items if k.active and k.idname == idname and k.type == type
            and k.value == 'PRESS' and k.shift == shift and k.ctrl == ctrl and k.alt == alt]


# --- preferences: left alone ---------------------------------------------

def test_navigation_preferences_left_alone():
    """The Maya navigation preset (turntable, dolly, no zoom to mouse, ...) is gone:
    Maya mode leaves Blender's navigation preferences at the user's values."""
    defaults = {p.identifier: p.default for p in INPUTS.bl_rna.properties
                if p.identifier in ("view_zoom_axis", "view_zoom_method", "use_zoom_to_mouse", "view_rotate_method")}
    for name, default in defaults.items():
        assert getattr(INPUTS, name) == default, (name, getattr(INPUTS, name), default)
    assert not hasattr(preferences.get(), "use_maya_navigation")


# --- view history ----------------------------------------------------------------

def test_view_history_records_settled_changes():
    h = view.ViewHistory(limit=3)
    h.observe("A")
    h.observe("B")            # moving
    h.observe("C")            # still moving
    h.observe("C")            # settled -> A recorded
    assert h.undo == ["A"] and h.stable == "C"
    assert h.step_back("C") == "A" and h.redo == ["C"]
    h.observe("A")            # the restored view is not recorded again
    assert h.undo == []
    assert h.step_forward("A") == "C"
    assert h.step_back("C") == "A"
    h.observe("D")
    h.observe("D")            # new change after undo clears redo
    assert h.redo == [] and h.undo == ["A"]


def test_view_history_unsettled_change_and_limit():
    h = view.ViewHistory(limit=2)
    h.observe("A")
    assert h.step_back("B") == "A"   # change not yet settled is recorded first
    assert h.step_forward("A") == "B"
    for s in "CDEF":
        h.observe(s)
        h.observe(s)
    assert len(h.undo) == 2
    assert h.step_forward("F") is None
    fresh = view.ViewHistory()
    assert fresh.step_back("X") is None and fresh.undo == []
    assert view.ViewHistory().step_forward("X") is None


def test_capture_restore_roundtrip():
    rv3d = next(a.spaces.active.region_3d for s in bpy.data.screens for a in s.areas
                if a.type == 'VIEW_3D')
    before = view.capture(rv3d)
    rv3d.view_distance *= 3
    rv3d.view_location = (1.0, 2.0, 3.0)
    assert view.capture(rv3d) != before
    view.restore(rv3d, before)
    assert view.capture(rv3d) == before


def test_view_history_timer_registered():
    assert bpy.app.timers.is_registered(view.poll_views)
    kit.disable()
    try:
        assert not bpy.app.timers.is_registered(view.poll_views)
    finally:
        kit.enable()


class _RV3D:
    def __init__(self, persp, side):
        self.view_perspective, self.is_orthographic_side_view = persp, side


def test_tumble_lock_rule():
    assert view.tumble_locked(_RV3D('ORTHO', True), True)
    assert not view.tumble_locked(_RV3D('ORTHO', False), True)   # user ortho
    assert not view.tumble_locked(_RV3D('PERSP', False), True)
    assert not view.tumble_locked(_RV3D('ORTHO', True), False)  # option off


# --- smooth preview / component modes --------------------------------------------

def _mesh(name):
    me = bpy.data.meshes.new(name)
    me.from_pydata([(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)], [], [(0, 1, 2, 3)])
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def _select(ob):
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob


def test_smooth_preview_levels():
    ob = _mesh("sp_a")
    _select(ob)
    assert bpy.ops.allset.smooth_preview(level=3) == {'FINISHED'}
    mods = [m for m in ob.modifiers if m.type == 'SUBSURF']
    assert len(mods) == 1 and mods[0].name == display.PREVIEW_MOD_NAME
    m = mods[0]
    assert m.show_viewport and not m.show_render and m.levels == 2 and not ob.show_wire
    bpy.ops.allset.smooth_preview(level=2)
    assert m.show_viewport and ob.show_wire
    bpy.ops.allset.smooth_preview(level=1)
    assert not m.show_viewport and not ob.show_wire
    bpy.ops.allset.smooth_preview(level=3)
    assert len(ob.modifiers) == 2, "re-uses the preview (+ its shading) modifier"


def test_smooth_preview_leaves_user_subsurf_and_user_wire():
    # 1/2/3 don't re-use the first Subsurf: they only touch the kit's
    # preview modifier (a user Subsurf is history in Maya terms).
    ob = _mesh("sp_b")
    user = ob.modifiers.new("Mine", 'SUBSURF')
    user.levels = 3
    ob.show_wire = True
    _select(ob)
    bpy.ops.allset.smooth_preview(level=1)
    assert user.show_viewport and len(ob.modifiers) == 1
    bpy.ops.allset.smooth_preview(level=3)
    assert user.show_viewport and user.levels == 3
    assert ob.modifiers[-1].name == display.PREVIEW_MOD_NAME
    bpy.ops.allset.smooth_preview(level=1)
    assert user.show_viewport, "1 does not hide the user's own Subsurf"
    assert ob.show_wire, "a wire display the user set is not cleared"


def test_component_modes():
    ob = _mesh("cm")
    _select(ob)
    ts = bpy.context.scene.tool_settings
    for comp, want in (("EDGE", (False, True, False)), ("VERT", (True, False, False)),
                       ("FACE", (False, False, True)), ("MULTI", (True, True, True))):
        assert bpy.ops.allset.component_mode(type=comp) == {'FINISHED'}
        assert bpy.context.mode == 'EDIT_MESH'
        assert tuple(ts.mesh_select_mode) == want, (comp, tuple(ts.mesh_select_mode))
    bpy.ops.object.mode_set(mode='OBJECT')


# --- keys ----------------------------------------------------------------------------

def test_camera_keys():
    assert _kmis("3D View", "allset.tumble", "LEFTMOUSE", alt=True)
    assert not _kmis("3D View", "view3d.rotate", "LEFTMOUSE", alt=True)
    assert _kmis("3D View", "allset.frame_all_views", "F", shift=True)[0].properties.selected
    assert not _kmis("3D View", "allset.frame_all_views", "A", shift=True)[0].properties.selected
    # plain F = the kit's Maya-fit framing instead of IC view_selected.
    assert _kmis("3D View", "allset.frame", "F") and not _kmis("3D View", "view3d.view_selected", "F")


def test_view_history_keys():
    for type, alt, direction in (("LEFT_BRACKET", False, "UNDO"), ("RIGHT_BRACKET", False, "REDO"),
                                 ("Z", True, "UNDO"), ("Y", True, "REDO")):
        items = _kmis("3D View", "allset.view_history", type, alt=alt)
        assert [k.properties.direction for k in items] == [direction], type
    assert not _kmis("Object Mode", "object.select_hierarchy", "LEFT_BRACKET")


def test_space_ctrl_space_keys():
    # the Space tap (four views) now lives in the hotbox operator.
    assert len(_kmis("3D View", "allset.hotbox", "SPACE")) == 1
    assert _kmis("Screen", "screen.screen_full_area", "SPACE", ctrl=True)[0].properties.use_hide_panels


def test_smooth_and_component_keys():
    for key, level in maya_patches.SMOOTH_KEYS:
        for km in ("Object Mode", "Mesh"):
            items = _kmis(km, "allset.smooth_preview", key)
            assert [k.properties.level for k in items] == [level], (km, key)
    assert not _kmis("Mesh", "mesh.select_mode", "ONE")
    for key, comp in maya_patches.COMPONENT_KEYS:
        items = _kmis("Object Non-modal", "allset.component_mode", key)
        assert [k.properties.type for k in items] == [comp], key
