"""A shelf double-click = the button's option box (the first click ran the command once), and Maya's shelf
overflow (rows that wrap, one shown, a scroll bar / the wheel move one row), like Maya.
"""

from importlib import import_module
from types import SimpleNamespace

import bpy

import kit

shelf = import_module(kit.MODULE + ".ui.shelf")
menu_sets = import_module(kit.MODULE + ".ui.menu_sets")
modal = import_module(kit.MODULE + ".marking.modal")


def _fresh():
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    shelf._last_click.clear()


def _index(shelf_id, label):
    return next(i for i, lab, _a, _ic in shelf.all_buttons(shelf_id) if lab == label)


class _Ops:
    """Stands in for ``bpy`` inside ui/shelf.py: records the option-box / undo calls, passes the rest through."""

    def __init__(self, log):
        self.log = log
        outer = self

        class Allset:
            def __getattr__(self, name):
                if name == "menu_option_box":
                    return lambda *a, **k: outer.log.append(("option_box", k.get("item"))) or {'FINISHED'}
                return getattr(bpy.ops.allset, name)

        class Ed:
            def undo(self):
                outer.log.append(("undo",))
                return {'FINISHED'}

        self.ops = SimpleNamespace(allset=Allset(), ed=Ed())

    def __getattr__(self, name):
        return getattr(bpy, name)


def _click(shelf_id, index, value='PRESS', ctrl=False):
    """ALLSET_OT_shelf_button.invoke as a gizmo click would call it (background ops run execute, not invoke)."""
    op = SimpleNamespace(shelf=shelf_id, index=index, option=False, double=False)
    op.report = lambda *a: None
    op.execute = lambda ctx: shelf.ALLSET_OT_shelf_button.execute(op, ctx)
    op._run_menu = lambda ctx, b: shelf.ALLSET_OT_shelf_button._run_menu(op, ctx, b)
    ev = SimpleNamespace(value=value, ctrl=ctrl, type='LEFTMOUSE')
    return shelf.ALLSET_OT_shelf_button.invoke(op, bpy.context, ev)


def test_double_click_runs_once_then_opens_the_option_window():
    _fresh()
    i = _index("Polygons", "Polygon Cube")
    path = shelf.menu_path_of("Polygons", "Cube", shelf.all_buttons("Polygons")[i][2])
    assert path == "Create/Polygon Primitives/Cube", path
    assert menu_sets.option_kind(path) == "window", "Polygon Cube Options (option_windows poly_cube)"
    log = []
    saved = shelf.bpy
    shelf.bpy = _Ops(log)
    try:
        assert _click("Polygons", i) == {'FINISHED'}
        assert _click("Polygons", i) == {'FINISHED'}         # second press within the double-click time
    finally:
        shelf.bpy = saved
    cubes = [o for o in bpy.data.objects if o.type == 'MESH']
    assert len(cubes) == 1, [o.name for o in cubes]
    assert log == [("option_box", path)], log      # no redo_last, no undo (an option window doesn't run again)


def test_double_click_event_and_ctrl_click():
    _fresh()
    i = _index("Polygons", "Polygon Cube")
    log = []
    saved = shelf.bpy
    shelf.bpy = _Ops(log)
    try:
        assert _click("Polygons", i, value='DOUBLE_CLICK') == {'FINISHED'}
        assert _click("Polygons", i, ctrl=True) == {'FINISHED'}      # no first run, the box only
    finally:
        shelf.bpy = saved
    assert not [o for o in bpy.data.objects if o.type == 'MESH']
    assert log == [("option_box", "Create/Polygon Primitives/Cube")] * 2, log


def test_double_click_redo_kind_takes_the_first_run_back():
    _fresh()
    redo = next((p for p in menu_sets.menu_map.MAP if p.split("/")[0] == "Mesh"
                 and menu_sets.option_kind(p) == "redo"), None)
    assert redo is not None
    log = []
    saved = shelf.bpy
    shelf.bpy = _Ops(log)
    try:
        shelf.take_back_run(redo)
        shelf.take_back_run("Create/Polygon Primitives/Cube")
    finally:
        shelf.bpy = saved
    assert log == [("undo",)], log


def test_two_far_apart_clicks_run_twice():
    _fresh()
    i = _index("Polygons", "Polygon Cube")
    _click("Polygons", i)
    shelf._last_click["time"] -= 1.0          # long after
    _click("Polygons", i)
    assert len([o for o in bpy.data.objects if o.type == 'MESH']) == 2


def test_row_layout_wraps_like_maya():
    lay = shelf.row_layout(1600, 43, 1.0)
    assert {r for r, _x in lay} == {0}, "43 buttons fit one 1600 px row at UI 1.0"
    lay = shelf.row_layout(1600, 43, 1.25, gaps=(7, 9, 13, 15, 18, 25, 28, 33))
    rows = [r for r, _x in lay]
    assert rows[0] == 0 and rows[-1] == 1, rows                 # 1600 px at UI 1.25: the last buttons wrap
    first_of_row1 = rows.index(1)
    assert lay[first_of_row1][1] == lay[0][1], "a new row starts at the left"
    limit = 1600 - (shelf.SCROLL_PX + shelf.SCROLL_RIGHT_PX + 2) * 1.25
    assert all(x + shelf.ICON_PX * 1.25 <= limit for _r, x in lay), "nothing under the scroll bar"
    lay = shelf.row_layout(1000, 43, 1.0, gaps=(7, 9))
    assert max(r for r, _x in lay) == 1, "at 1000 px: two rows"


def test_scroll_clamps_and_keymap():
    kc = kit.maya_kc()
    km = kc.keymaps["Image"]
    items = [k for k in km.keymap_items if k.idname == "allset.shelf_scroll"]
    assert {(k.type, k.properties.delta) for k in items} == {('WHEELUPMOUSE', -1), ('WHEELDOWNMOUSE', 1)}, items
    region = SimpleNamespace(width=1600, height=80, tag_redraw=lambda: None, as_pointer=lambda: 1)
    shelf._row.clear()
    ctx = SimpleNamespace(region=region, preferences=bpy.context.preferences, window_manager=bpy.context.window_manager,
                          scene=bpy.context.scene)
    orig = shelf.current
    shelf.current = lambda context=None: "Polygons"
    orig_layout = shelf._layout
    shelf._layout = lambda r, s: ("Polygons", True, shelf.row_layout(r.width, 43, 1.25, (7, 9, 13, 15, 18, 25)))
    try:
        assert shelf.rows_of(region, 1.25) == (2, 0)
        assert shelf.scroll_shelf(ctx, 1) and shelf.rows_of(region, 1.25) == (2, 1)
        assert not shelf.scroll_shelf(ctx, 5), "clamped at the last row"
        x, _y, _s = shelf.icon_rect(region, 0, 1.25)
        assert x > region.width, "row 0 is hidden while row 1 shows"
        x, _y, _s = shelf.icon_rect(region, 42, 1.25)
        assert x < region.width, "the last button is reachable"
        assert len(shelf.scroll_rects(region, 1.25)) == 2
        shelf.scroll_shelf(ctx, -3)
        assert shelf.rows_of(region, 1.25) == (2, 0)
    finally:
        shelf.current = orig
        shelf._layout = orig_layout
        shelf._row.clear()
