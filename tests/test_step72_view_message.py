"""Maya in-view messages (ui/view_message.py) and the top bar repaint after F2-F6.
GUI: tests/gui/gui_step72_view_message.py, gui_step35 (F3 shot)."""

from importlib import import_module

import bpy

import kit

vm = import_module(kit.MODULE + ".ui.view_message")
status_line = import_module(kit.MODULE + ".ui.status_line")
visibility = import_module(kit.MODULE + ".operators.visibility")
preferences = import_module(kit.MODULE + ".preferences")


def test_parse_markup():
    assert vm.parse("plain") == [[("plain", False)]]
    assert vm.parse("Soft <hl>on</hl>.\nTap <hl>b</hl>") == [
        [("Soft ", False), ("on", True), (".", False)],
        [("Tap ", False), ("b", True)]]
    assert vm.parse("<hl>x</hl>") == [[("x", True)]]


def test_fade_curve():
    # 0.25 s rising, full by 1.5 s, still full at 2.3 s, nearly gone at 3.6 s
    assert vm.alpha(-0.1) == 0.0
    assert 0.7 < vm.alpha(0.25) < 0.9
    assert vm.alpha(1.5) == 1.0 and vm.alpha(2.25) == 1.0
    assert 0.1 < vm.alpha(3.6) < 0.25
    assert vm.alpha(vm.FADE_IN + vm.HOLD + vm.FADE_OUT) == 0.0
    assert vm.HOLD == 2.0   # inViewMessageDisplayTime


def test_box_positions():
    bounds = (0, 0, 1000, 600)
    x0, y0, x1, y1 = vm.box_rect(bounds, (200, 45), 'TOP_LEFT')
    assert (x0, y1) == (10.0, 589.0) and (x1 - x0, y1 - y0) == (200, 45)
    x0, _y0, x1, y1 = vm.box_rect(bounds, (300, 70), 'TOP_CENTER', scale=2.0)
    assert (x0 + x1) / 2 == 500 and y1 == 600 - 22.0


def test_visibility_messages():
    m = visibility.message
    assert "Shift+H" in m('HIDE', True, 1) and m('HIDE', False, 0).startswith("Nothing")
    assert "Shift+H" in m('HIDE_UNSELECTED', True, 2) and m('HIDE_UNSELECTED', True, 0).startswith("No ")
    assert m('TOGGLE', True, 1) is None and m('TOGGLE', False, 0) is not None
    assert m('SHOW_SELECTED', False, 0) is None


def test_pref_and_background():
    prefs = preferences.get(bpy.context)
    assert prefs.in_view_messages is True                      # on by default
    assert vm.show(bpy.context, "x") is False                  # nothing to draw in background
    assert vm.current() is None


def test_f8_operator():
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    bpy.ops.mesh.primitive_cube_add()
    assert bpy.ops.allset.toggle_sel_mode() == {'FINISHED'}
    assert bpy.context.mode == 'EDIT_MESH'
    assert bpy.ops.allset.toggle_sel_mode() == {'FINISHED'}
    assert bpy.context.mode == 'OBJECT'


def test_top_bar_redraw_is_safe():
    status_line._top_bars[123456] = None   # a closed window's entry is dropped, not tagged
    status_line.redraw_top_bars()
    assert 123456 not in status_line._top_bars
    bpy.ops.allset.menu_set(set='riggingMenuSet')
    assert preferences.get(bpy.context).menu_set == 'riggingMenuSet'
    bpy.ops.allset.menu_set(set='modelingMenuSet')
