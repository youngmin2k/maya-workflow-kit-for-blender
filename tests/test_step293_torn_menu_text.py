"""A torn-off menu draws its items' text from the left edge, like the menu (Blender centres an operator
button's text outside a menu). Each operator / press-and-hold / radio button goes into its own row aligned LEFT;
sub-menu rows, check boxes and labels stay on the column; the window height estimate is unchanged."""

from importlib import import_module
from types import SimpleNamespace

import bpy

import kit

maya_dock = import_module(kit.MODULE + ".ui.maya_dock")
menu_sets = import_module(kit.MODULE + ".ui.menu_sets")
layout_measure = import_module(kit.MODULE + ".ui.layout_measure")


class Rec:
    """A stand-in UILayout: logs (call, layout kind, layout alignment, text) of every item."""

    def __init__(self, log=None, kind="COL"):
        object.__setattr__(self, "log", [] if log is None else log)
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "alignment", 'EXPAND')

    def __setattr__(self, name, value):
        object.__setattr__(self, name, value)

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        if name in ("row", "column", "split", "box"):
            return lambda *a, **k: Rec(self.log, "ROW" if name in ("row", "split") else "COL")

        def add(*args, **kw):
            self.log.append((name, self.kind, self.alignment, kw.get("text", "")))
            return SimpleNamespace()
        return add


def _file_menu():
    return menu_sets.menu_idname(next(n for n in menu_sets.menus_for_set(menu_sets.current_set()) if "File" in n))


def test_centred_buttons_go_into_left_rows():
    rec = Rec()
    left = maya_dock._LeftItems(rec)
    left.operator("wm.save_mainfile", text="Save")
    left.operator_menu_hold("wm.save_mainfile", text="Save  ❒", menu="X")
    left.prop_enum(bpy.context.scene.render, "engine", "BLENDER_EEVEE", text="Eevee")
    left.menu("TOPBAR_MT_file", text="File")
    left.prop(bpy.context.scene.render, "use_simplify", text="Simplify")
    left.label(text="Section")
    left.separator()
    by_name = {name: (kind, align) for name, kind, align, _t in rec.log}
    for name in ("operator", "operator_menu_hold", "prop_enum"):
        assert by_name[name] == ("ROW", 'LEFT'), (name, by_name[name])
    for name in ("menu", "prop", "label", "separator"):
        assert by_name[name] == ("COL", 'EXPAND'), (name, by_name[name])
    left.scale_y = 0.8                 # settings reach the column itself
    assert rec.scale_y == 0.8


def test_torn_file_menu_items_start_on_the_left():
    idname = _file_menu()
    window = bpy.context.window
    assert window is not None
    maya_dock._torn_menus[window.as_pointer()] = (idname, "File")
    try:
        rec = Rec()
        maya_dock.draw_torn_menu(rec, bpy.context)
    finally:
        maya_dock._torn_menus.pop(window.as_pointer(), None)
    ops = [(kind, align, text) for name, kind, align, text in rec.log if name.startswith("operator")]
    assert len(ops) > 10, rec.log
    assert all(kind == "ROW" and align == 'LEFT' for kind, align, _t in ops), ops
    # the hotkey / option box column is still in the text (``menu_sets.item_texts``)
    assert any(text.startswith("New Scene") and "Ctrl+N" in text and text.endswith(menu_sets.BOX_MARK)
               for _k, _a, text in ops), ops
    # no tear-off line in the torn copy, and the sub-menu rows stay on the column
    assert not any(text == maya_dock.TEAR_LINE for _k, _a, text in ops)
    assert all(kind == "COL" for name, kind, _a, _t in rec.log if name == "menu")


def test_window_height_estimate_is_unchanged():
    cls = getattr(bpy.types, _file_menu())

    def torn(holder, context):
        maya_dock._drawing_torn[0] = True
        try:
            cls.draw(maya_dock._Holder(maya_dock._LeftItems(holder.layout)), context)
        finally:
            maya_dock._drawing_torn[0] = False

    wrapped = layout_measure.rows(torn, bpy.context)
    assert wrapped is not None, layout_measure.LAST_ERROR
    assert maya_dock.menu_rows(bpy.context, cls.bl_idname) == wrapped + 2
