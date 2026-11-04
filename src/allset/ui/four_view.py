# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya Four View = four real 3D View panels (Issue #148).

Blender's Quad View splits one 3D View region in four: one header, one shading / overlay set for all four panes. A
Maya model panel has its own camera, shading, Show settings and panel menu bar, so the kit's four view is four 3D
View *areas* (``screen.area_split`` three times), each with its own ``SpaceView3D``:

    top   | persp
    ------+------
    front | side

Blender's split rules (``hypershade_layout`` docstring): HORIZONTAL with
factor > 0.5 puts the new area on top, VERTICAL with factor < 0.5 on the left — so the panels' places are known
without reading rects (areas get their rects one tick after a split).

Space tap / Panels > Layouts > Single Perspective View leave the four view by joining the other three areas into the
panel under the mouse (or the persp panel) with ``screen.area_join`` (GUI only).
A panel of the four view may be any editor (Graph Editor, render view, Outliner ...), like a Maya panel: the four view
is the 2 x 2 block of areas inside the rectangle recorded on the screen (``rect``, window px), whatever their editor
types, and each role keeps its editor type across four <-> one. Outside that block a Space tap maximizes the pane.
Each panel's settings (shading, overlays, object types shown, lens / clip, camera) are kept per *role* (top / persp /
front / side) as JSON in the Screen ID property ``allset_four_view`` — saved with the file, never area pointers
(#36) — and put back when the four view comes back, like Maya's panels keep theirs. Blender Quad View is not used.
"""

import json
import math

import bpy
from mathutils import Euler, Quaternion

PROP = "allset_four_view"
ROLES = ("top", "persp", "front", "side")
# (column, row from the top) of each role in Maya's Four View
SLOTS = {"top": (0, 0), "persp": (1, 0), "front": (0, 1), "side": (1, 1)}
# Blender view rotations of Maya's ortho cameras (Maya side looks from +X = Blender Right view)
AXIS = {"top": Quaternion(), "front": Euler((math.pi / 2, 0.0, 0.0)).to_quaternion(),
        "side": Euler((math.pi / 2, 0.0, math.pi / 2)).to_quaternion()}
# Shading of a new four view, like Maya: every panel Smooth Shade All (= Blender Solid)
DEFAULT_SHADING = {"top": 'SOLID', "persp": 'SOLID', "front": 'SOLID', "side": 'SOLID'}
SPLITS = (0.5001, 0.4999)            # HORIZONTAL (new on top), VERTICAL (new on the left)

_SPACE_PROPS = ("lens", "clip_start", "clip_end")
_SKIP = {"rna_type"}


# --- the record on the screen --------------------------------------------------------------------------------------

def state(screen):
    try:
        return json.loads(screen.get(PROP) or "{}")
    except (TypeError, ValueError):
        return {}


def _save_state(screen, st):
    screen[PROP] = json.dumps(st)


def is_four(screen):
    return screen is not None and bool(block(screen))


def panes(screen):
    """The 3D View panels of ``screen`` (the Tool Box column is not a panel)."""
    from .toolbox import is_toolbox
    return [a for a in screen.areas if a.type == 'VIEW_3D' and not is_toolbox(a.spaces.active)]


def _areas(screen):
    """Every area that can be a panel: any editor but the Tool Box column."""
    from .toolbox import is_toolbox
    return [a for a in screen.areas if not (a.type == 'VIEW_3D' and is_toolbox(a.spaces.active))]


# --- the block by places (pure: anything with x / y / width / height) ---------------------------------------------

GAP = 6                              # px between neighbouring areas at UI scale 1 (border + pixel size), with room


def border_gap():
    """Px allowed between neighbouring areas: the area border grows with the UI scale (and the screen's DPI), e.g.
    3 px at scale 1 but 9 px at scale 2 — with a fixed tolerance a high-DPI four view was not found and every Space
    tap split it again (#302)."""
    try:
        scale = bpy.context.preferences.system.ui_scale
    except AttributeError:
        scale = 1.0
    return max(GAP, math.ceil(GAP * scale))


def rect(a):
    """(x0, y0, x1, y1) of an area, window px, y up."""
    return (a.x, a.y, a.x + a.width, a.y + a.height)


def union(rects):
    rects = list(rects)
    return (min(r[0] for r in rects), min(r[1] for r in rects), max(r[2] for r in rects), max(r[3] for r in rects))


def overlap(r, q):
    """Area of the intersection of two rects."""
    w = min(r[2], q[2]) - max(r[0], q[0])
    h = min(r[3], q[3]) - max(r[1], q[1])
    return w * h if w > 0 and h > 0 else 0


def _size(r):
    return max(0, r[2] - r[0]) * max(0, r[3] - r[1])


def grids(areas, gap=None):
    """Every 2 x 2 group of ``areas`` that fills a rectangle: [{role: area}] (top / persp over front / side; the
    middle edges of the two rows may differ). ``gap``: px allowed between neighbours (default: by the UI scale)."""
    tol = border_gap() if gap is None else gap

    def near(a, b):
        return abs(a - b) <= tol
    out = []
    for tl in areas:
        t = rect(tl)
        for tr in areas:
            r = rect(tr)
            if tr is tl or not (near(r[0], t[2]) and near(r[3], t[3])):
                continue
            for bl in areas:
                b = rect(bl)
                if bl is tl or bl is tr or not (near(b[0], t[0]) and near(b[3], t[1])):
                    continue
                for br in areas:
                    q = rect(br)
                    if br is tl or br is tr or br is bl:
                        continue
                    if near(q[0], b[2]) and near(q[2], r[2]) and near(q[1], b[1]) and near(q[3], r[1]):
                        out.append({"top": tl, "persp": tr, "front": bl, "side": br})
    return out


def best(candidates, recorded):
    """The candidate (a {role: area} grid, or one area) covering most of the ``recorded`` rect; None when none covers
    at least half of it (and, for one area, when less than half of the area lies inside it)."""
    if not recorded:
        return None
    want = _size(recorded)
    found, most = None, 0
    for c in candidates:
        r = union(rect(a) for a in c.values()) if isinstance(c, dict) else rect(c)
        o = overlap(r, recorded)
        if o * 2 < want or (not isinstance(c, dict) and o * 2 < _size(r)):
            continue
        if o > most:
            found, most = c, o
    return found


def block(screen):
    """{role: area} of the four view on ``screen`` (any editor types), {} when it shows no four view."""
    if screen is None:
        return {}
    st = state(screen)
    if not st.get("on"):
        return {}
    if st.get("rect"):
        return best(grids(_areas(screen)), st["rect"]) or {}
    return roles(screen, panes(screen))          # a record without a rect: four 3D View panels


def single(screen):
    """The one panel the four view was folded into (by the recorded rect), else None."""
    st = state(screen) if screen is not None else {}
    if st.get("on") or not st.get("rect"):
        return None
    return best(_areas(screen), st["rect"])


def roles(screen, areas=None):
    """{role: area} of a four view: the block on ``screen``, or ``areas`` by their places (GUI: rects)."""
    if areas is None:
        return block(screen)
    if len(areas) != 4:
        return {}
    cx = sum(a.x + a.width / 2 for a in areas) / 4
    cy = sum(a.y + a.height / 2 for a in areas) / 4
    out = {}
    for a in areas:
        col = 0 if a.x + a.width / 2 < cx else 1
        row = 0 if a.y + a.height / 2 > cy else 1           # Blender y goes up
        role = next(r for r, s in SLOTS.items() if s == (col, row))
        out.setdefault(role, a)
    return out if len(out) == 4 else {}


# --- panel settings -------------------------------------------------------------------------------------------------

def _props(struct):
    out = {}
    for p in struct.bl_rna.properties:
        if p.is_readonly or p.identifier in _SKIP or p.type in ('POINTER', 'COLLECTION'):
            continue
        v = getattr(struct, p.identifier)
        if p.type == 'ENUM' and p.is_enum_flag:
            v = sorted(v)
        elif not isinstance(v, (str, int, float, bool)):
            try:
                v = [float(x) for x in v]
            except TypeError:
                continue
        out[p.identifier] = v
    return out


def _apply_props(struct, values, first=("type",)):
    flags = {p.identifier for p in struct.bl_rna.properties if p.type == 'ENUM' and p.is_enum_flag}
    for key in (*[k for k in first if k in values], *[k for k in values if k not in first]):
        try:
            setattr(struct, key, set(values[key]) if key in flags else values[key])
        except (AttributeError, TypeError, ValueError):
            pass                     # a value this Blender / scene can't take (a studio light that went away ...)


def capture(space):
    """One panel's settings: shading, overlays, object types shown, lens / clip and the camera."""
    rv3d = space.region_3d
    view = {}
    if rv3d is not None:
        view = {"perspective": rv3d.view_perspective, "rotation": list(rv3d.view_rotation),
                "location": list(rv3d.view_location), "distance": rv3d.view_distance,
                "side": bool(rv3d.is_orthographic_side_view)}
    shown = {p.identifier: getattr(space, p.identifier) for p in space.bl_rna.properties
             if p.identifier.startswith("show_object_viewport_")}
    return {"shading": _props(space.shading), "overlay": _props(space.overlay),
            "space": {k: getattr(space, k) for k in _SPACE_PROPS}, "shown": shown, "view": view}


def capture_area(area):
    """One panel's record: its editor type, plus the 3D View settings when it is a 3D View."""
    out = {"ui_type": area.ui_type}
    if area.type == 'VIEW_3D':
        out.update(capture(area.spaces.active))
    return out


def apply(space, data):
    _apply_props(space.shading, data.get("shading", {}))
    _apply_props(space.overlay, data.get("overlay", {}), first=())
    _apply_props(space, {**data.get("space", {}), **data.get("shown", {})}, first=())
    view, rv3d = data.get("view"), space.region_3d
    if view and rv3d is not None:
        rv3d.view_perspective = view["perspective"] if view["perspective"] != 'CAMERA' else 'PERSP'
        rv3d.view_rotation = Quaternion(view["rotation"])
        rv3d.view_location = view["location"]
        rv3d.view_distance = view["distance"]
        if view["perspective"] == 'ORTHO':
            rv3d.is_orthographic_side_view = view["side"]


def default(space, role, scene):
    """A panel showing Maya's startup camera for ``role`` (persp = Maya's new-scene persp)."""
    from ..operators import units, view
    space.shading.type = DEFAULT_SHADING[role]
    rv3d = space.region_3d
    if rv3d is None:
        return
    if role == "persp":
        rv3d.view_perspective = 'PERSP'
        view.home_view(rv3d, units.maya_unit(scene))
        return
    rv3d.view_perspective = 'ORTHO'
    rv3d.view_rotation = AXIS[role]
    rv3d.view_location = (0.0, 0.0, 0.0)
    rv3d.view_distance = view.maya_ortho_distance(space, scene)
    rv3d.is_orthographic_side_view = True


# --- four <-> one ---------------------------------------------------------------------------------------------------

def _window_region(area):
    return next((r for r in area.regions if r.type == 'WINDOW'), None)


def _split(context, window, area, direction, factor):
    screen = window.screen
    before = {a.as_pointer() for a in screen.areas}
    with context.temp_override(window=window, screen=screen, area=area, region=_window_region(area)):
        try:
            if bpy.ops.screen.area_split(direction=direction, factor=factor) != {'FINISHED'}:
                return None
        except RuntimeError:         # poll failed (a maximized pane, an area too small to split)
            return None
    return next((a for a in screen.areas if a.as_pointer() not in before), None)


def _place(context, role, area, saved, window=None):
    """``area`` shows the panel of ``role``: its editor type, and for a 3D View its settings (else Maya's camera)."""
    data = saved.get(role) or {}
    want = data.get("ui_type", 'VIEW_3D')
    if area.ui_type != want:
        try:
            area.ui_type = want
        except (TypeError, ValueError):
            area.ui_type = 'VIEW_3D'
    if area.type == 'VIEW_3D':
        space = area.spaces.active
        if space.region_3d is None:
            if window is not None:
                _place_later(window.as_pointer(), area.as_pointer(), role)   # a new 3D View: region data next tick
        elif "shading" in data:
            apply(space, data)
        else:
            default(space, role, context.scene)
    area.tag_redraw()


def _place_later(win_ptr, area_ptr, role):
    from .. import live_refs

    def tick():
        window, area = live_refs.find_area(area_ptr, win_ptr)
        if window is not None and area is not None and area.type == 'VIEW_3D' \
                and area.spaces.active.region_3d is not None:
            _place(bpy.context, role, area, state(window.screen).get("panes", {}))
        return None
    bpy.app.timers.register(tick, first_interval=0.0)


def enter(context, area, window=None):
    """``area`` (one panel, any editor) becomes the four view. Returns the roles placed now ({} when it can't split: always
    in background mode, where a split-off area stays 0 x 0).

    Splits: ``area`` top / bottom, then the bottom left / right (front / side). A just-split area has no size until
    the next redraw (in the GUI too: splitting it in the same call fails), so the top part is split into
    top / persp from a timer one tick later (``_split_top_later``; pointers only, #36)."""
    window = window or context.window
    screen = window.screen
    if bpy.app.background:
        return {}
    st = state(screen)
    saved = st.get("panes", {})
    single = st.get("single", "persp")
    saved[single] = {**saved.get(single, {}), **capture_area(area)}
    whole = list(rect(area))
    top = _split(context, window, area, 'HORIZONTAL', SPLITS[0])
    if top is None:
        return {}
    bottom_left = _split(context, window, area, 'VERTICAL', SPLITS[1])
    if bottom_left is None:
        return {}
    placed = {"persp": top, "front": bottom_left, "side": area}
    st.update(on=True, panes=saved, rect=whole)
    _save_state(screen, st)
    for role, a in placed.items():
        _place(context, role, a, saved, window)
    _split_top_later(window.as_pointer(), top.as_pointer())
    return placed


def _split_top_later(win_ptr, top_ptr, tries=20):
    from .. import live_refs

    def tick():
        window, top = live_refs.find_area(top_ptr, win_ptr)
        if window is None or top is None:
            return None                                    # the window / panel went away
        if top.width < 2 or top.height < 2:
            nonlocal tries
            tries -= 1
            return 0.05 if tries > 0 else None
        left = _split(bpy.context, window, top, 'VERTICAL', SPLITS[1])
        if left is not None:
            saved = state(window.screen).get("panes", {})
            _place(bpy.context, "top", left, saved, window)
            _place(bpy.context, "persp", top, saved, window)
        return None
    bpy.app.timers.register(tick, first_interval=0.0)


def remember(screen):
    """Keep the four panels' settings on the screen (Maya's panels keep theirs across layouts)."""
    placed = roles(screen)
    if not placed:
        return {}
    st = state(screen)
    saved = st.get("panes", {})
    for role, a in placed.items():
        saved[role] = {**saved.get(role, {}), **capture_area(a)}     # a Graph Editor keeps its old 3D settings
    st["panes"] = saved
    st["rect"] = list(union(rect(a) for a in placed.values()))
    _save_state(screen, st)
    return placed


def leave(context, keep=None, window=None, role=None):
    """Back to one panel: ``keep`` (an area of the four view) or the panel of ``role`` stays. GUI only."""
    window = window or context.window
    screen = window.screen
    placed = remember(screen)
    st = state(screen)
    if not placed:
        st["on"] = False
        _save_state(screen, st)
        return None
    if keep is None or keep.as_pointer() not in {a.as_pointer() for a in placed.values()}:
        keep = placed[role or "persp"]
    keep_role = next(r for r, a in placed.items() if a == keep)
    if bpy.app.background:           # screen.area_join crashes without a UI
        return None
    keep_ptr = keep.as_pointer()
    _join_into(context, window, placed, keep_role)
    kept = next((a for a in screen.areas if a.as_pointer() == keep_ptr), None)
    st.update(on=False, single=keep_role)
    _save_state(screen, st)
    if kept is not None:
        kept.tag_redraw()
    return kept


ROWS = (("top", "persp"), ("front", "side"))


def _centre(*areas):
    x0 = min(a.x for a in areas)
    y0 = min(a.y for a in areas)
    x1 = max(a.x + a.width for a in areas)
    y1 = max(a.y + a.height for a in areas)
    return (x0 + x1) // 2, (y0 + y1) // 2


def _join(context, window, source_xy, target_xy):
    """``screen.area_join``: the area at ``source_xy`` takes over the one at ``target_xy`` (window px; same props in
    4.5 / 5.0 / 5.2)."""
    with context.temp_override(window=window, screen=window.screen):
        try:
            return bpy.ops.screen.area_join(source_xy=source_xy, target_xy=target_xy) == {'FINISHED'}
        except RuntimeError:
            return False


def _join_into(context, window, placed, keep_role):
    """The four panels back into the kept one, joined only with each other (``screen.area_close`` gave a closing
    panel to whichever neighbour shared its edge — the Outliner / Properties column took half the viewport).
    The other row first, then the kept panel takes its row mate, then the other row."""
    mine = next(r for r in ROWS if keep_role in r)
    other = next(r for r in ROWS if keep_role not in r)
    mate = next(r for r in mine if r != keep_role)
    k, m = placed[keep_role], placed[mate]
    o0, o1 = placed[other[0]], placed[other[1]]
    keep_c, mate_c = _centre(k), _centre(m)
    other_c = _centre(o0, o1)
    _join(context, window, _centre(o0), _centre(o1))
    _join(context, window, keep_c, mate_c)
    _join(context, window, keep_c, other_c)


def tap(context, area=None, window=None):
    """Maya Space tap over ``area``: in the four view the panel under the mouse (any editor) stays alone; the panel
    the four view was folded into (or any 3D View panel) becomes the four view again. Returns 'single' / 'four' when
    done, 'failed' when Blender refused the split / join, None when ``area`` is no panel of the layout (the caller
    maximizes it)."""
    window = window or context.window
    area = area or context.area
    from .toolbox import is_toolbox
    if window is None or area is None or (area.type == 'VIEW_3D' and is_toolbox(area.spaces.active)):
        return None
    screen = window.screen
    four = block(screen)
    if four:
        if area.as_pointer() not in {a.as_pointer() for a in four.values()}:
            return None
        if bpy.app.background:
            return "failed"          # screen.area_join needs the Blender window
        return "single" if leave(context, keep=area, window=window) is not None else "failed"
    one = single(screen)
    if area.type != 'VIEW_3D' and (one is None or one.as_pointer() != area.as_pointer()):
        return None
    return "four" if enter(context, area, window) else "failed"


def toggle(context, area=None, window=None):
    """Maya Space tap: four view -> the panel under the mouse alone; one panel -> the four view again."""
    window = window or context.window
    area = area or context.area
    got = tap(context, area, window)
    if got == "four":
        return block(window.screen)
    if got == "single":
        return area
    return None


def set_layout(context, window, four, area=None):
    """Panels > Layouts / Tool Box quick layouts: Four View (``four``) or Single Perspective View. A four view is
    never split again and one panel never joined again. Returns the four view's roles / the single panel, None when
    nothing could be done."""
    from .toolbox import is_toolbox
    screen = window.screen
    if area is not None and area.type == 'VIEW_3D' and is_toolbox(area.spaces.active):
        area = None
    if four:
        placed = block(screen)
        if placed:
            return placed
        target = single(screen) or area
        return (enter(context, target, window) or None) if target is not None else None
    if is_four(screen):
        kept = leave(context, window=window, role="persp")
    else:
        kept = single(screen) or area
    if kept is not None and kept.type != 'VIEW_3D':
        kept.ui_type = 'VIEW_3D'          # Maya Single Perspective View = the persp camera's panel
    return kept


def collapse_all(context):
    """Every four view back to its persp panel (switching to Blender / disabling: the user's screen as it was)."""
    if bpy.app.background:
        return 0
    n = 0
    for window in context.window_manager.windows:
        if is_four(window.screen):
            if leave(context, window=window, role="persp") is not None:
                n += 1
    return n
