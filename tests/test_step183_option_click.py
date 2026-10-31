"""#82: option box click zone (ui/option_click.py). Headless: the row texts the zone is built on are the
texts the Maya menus draw, the zone model is off where it can't be trusted (no window / not opened from the menu
bar), the click-point operator exists, and an option-box item still runs its command when nothing says "box".
The geometry against real menus: tests/gui/gui_step183_option_click.py (UI scale 1.0 and 1.25)."""

from importlib import import_module

import bpy

import kit

oc = import_module(kit.MODULE + ".ui.option_click")
ms = import_module(kit.MODULE + ".ui.menu_sets")
md = import_module(kit.MODULE + ".ui.menu_data")


def test_rows_are_the_drawn_texts():
    out, texts = oc.rows("Edit Mesh")
    assert out[0][0] == import_module(kit.MODULE + ".ui.maya_dock").TEAR_LINE
    bevel = texts["Edit Mesh/Bevel"]
    assert bevel.startswith("Bevel") and bevel.endswith("❒"), bevel
    assert "Ctrl+B" in bevel, bevel            # Maya hotkey before the box
    sub, sub_texts = oc.rows("Create/Polygon Primitives")
    assert sub_texts["Create/Polygon Primitives/Cube"].endswith("❒")
    assert not any(is_sub for _t, is_sub in sub)
    top, _ = oc.rows("Create")
    assert any(is_sub for _t, is_sub in top)   # NURBS Primitives ... are submenu rows
    assert oc.rows("No Such Menu") is None


def test_boxed_rows_end_on_one_column():
    size = ms.font_size()
    _out, texts = oc.rows("Edit Mesh")
    ends = {round(ms.text_width(t, size)) for p, t in texts.items() if p in ms.OPTION_BOXES}
    assert max(ends) - min(ends) <= 3, ends    # item_texts aligns the tails: one ❒ column


def test_width_model_grows_with_text_and_unit():
    w20, w25 = oc.width("Edit Mesh", 20, 11.0), oc.width("Edit Mesh", 25, 13.75)
    assert 200 < w20 < w25 < 600, (w20, w25)


def test_no_zone_without_a_menu_bar_window():
    assert oc.box_zone(bpy.context, "Edit Mesh/Bevel") is None
    assert oc.on_box(bpy.context, "Edit Mesh/Bevel") is False
    assert hasattr(bpy.types, "ALLSET_OT_click_point")


def test_box_tip_names_the_click():
    assert "click the box" in ms.BOX_TIP and "hold" in ms.BOX_TIP


def test_label_click_still_runs_the_command():
    calls = []
    orig = ms.ALLSET_OT_menu_option_box.execute

    def spy(self, context):
        calls.append(self.item)
        return {'CANCELLED'}
    ms.ALLSET_OT_menu_option_box.execute = spy
    try:
        bpy.ops.allset.menu_item(item="Display/Grid", clicked=True)
    finally:
        ms.ALLSET_OT_menu_option_box.execute = orig
    assert calls == [], calls
