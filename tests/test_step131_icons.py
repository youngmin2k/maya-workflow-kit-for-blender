"""#23: kit-drawn Maya-recognisable icons — every shelf button and every Status Line / panel toolbar
button has its own picture, drawn at 1x and 2x.
"""

from importlib import import_module

import numpy as np

import kit

shelf_data = import_module(kit.MODULE + ".ui.shelf_data")
shelf_icons = import_module(kit.MODULE + ".ui.shelf_icons")
status_icons = import_module(kit.MODULE + ".ui.status_icons")
panel_toolbar = import_module(kit.MODULE + ".ui.panel_toolbar")

# Two icons are "different" when enough pixels differ clearly: a two-letter badge on the same picture is not
# enough (about 15 px of a 32 px icon), a different picture is (hundreds of pixels).
MIN_DIFF = 0.04          # share of pixels
PIXEL_DIFF = 0.25        # max channel difference of premultiplied RGBA

# Status Line chrome that is not a button picture (group bar, collapse handles).
CHROME = {"bar", "open", "closed"}


def _premul(px):
    px = np.asarray(px, np.float32)
    return np.concatenate([px[..., :3] * px[..., 3:4], px[..., 3:4]], axis=-1)


def different(a, b):
    d = np.abs(_premul(a) - _premul(b)).max(axis=-1)
    return float((d > PIXEL_DIFF).mean()) >= MIN_DIFF


def _same_pairs(images):
    names = list(images)
    out = []
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            if not different(images[a], images[b]):
                out.append((a, b))
    return out


def _panel_glyphs():
    """The panel toolbar's glyphs are in ``status_icons.EXTRA`` while Maya mode is on (kit.enable opts in)."""
    missing = [n for n in panel_toolbar.GLYPHS if "pt_" + n not in status_icons.EXTRA]
    assert not missing, missing


def _status_images(names, size=32):
    return {n: status_icons.image(n, size) for n in names}


def test_shelf_buttons_unique():
    bad = []
    for shelf, _label, buttons in shelf_data.SHELVES:
        images = {}
        for i, (label, _command) in enumerate(buttons):     # FX has two "From Current", FX Caching two "Delete Cache"
            images[f"{i + 1}. {label}"] = shelf_icons.draw(label, shelf, index=i)
        bad += [(shelf, a, b) for a, b in _same_pairs(images)]
    assert not bad, f"{len(bad)} shelf buttons share a picture: {bad[:20]}"


def test_shelf_icons_sizes():
    for shelf, _label, buttons in shelf_data.SHELVES:
        for label, _command in buttons:
            for size in (32, 64):
                px = shelf_icons.draw(label, shelf, size=size)
                assert px.shape == (size, size, 4), (shelf, label, size, px.shape)
                assert px[..., 3].max() > 0.5, (shelf, label, size)
    # the 2x picture is the same drawing: scaled down it matches the 1x one
    a = shelf_icons.draw("Polygon Cube", "Polygons", size=32)
    b = shelf_icons.draw("Polygon Cube", "Polygons", size=64).reshape(32, 2, 32, 2, 4).mean(axis=(1, 3))
    assert not different(a, b)


def test_status_line_unique():
    names = [n for n in status_icons.GLYPHS if n not in CHROME]
    bad = _same_pairs(_status_images(names))
    assert not bad, f"Status Line glyphs share a picture: {bad}"


def test_panel_toolbar_unique():
    _panel_glyphs()
    names = ["pt_" + n for n in panel_toolbar.GLYPHS]
    bad = _same_pairs(_status_images(names))
    assert not bad, f"panel toolbar glyphs share a picture: {bad}"


def test_status_icon_sizes():
    _panel_glyphs()
    for name in list(status_icons.GLYPHS) + ["pt_" + n for n in panel_toolbar.GLYPHS]:
        for size in (16, 20, 24, 32, 48):
            px = status_icons.image(name, size)
            assert px.shape == (size, size, 4), (name, size, px.shape)
            if name not in CHROME:
                assert px[..., 3].max() > 0.5, (name, size)


def test_graph_toolbar_pictures_unique():
    """#277: every Graph Editor / Dope Sheet toolbar button has its own kit picture, unlike the rest of its row."""
    chrome = import_module(kit.MODULE + ".ui.editor_chrome")
    graph_icons = import_module(kit.MODULE + ".ui.graph_icons")
    for editor in ("Graph Editor", "Dope Sheet"):
        keys = [it[0] for it in chrome.ICONS[editor] if isinstance(it, tuple)]
        missing = [k for k in keys if k not in graph_icons.GLYPHS or graph_icons.name(k) not in status_icons.EXTRA]
        assert not missing, (editor, missing)
        bad = _same_pairs({k: status_icons.image(graph_icons.name(k), 32) for k in keys})
        assert not bad, f"{editor} toolbar buttons share a picture: {bad}"
        for k in keys:
            for size in (16, 20, 32):
                px = status_icons.image(graph_icons.name(k), size)
                assert px.shape == (size, size, 4) and px[..., 3].max() > 0.5, (editor, k, size)
    unused = set(graph_icons.GLYPHS) - {it[0] for ed in ("Graph Editor", "Dope Sheet") for it in chrome.ICONS[ed]
                                         if isinstance(it, tuple)}
    assert not unused, unused
