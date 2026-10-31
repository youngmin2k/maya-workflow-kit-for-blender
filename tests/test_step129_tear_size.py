"""A torn-off panel / menu window is sized to its content — the content height comes from
a stand-in layout (ui/layout_measure.py) and clamped (ui/maya_dock.content_height)."""

from importlib import import_module

import bpy

import kit

measure = import_module(kit.MODULE + ".ui.layout_measure")
dock = import_module(kit.MODULE + ".ui.maya_dock")
menu_sets = import_module(kit.MODULE + ".ui.menu_sets")


def test_rows_of_simple_layouts():
    def draw(self, _context):
        lay = self.layout
        lay.label(text="title")
        row = lay.row()
        row.operator("a.b")
        row.prop(None, "x")                 # a row = one line
        col = lay.column()
        col.operator("c.d").value = 3       # operator props accept attributes
        col.separator()
        sub = col.row()
        sub.scale_y = 2.0
        sub.label(text="big")
        box = lay.box()
        box.label(text="in box")
        lay.template_list("X", "", None, "", None, "", rows=3)
    n = measure.rows(draw, bpy.context)
    want = 1 + 1 + (1 + measure.SEPARATOR + 2) + (1 + measure.BOX_PAD) + 4
    assert abs(n - want) < 1e-6, (n, want)


def test_failing_draw_gives_none():
    def draw(self, _context):
        raise RuntimeError("needs a real layout")
    assert measure.rows(draw, bpy.context) is None


def test_menu_rows_follow_item_count():
    counts = {}
    for name in menu_sets.menus_for_set(menu_sets.current_set()):
        idname = menu_sets.menu_idname(name)
        n = dock.menu_rows(bpy.context, idname)
        assert n is not None, idname
        counts[idname] = n
    assert len(counts) >= 3, counts
    assert max(counts.values()) > min(counts.values()) + 5, counts   # a long menu measures longer than a short one


def test_content_height_clamped():
    s = bpy.context.preferences.system.ui_scale or 1.0
    short = dock.content_height(bpy.context, 2, 2000)
    assert abs(short - measure.px(dock.MIN_ROWS, bpy.context)) < 1e-6, short
    mid = dock.content_height(bpy.context, 20, 2000)
    assert abs(mid - (20 + dock.PAD_ROWS) * measure.ROW_PX * s) < 1e-6, mid
    assert dock.content_height(bpy.context, 500, 700) == 700
