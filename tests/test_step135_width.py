"""Lane WIDTH (#60): the Maya tab stack width follows the UI scale — wide enough for its tab row, the Channel
Box labels and the AE menu bar (blf widths), between the Channel Box stack (277 px) and the stack with the
Attribute Editor raised (480 px) times the scale. GUI side:
tests/gui/gui_step135_width.py."""

import sys
from importlib import import_module
from pathlib import Path

import kit

ROOT = Path(__file__).resolve().parent.parent
toolbox = import_module(kit.MODULE + ".ui.toolbox")
maya_dock = import_module(kit.MODULE + ".ui.maya_dock")
attribute_editor = import_module(kit.MODULE + ".ui.attribute_editor")

SCALES = (1.0, 1.25, 1.5)


def test_width_grows_with_the_ui_scale():
    widths = [toolbox.dock_width(s) for s in SCALES]
    print("dock widths", dict(zip(SCALES, widths)), {s: toolbox.dock_need(s) for s in SCALES})
    assert widths == sorted(widths) and widths[0] < widths[-1], widths
    for s, w in zip(SCALES, widths):
        assert round(toolbox.DOCK_MAYA_PX * s) <= w <= round(toolbox.DOCK_MAX_PX * s), (s, w)


def test_contents_fit_the_width():
    for s in SCALES:
        w = toolbox.dock_width(s)
        need = toolbox.dock_need(s)
        assert need["labels"] <= w, (s, w, need)          # the AE width rule is its own
        u = toolbox._unit(s)
        # the label column is half the panel: the longest standard channel label fits it with its margins
        longest = max(toolbox.text_px(t, s) for t in toolbox.LONG_LABELS)
        assert (w - 0.8 * u) / 2 >= longest + 0.8 * u, (s, w, longest)
        # #78: the content column ends left of Maya's vertical tab strip
        assert (w - maya_dock.reserved_px(s) - 0.8 * u) / 2 >= longest + 0.8 * u, (s, w, longest)


class _Ctx:
    """Just what attribute_editor.fits reads."""
    def __init__(self, width, scale):
        self.region = type("R", (), {"width": width})()
        self.preferences = type("P", (), {"system": type("S", (), {"ui_scale": scale})()})()


def test_ae_menu_bar_is_one_row_at_that_width():
    for s in SCALES:
        w = toolbox.dock_width(s, kind='ATTRIBUTE_EDITOR')     # the stack widens with the AE raised
        assert attribute_editor.fits(_Ctx(w - maya_dock.reserved_px(s), s), attribute_editor.MENU_BAR), (s, w)
        assert not attribute_editor.fits(_Ctx(round(toolbox.DOCK_MAYA_PX * s), s), attribute_editor.MENU_BAR), s


def test_rule_is_blf_based_with_a_fallback():
    assert abs(toolbox.text_px("Subdivisions Height", 1.0) - 107) <= 3        # blf width, 11 pt UI font
    fixed = toolbox.dock_width(1.25, measure=lambda text, s: len(text) * 7 * s)
    assert round(toolbox.DOCK_MAYA_PX * 1.25) <= fixed <= round(toolbox.DOCK_MAX_PX * 1.25)


def test_template_dock_is_the_rule_at_scale_1():
    sys.path.insert(0, str(ROOT / "tools"))
    import make_startup
    assert abs(make_startup.DOCK_PX - toolbox.dock_width(1.0)) <= 2, (make_startup.DOCK_PX, toolbox.dock_width(1.0))
