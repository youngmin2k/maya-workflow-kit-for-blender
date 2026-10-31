"""Maya's vertical dock tab strip and the dock width per raised tab (#78), the menu bar's » overflow
and the Set Driven Key lists that give up rows (#77), Maya manipulator axis colours and the dormant wireframe colour
(#76). Rules only; real windows: tests/gui/gui_step142_ui.py."""

import re
from importlib import import_module
from pathlib import Path
from types import SimpleNamespace

import bpy

import kit

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "allset"
toolbox = import_module(kit.MODULE + ".ui.toolbox")
maya_dock = import_module(kit.MODULE + ".ui.maya_dock")
attribute_editor = import_module(kit.MODULE + ".ui.attribute_editor")
status_line = import_module(kit.MODULE + ".ui.status_line")
menu_sets = import_module(kit.MODULE + ".ui.menu_sets")
set_driven_key = import_module(kit.MODULE + ".ui.set_driven_key")
manipulator = import_module(kit.MODULE + ".ui.manipulator")
selection_wire = import_module(kit.MODULE + ".ui.selection_wire")

SCALES = (1.0, 1.25, 1.5)
OLD_DOCK = {1.0: 466, 1.25: 574, 1.5: 672}      # one horizontal tab row


# --- #78 dock ------------------------------------------------------------------------------------------------------

def test_channel_box_stack_is_maya_narrow():
    for s in SCALES:
        cb = toolbox.dock_width(s)
        mtk = toolbox.dock_width(s, kind='MODELING_TOOLKIT')
        ae = toolbox.dock_width(s, kind='ATTRIBUTE_EDITOR')
        print("scale", s, "CB", cb, "MTK", mtk, "AE", ae, toolbox.dock_need(s))
        # 277 px x the scale with the Channel Box up; the kit only as much wider as its labels need
        assert round(toolbox.DOCK_MAYA_PX * s) <= cb <= round(toolbox.DOCK_MAYA_PX * s * 1.06), (s, cb)
        assert cb < OLD_DOCK[s] - 150, (s, cb)
        assert mtk == cb, (s, mtk, cb)
        # Maya's stack with the Attribute Editor raised: 480 px x the scale
        assert ae == round(toolbox.DOCK_MAX_PX * s), (s, ae)


def test_contents_fit_left_of_the_strip():
    for s in SCALES:
        u = toolbox._unit(s)
        cb = toolbox.dock_width(s)
        content = cb - maya_dock.reserved_px(s)
        longest = max(toolbox.text_px(t, s) for t in toolbox.LONG_LABELS)
        assert (content - 0.8 * u) / 2 >= longest + 0.8 * u, (s, cb, longest)
        ae = toolbox.dock_width(s, kind='ATTRIBUTE_EDITOR')
        assert attribute_editor.fits(_Ctx(ae - maya_dock.reserved_px(s), s), attribute_editor.MENU_BAR), (s, ae)


class _Ctx:
    def __init__(self, width, scale, area=None):
        self.region = SimpleNamespace(width=width)
        self.area = area
        self.preferences = SimpleNamespace(system=SimpleNamespace(ui_scale=scale, pixel_size=1))


def test_strip_tabs_geometry():
    kinds = list(maya_dock.KINDS)
    for s in SCALES:
        w, h = 300 * s, 700 * s
        tabs = maya_dock.strip_tabs(kinds, w, h, s)
        assert [t[0] for t in tabs] == kinds
        prev_y0 = h
        for kind, x0, y0, x1, y1 in tabs:
            assert x1 == w and w - x0 == maya_dock.strip_px(s), (kind, x0, x1)
            # a tab is its caption plus the tab ends (162 px for a 140 px caption at 100 %)
            assert y1 - y0 >= toolbox.text_px(maya_dock.LABELS[kind], s) + 2 * maya_dock.TAB_END_PX * s - 1
            assert y1 <= prev_y0, (kind, y1, prev_y0)
            prev_y0 = y0
        # the strip is 16 px at 100 %
        assert 16 * s <= maya_dock.strip_px(s) <= 20 * s
        # clicks map to the tab under the point; left of the strip passes through
        for kind, x0, y0, x1, y1 in tabs:
            assert maya_dock.strip_hit(kinds, w, h, s, (x0 + x1) / 2, (y0 + y1) / 2) == (True, kind)
        assert maya_dock.strip_hit(kinds, w, h, s, w - maya_dock.strip_px(s) - 2, h - 20 * s) == (False, None)
        assert maya_dock.strip_hit(kinds, w, h, s, w - 2, 2) == (True, None)        # strip, below the tabs


def test_content_column_keeps_clear_of_the_strip():
    for s in SCALES:
        for w in (toolbox.dock_width(s), toolbox.dock_width(s, kind='ATTRIBUTE_EDITOR')):
            u = toolbox._unit(s)
            f = maya_dock.content_factor(w, s)
            margin = maya_dock.PANEL_MARGIN_U * u
            right = margin + f * (w - 2 * margin)
            assert right <= w - maya_dock.strip_px(s) - 2, (s, w, right)
            assert right >= w - maya_dock.reserved_px(s) - margin - 1, (s, w, right)


def test_stack_panel_has_no_tab_buttons():
    rec = []

    class Rec:
        def __getattr__(self, name):
            if name in ("row", "column", "split", "box", "grid_flow", "column_flow"):
                return lambda *a, **k: Rec()
            if name == "panel":
                return lambda *a, **k: (Rec(), Rec())
            if name in ("menu", "operator", "prop", "label", "popover"):
                def add(*args, **kw):
                    rec.append((name, args[0] if args else "", kw.get("text", "")))
                    return SimpleNamespace()
                return add
            return lambda *a, **k: None

        def __setattr__(self, name, value):
            pass

    screen = bpy.context.window.screen
    area = next(a for a in screen.areas if a.type == 'PROPERTIES')
    sp = area.spaces.active
    saved = {f: getattr(sp, f) for f in maya_dock.ROLE_FLAGS.values()}
    saved_ctx, saved_header = sp.context, sp.show_region_header
    try:
        assert maya_dock.set_role(area, 'STACK')
        region = next(r for r in area.regions if r.type == 'WINDOW')
        with bpy.context.temp_override(area=area, region=region):
            bpy.types.ALLSET_PT_maya_dock.draw(SimpleNamespace(layout=Rec()), bpy.context)
    finally:
        for f, v in saved.items():
            setattr(sp, f, v)
        sp.show_region_header = saved_header
        try:
            sp.context = saved_ctx
        except TypeError:
            pass
    assert ("operator", "allset.dock_handle", maya_dock.HANDLE) in rec, rec[:4]
    assert not [r for r in rec if r[1] == "allset.dock_tab"], rec[:6]


def test_strip_click_keymap_item():
    patches = import_module(kit.MODULE + ".keymap.maya_patches")
    items = [(km, ev["type"], ev["value"]) for km, idname, ev, _p, _s in patches.ADDED
             if idname == "allset.dock_strip_click"]
    # the View2D Buttons List handler runs before Property Editor (its scroller sits on the strip's edge)
    assert items == [("View2D Buttons List", "LEFTMOUSE", "PRESS")], items
    assert "allset.dock_strip_click" in patches.PASS_THROUGH_FIRST
    assert hasattr(bpy.types, "ALLSET_OT_dock_strip_click")


def test_tab_change_resizes_only_between_narrow_and_wide():
    calls = []
    real = bpy.app.timers.register
    bpy.app.timers.register = lambda fn, **kw: calls.append(fn)
    try:
        win = bpy.context.window
        toolbox.tab_changed(win, 'CHANNEL_BOX', 'MODELING_TOOLKIT')
        assert not calls
        toolbox.tab_changed(win, 'CHANNEL_BOX', 'ATTRIBUTE_EDITOR')
        toolbox.tab_changed(win, 'ATTRIBUTE_EDITOR', 'MODELING_TOOLKIT')
        assert len(calls) == 2
    finally:
        bpy.app.timers.register = real


def test_ae_fits_counts_the_strip():
    s = 1.0
    w = toolbox.dock_need(s)["ae_menu"] - maya_dock.reserved_px(s)   # exactly the one-row width without a strip
    stack = SimpleNamespace(type='PROPERTIES')
    plain = _Ctx(w, s)
    assert attribute_editor.fits(plain, attribute_editor.MENU_BAR)
    real = maya_dock.area_role
    maya_dock.area_role = lambda context: 'STACK' if getattr(context, "area", None) is stack else None
    try:
        assert not attribute_editor.fits(_Ctx(w, s, stack), attribute_editor.MENU_BAR)
    finally:
        maya_dock.area_role = real


# --- #77 menu bar overflow / Set Driven Key -------------------------------------------------------------------------

def test_menu_fit_rule():
    widths = [40, 60, 80, 50]
    assert status_line.menu_fit(widths, 400, 30, 20) == 4                 # all fit: no » button
    n = status_line.menu_fit(widths, 200, 30, 20)
    assert n == 2 and 30 + 20 + 40 + 60 <= 200 < 30 + 20 + 40 + 60 + 80, n
    assert status_line.menu_fit(widths, 30, 30, 20) == 0
    # shrinking never shows more
    last = 4
    for width in range(400, 0, -5):
        k = status_line.menu_fit(widths, width, 30, 20)
        assert k <= last
        last = k


def _ctx(scale):
    prefs = bpy.context.preferences
    return SimpleNamespace(preferences=SimpleNamespace(system=SimpleNamespace(ui_scale=scale, pixel_size=1),
                                                       ui_styles=prefs.ui_styles))


def test_menu_bar_overflows_a_1600_px_window_only_at_150():
    names = menu_sets.menus_for_set(menu_sets.DEFAULT_SET)
    assert len(names) == 18, names
    right = {}
    for s in SCALES:
        widths, fixed, more = status_line.menu_bar_widths(_ctx(s), names, False)
        # the top bar's right region: "Workspace:" + dropdown (7 U) + Maya | Blender (~ 13 U at 1.25)
        right[s] = round(18 * (round(18 * s) + 2))
        n = status_line.menu_fit(widths, 1600 - right[s], fixed, more)
        print("scale", s, "menus", sum(widths) + fixed, "shown", n, "of", len(names))
        if s == 1.0:
            assert n == len(names), (s, n)
        elif s == 1.5:
            assert 10 <= n < len(names), (s, n)
            assert fixed + more + sum(widths[:n]) <= 1600 - right[s]


def test_overflow_menu_lists_the_hidden_menus():
    assert hasattr(bpy.types, "ALLSET_MT_menu_more")
    names = menu_sets.menus_for_set(menu_sets.DEFAULT_SET)
    win = bpy.context.window
    status_line._menus_shown[win.as_pointer()] = (tuple(names), 12)
    try:
        log = []
        layout = SimpleNamespace(menu=lambda idname, **kw: log.append(idname))
        bpy.types.ALLSET_MT_menu_more.draw(SimpleNamespace(layout=layout), bpy.context)
    finally:
        status_line._menus_shown.pop(win.as_pointer(), None)
    assert log == [menu_sets.menu_idname(n) for n in names[12:]], log


def test_sdk_lists_give_up_rows():
    assert set_driven_key.list_rows(None) == set_driven_key.ROWS == 4
    assert set_driven_key.list_rows(100) == 4
    assert set_driven_key.list_rows(set_driven_key.FIXED_UNITS + 4.5) == 2
    assert set_driven_key.list_rows(0) == set_driven_key.MIN_ROWS == 2
    rows = [set_driven_key.list_rows(r / 2) for r in range(0, 60)]
    assert rows == sorted(rows)


# --- #76 colours ---------------------------------------------------------------------------------------------------

def test_manipulator_axes_are_maya_colours():
    c = manipulator.axis_colours()
    assert manipulator.MAYA_AXIS == {'X': "#e60000", 'Y': "#00e600", 'Z': "#0000ff"}
    assert c['X'] == (230 / 255, 0.0, 0.0) and c['Y'] == (0.0, 230 / 255, 0.0) and c['Z'] == (0.0, 0.0, 1.0)
    text = (SRC / "ui" / "manipulator.py").read_text(encoding="utf-8")
    assert not re.search(r"\.axis_[xyz]\b", text), "the Move / Scale handles don't read the theme's axis colours"


def test_dormant_wire_colour_and_objects():
    assert selection_wire.DORMANT == "#000460"
    lin = selection_wire.dormant_color()
    assert abs(lin[0]) < 1e-6 and 0.0 < lin[1] < 0.003 and 0.1 < lin[2] < 0.12 and lin[3] == 1.0, lin

    def ob(name, selected, kind='MESH', mode='OBJECT'):
        return SimpleNamespace(name=name, type=kind, mode=mode, select_get=lambda: selected,
                               local_view_get=lambda space: True)

    a, b, c, lamp = ob("a", True), ob("b", False), ob("c", False, mode='EDIT'), ob("l", False, kind='LIGHT')

    def ctx(shading, mesh=True):
        space = SimpleNamespace(type='VIEW_3D', shading=SimpleNamespace(type=shading), local_view=None,
                                show_object_viewport_mesh=mesh)
        return SimpleNamespace(space_data=space, visible_objects=[a, b, c, lamp])
    assert [o.name for o in selection_wire.dormant_objects(ctx('WIREFRAME'))] == ["b"]
    assert selection_wire.dormant_objects(ctx('SOLID')) == []
    assert selection_wire.dormant_objects(ctx('WIREFRAME', mesh=False)) == []     # the Tool Box column


def test_no_theme_or_preference_writes():
    for name in ("maya_dock.py", "toolbox.py", "status_line.py", "set_driven_key.py", "manipulator.py",
                 "selection_wire.py"):
        text = (SRC / "ui" / name).read_text(encoding="utf-8")
        assert not re.search(r"themes\[0\][\w.]*\s*=[^=]", text), name
