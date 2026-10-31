"""Marking menu engine logic, hotbox layout, zone menus, zone operators, keymap, prefs."""

import math
import types
from importlib import import_module

import bpy

import kit

engine = import_module(kit.MODULE + ".marking.engine")
mm = import_module(kit.MODULE + ".marking.menus")
modal = import_module(kit.MODULE + ".marking.modal")
draw = import_module(kit.MODULE + ".marking.draw")
marking = import_module(kit.MODULE + ".marking")
maya_patches = import_module(kit.MODULE + ".keymap.maya_patches")


def measure(text):
    return 7.0 * len(text)


P = engine.Params()
R = P.radius


def _session(menu, enabled=None, t0=0.0):
    return engine.Session(menu, (500.0, 400.0), t0, measure, P, enabled)


def _at(direction, dist):
    ux, uy = engine._UNIT[direction]
    return 500.0 + ux * dist, 400.0 + uy * dist


def _override():
    win = bpy.context.window_manager.windows[0]
    area = next(a for a in win.screen.areas if a.type == 'VIEW_3D')
    region = next(r for r in area.regions if r.type == 'WINDOW')
    return bpy.context.temp_override(window=win, area=area, region=region)


# --- geometry ------------------------------------------------------------------------

def test_direction_sectors():
    d = engine.direction
    assert d(0, 5, 12) is None and d(8, 8, 12) is None, "dead zone"
    assert d(0, 50, 12) == "N" and d(0, -50, 12) == "S" and d(50, 0, 12) == "E" and d(-50, 0, 12) == "W"
    assert d(40, 40, 12) == "NE" and d(-40, 40, 12) == "NW" and d(40, -40, 12) == "SE" and d(-40, -40, 12) == "SW"
    # Sector edges at 22.5 degrees.
    a = math.radians(22.0)
    assert d(100 * math.cos(a), 100 * math.sin(a), 12) == "E"
    a = math.radians(23.0)
    assert d(100 * math.cos(a), 100 * math.sin(a), 12) == "NE"


def test_layout_maya_placement():
    lay = engine.Layout(mm.SHIFT_EDGE, measure, P)
    r = lay.radial
    assert set(r) == set(mm.SHIFT_EDGE.radial)
    n, s, e, w = r["N"].rect, r["S"].rect, r["E"].rect, r["W"].rect
    assert abs((n[0] + n[2]) / 2) < 1e-6 and n[1] > 0, "N centred above"
    assert abs((s[0] + s[2]) / 2) < 1e-6 and s[3] < 0, "S centred below"
    assert abs(e[0] - R) < 1e-6, "E grows to the right of its anchor"
    assert abs(w[2] + R) < 1e-6, "W grows to the left"
    lists = [it for it in lay.items if it.kind == "list"]
    assert lists and all(it.rect[3] <= s[1] for it in lists), "the list is under the ring"
    rects = [it.rect for it in lay.items]
    for i, a in enumerate(rects):
        for b in rects[i + 1:]:
            assert a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1], ("overlap", a, b)
    # Option boxes where Maya has them (E Bevel Edge, W Multi-Cut), none on submenus.
    assert r["E"].opt_rect and r["W"].opt_rect and r["N"].opt_rect is None


# --- session ------------------------------------------------------------------------

def test_drag_release_selects_direction():
    s = _session(mm.RMB_MESH)
    s.move(*_at("N", 40), 0.1)
    assert s.hover[0].label == "Edge"
    res = s.release(*_at("N", 60), 0.5)
    assert res[0] == "RUN" and res[1].label == "Edge" and res[2] is False


def test_release_in_dead_zone():
    s = _session(mm.RMB_MESH)
    assert s.release(503, 402, 0.1) is None and s.mode == "CLICK", "quick click keeps it open"
    s.move(*_at("W", 50), 0.5)
    res = s.click(*_at("W", 50), 0.6)
    assert res[0] == "RUN" and res[1].label == "Vertex"
    s = _session(mm.RMB_MESH)
    assert s.release(503, 402, 1.0)[0] == "CANCEL", "long hold released at the centre cancels"
    s = _session(mm.RMB_MESH)
    s.release(500, 400, 0.1)
    assert s.click(501, 401, 0.3)[0] == "CANCEL", "click at the centre in click mode cancels"


def test_flick_before_menu_is_drawn():
    s = _session(mm.RMB_MESH)
    assert not s.visible(0.05)
    s.move(*_at("S", 30), 0.04)
    res = s.release(*_at("S", 45), 0.08)
    assert not s.visible(0.08) and res[0] == "RUN" and res[1].label == "Face"
    assert s.visible(P.show_delay + 0.01) or s.result


def test_submenu_in_place_and_zigzag():
    s = _session(mm.SHIFT_EDGE)
    s.move(*_at("N", 50), 0.1)
    assert s.hover[0].label == "Merge/Collapse Edges"
    x, y = _at("N", R + 5)
    s.move(x, y, 0.2)
    assert len(s.stack) == 2 and s.center == (x, y), "submenu opens where the pointer is"
    # Second stroke east = Collapse Edge (Merge/Collapse submenu E).
    res = s.release(x + 60, y, 0.3)
    assert res[0] == "RUN" and res[1].label == "Collapse Edge", res
    # Same as one quick zig-zag mark (never drawn).
    s = _session(mm.SHIFT_EDGE)
    s.move(*_at("NE", 40), 0.02)
    x, y = _at("NE", R + 2)
    s.move(x, y, 0.04)
    res = s.release(x - 50, y, 0.07)
    assert res[1].label == "Spin Backward", res


def test_option_box_and_list_hits():
    s = _session(mm.SHIFT_EDGE)
    lay = s.layout
    bevel = lay.radial["E"]
    ox = 500 + (bevel.opt_rect[0] + bevel.opt_rect[2]) / 2
    oy = 400 + (bevel.opt_rect[1] + bevel.opt_rect[3]) / 2
    res = s.release(ox, oy, 0.5)
    assert res[0] == "RUN" and res[1].label == "Bevel Edge" and res[2] is True, res
    s = _session(mm.SHIFT_EDGE)
    bridge = next(it for it in lay.items if it.label == "Bridge")
    cx = 500 + (bridge.rect[0] + bridge.rect[2]) / 2 - 20
    cy = 400 + (bridge.rect[1] + bridge.rect[3]) / 2
    res = s.release(cx, cy, 0.5)
    assert res[1].label == "Bridge" and res[2] is False, "list rows hit by rectangle"


def test_disabled_items_do_not_run():
    s = _session(mm.RMB_MESH, enabled=lambda a: a is not None)
    assert not s.layout.radial["SW"].enabled  # Vertex Face (UV in E works)
    assert s.release(*_at("SW", 60), 0.5)[0] == "CANCEL"


def test_list_submenu_opens_on_hover():
    s = _session(mm.HB_CENTER)
    style = next(it for it in s.layout.items if it.label == "Hotbox Style")
    s.move(500 + style.rect[0] + 5, 400 + (style.rect[1] + style.rect[3]) / 2, 0.3)
    assert len(s.stack) == 2 and s.layout.sub is style.sub
    first = s.layout.items[0]
    res = s.release(s.center[0] + (first.rect[0] + first.rect[2]) / 2,
                    s.center[1] + (first.rect[1] + first.rect[3]) / 2, 0.6)
    assert res[1].label == "Zones and Menu Rows", res


# --- hotbox ----------------------------------------------------------------------------

def test_hotbox_layout_rows_and_zones():
    rows = [[("RECENT", "Recent Commands"), ("CONTROLS", "Hotbox Controls")],
            [("A", "File"), ("B", "Edit")], [("C", "Mesh"), ("D", "UV")]]
    lay = engine.HotboxLayout(rows, (600.0, 400.0), measure)
    assert len(lay.labels) == 6
    ys = [r[1] for r, _k, _l in lay.labels]
    assert ys[0] > ys[2] > ys[4] > lay.center_rect[3], "rows stack upward, first row on top"
    rect, key, _label = lay.labels[2]
    assert lay.label_at((rect[0] + rect[2]) / 2, (rect[1] + rect[3]) / 2) == "A"
    assert lay.zone(600, 400) == "C"
    assert lay.zone(600, 100) == "S" and lay.zone(900, 400) == "E" and lay.zone(300, 380) == "W"
    assert lay.zone(610, 380 + 300) == "N"
    centre_only = engine.HotboxLayout(rows, (600.0, 400.0), measure, style="CENTER")
    assert not centre_only.labels and centre_only.zone(900, 400) is None
    zones_only = engine.HotboxLayout(rows, (600.0, 400.0), measure, style="ZONES")
    assert not zones_only.labels and zones_only.zone(900, 400) == "E"


def test_tap_timing():
    assert engine.is_tap(0.0, 0.3, False)
    assert not engine.is_tap(0.0, 0.5, False), "held past -noClickDelay 0.4"
    assert not engine.is_tap(0.0, 0.2, True), "a click is not a tap"


def test_hotbox_rows_follow_menu_set():
    prefs = bpy.context.preferences.addons[kit.MODULE].preferences
    assert prefs.hotbox_all_sets, "default: Show All Menu Sets"
    above, sides, below = modal.hotbox_rows(bpy.context)
    assert sides[0][0] == "RECENT" and [l for _k, l in above[0]][:3] == ["File", "Edit", "Create"]
    assert "Mesh" in [l for _k, l in below[0]] and len(below) == 5
    try:
        prefs.hotbox_all_sets = False
        assert len(modal.hotbox_rows(bpy.context)[2]) == 1
    finally:
        prefs.hotbox_all_sets = True


# --- zone menus ----------------------------------------------------------------------


def test_zone_operators():
    with _override():
        area = bpy.context.area
        rv3d = area.spaces.active.region_3d
        rv3d.view_perspective = 'PERSP'
        rot = rv3d.view_rotation.copy()
        bpy.ops.allset.hb_view(view='TOP')
        assert rv3d.view_perspective == 'ORTHO'
        bpy.ops.allset.hb_view(view='PERSP')
        assert rv3d.view_perspective == 'PERSP' and rv3d.view_rotation == rot, "persp view restored"
        bpy.ops.allset.hb_mask(preset='POLYGONS')
        sp = area.spaces.active
        assert sp.show_object_select_mesh and not sp.show_object_select_camera and not sp.show_object_select_curve
        bpy.ops.allset.hb_mask(preset='ALL')
        assert sp.show_object_select_camera
        prefs = bpy.context.preferences.addons[kit.MODULE].preferences
        before = prefs.show_help_line
        bpy.ops.allset.hb_ui(element='HELP_LINE')
        assert prefs.show_help_line != before
        bpy.ops.allset.hb_ui(element='HELP_LINE')
        # TOOLBOX (show_region_toolbar) is checked in the GUI test: no toolbar region in -b.
        bpy.ops.allset.hb_style(style='ZONES')
        assert prefs.hotbox_style == 'ZONES'
        prefs.hotbox_style = 'ALL'
        bpy.ops.allset.hb_pane(ui_type='OUTLINER')
        assert area.type == 'OUTLINER'
    win = bpy.context.window_manager.windows[0]
    with bpy.context.temp_override(window=win, area=area):
        bpy.ops.allset.hb_view(view='PERSP')  # back to a model panel
    assert area.type == 'VIEW_3D'


def test_actions_of_zone_menus_exist():
    bad = []
    for menu in mm.HOTBOX_ZONES.values():
        for path, _label, action in mm.walk(menu, menu.name):
            if action is None or isinstance(action, mm.Sub):
                continue
            kind, target, props = marking.menu_map.normalize(action)
            mod, op = target.split(".")
            try:
                rna = getattr(getattr(bpy.ops, mod), op).get_rna_type()
            except (AttributeError, KeyError):
                bad.append((path, target))
                continue
            bad.extend((path, k) for k in props if k not in rna.properties)
    assert not bad, bad


def test_poll_action_cache_inputs():
    assert modal.poll_action(None) is False
    assert modal.poll_action(mm.SOFT_HARD) is True
    assert modal.poll_action(("tool", "builtin.move", False)) is True
    with _override():
        for ob in list(bpy.data.objects):
            bpy.data.objects.remove(ob)
        assert modal.poll_action("object.join") is False, "poll fails with nothing selected"


# --- keymap, prefs, cleanup ----------------------------------------------------------

def test_space_hotbox_keymap():
    kc = kit.maya_kc()
    for km in maya_patches.HOTBOX_KEYMAPS:
        items = [k for k in kc.keymaps[km].keymap_items if k.type == 'SPACE' and not (k.ctrl or k.shift or k.alt)]
        assert [k.idname for k in items] == ["allset.hotbox"], (km, [k.idname for k in items])


def test_engine_is_default_and_pie_fallback():
    prefs = bpy.context.preferences.addons[kit.MODULE].preferences
    assert prefs.marking_menu_style == 'ENGINE'
    calls = []
    try:
        modal.bpy = types.SimpleNamespace(
            context=bpy.context,
            ops=types.SimpleNamespace(
                allset=types.SimpleNamespace(mm_engine=lambda *a, **k: calls.append(("engine", k))),
                wm=types.SimpleNamespace(call_menu_pie=lambda **k: calls.append(("pie", k)))))
        modal.open_menu("RMB_MESH", "RIGHTMOUSE")
        prefs.marking_menu_style = 'PIE'
        modal.open_menu("RMB_MESH", "RIGHTMOUSE")
    finally:
        modal.bpy = bpy
        prefs.marking_menu_style = 'ENGINE'
    assert calls[0] == ("engine", {"menu": "RMB_MESH", "button": "RIGHTMOUSE"}), calls
    modal.bpy = types.SimpleNamespace(context=bpy.context, ops=types.SimpleNamespace(
        allset=types.SimpleNamespace(mm_engine=lambda *a, **k: calls.append(("engine", k)))))
    try:
        modal.open_menu("RMB_MESH", "LEFTMOUSE", (10, 20))
    finally:
        modal.bpy = bpy
    assert calls[-1] == ("engine", {"menu": "RMB_MESH", "button": "LEFTMOUSE", "origin": (10, 20)})
    assert calls[1] == ("pie", {"name": marking.idname("RMB_MESH")}), calls


def test_draw_handlers_removed_on_disable():
    assert len(draw._handles) >= len(draw.COVER_SPACES) * 2   # editors x region types
    kit.disable()
    try:
        assert not draw._handles and not draw.ACTIVE
    finally:
        kit.enable()
