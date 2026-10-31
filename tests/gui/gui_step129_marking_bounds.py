"""#5: a marking menu / hotbox opened low in the viewport stays open while the cursor goes down into the
Time Slider (the timeline area under the view), and releasing / clicking over an item drawn there runs it.
Part 1: factory layout, RMB drag south into the timeline = Face. Part 2: Maya Workflow Kit layout, RMB drag down
through the list (past the Paint cascade row) onto a row drawn over the Time Slider; the hotbox opened low, a menu
row drawn over the Time Slider is clicked."""

import os
import sys
from importlib import import_module

import bpy
from bpy_extras.view3d_utils import location_3d_to_region_2d, region_2d_to_location_3d

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, run, setup, step, tap, win, load_maya_layout  # noqa: E402

C = {}
# rows with an effect the test can see (object mode, one mesh in the scene)
SAFE_ROWS = ("Select All", "Deselect All", "Invert Selection", "Select")
# the list stays one column (Maya); low in the view it stands beside the ring, slid up from the window
# bottom, so the rows over the Time Slider are its last ones: the Assign ... Material cascades. Reaching one there
# opens its cascade (KIT_ROWS); releasing over a cascade row runs nothing and closes the menu.
KIT_ROWS = ("Assign Favorite Material", "Assign Existing Material")


def draw():
    return import_module(MODULE + ".marking.draw")


def main_view():
    return import_module(MODULE + ".ui.status_line").main_view3d(win().screen)


def timeline():
    areas = [a for a in win().screen.areas if a.type == 'DOPESHEET_EDITOR']
    return next((a for a in areas if a.ui_type == 'TIMELINE'), areas[0] if areas else None)


def in_area(area, x, y):
    return area.x <= x < area.x + area.width and area.y <= y < area.y + area.height


def redraw():
    for a in win().screen.areas:
        a.tag_redraw()


def place_low(ob, above_px):
    """Move ``ob`` so it shows ``above_px`` over the bottom of the main view, half way across; its window point."""
    _area, region = main_view()
    target = location_3d_to_region_2d(region, region.data, ob.location)
    target.x, target.y = region.width / 2, above_px
    ob.location = region_2d_to_location_3d(region, region.data, target, ob.location)
    bpy.ops.object.select_all(action='DESELECT')
    return region.x + int(target.x), region.y + above_px


def abs_center(s, it, level=0):
    _lay, (cx, cy) = s.stack[level]
    _area, region = main_view()
    return (region.x + int(cx + (it.rect[0] + it.rect[2]) / 2), region.y + int(cy + (it.rect[1] + it.rect[3]) / 2))


def path(a, b, n):
    return [(round(a[0] + (b[0] - a[0]) * k / n), round(a[1] + (b[1] - a[1]) * k / n)) for k in range(1, n + 1)]


def mover(key, label):
    """One MOUSEMOVE per tick along C[key]; records whether the menu was up at every point."""
    def fn():
        pts = C[key]
        if not pts:
            return
        x, y = pts.pop(0)
        ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
        if not draw().ACTIVE:
            C.setdefault("closed_" + label, (x, y))
        if pts:
            _steps_insert(fn)
    return fn


def _steps_insert(fn):
    import sim
    sim._steps.insert(0, fn)


# --- part 1: factory layout, radial south item over the timeline --------------------------------------------------

@step
def s_setup():
    setup()
    C["press"] = place_low(bpy.data.objects["Cube"], 40)


@step
def s_press():
    x, y = C["press"]
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
    ev('RIGHTMOUSE', 'PRESS', x=x, y=y)
    C["south"] = path((x, y), (x, y - 85), 6)


step(mover("south", "south"))


@step
def s_in_timeline():
    s = draw().ACTIVE.get("session")
    x, y = C["press"]
    check("factory: cursor is over the timeline", in_area(timeline(), x, y - 85))
    check("factory: RMB menu stays open while dragging down into the timeline",
          s is not None and "closed_south" not in C)
    if s is not None:
        item = s.hover[0]
        print("GUI-DBG on_row stack", len(s.stack), "hover", item and item.label, "pos", s.pos, flush=True)
        # the ring stays at the press point (the list goes beside it), so dragging down picks Face
        check(f"factory: south item (Face) highlighted over the timeline ({item and item.label})",
              item is not None and item.label == "Face")


@step
def s_release():
    x, y = C["press"]
    ev('RIGHTMOUSE', 'RELEASE', x=x, y=y - 85)


@step
def s_released():
    check("factory: release over the timeline runs the south item (face mode)",
          bpy.context.mode == 'EDIT_MESH'
          and tuple(bpy.context.scene.tool_settings.mesh_select_mode) == (False, False, True))


@step
def s_closed():
    check("factory: menu closed", not draw().ACTIVE)
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    load_maya_layout()


# --- part 2: Maya Workflow Kit layout --------------------------------------------------------------------------------

@step
def s_kit_scene():
    bpy.ops.allset.keymap_activate()
    area, region = main_view()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        bpy.ops.allset.create(kind='CUBE')
    tl = timeline()
    print("GUI-DBG kit view", region.x, region.y, region.width, region.height,
          "timeline", tl and (tl.x, tl.y, tl.width, tl.height))
    redraw()


def rmb_height():
    """Height over the view's bottom where the RMB list ends with a SAFE_ROWS row over the Time Slider (the
    engine lays it out the same way: one column, beside the ring when it doesn't fit under it)."""
    engine, modal, mm = (import_module(MODULE + ".marking." + n) for n in ("engine", "modal", "menus"))
    _area, region = main_view()
    tl = timeline()
    bounds = draw().window_bounds(win(), region)
    menu = mm.with_object_name(mm.RMB_MESH, "pCube1")
    for h in range(30, region.height - 60, 4):
        s = engine.Session(menu, (region.width / 2, h), 0.0, draw().measure, modal._params(), modal.poll_action, bounds)
        for it in s.layout.items:
            cx, cy = (it.rect[0] + it.rect[2]) / 2 + region.width / 2, (it.rect[1] + it.rect[3]) / 2 + h
            if it.kind == "list" and it.label in SAFE_ROWS + KIT_ROWS and in_area(tl, region.x + cx, region.y + cy):
                return h
    return 30


def hotbox_height():
    """Height over the view's bottom where a hotbox menu row lands over the Time Slider."""
    engine, modal = (import_module(MODULE + ".marking." + n) for n in ("engine", "modal"))
    _area, region = main_view()
    tl = timeline()
    prefs = modal._prefs(bpy.context)
    above, sides, below = modal.hotbox_rows(bpy.context, 'VIEW_3D')
    bounds = draw().window_bounds(win(), region)
    for h in range(30, region.height - 60, 4):
        lay = engine.HotboxLayout(above, (region.width // 2, h), draw().measure, style=prefs.hotbox_style,
                                  scale=draw().ui_scale(), bounds=bounds, below=below, side=sides, title="x")
        if any(in_area(tl, region.x + (r[0] + r[2]) / 2, region.y + (r[1] + r[3]) / 2) for r, _k, _l in lay.labels):
            return h
    return 30


@step
def s_kit_press():
    ob = bpy.data.objects["pCube1"]
    C["kpress"] = place_low(ob, rmb_height())
    x, y = C["kpress"]
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
    ev('RIGHTMOUSE', 'PRESS', x=x, y=y)


@step
def s_kit_plan():
    s = draw().ACTIVE.get("session")
    check("kit: RMB on pCube1 opens the object marking menu", s is not None)
    if s is None:
        return
    tl = timeline()
    rows = [it for it in s.layout.items if it.kind == "list"]
    for it in rows:
        print("GUI-DBG row", it.label, abs_center(s, it))
    over = [it for it in rows if it.label in SAFE_ROWS + KIT_ROWS and in_area(tl, *abs_center(s, it))]
    paint = next(it for it in rows if it.label == "Paint")
    check("kit: a list row is drawn over the Time Slider", bool(over))
    if not over:
        return
    target = over[0]
    C["target"] = target.label
    p = abs_center(s, paint)
    t = abs_center(s, target)
    x, y = C["kpress"]
    # to the Paint row (opens its cascade), then on to the row over the Time Slider
    C["list"] = path((x, y), p, 8) + path(p, (p[0], t[1]), 10) + path((p[0], t[1]), t, 4)
    C["paint_seen"] = False
    print("GUI-DBG target", target.label, t, "paint", p)


def _list_mover():
    pts = C.get("list")
    if not pts:
        return
    x, y = pts.pop(0)
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
    s = draw().ACTIVE.get("session")
    if s is None:
        C.setdefault("closed_list", (x, y))
    elif len(s.stack) == 2:
        C["paint_seen"] = True
    if pts:
        _steps_insert(_list_mover)


step(_list_mover)


@step
def s_kit_on_row():
    s = draw().ACTIVE.get("session")
    check("kit: the menu stays open dragging down the list past Paint into the Time Slider",
          s is not None and "closed_list" not in C)
    check("kit: the Paint cascade opened on the way", C.get("paint_seen"))
    if s is not None:
        item = s.hover[0]
        print("GUI-DBG on_row stack", len(s.stack), "hover", item and item.label, "pos", s.pos, flush=True)
        check(f"kit: the row over the Time Slider ({C.get('target')}) is highlighted",
              item is not None and item.label == C.get("target"))
        if C.get("target") in KIT_ROWS:
            check("kit: its cascade opens over the Time Slider", len(s.stack) == 2)
        x, y = abs_center(s, item, len(s.stack) - 1) if item is not None else C["kpress"]
        C["release"] = (x, y)
        C["before"] = [o.select_get() for o in bpy.context.scene.objects]


@step
def s_kit_release():
    x, y = C.get("release", C["kpress"])
    ev('RIGHTMOUSE', 'RELEASE', x=x, y=y)


@step
def s_kit_released():
    sel = [o.select_get() for o in bpy.context.scene.objects]
    label = C.get("target")
    want = {"Select All": all(sel), "Deselect All": not any(sel), "Select": any(sel),
            "Invert Selection": sel == [not v for v in C.get("before", [])],
            }.get(label, label in KIT_ROWS and sel == C.get("before"))
    check(f"kit: release over the Time Slider runs {label} (a cascade row: nothing) and closes the menu",
          want and not draw().ACTIVE)


# --- hotbox ------------------------------------------------------------------------------------------------------------

@step
def s_hotbox_press():
    area, region = main_view()
    x, y = region.x + region.width // 2, region.y + hotbox_height()
    C["hb"] = (x, y)
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
    ev('SPACE', 'PRESS', x=x, y=y)


@step
def s_hotbox_plan():
    lay = draw().ACTIVE.get("hotbox")
    check("kit: Space hold low in the view opens the hotbox", lay is not None)
    if lay is None:
        return
    _area, region = main_view()
    tl = timeline()
    over = [(r, k, l) for r, k, l in lay.labels
            if in_area(tl, region.x + (r[0] + r[2]) / 2, region.y + (r[1] + r[3]) / 2) and k.startswith("ALLSET_MT")]
    for r, k, l in lay.labels:
        print("GUI-DBG hb", l, k, region.x + (r[0] + r[2]) / 2, region.y + (r[1] + r[3]) / 2)
    check("kit: a hotbox menu row is drawn over the Time Slider", bool(over))
    if not over:
        return
    r, key, label = over[0]
    t = (region.x + round((r[0] + r[2]) / 2), region.y + round((r[1] + r[3]) / 2))
    C["hb_key"], C["hb_label"] = key, label
    C["hbpath"] = path(C["hb"], t, 5)
    # record the menu the click opens (instead of opening a popup that would eat the next events)
    hb = import_module(MODULE + ".marking.modal").ALLSET_OT_hotbox
    hb._open_label = staticmethod(lambda k: C.__setitem__("opened", k))


step(mover("hbpath", "hb"))


@step
def s_hotbox_hover():
    check("kit: the hotbox stays open with the cursor over the Time Slider", draw().ACTIVE.get("hotbox") is not None
          and "closed_hb" not in C)
    check(f"kit: the hotbox row over the Time Slider ({C.get('hb_label')}) is highlighted",
          draw().ACTIVE.get("hover") == C.get("hb_key"))
    ev('LEFTMOUSE', 'PRESS')


@step
def s_hotbox_click():
    ev('LEFTMOUSE', 'RELEASE')


@step
def s_hotbox_menu():
    check("kit: clicking it closes the hotbox and opens that menu",
          not draw().ACTIVE.get("hotbox") and C.get("opened") == C.get("hb_key"))
    x, y = C["hb"]
    ev('SPACE', 'RELEASE', x=x, y=y)


run()
