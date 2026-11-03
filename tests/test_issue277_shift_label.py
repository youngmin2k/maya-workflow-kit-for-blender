"""Shift+drag on the manipulator names what it does: an in-view label "Shift Duplicate" / "Shift Extrude"
(the names of the tool options that turn the behaviour off), translated with the interface.
GUI: tests/gui/gui_issue277_shift_label.py (label on drag, none on click, In-View Messages off)."""

from importlib import import_module

import bpy

import kit

manip = import_module(kit.MODULE + ".operators.manip")
i18n = import_module(kit.MODULE + ".i18n")


def test_labels():
    assert manip.label('DUPLICATE') == "<hl>Shift Duplicate</hl>"
    assert manip.label('EXTRUDE') == "<hl>Shift Extrude</hl>"
    assert manip.label('PRESS') is None and manip.label(None) is None


def test_labels_are_translated():
    for text in manip.LABELS.values():
        for strings in i18n.LANGUAGES.values():
            assert strings.get(text), text


def test_no_window_no_label():
    assert manip.announce({"kind": 'DUPLICATE'}, None, None, 0) is False
    assert manip.announce({"kind": 'PRESS'}, None, None, 0) is False
