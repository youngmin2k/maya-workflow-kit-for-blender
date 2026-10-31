"""The two kit bugs found in the marketing shots — the asset shelf header strip that kept a second camera
label in pose / paint modes (ui/view_furniture.strip_action decides hide / show) and the welcome dialog body cut at
125 % UI scale (welcome.wrap breaks the paragraphs by text width). The drawing itself is checked in
tests/gui/gui_step124_persp_label.py and gui_step124_welcome.py."""

from importlib import import_module

import kit

vf = import_module(kit.MODULE + ".ui.view_furniture")
welcome = import_module(kit.MODULE + ".welcome")


class _Region:
    def __init__(self, kind, height):
        self.type, self.height = kind, height


class _Area:
    def __init__(self, shelf, header, ptr=1):
        self.regions = [_Region('WINDOW', 600), _Region('ASSET_SHELF', shelf), _Region('ASSET_SHELF_HEADER', header)]
        self._ptr = ptr

    def as_pointer(self):
        return self._ptr


def test_strip_action():
    vf._HIDDEN.clear()
    try:
        # collapsed shelf, strip showing, no region overlap: hide it
        assert vf.strip_action(_Area(1, 29), overlap=False) == 'HIDE'
        # with overlap Blender draws the strip itself: leave it
        assert vf.strip_action(_Area(1, 29), overlap=True) is None
        # an open shelf keeps its header
        assert vf.strip_action(_Area(200, 29), overlap=False) is None
        # a view without an asset shelf (object mode)
        area = _Area(1, 29)
        area.regions = area.regions[:1]
        assert vf.strip_action(area, overlap=False) is None
        # hidden by the kit: shown again when the shelf opens or overlap comes back, never a strip the kit didn't hide
        assert vf.strip_action(_Area(200, 1, ptr=7), overlap=False) is None
        vf._HIDDEN.add(7)
        assert vf.strip_action(_Area(200, 1, ptr=7), overlap=False) == 'SHOW'
        assert vf.strip_action(_Area(1, 1, ptr=7), overlap=True) == 'SHOW'
        assert vf.strip_action(_Area(1, 1, ptr=7), overlap=False) is None
    finally:
        vf._HIDDEN.clear()


def test_welcome_wrap():
    width = lambda text, _size: 10.0 * len(text)       # noqa: E731 — 10 px per character
    lines = welcome.wrap("aa bbb cccc dd e", 70, 11, measure=width)
    assert lines == ["aa bbb", "cccc dd", "e"], lines
    assert all(width(ln, 11) <= 70 for ln in lines)
    assert welcome.wrap("averyveryverylongword x", 50, 11, measure=width) == ["averyveryverylongword", "x"]
    for para in welcome.PARAGRAPHS:
        got = welcome.wrap(para, 300, 11, measure=width)
        assert " ".join(got).split() == para.split()
    # room left of the icon is what the dialog really leaves (unscaled px)
    assert 0 < welcome.text_room() < welcome.text_room(with_icon=False) < welcome.DIALOG_WIDTH
