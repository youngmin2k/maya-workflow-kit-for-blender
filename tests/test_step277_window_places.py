"""#203: kit windows reopen at their last size and place (per window kind, fitted into view).
The real windows: tests/gui/gui_step277_window_places.py."""

import json
import os
from importlib import import_module

import bpy

import kit

wp = import_module(kit.MODULE + ".ui.window_places")
menu_extras = import_module(kit.MODULE + ".operators.menu_extras")


def test_fit_keeps_a_rect_that_is_inside():
    assert wp.fit((100, 100, 400, 300), (0, 0, 1600, 900)) == (100, 100, 400, 300)


def test_fit_brings_back_a_rect_that_is_off_screen():
    bounds = (0, 0, 1600, 900)
    assert wp.fit((-3000, 50, 400, 300), bounds) == (0, 50, 400, 300)          # another monitor on the left
    assert wp.fit((1500, 850, 400, 300), bounds) == (1200, 600, 400, 300)      # hanging over the right / top
    assert wp.fit((100, 100, 4000, 3000), bounds) == (0, 0, 1600, 900)         # bigger than the window
    assert wp.fit((100, 100, 20, 10), bounds) == (100, 100, wp.MIN_SIZE, wp.MIN_SIZE)
    assert wp.fit((0, 0, 400, 300), (0, 0, 80, 900)) is None                   # no room


def test_thin_margins_go_to_the_window():
    bounds = (0, 0, 1600, 900)
    assert wp.snap_margins((10, 20, 400, 300), bounds) == (0, 0, 410, 320)
    assert wp.snap_margins((100, 100, 1480, 780), bounds) == (100, 100, 1500, 800)
    assert wp.snap_margins((100, 100, 400, 300), bounds) == (100, 100, 400, 300)


def test_cuts():
    bounds = (50, 40, 1600, 900)
    assert wp.cuts((50, 40, 1600, 900), bounds) == []
    assert wp.cuts((150, 140, 400, 300), bounds) == [('VERTICAL', 150), ('VERTICAL', 550),
                                                    ('HORIZONTAL', 140), ('HORIZONTAL', 440)]
    assert wp.cuts((50, 40, 400, 940 - 40), bounds) == [('VERTICAL', 450)]


class _Win:
    def __init__(self, x, y):
        self.x, self.y = x, y


class _Area:
    def __init__(self, x, y, w, h):
        self.x, self.y, self.width, self.height = x, y, w, h


def test_target_in_window_px():
    wp._places.clear()
    wp._state["loaded"] = True
    assert wp.target_in_window("render_settings", _Win(0, 0), _Area(0, 0, 1600, 900)) is None
    wp.remember("render_settings", (300, 240, 500, 400))           # screen px
    # main window at screen (200, 100): the place is (100, 140) in it
    assert wp.target_in_window("render_settings", _Win(200, 100), _Area(0, 30, 1600, 870)) == (100, 140, 500, 400)
    # a place on a second monitor to the left comes back inside the area, size kept
    wp.remember("render_settings", (-1800, 240, 500, 400))
    assert wp.target_in_window("render_settings", _Win(200, 100), _Area(0, 30, 1600, 870)) == (0, 140, 500, 400)


def test_saved_per_kind_and_read_back():
    p = wp.path()
    assert p and os.path.dirname(p), p
    wp._places.clear()
    wp.remember("hypershade", (10, 20, 1440, 900))
    wp.remember("marked:PREFERENCES", (30, 40, 700, 600))
    wp.save()
    with open(p, encoding="utf-8") as fh:
        data = json.load(fh)
    assert data["hypershade"] == [10, 20, 1440, 900] and data["marked:PREFERENCES"] == [30, 40, 700, 600]
    wp._places.clear()
    wp._state["loaded"] = False
    assert wp.place("hypershade") == [10, 20, 1440, 900]
    # a broken file is ignored
    with open(p, "w", encoding="utf-8") as fh:
        fh.write("{not json")
    wp._places.clear()
    wp._state["loaded"] = False
    assert wp.place("hypershade") is None
    os.remove(p)


def test_a_new_place_wins_over_the_file():
    wp._places.clear()
    wp.remember("render_view", (1, 2, 300, 200))
    wp.save()
    wp._places.clear()
    wp._state["loaded"] = False
    wp.remember("render_view", (5, 6, 640, 480))      # before anything read the file
    assert wp.place("render_view") == [5, 6, 640, 480]
    os.remove(wp.path())


def test_not_in_the_blend():
    wp.remember("script_editor", (1, 2, 300, 200))
    assert not any("window_places" in k for k in bpy.context.scene.keys())
    assert all("window_places" not in t.name for t in bpy.data.texts)


def test_open_window_takes_a_kind():
    import inspect
    assert list(inspect.signature(menu_extras.open_window).parameters) == ["context", "area", "kind"]


def test_disable_stops_the_timer():
    kit.disable()
    assert not bpy.app.timers.is_registered(wp._tick)
    kit.enable()
