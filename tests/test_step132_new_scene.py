"""#44: Maya's New Scene key (Ctrl+N) = allset.new_maya_scene, the same as File > New Scene and the
Status Line "new" button (not IC's wm.read_homefile, which opens Blender's default file)."""

from importlib import import_module

import kit

mapping = import_module(kit.MODULE + ".keymap.mapping")
menu_map = import_module(kit.MODULE + ".ui.menu_map")
menu_hotkeys = import_module(kit.MODULE + ".ui.menu_hotkeys")


def _ctrl_n(km_name):
    km = kit.maya_kc().keymaps[km_name]
    return [k for k in km.keymap_items if k.active and k.type == 'N' and k.value == 'PRESS'
            and k.ctrl and not (k.shift or k.alt or k.oskey)]


def test_ctrl_n_is_maya_new_scene():
    items = _ctrl_n("Window")
    assert [k.idname for k in items] == ["allset.new_maya_scene"], [k.idname for k in items]


def test_mapping_row_and_menu_agree():
    entry = mapping.ENTRIES["NewScene"]
    assert entry["status"] == "KIT" and entry["check"] == ("Window", "allset.new_maya_scene", {}), entry
    assert menu_map.MAP["File/New Scene"] == "allset.new_maya_scene"
    assert menu_hotkeys.HOTKEYS["File/New Scene"] == "Ctrl+N"
