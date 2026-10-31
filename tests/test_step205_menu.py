"""The Maya menu paths of the new deformers / pins run what their modules declare (ui/menu_map.py writes
them literally because tools/menu_count.py loads the menu maps without bpy; a hand copy once passed `kind="tension"`
where the operator's enum is 'TENSION' — the GUI run caught it)."""

from importlib import import_module

import kit

menu_map = import_module(kit.MODULE + ".ui.menu_map")
MODULES = ("deformers_205a", "deformers_205b")


def _norm(action):
    if isinstance(action, str):
        return (action, {})
    return (action[0], dict(action[1]) if len(action) > 1 else {})


def test_menu_entries_match_the_modules():
    for name in MODULES:
        mod = import_module(kit.MODULE + ".operators." + name)
        for path, action in mod.MENU.items():
            assert path in menu_map.MAP, (name, path)
            assert _norm(menu_map.MAP[path]) == _norm(action), (path, menu_map.MAP[path], action)


def test_menu_props_are_valid_for_their_operators():
    import bpy
    for name in MODULES:
        mod = import_module(kit.MODULE + ".operators." + name)
        for path in mod.MENU:
            op, props = _norm(menu_map.MAP[path])
            rna = getattr(getattr(bpy.ops, op.split(".")[0]), op.split(".")[1]).get_rna_type()
            for key, value in props.items():
                prop = rna.properties[key]
                if prop.type == 'ENUM':
                    assert value in {it.identifier for it in prop.enum_items}, (path, key, value)
