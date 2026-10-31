"""Maya's viewport background — Alt+B cycle (rule and colours of Maya 2022),
every view at once, per view: flat colours and the kit-drawn gradient (the kit never edits the
user's theme), Ctrl+B stays Maya's Bevel, Windows > Settings/Preferences > Color Settings."""

from importlib import import_module
from pathlib import Path

import bpy

import kit

kb3 = import_module(kit.MODULE + ".operators.key_batch3")
menu_map = import_module(kit.MODULE + ".ui.menu_map")
menu_sets = import_module(kit.MODULE + ".ui.menu_sets")
notices = import_module(kit.MODULE + ".ui.notices")

ROOT = Path(__file__).resolve().parents[1]


def _views():
    return [space for _area, space in kb3.view_spaces()]


def _display(sh):
    return kb3.linear_to_srgb(sh.background_color[0])


def _theme_state():
    t = bpy.context.preferences.themes[0]
    gr = t.view_3d.space.gradients
    return kit._struct_hash(t), gr.background_type, tuple(gr.high_gradient), tuple(gr.gradient)


def test_maya_rule():
    # Maya Alt+B background cycle: 0 -> 0.36; < 0.5 -> 0.631; else -> gradient; gradient -> black
    assert [kb3.next_state(s) for s in kb3.CYCLE] == ["LIGHT", "GRADIENT", "BLACK", "GREY"]
    assert kb3.next_state(0.2) == "LIGHT" and kb3.next_state(0.7) == "GRADIENT" and kb3.next_state(0.0) == "GREY"
    assert not hasattr(kb3, "theme_gradients") and not hasattr(kb3, "set_gradient")


def test_gradient_ramp_top_to_bottom():
    rows = kb3.ramp_rows()
    assert rows[0][0] == 1.0 and rows[-1][0] == -1.0 and len(rows) == 11
    top, bottom = rows[0][1], rows[-1][1]
    assert abs(kb3.linear_to_srgb(top[0]) * 255 - 136) < 0.01 and abs(kb3.linear_to_srgb(bottom[2]) * 255 - 13) < 0.01
    assert all(a[0] > b[0] for a, b in zip(rows, rows[1:]))      # rows go down the view
    assert all(r[1][3] == 1.0 for r in rows)


def test_gradient_is_a_view_setting():
    sh = _views()[0].shading
    kb3.set_shading(sh, "GRADIENT")
    assert sh.background_type == 'VIEWPORT' and kb3.is_gradient(sh) and kb3.background_state(sh) == "GRADIENT"
    assert abs(kb3.linear_to_srgb(sh.background_color[1]) - 110 / 255) < 1e-4    # the ramp's middle colour
    kb3.set_shading(sh, "LIGHT")
    assert not kb3.is_gradient(sh)
    sh.background_type = 'THEME'
    assert not kb3.is_gradient(sh)


def test_cycle_every_view_per_view_colour():
    views = _views()
    assert views, "factory startup has 3D views"
    before = _theme_state()
    sh = views[0].shading
    for v in views:
        v.shading.background_type = 'THEME'      # the user's theme background = the starting point, like Maya
    assert kb3.cycle_background(sh) == "LIGHT"
    assert all(v.shading.background_type == 'VIEWPORT' and abs(_display(v.shading) - 0.631) < 1e-4 for v in views)
    assert kb3.cycle_background(sh) == "GRADIENT"
    assert all(kb3.is_gradient(v.shading) for v in views)
    assert kb3.cycle_background(sh) == "BLACK"
    assert all(v.shading.background_type == 'VIEWPORT' and v.shading.background_color[0] == 0.0 for v in views)
    assert kb3.cycle_background(sh) == "GREY"
    assert all(v.shading.background_type == 'VIEWPORT' and abs(_display(v.shading) - 0.36) < 1e-4 for v in views)
    assert kb3.cycle_background(sh) == "LIGHT"
    assert _theme_state() == before, "Alt+B never writes the theme"


def test_reset_is_maya_flat_grey_and_keeps_theme():
    before = _theme_state()
    kb3.reset_background()
    assert all(v.shading.background_type == 'VIEWPORT' and abs(_display(v.shading) - 0.36) < 1e-4 for v in _views())
    assert _theme_state() == before


def test_color_settings_operator():
    before = _theme_state()
    assert bpy.ops.allset.color_settings(background=(0.2, 0.3, 0.4)) == {'FINISHED'}
    sh = _views()[0].shading
    assert sh.background_type == 'VIEWPORT'
    assert abs(kb3.linear_to_srgb(sh.background_color[2]) - 0.4) < 1e-4
    assert bpy.ops.allset.color_settings(background=(0.36, 0.36, 0.36)) == {'FINISHED'}
    assert sh.background_type == 'VIEWPORT' and abs(_display(sh) - 0.36) < 1e-4
    props = {p.identifier for p in bpy.ops.allset.color_settings.get_rna_type().properties}
    assert "gradient" not in props and "background" in props
    assert _theme_state() == before


def test_keys_alt_b_cycles_ctrl_b_bevels():
    kc = kit.maya_kc()
    km = kc.keymaps["3D View"]
    alt_b = [k for k in km.keymap_items if k.type == 'B' and k.alt and not k.ctrl and not k.shift and k.active]
    assert [k.idname for k in alt_b] == ["allset.cycle_background"]
    assert not [k for km in kc.keymaps for k in km.keymap_items if k.idname == "allset.cycle_background" and k.ctrl]
    mesh = [k.idname for k in kc.keymaps["Mesh"].keymap_items if k.type == 'B' and k.ctrl and not k.alt]
    assert mesh == ["allset.bevel"]      # Maya Ctrl+B = BevelPolygon (Maya hotkey)


def test_settings_preferences_menu():
    kids = [it[0] for it in menu_map.CHILDREN["Windows/Settings/Preferences"] if it[0] != "-"]
    assert kids == ["Preferences", "Hotkey Editor", "Color Settings", "Marking Menu Editor", "Shelf Editor",
                    "Panel Editor", "Plug-in Manager"]
    assert menu_map.MAP["Windows/Settings/Preferences/Color Settings"] == "allset.color_settings"
    assert "Windows/Settings/Preferences" not in menu_map.MAP       # a submenu now, not a leaf
    for label in ("Shelf Editor", "Panel Editor"):
        assert f"Windows/Settings/Preferences/{label}" in notices.NOTICES
    # a kit window now (marking/menu_editor.py)
    assert menu_map.MAP["Windows/Settings/Preferences/Marking Menu Editor"] == "allset.marking_menu_editor"
    assert "Windows/Settings/Preferences/Marking Menu Editor" not in notices.NOTICES
    paths = {p for p, _it in menu_sets.iter_items()} if hasattr(menu_sets, "iter_items") else set()
    if paths:
        assert "Windows/Settings/Preferences/Color Settings" in paths
