"""#101: lane A: Display > Grid ❒ = Maya's Grid Options, and the kit grid
(ui/maya_grid.py) follows its values: length and width, grid lines every, subdivisions, colours, Display checks, in
Maya units."""

import json
from importlib import import_module

import bpy

import kit

grid = import_module(kit.MODULE + ".ui.maya_grid")
ow = import_module(kit.MODULE + ".operators.option_windows")
owd = import_module(kit.MODULE + ".operators.option_windows_display")
menu_sets = import_module(kit.MODULE + ".ui.menu_sets")
preferences = import_module(kit.MODULE + ".preferences")

GREY = (0.25, 0.25, 0.25)        # Maya colour index 2


def _window():
    w = ow.find_path("Display/Grid")
    assert w is not None and w.key == "grid_options", w
    return w


def _reset():
    ow.store("grid_options", None)


def test_window_is_maya_grid_options():
    w = _window()
    assert w.title == "Grid Options" and w.action == "Apply and Close" and w.apply_text == "Apply"
    rows = [(f.label, f.kind, f.default, f.text) for f in w.fields]
    assert rows == [
        ("Length and width:", "float", 12.0, None),
        ("Grid lines every:", "float", 5.0, None),
        ("Subdivisions:", "int", 5, None),
        ("Axes:", "vec3color", GREY, None),
        ("Grid lines & numbers:", "vec3color", GREY, None),
        ("Subdivision lines:", "vec3color", GREY, None),
        ("Display:", "bool", True, "Axes"),
        ("", "bool", True, "Thicker line for axes"),
        ("", "bool", True, "Grid lines"),
        ("", "bool", True, "Subdivision lines"),
    ], rows
    subdiv = next(f for f in w.fields if f.name == "divisions")
    assert (subdiv.lo, subdiv.hi) == (1, 20)          # Maya's slider range
    assert any("Perspective grid numbers" in m for m in w.missing)
    assert any("Orthographic grid numbers" in m for m in w.missing)
    assert menu_sets.option_kind("Display/Grid") == "window"
    assert hasattr(bpy.ops.allset, "opt_grid_options")


def test_factory_values_are_the_old_grid():
    _reset()
    s = grid.settings()
    assert (s["size"], s["spacing"], s["divisions"]) == (grid.SIZE, grid.SPACING, grid.DIVISIONS) == (12, 5, 5)
    assert grid.line_colour() == (*GREY, 1.0)
    st = grid.styles(s)
    assert st == {"minor": (1.0, GREY), "major": (2.0, GREY), "axis": (2.0, GREY)}, st


def test_segments_follow_size_spacing_divisions():
    segs = grid.segments(20, 10, 2)                    # a line every 5, majors every 10, out to 20
    lines = sorted({ln[0][0] for k in segs for ln in segs[k] if ln[0][1] == -20})
    assert lines == [-20, -15, -10, -5, 0, 5, 10, 15, 20], lines
    assert sorted({ln[0][0] for ln in segs["major"] if ln[0][1] == -20}) == [-20, -10, 10, 20]
    ends = [c for k in segs for ln in segs[k] for p in ln for c in p]
    assert min(ends) == -20 and max(ends) == 20
    # a last step that doesn't fit stays out (lines stop at the edge)
    segs = grid.segments(12, 5, 2)                     # every 2.5: 2.5 ... 10, not 12.5
    xs = sorted({ln[0][0] for k in segs for ln in segs[k] if ln[0][1] == -12})
    assert xs[0] == -10 and xs[-1] == 10 and len(xs) == 9, xs
    assert all(abs(ln[0][1]) == 12 for k in segs for ln in segs[k] if ln[0][0] == ln[1][0])
    # one subdivision = majors only
    segs = grid.segments(10, 2, 1)
    assert not segs["minor"] and len(segs["major"]) == 2 * 10
    # absurd values stay bounded
    segs = grid.segments(1000, 0.001, 20)
    assert sum(len(v) for v in segs.values()) <= 2 * (2 * grid.MAX_LINES + 1)


def test_plane_points_use_maya_units():
    segs = grid.segments(20, 10, 2)["axis"]
    for unit in (0.01, 1.0):
        pts = grid.plane_points(segs, "FLOOR", unit)
        assert max(abs(c) for p in pts for c in p) == 20 * unit
    assert grid.corners("FLOOR", 0.01, size=20)[2] == (0.2, 0.2, 0.0)


def test_window_run_changes_drawn_grid():
    _reset()
    w = _window()
    red, green, blue = (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)
    try:
        values = {**w.defaults(), "size": 30.0, "spacing": 10.0, "divisions": 2, "axis_color": red,
                  "line_color": green, "division_color": blue}
        ow.store(w.key, values)                         # what execute / Apply do before running
        assert ow.run(w, bpy.context, values) == {'FINISHED'}
        s = grid.settings()
        assert (s["size"], s["spacing"], s["divisions"]) == (30.0, 10.0, 2)
        assert grid.styles(s) == {"minor": (1.0, blue), "major": (2.0, green), "axis": (2.0, red)}
        assert grid.line_colour() == (*green, 1.0)
        segs = grid.segments(s["size"], s["spacing"], s["divisions"])
        assert len(segs["major"]) == 2 * 6 and len(segs["minor"]) == 2 * 6   # ±10/20/30 and ±5/15/25
        # Display checks
        ow.store(w.key, {**values, "show_axes": False})
        st = grid.styles(grid.settings())
        assert st["axis"] == st["major"] == (2.0, green)  # the origin lines become ordinary grid lines
        ow.store(w.key, {**values, "thick_axes": False, "show_divisions": False, "show_lines": False})
        st = grid.styles(grid.settings())
        assert st == {"axis": (1.0, red)}, st
        # the stored JSON round trip (colours come back as tuples)
        raw = json.loads(preferences.get().option_settings)["grid_options"]
        assert raw["size"] == 30.0 and list(raw["axis_color"]) == list(red)
    finally:
        _reset()
    assert grid.settings()["size"] == 12.0


def test_operator_apply_and_reset():
    _reset()
    try:
        res = bpy.ops.allset.opt_grid_options('EXEC_DEFAULT', size=24.0, divisions=4,
                                              line_color=(0.5, 0.5, 0.5))
        assert res == {'FINISHED'}, res
        s = grid.settings()
        assert s["size"] == 24.0 and s["divisions"] == 4 and abs(s["line_color"][0] - 0.5) < 1e-6
        assert ow.saved("grid_options")["size"] == 24.0
    finally:
        _reset()


def test_plain_click_still_toggles_the_grid():
    """Display > Grid with saved options keeps toggling the grid (Maya ToggleGrid), the window only sets its look."""
    from importlib import import_module as im
    modal = im(kit.MODULE + ".marking.modal")
    menu_map = im(kit.MODULE + ".ui.menu_map")
    w = _window()
    assert w.click_saved is False
    ow.store(w.key, {**w.defaults(), "size": 6.0})
    called = []
    orig = ow.run_saved
    ow.run_saved = lambda *a, **k: called.append(a) or {'FINISHED'}
    try:
        try:
            modal.run_action(bpy.context, menu_map.MAP["Display/Grid"], path="Display/Grid")
        except RuntimeError:
            pass          # no 3D View context in -b: allset.menu_run / toggle_grid may fail; it must not run the window
        assert not called
    finally:
        ow.run_saved = orig
        _reset()


def test_draw_handler_survives_settings():
    """The drawer builds its batches from the settings (no GPU in -b: the pure parts only)."""
    _reset()
    s = grid.settings()
    for kind, (width, rgb) in grid.styles(s).items():
        assert kind in ("minor", "major", "axis") and width in grid.WIDTHS and len(rgb) == 3
