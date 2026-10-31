"""Lane MENU (#23): Maya menu items that Maya draws with an icon show the kit's own drawing of the same
command (ui/menu_icons.py, table ui/menu_icon_data.py from tools/gen_menu_icons.py).
GUI: tests/gui/gui_step131_menu_icons.py."""

import collections
from importlib import import_module
from types import SimpleNamespace

import bpy
import numpy as np

import kit

ms = import_module(kit.MODULE + ".ui.menu_sets")
mi = import_module(kit.MODULE + ".ui.menu_icons")
data = import_module(kit.MODULE + ".ui.menu_icon_data")
shelf_icons = import_module(kit.MODULE + ".ui.shelf_icons")
status_icons = import_module(kit.MODULE + ".ui.status_icons")
kit_icons = import_module(kit.MODULE + ".ui.kit_icons")
menu_drawings = import_module(kit.MODULE + ".ui.menu_drawings")

SIZES = (16, 20, 24)            # menu icon px at UI scale 1.0 / 1.25 / 1.5
# Menus where Maya itself shows one picture on two items 
MAYA_SHARED = {"nCache/Merge Caches", "nHair/Convert Selection"}


def _parent(path):
    return path.rsplit("/", 1)[0]


def test_paths_are_kit_menu_items():
    paths = {p for p, _it in ms.iter_items()}
    missing = sorted(set(data.ICONS) - paths)
    assert not missing, missing
    assert len(data.ICONS) >= 180, len(data.ICONS)
    for path in ("Create/Polygon Primitives/Cube", "Create/NURBS Primitives/Sphere", "Mesh/Combine",
                 "Edit Mesh/Bevel", "Mesh Tools/Multi-Cut", "Deform/Blend Shape", "Constrain/Parent", "Key/Set Key",
                 "Windows/General Editors/Attribute Editor", "Modify/Transformation Tools/Move Tool"):
        assert path in data.ICONS, path
    # Maya draws these without an icon: the kit neither
    for path in ("Create/Polygon Primitives/Interactive Creation", "File/New Scene", "Edit/Undo"):
        assert path not in data.ICONS, path


def test_every_picture_is_a_kit_drawing():
    for path, pic in data.ICONS.items():
        kind = pic[0]
        if kind == "shelf":
            _k, shelf, label, index = pic
            assert shelf_icons.icon_for(label, shelf, index) is not None, (path, pic)   # not the user-button letters
        elif kind == "status":
            assert pic[1] in status_icons.GLYPHS, (path, pic)
        elif kind == "kit":
            assert pic[1] in kit_icons.GLYPHS, (path, pic)
        elif kind == "menu":            # #54: menu-only drawings
            assert pic[1] in menu_drawings.DRAWINGS, (path, pic)
        else:
            raise AssertionError((path, pic))


def test_sizes():
    for pic in sorted(set(data.ICONS.values()), key=repr):
        for n in SIZES:
            px = mi.picture(pic, n)
            assert px.shape == (n, n, 4) and px.dtype == np.float32, (pic, n, px.shape)
            alpha = px[..., 3]
            assert alpha.max() > 0.9 and (alpha > 0.5).sum() >= n * n // 10, (pic, n, "nearly empty")
            assert 0.0 <= px.min() and px.max() <= 1.0, (pic, n)


def test_icons_are_distinct_within_a_menu():
    by_menu = collections.defaultdict(list)
    for path, pic in data.ICONS.items():
        by_menu[_parent(path)].append((path, pic))
    for menu, rows in by_menu.items():
        seen = {}
        for path, pic in rows:
            key = mi.picture(pic, 16).tobytes()
            # one menu drawing on several items = Maya shows one icon file there (the generator links them)
            # a repeated label ("#2", Maya's legacy row of the same command) shows the same icon, like Maya
            twin = path.split("#", 1)[0] == seen.get(key, ("",))[0].split("#", 1)[0]
            if key in seen and menu not in MAYA_SHARED and not twin and not (pic[0] == "menu" and seen[key][1] == pic):
                raise AssertionError(f"{menu}: {path} looks like {seen[key][0]}")
            seen.setdefault(key, (path, pic))


def _preview(path):
    """The preview made for ``path`` (preview icon ids are 0 in background, so look it up by key)."""
    mi.icon_value(path)
    return mi._pcoll[0].get(mi._key(data.ICONS[path], mi.icon_px())) if mi._pcoll else None


def test_icon_value_is_a_preview_of_the_menu_icon_size():
    n = mi.icon_px()
    assert n == 16, n          # background: UI scale reads 0 -> 1
    pv = _preview("Create/Polygon Primitives/Cube")
    assert pv is not None, "no preview"
    assert tuple(pv.icon_size) == (n, n) and tuple(pv.image_size) == (n, n)
    px = np.array(pv.icon_pixels_float[:]).reshape(n, n, 4)[::-1]
    want = mi.picture(data.ICONS["Create/Polygon Primitives/Cube"], n)
    err = np.abs(px[..., 3] - want[..., 3]).max()
    assert err < 0.01, f"preview alpha differs from the drawing by {err}"   # stored as bytes
    assert mi.icon_value("Create/Polygon Primitives/Interactive Creation") == 0
    assert mi.icon_value("No/Such/Item") == 0


class Recorder:
    def __init__(self):
        self.log = []

    def _sub(self, *a, **k):
        return self

    row = column = split = box = _sub

    def separator(self, *a, **k):
        pass

    def label(self, text="", **k):
        self.log.append(("label", text, k))

    def menu(self, idname, text="", **k):
        self.log.append(("menu", text, k))

    def prop(self, owner, attr, text="", **k):
        self.log.append(("prop", text, k))

    def operator(self, idname, text="", **k):
        self.log.append(("op", text, k))
        return SimpleNamespace()

    operator_menu_hold = operator

    def __setattr__(self, name, value):
        if name == "log":
            object.__setattr__(self, name, value)


def _draw(idname):
    rec = Recorder()
    getattr(bpy.types, idname).draw(SimpleNamespace(layout=rec), bpy.context)
    return rec.log


def test_menus_draw_the_icons_with_hotkeys_and_boxes_kept():
    # preview icon ids are 0 in background: stand in a fake id per picture to see what the menus hand Blender
    real = mi.icon_value
    mi.icon_value = lambda path, context=None: 7 if path in data.ICONS else 0
    try:
        _check_menus()
    finally:
        mi.icon_value = real


def _check_menus():
    log = _draw(ms.SUBMENU_IDS["Create/Polygon Primitives"])
    rows = {t.split("  ")[0].replace(ms.HAIR, "").strip(): k for kind, t, k in log if kind == "op"}
    for label in ("Sphere", "Cube", "Cylinder", "Cone", "Torus", "Plane", "Polygon Disc"):
        assert rows[label].get("icon_value"), (label, rows[label])
    assert not rows.get("Interactive Creation", {}).get("icon_value"), "the check item has no shelf picture"
    texts = [t for kind, t, _k in log if kind == "op"]
    assert any(t.rstrip().endswith("❒") for t in texts), "option boxes still drawn"
    # Edit Mesh: Bevel keeps its Maya hotkey and box, and gets its icon
    log = _draw(ms.menu_idname("mainEditMeshMenu"))
    bevel = next((t, k) for kind, t, k in log if kind == "op" and t.startswith("Bevel"))
    assert "Ctrl+B" in bevel[0] and bevel[0].rstrip().endswith("❒") and bevel[1].get("icon_value"), bevel
    # Windows > General Editors: a submenu entry and run-time items get the Status Line pictures
    log = _draw(ms.SUBMENU_IDS["Windows/General Editors"])
    ae = next(k for kind, t, k in log if t.startswith("Attribute Editor"))
    assert ae.get("icon_value"), ae


def test_unregister_frees_the_previews():
    assert _preview("Mesh/Combine") is not None
    kit.disable()
    try:
        assert not mi._pcoll and mi._ready[0] == 0
        assert not bpy.app.timers.is_registered(mi._tick)
    finally:
        kit.enable()
