"""Wrong daily keys fixed (Alt+R, Ctrl+I, F1, Alt+C, m, Ctrl+PgUp/PgDn, Ctrl+,), missing keys bound (menu
bars, Alt+B, skin paint, sculpt, Graph Editor h / j, Time Slider bookmarks), every Maya hotkey row classified."""

from importlib import import_module
from types import SimpleNamespace

import bpy

import kit

kb3 = import_module(kit.MODULE + ".operators.key_batch3")
bookmarks = import_module(kit.MODULE + ".operators.bookmarks")
mapping = import_module(kit.MODULE + ".keymap.mapping")
status_line = import_module(kit.MODULE + ".ui.status_line")
symmetry = import_module(kit.MODULE + ".operators.symmetry")


def _keymap():
    return kit.maya_kc().keymaps


def _items(km, t, **mods):
    return [k for k in _keymap()[km].keymap_items if k.active and k.type == t and k.value in ('PRESS', 'CLICK')
            and all(getattr(k, m) == mods.get(m, False) for m in ("shift", "ctrl", "alt", "oskey"))]


def _one(km, t, idname, props=None, **mods):
    found = [k for k in _items(km, t, **mods) if k.idname == idname
             and all(getattr(k.properties, p) == v for p, v in (props or {}).items())]
    assert len(found) == 1, (km, t, idname, props, mods, [k.idname for k in _items(km, t, **mods)])
    return found[0]


def _none(km, t, idname, **mods):
    assert not [k for k in _items(km, t, **mods) if k.idname == idname], (km, t, idname, mods)


# --- wrong keys --------------------------------------------------------------------------------------------------

def test_alt_r_is_reflection_not_clear_scale():
    _none("Object Mode", 'R', "object.scale_clear", alt=True)
    _none("Pose", 'R', "pose.scale_clear", alt=True)
    _one("3D View", 'R', "allset.symmetry", {"mode": 'TOGGLE'}, alt=True)
    scene = bpy.context.scene
    sym = symmetry.state(scene)
    before = sym.on
    assert bpy.ops.allset.symmetry(mode='TOGGLE') == {'FINISHED'}
    assert sym.on != before
    bpy.ops.allset.symmetry(mode='TOGGLE')
    assert sym.on == before


def test_ctrl_i_no_longer_inverts_in_3d_modes():
    for km in ("Object Mode", "Mesh", "Pose"):
        assert not [k for k in _items(km, 'I', ctrl=True) if k.idname.endswith("select_all")], km
    # Maya's Select > Invert stays on Ctrl+Shift+I
    _one("Object Mode", 'I', "object.select_all", {"action": 'INVERT'}, ctrl=True, shift=True)
    # editors keep theirs (Outliner, Graph Editor)
    _one("Outliner", 'I', "outliner.select_all", {"action": 'INVERT'}, ctrl=True)


def test_f1_is_help():
    _none("3D View", 'F1', "view3d.view_axis")
    _none("Image", 'F1', "image.view_zoom_ratio")
    _one("Window", 'F1', "wm.doc_view_manual_ui_context")


def test_alt_c_and_m_lose_blender_tools():
    _none("Mesh", 'C', "wm.tool_set_by_id", alt=True)
    _one("Weight Paint", 'C', "allset.color_feedback", alt=True)
    for km in ("Object Mode", "Mesh", "Pose", "Curve", "Armature"):
        assert not [k for k in _items(km, 'M') if k.idname == "wm.tool_set_by_id"
                    and k.properties.name == "builtin.measure"], km
    k = _one("Sculpt", 'M', "wm.radial_control")
    assert k.properties.data_path_primary.endswith("brush.strength")


def test_pick_walk_in_out_and_no_preferences_key():
    _none("Screen", 'PAGE_UP', "screen.workspace_cycle", ctrl=True)
    _none("Screen", 'PAGE_DOWN', "screen.workspace_cycle", ctrl=True)
    _one("Object Mode", 'PAGE_UP', "object.select_hierarchy", {"direction": 'CHILD'}, ctrl=True)
    _one("Object Mode", 'PAGE_DOWN', "object.select_hierarchy", {"direction": 'PARENT'}, ctrl=True)
    _one("Pose", 'PAGE_UP', "pose.select_hierarchy", {"direction": 'CHILD'}, ctrl=True)
    _none("Screen", 'COMMA', "screen.userpref_show", ctrl=True)
    # in / out walk the hierarchy
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    parent = bpy.data.objects.new("group1", None)
    child = bpy.data.objects.new("pCube1", None)
    for ob in (parent, child):
        bpy.context.scene.collection.objects.link(ob)
    child.parent = parent
    bpy.context.view_layer.update()
    parent.select_set(True)
    bpy.context.view_layer.objects.active = parent
    assert bpy.ops.object.select_hierarchy(direction='CHILD', extend=False) == {'FINISHED'}
    assert child.select_get() and not parent.select_get()


# --- missing keys ------------------------------------------------------------------------------------------------

def test_menu_bar_keys():
    _one("Screen", 'M', "allset.main_menubar_toggle", ctrl=True)
    _one("Screen", 'M', "wm.context_toggle", {"data_path": "area.show_menus"}, shift=True)
    _one("3D View", 'M', "wm.context_toggle", {"data_path": "space_data.show_region_header"}, ctrl=True, shift=True)
    # Ctrl+M folds the top bar menus (the area the kit menu bar draws in)
    fake = SimpleNamespace(show_menus=True, tag_redraw=lambda: None)
    window = bpy.context.window_manager.windows[0] if bpy.context.window_manager.windows else None
    if window is not None:
        status_line._top_bars[window.as_pointer()] = fake
        try:
            with bpy.context.temp_override(window=window):
                assert bpy.ops.allset.main_menubar_toggle() == {'FINISHED'}
            assert fake.show_menus is False
        finally:
            status_line._top_bars.pop(window.as_pointer(), None)


def test_background_cycle_follows_maya():
    _one("3D View", 'B', "allset.cycle_background", alt=True)
    sh = bpy.context.scene.display.shading     # a View3DShading like a 3D View's
    sh.background_type = 'THEME'
    # per view (tests/test_step120_background.py)
    assert kb3.cycle_background(sh) == "LIGHT" and sh.background_type == 'VIEWPORT'
    assert abs(sh.background_color[0] - kb3.srgb_to_linear(0.631)) < 1e-4
    assert kb3.cycle_background(sh) == "GRADIENT" and kb3.is_gradient(sh)
    assert kb3.cycle_background(sh) == "BLACK" and sh.background_color[0] == 0.0
    assert kb3.cycle_background(sh) == "GREY" and sh.background_type == 'VIEWPORT'
    assert abs(sh.background_color[0] - kb3.srgb_to_linear(0.36)) < 1e-4


def test_skin_paint_keys():
    _one("Weight Paint", 'U', "wm.call_menu", {"name": "ALLSET_MT_paint_operation"})
    assert not [k for k in _items("Weight Paint", 'U') if k.idname == "wm.radial_control"]
    k = _one("Weight Paint", 'N', "wm.radial_control")
    assert k.properties.data_path_primary.endswith("brush.weight")
    k = _one("Weight Paint", 'B', "wm.radial_control")
    assert k.properties.data_path_primary.endswith("brush.size")
    _one("Weight Paint", 'F', "allset.flood_weights", alt=True)     # Maya Flood (Alt+F)
    _one("Mesh", 'C', "allset.copy_vertex_weights", ctrl=True, alt=True)
    _one("Mesh", 'V', "allset.paste_vertex_weights", ctrl=True, alt=True)
    assert hasattr(bpy.types, "ALLSET_MT_paint_operation")


def test_sculpt_keys():
    names = dict(kb3_name for kb3_name in (("ZERO", "Mask"), ("ONE", "Draw"), ("TWO", "Smooth"), ("FOUR", "Grab")))
    for key, brush in names.items():
        k = _one("Sculpt", key, "brush.asset_activate", ctrl=True)
        assert k.properties.relative_asset_identifier.endswith("/Brush/" + brush), k.properties.relative_asset_identifier
    assert not [k for k in _items("Sculpt", 'ONE', ctrl=True) if k.idname == "object.subdivision_set"]
    for key in ("FIVE", "SIX", "SEVEN", "EIGHT", "NINE", "THREE"):
        _one("Sculpt", key, "brush.asset_activate", ctrl=True)
    assert _one("Sculpt", 'B', "wm.radial_control").properties.data_path_primary.endswith("brush.size")
    _one("Sculpt", 'U', "paint.mask_flood_fill", {"mode": 'VALUE'}, shift=True)
    _one("Sculpt", 'I', "paint.mask_flood_fill", {"mode": 'INVERT'}, ctrl=True, shift=True)
    # the brushes named exist in Blender's essentials library
    import os
    lib = os.path.join(bpy.utils.system_resource('DATAFILES'), "assets", "brushes",
                       "essentials_brushes-mesh_sculpt.blend")
    with bpy.data.libraries.load(lib) as (src, _dst):
        have = set(src.brushes)
    from importlib import import_module as im
    patches = im(kit.MODULE + ".keymap.maya_patches")
    for _key, brush in patches.SCULPT_BRUSHES:
        assert brush in have, brush


def test_graph_editor_lock_keys():
    _one("Graph Editor", 'H', "anim.channels_setting_enable", {"type": 'PROTECT'})
    _one("Graph Editor", 'J', "anim.channels_setting_disable", {"type": 'PROTECT'})


def test_bookmark_keys_and_ranges():
    _one("Screen", 'T', "allset.bookmark_create", alt=True)
    _one("Screen", 'T', "allset.bookmark_create", {"quick": True}, alt=True, shift=True)
    _one("Screen", 'QUOTE', "screen.marker_jump", {"next": True})
    _one("Screen", 'SEMI_COLON', "screen.marker_jump", {"next": False})
    _one("Screen", 'BACK_SLASH', "allset.bookmark_frame", {"which": 'CURRENT'}, shift=True)
    _one("Screen", 'QUOTE', "allset.bookmark_frame", {"which": 'NEXT'}, shift=True)
    _one("Screen", 'SEMI_COLON', "allset.bookmark_frame", {"which": 'PREVIOUS'}, shift=True)
    scene = bpy.context.scene
    scene.timeline_markers.clear()
    scene.pop(bookmarks.ENDS, None)
    scene.frame_start, scene.frame_end = 1, 120
    wm = bpy.context.window_manager
    # a bookmark from a selected Time Slider range keeps its end
    wm.allset_time_range, wm.allset_time_range_on = (10, 30), True
    assert bpy.ops.allset.bookmark_create(quick=True) == {'FINISHED'}
    wm.allset_time_range_on = False
    scene.frame_current = 50
    assert bpy.ops.allset.bookmark_create(quick=True) == {'FINISHED'}
    names = [m.name for m in bookmarks.markers(scene)]
    assert names == ["bookmark1", "bookmark2"], names
    m1, m2 = bookmarks.markers(scene)
    assert bookmarks.bookmark_range(scene, m1) == (10, 30)
    assert bookmarks.bookmark_range(scene, m2) == (50, 120)      # no range: up to the scene end
    scene.frame_current = 20
    assert bpy.ops.allset.bookmark_frame(which='CURRENT') == {'FINISHED'}
    assert scene.use_preview_range and (scene.frame_preview_start, scene.frame_preview_end) == (10, 30)
    assert bpy.ops.allset.bookmark_frame(which='NEXT') == {'FINISHED'}
    assert (scene.frame_preview_start, scene.frame_preview_end) == (50, 120) and scene.frame_current == 50
    assert bpy.ops.allset.bookmark_frame(which='PREVIOUS') == {'FINISHED'}
    assert scene.frame_current == 10
    scene.use_preview_range = False
    scene.timeline_markers.clear()


def test_other_keys():
    _one("Screen", 'F', "wm.search_menu", ctrl=True)
    _one("3D View", 'FIVE', "allset.panel_set", {"key": 'DEFAULT_MATERIAL'}, ctrl=True, shift=True)
    _one("UV Editor", 'SEVEN', "wm.context_toggle", {"data_path": "space_data.uv_editor.show_stretch"})
    _one("UV Editor", 'FIVE', "allset.uv_display", {"mode": 'SHADED'})     # Maya 5 = shaded (set, not toggle)
    assert "show_faces" in bpy.types.SpaceUVEditor.bl_rna.properties
    assert "show_stretch" in bpy.types.SpaceUVEditor.bl_rna.properties


# --- every row classified ------------------------------------------------------------------------------------------

