"""#82: Maya option boxes open without a drag.
GUI: tests/gui/gui_step146_option_box.py (hold Display > Grid, Key > Set Key, Constrain > Parent, let go)."""

import types
from importlib import import_module

import bpy

import kit

menu_sets = import_module(kit.MODULE + ".ui.menu_sets")
keystate = import_module(kit.MODULE + ".operators.keystate")

BOXED = "Display/Grid"


class _Layout:
    def __init__(self):
        self.ops = []
        self.scale_y = 1.0

    def operator(self, idname, text="", **kw):
        props = types.SimpleNamespace(item="", from_hold=False)
        self.ops.append((idname, text, props))
        return props


def _spy_option_box(calls):
    orig = menu_sets.ALLSET_OT_menu_option_box.execute

    def execute(self, context):
        calls.append((self.item, self.from_hold))
        return {'FINISHED'}
    menu_sets.ALLSET_OT_menu_option_box.execute = execute
    return orig


def test_boxed_items_say_how_to_open_the_box():
    assert BOXED in menu_sets.OPTION_BOXES
    tip = menu_sets.ALLSET_OT_menu_item.description(bpy.context, types.SimpleNamespace(item=BOXED))
    assert tip.endswith("\n" + menu_sets.BOX_TIP), tip
    assert "hold" in menu_sets.BOX_TIP and "Shift" in menu_sets.BOX_TIP
    plain = next(p for p in menu_sets.menu_map.MAP if p not in menu_sets.OPTION_BOXES)
    tip = menu_sets.ALLSET_OT_menu_item.description(bpy.context, types.SimpleNamespace(item=plain))
    assert menu_sets.BOX_TIP not in tip, (plain, tip)


def test_hold_menu_row_is_tall_and_marked_from_hold():
    layout = _Layout()
    menu = types.SimpleNamespace(layout=layout)
    ctx = types.SimpleNamespace(button_operator=types.SimpleNamespace(item=BOXED), window=None)
    menu_sets.ALLSET_MT_option_box.draw(menu, ctx)
    (idname, text, props), = layout.ops
    assert idname == menu_sets.ALLSET_OT_menu_option_box.bl_idname
    assert text == "Option Box" + menu_sets.BOX_MARK
    assert props.item == BOXED and props.from_hold is True
    assert layout.scale_y == menu_sets.HOLD_ROW_SCALE > 1.0


def test_shift_or_ctrl_click_runs_the_option_box():
    calls = []
    orig_box = _spy_option_box(calls)
    orig_down = keystate.is_down
    try:
        for key in ("LEFT_SHIFT", "RIGHT_CTRL"):
            keystate.is_down = lambda t, key=key: t == key
            del calls[:]
            assert bpy.ops.allset.menu_item(item=BOXED) == {'FINISHED'}
            assert calls == [(BOXED, False)], (key, calls)
        keystate.is_down = lambda t: None      # unknown (not Windows): a plain click = the command
        assert not menu_sets.modifier_held()
        keystate.is_down = lambda t: False
        del calls[:]
        bpy.ops.allset.menu_item(item=BOXED)
        assert calls == [], calls
    finally:
        keystate.is_down = orig_down
        menu_sets.ALLSET_OT_menu_option_box.execute = orig_box


def test_modifier_vk_codes():
    for k in ("LEFT_SHIFT", "RIGHT_SHIFT", "LEFT_CTRL", "RIGHT_CTRL"):
        assert keystate.vk_code(k) is not None, k


def test_from_hold_in_background_runs_directly():
    # no window to move the pointer in: the option box runs at once (headless callers keep working)
    bpy.ops.allset.menu_option_box(item="Create/Polygon Primitives/Cube", from_hold=True)
    assert any(ob.name.startswith("pCube") for ob in bpy.data.objects)


def test_point_operator_registered():
    rna = bpy.ops.allset.option_box_point.get_rna_type()
    assert {i.identifier for i in rna.properties["move"].enum_items} == {'HOLD_ROW', 'AWAY', 'BACK'}
