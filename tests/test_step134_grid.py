"""Lane GRID (#59): the Maya grid is drawn in a fixed #404040 whatever the theme
(the kit ships none), the Maya layout views hide the 3D cursor, and the component pivot edit (D /
Insert) shows it only while the cursor is the pivot."""

import inspect
import os
from importlib import import_module

import bpy

import kit

grid = import_module(kit.MODULE + ".ui.maya_grid")
hold = import_module(kit.MODULE + ".operators.hold")
app_template = import_module(kit.MODULE + ".app_template")


def _views():
    return [sp for sc in bpy.data.screens for a in sc.areas for sp in a.spaces if sp.type == 'VIEW_3D']


def test_line_colour_is_maya_grey():
    r, g, b, a = grid.line_colour()
    assert (round(r * 255), round(g * 255), round(b * 255), a) == (64, 64, 64, 1.0)   # Maya displayColor grid #404040


def test_line_colour_ignores_the_theme():
    theme = bpy.context.preferences.themes[0].view_3d
    old = tuple(theme.grid)
    before = grid.line_colour()
    try:
        theme.grid = (0.9, 0.1, 0.1, 1.0)[:len(old)]
        assert grid.line_colour() == before
    finally:
        theme.grid = old
    src = inspect.getsource(grid)
    assert "themes" not in src and "preferences" not in src, "the grid colour must not come from the theme"


def test_template_views_hide_the_cursor():
    path = os.path.join(app_template.SOURCE_DIR, "startup.blend")
    bpy.ops.wm.open_mainfile(filepath=path)
    try:
        views = _views()
        assert views
        shown = [sp for sp in views if sp.overlay.show_cursor]
        assert not shown, f"{len(shown)} of {len(views)} Maya layout views show Blender's 3D cursor"
    finally:
        bpy.ops.wm.read_homefile()


def test_component_pivot_shows_only_hidden_cursors():
    views = _views()
    assert len(views) >= 1
    hidden, kept = views[0], views[1:]
    for sp in views:
        sp.overlay.show_cursor = True
    hidden.overlay.show_cursor = False
    try:
        shown = hold.show_cursors()
        assert shown == {hidden.as_pointer()}, shown
        assert all(sp.overlay.show_cursor for sp in views)
        assert hold.show_cursors() == set()          # nothing left hidden: a second start adds nothing
        hold.hide_cursors(shown)
        assert not hidden.overlay.show_cursor
        assert all(sp.overlay.show_cursor for sp in kept)   # views that showed it before keep it
        hold.hide_cursors(set())                       # nothing to do
    finally:
        for sp in views:
            sp.overlay.show_cursor = True


def test_component_edit_restores_the_cursor():
    """start() / finish() of the D / Insert pivot edit: the cursor shows during the edit, hidden again after."""
    views = _views()
    for sp in views:
        sp.overlay.show_cursor = False
    bpy.ops.mesh.primitive_cube_add()
    bpy.ops.object.mode_set(mode='EDIT')
    comp = hold.ComponentPivotEdit()
    try:
        comp.start(bpy.context, toggled=True)
        assert comp.on and all(sp.overlay.show_cursor for sp in views)
        comp.finish(bpy.context)
        assert not comp.on and not any(sp.overlay.show_cursor for sp in views)
        assert comp.cursors == set()
    finally:
        if bpy.context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        ob = bpy.context.active_object
        if ob is not None:
            bpy.data.objects.remove(ob)
        for sp in views:
            sp.overlay.show_cursor = True
