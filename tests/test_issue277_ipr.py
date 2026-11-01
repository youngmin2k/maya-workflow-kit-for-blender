"""IPR in its own window (#277): the IPR view copies where the main view looks, shows only the rendered picture,
and without a window IPR falls back to the viewport's Rendered shading. GUI side: tests/gui/gui_issue277_ipr.py."""

from importlib import import_module

import bpy
from mathutils import Quaternion, Vector

import kit

ipr = import_module(kit.MODULE + ".ui.ipr_window")
sl = import_module(kit.MODULE + ".ui.status_line")
notices = import_module(kit.MODULE + ".ui.notices")
menu_map = import_module(kit.MODULE + ".ui.menu_map")


def _two_views():
    """The factory 3D View and a second area turned into a 3D View; (main space, other space, other area)."""
    screen = bpy.context.window_manager.windows[0].screen
    main = next(a for a in screen.areas if a.type == 'VIEW_3D')
    other = next(a for a in screen.areas if a != main and a.type != 'VIEW_3D')
    old = other.ui_type
    other.ui_type = 'VIEW_3D'
    return main.spaces.active, other.spaces.active, other, old


def test_ipr_view_follows_the_main_view():
    src, dst, area, old = _two_views()
    try:
        rv = src.region_3d
        rv.view_location = Vector((1.0, 2.0, 3.0))
        rv.view_rotation = Quaternion((0.9, 0.1, 0.3, 0.2)).normalized()
        rv.view_distance = 17.5
        rv.view_perspective = 'PERSP'
        src.lens = 70.0
        src.clip_end = 5000.0
        assert ipr.copy_view(src, dst), "a different view is copied"
        d = dst.region_3d
        assert (d.view_location - rv.view_location).length < 1e-6
        assert abs(d.view_rotation.rotation_difference(rv.view_rotation).angle) < 1e-5
        assert abs(d.view_distance - 17.5) < 1e-6 and d.view_perspective == 'PERSP'
        assert abs(dst.lens - 70.0) < 1e-6 and abs(dst.clip_end - 5000.0) < 1e-3
        assert not ipr.copy_view(src, dst), "nothing left to copy"
        rv.view_distance = 9.0
        assert ipr.copy_view(src, dst) and abs(d.view_distance - 9.0) < 1e-6
    finally:
        area.ui_type = old


def test_ipr_view_shows_only_the_rendered_picture():
    src, dst, area, old = _two_views()
    try:
        main_shading = src.shading.type
        ipr.setup_view(dst)
        assert dst.shading.type == 'RENDERED'
        assert not dst.overlay.show_overlays and not dst.show_gizmo
        assert not dst.show_region_toolbar and not dst.show_region_ui
        assert src.shading.type == main_shading, "the main view keeps its display"
    finally:
        area.ui_type = old


def test_without_a_window_ipr_is_the_viewport_rendered_shading():
    screen = bpy.context.window_manager.windows[0].screen
    area, _r = sl.main_view3d(screen)
    space = area.spaces.active
    space.shading.type = 'WIREFRAME'
    with bpy.context.temp_override(window=bpy.context.window_manager.windows[0]):
        bpy.ops.allset.ipr_toggle()
        assert space.shading.type == 'RENDERED' and not ipr.is_open()
        bpy.ops.allset.ipr_toggle()
    assert space.shading.type == 'WIREFRAME'
    space.shading.type = 'SOLID'


def test_menu_and_notice():
    assert menu_map.MAP["Render/IPR Render Current Frame"] == "allset.ipr_toggle"
    assert menu_map.MAP["Render/Redo Previous IPR Render"] == "allset.ipr_toggle"
    sub, text = notices.NOTICES["Render/IPR Render Current Frame"]
    assert "own window" in text and "closes" in text, text
    assert "own window" in sl.ALLSET_OT_ipr_toggle.__doc__
