"""Maya hotkeys right-aligned in the kit's Maya menus (from the item's Maya command and the kit keymap),
never a Blender shortcut."""

from importlib import import_module
from pathlib import Path
from types import SimpleNamespace

import bpy

import kit

ms = import_module(kit.MODULE + ".ui.menu_sets")
hotkeys = import_module(kit.MODULE + ".ui.menu_hotkeys")
ROOT = Path(kit.__file__).resolve().parent.parent

KIT_OPS = {"allset.menu_item", "allset.menu_unavailable", "allset.menu_run", "allset.menu_tool",
           "allset.menu_set_value", "wm.call_menu_pie",
           "allset.menu_tear_off"}   # Maya's tear-off line: no keymap item runs it


class Recorder:
    """Stands in for a menu's UILayout: records (kind, text, target)."""

    def __init__(self, log=None):
        self.log = [] if log is None else log

    def _sub(self, *_a, **_k):
        return Recorder(self.log)

    row = column = split = box = _sub

    def separator(self, *a, **k):
        self.log.append(("sep", "", None))

    def label(self, text="", **k):
        self.log.append(("label", text, None))

    def menu(self, idname, text="", **k):
        self.log.append(("menu", text, idname))

    def prop(self, owner, attr, text="", **k):
        self.log.append(("prop", text, attr))

    def prop_enum(self, owner, attr, value, text="", **k):
        self.log.append(("prop", text, attr))

    def operator(self, idname, text="", **k):
        self.log.append(("op", text, idname))
        return SimpleNamespace()

    operator_menu_hold = operator

    def __setattr__(self, name, value):
        if name == "log":
            object.__setattr__(self, name, value)


def draw_menu(maya_name):
    cls = getattr(bpy.types, ms.menu_idname(maya_name))
    rec = Recorder()
    cls.draw(SimpleNamespace(layout=rec), bpy.context)
    return rec.log


def texts(log):
    return {t.split("  ")[0].replace(ms.HAIR, ""): t for kind, t, _x in log if kind == "op"}


def test_drawn_items_carry_the_maya_key():
    file_items = texts(draw_menu("mainFileMenu"))
    for label, key in (("New Scene", "Ctrl+N"), ("Open Scene...", "Ctrl+O"), ("Save Scene", "Ctrl+S"),
                       ("Save Scene As...", "Ctrl+Shift+S"), ("Increment and Save", "Ctrl+Alt+S"),
                       ("Create Reference...", "Ctrl+R"), ("Exit", "Ctrl+Q")):
        text = file_items.get(label)
        assert text is not None, (label, sorted(file_items))
        assert text.startswith(label) and key in text, (label, text)
        assert text.index(key) > len(label), text            # the key comes after the label, separated
    assert file_items["Import..."].rstrip().endswith("❒") and "Ctrl" not in file_items["Import..."]
    mesh_items = texts(draw_menu("mainEditMeshMenu"))
    for label, key in (("Bevel", "Ctrl+B"), ("Extrude", "Ctrl+E"), ("Delete Edge/Vertex", "Ctrl+Del"),
                       ("Spin Edge Forward", "Ctrl+Alt+Right")):
        assert key in mesh_items[label], (label, mesh_items[label])


def test_tails_are_right_aligned():
    size = 13.75
    for maya_name in ("mainFileMenu", "mainEditMeshMenu", "mainEditMenu"):
        rows = []
        for path, it in ms.children(*_menu_items(maya_name)):
            if path is not None and not (ms.sub_items(path, it) and path not in ms.menu_map.MAP):
                rows.append((path, it[0], path in ms.OPTION_BOXES))
        out = ms.item_texts(rows, size)
        tailed = [out[p] for p, label, boxed in rows if ms.hotkey(p) or boxed]
        widths = [ms.text_width(t, size) for t in tailed]
        assert widths and max(widths) - min(widths) <= 3.0, (maya_name, min(widths), max(widths))
        # keys end on one line whether or not the item has an option box
        key_ends = [ms.text_width(out[p].rsplit(ms.hotkey(p), 1)[0] + ms.hotkey(p), size)
                    for p, _l, _b in rows if ms.hotkey(p)]
        if key_ends:
            assert max(key_ends) - min(key_ends) <= 3.0, (maya_name, key_ends)


def _menu_items(maya_name):
    label, _set, _src, items = ms.menu_data.MENUS[maya_name]
    return items, label


def test_no_blender_shortcut_source_in_menus():
    for maya_name in ("mainFileMenu", "mainEditMenu", "mainEditMeshMenu", "mainSelectMenu", "mainKeysMenu"):
        for kind, text, target in draw_menu(maya_name):
            if kind == "op":
                assert target in KIT_OPS, (maya_name, text, target)
            if kind == "menu":
                blender_menus = {v[0] for v in ms.menu_map.BLENDER_MENU.values()}   # the kit's "Blender" submenus
                assert target.startswith("ALLSET_MT_") or target == "TOPBAR_MT_file_open_recent" \
                    or target in blender_menus, (maya_name, text, target)
    km = kit.maya_kc().keymaps["Window"]
    assert not [k for k in km.keymap_items if k.idname == "wm.call_menu" and k.type == 'O' and k.ctrl and k.shift]


def test_proxy_menus_follow_the_kit():
    targets = ms._menu_targets()
    assert "TOPBAR_MT_file_open_recent" in targets
    for cls in ms._PROXY_CLASSES:
        base = cls.__mro__[1]
        assert cls.is_registered and ms._proxies[getattr(base, "bl_idname", base.__name__)] == cls.bl_idname, cls
    kit.disable()
    try:
        assert not ms._proxies and not [c for c in dir(bpy.types) if c.startswith("ALLSET_MT_proxy_")]
    finally:
        kit.enable()
