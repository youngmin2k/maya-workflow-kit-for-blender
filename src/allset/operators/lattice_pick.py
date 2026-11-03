# SPDX-License-Identifier: GPL-3.0-or-later
"""Lattice points picked where they are drawn (#274).

In lattice edit mode Blender draws the points where the lattice's own deformers (a Bend, a Twist ...) put them, but
its click and box selection test the undeformed points, so a point can't be picked where the user sees it. Maya picks
a lattice point where it is drawn.

The kit takes over only while a lattice in edit mode is drawn deformed (its evaluated points differ from its own);
otherwise Blender's selection runs untouched.

* Click: ``allset.select_priority`` (first in the viewport click items) calls ``click``: the nearest drawn point within
  Blender's click distance, with Maya's modifiers (plain replaces — nothing hit clears —, Shift toggles, Ctrl removes,
  Ctrl+Shift adds).
* Box: ``allset.select_through`` (first in the select tools' drag items) hands the drag to ``allset.lattice_box``,
  which draws the marquee and applies it to the drawn points with Maya's modifiers: one undo step.
* Lasso tool: ``begin_box`` remembers the selection, Blender's lasso runs, and once it ended the remembered selection
  comes back and the lasso it registered is applied to the drawn points (same watcher as the kit's joint marquee).
"""

import bpy
import gpu
import numpy as np
from bpy.props import BoolProperty, IntProperty
from gpu_extras.batch import batch_for_shader

from .. import live_refs
from .preselect import project

CLICK_PX = 75.0       # Blender's click distance for lattice points (px at pixel size 1)
EPS = 1e-6
_TICK = 0.05
_GIVE_UP = 1.5
_pending = []


# --- pure helpers (tests/test_issue274_lattice_pick.py) -----------------------------------------------------------

def nearest(screen, front, mouse, radius):
    """Index of the in-front point of ``screen`` (N x 2) nearest to ``mouse`` within ``radius``, else None."""
    screen = np.asarray(screen, dtype=np.float64).reshape(-1, 2)
    if not len(screen):
        return None
    d = np.hypot(screen[:, 0] - mouse[0], screen[:, 1] - mouse[1])
    d = np.where(np.asarray(front, dtype=bool), d, np.inf)
    i = int(np.argmin(d))
    return i if d[i] <= radius else None


def inside(screen, front, poly):
    """Mask of in-front points of ``screen`` inside the polygon ``poly`` (a box is its 4 corners; even-odd rule,
    points on a box edge count as inside)."""
    screen = np.asarray(screen, dtype=np.float64).reshape(-1, 2)
    front = np.asarray(front, dtype=bool)
    poly = np.asarray(poly, dtype=np.float64).reshape(-1, 2)
    if len(poly) < 3 or not len(screen):
        return np.zeros(len(screen), dtype=bool)
    x, y = screen[:, 0], screen[:, 1]
    lo, hi = poly.min(axis=0), poly.max(axis=0)
    box = len(poly) == 4 and len(set(np.round(poly[:, 0], 6))) == 2 and len(set(np.round(poly[:, 1], 6))) == 2
    if box:
        return front & (x >= lo[0]) & (x <= hi[0]) & (y >= lo[1]) & (y <= hi[1])
    hit = np.zeros(len(screen), dtype=bool)
    for (x0, y0), (x1, y1) in zip(poly, np.roll(poly, -1, axis=0)):
        crosses = (y0 > y) != (y1 > y)
        with np.errstate(divide='ignore', invalid='ignore'):
            xs = x0 + (y - y0) * (x1 - x0) / (y1 - y0)
        hit ^= crosses & (x < xs)
    return front & hit


def combine(before, hits, mode):
    """New selection mask from ``before`` and ``hits`` for a select mode: SET, ADD, SUB, XOR or AND."""
    before, hits = np.asarray(before, dtype=bool), np.asarray(hits, dtype=bool)
    if mode == 'ADD':
        return before | hits
    if mode == 'SUB':
        return before & ~hits
    if mode == 'XOR':
        return before ^ hits
    if mode == 'AND':
        return before & hits
    return hits.copy()


def click_mode(shift, ctrl):
    """Maya click modifiers as a select mode: plain replaces, Shift toggles, Ctrl removes, Ctrl+Shift adds."""
    return {(True, False): 'XOR', (False, True): 'SUB', (True, True): 'ADD'}.get((bool(shift), bool(ctrl)), 'SET')


# --- scene -----------------------------------------------------------------------------------------------------------

def lattices(context):
    """Lattices in edit mode in this view, each as (object, drawn world points N x 3, own world points N x 3)."""
    obs = [ob for ob in getattr(context, "objects_in_mode", None) or () if ob.type == 'LATTICE']
    if not obs:
        return []
    depsgraph = context.evaluated_depsgraph_get()
    out = []
    for ob in obs:
        n = len(ob.data.points)
        own = np.empty(n * 3)
        ob.data.points.foreach_get("co_deform", own)
        ev = ob.evaluated_get(depsgraph)
        drawn = np.empty(n * 3)
        if len(ev.data.points) == n:
            ev.data.points.foreach_get("co_deform", drawn)
        else:
            drawn[:] = own
        m = np.asarray(ob.matrix_world, dtype=np.float64)
        to_world = (lambda p: p.reshape(-1, 3) @ m[:3, :3].T + m[:3, 3])
        out.append((ob, to_world(drawn), to_world(own)))
    return out


def deformed(found):
    """Some lattice of ``lattices(...)`` is drawn away from its own points."""
    return any(len(d) and float(np.abs(d - o).max()) > EPS for _ob, d, o in found)


def _view(context):
    space, region, rv3d = context.space_data, context.region, context.region_data
    if (context.mode != 'EDIT_LATTICE' or space is None or space.type != 'VIEW_3D' or region is None
            or region.type != 'WINDOW' or rv3d is None):
        return None
    return region, rv3d


def _selection(ob):
    sel = np.zeros(len(ob.data.points), dtype=bool)
    ob.data.points.foreach_get("select", sel)
    return sel


def _write(ob, sel):
    ob.data.points.foreach_set("select", np.asarray(sel, dtype=bool))
    ob.data.update_tag()


def _screen(context, found):
    region, rv3d = _view(context)
    persp = np.asarray(rv3d.perspective_matrix, dtype=np.float64)
    return [project(drawn, persp, region.width, region.height) for _ob, drawn, _own in found]


def click(context, event):
    """Pick the drawn lattice point under a click. False when the kit doesn't take this click."""
    if _view(context) is None:
        return False
    found = lattices(context)
    if not deformed(found):
        return False
    mouse = (event.mouse_region_x, event.mouse_region_y)
    radius = CLICK_PX * (context.preferences.system.pixel_size or 1.0)
    best = None
    for k, (xy, front) in enumerate(_screen(context, found)):
        i = nearest(xy, front, mouse, radius)
        if i is not None:
            d = float(np.hypot(*(xy[i] - mouse)))
            if best is None or d < best[0]:
                best = (d, k, i)
    mode = click_mode(event.shift, event.ctrl)
    for k, (ob, _d, _o) in enumerate(found):
        hits = np.zeros(len(ob.data.points), dtype=bool)
        if best is not None and best[1] == k:
            hits[best[2]] = True
        _write(ob, combine(_selection(ob), hits, mode))
    for area in context.screen.areas if context.screen else ():
        area.tag_redraw()
    return True


def apply_region(context, poly, mode, snap):
    """Put the remembered selection ``snap`` (object name -> mask) back and apply the drag region ``poly`` (region
    px) to the drawn points with ``mode``. False when no lattice is drawn deformed."""
    found = lattices(context)
    if _view(context) is None or not deformed(found):
        return False
    for (ob, _d, _o), (xy, front) in zip(found, _screen(context, found)):
        before = snap.get(ob.name)
        if before is None or len(before) != len(ob.data.points):
            before = _selection(ob)
        _write(ob, combine(before, inside(xy, front, poly), mode))
    return True


def box_takes(context):
    """The kit draws this drag's marquee itself: a deformed lattice in edit mode, and the tool is not the Lasso."""
    if _view(context) is None or not deformed(lattices(context)):
        return False
    try:
        tool = context.workspace.tools.from_space_view3d_mode(context.mode, create=False)
    except (AttributeError, RuntimeError):
        tool = None
    return tool is None or tool.idname != "builtin.select_lasso"


def start_box(context, event):
    """Start ``allset.lattice_box`` from the drag that ``event`` (a LMB CLICK_DRAG) began."""
    x = getattr(event, "mouse_prev_press_x", event.mouse_x) - context.region.x
    y = getattr(event, "mouse_prev_press_y", event.mouse_y) - context.region.y
    bpy.ops.allset.lattice_box('INVOKE_DEFAULT', x=x, y=y, shift=event.shift, ctrl=event.ctrl)


class ALLSET_OT_lattice_box(bpy.types.Operator):
    """Marquee on lattice points where they are drawn (Shift toggles, Ctrl removes, Ctrl+Shift adds)"""
    bl_idname = "allset.lattice_box"
    bl_label = "Box Select"
    bl_options = {'INTERNAL'}

    x: IntProperty(options={'HIDDEN', 'SKIP_SAVE'})
    y: IntProperty(options={'HIDDEN', 'SKIP_SAVE'})
    shift: BoolProperty(options={'HIDDEN', 'SKIP_SAVE'})
    ctrl: BoolProperty(options={'HIDDEN', 'SKIP_SAVE'})

    def invoke(self, context, event):
        if _view(context) is None:
            return {'CANCELLED'}
        self._start = (self.x, self.y)
        self._end = (event.mouse_region_x, event.mouse_region_y)
        self._region = context.region
        self._handle = context.space_data.draw_handler_add(self._draw, (), 'WINDOW', 'POST_PIXEL')
        context.window_manager.modal_handler_add(self)
        self._region.tag_redraw()
        return {'RUNNING_MODAL'}

    def _draw(self):
        if bpy.context.region != self._region:
            return
        (x0, y0), (x1, y1) = self._start, self._end
        shader = gpu.shader.from_builtin('UNIFORM_COLOR')
        loop = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
        gpu.state.blend_set('ALPHA')
        for width, color in ((3.0, (0.0, 0.0, 0.0, 0.6)), (1.0, (1.0, 1.0, 1.0, 0.9))):
            gpu.state.line_width_set(width)
            shader.uniform_float("color", color)
            batch_for_shader(shader, 'LINE_LOOP', {"pos": loop}).draw(shader)
        gpu.state.line_width_set(1.0)
        gpu.state.blend_set('NONE')

    def _stop(self, context):
        context.space_data.draw_handler_remove(self._handle, 'WINDOW')
        self._region.tag_redraw()

    def modal(self, context, event):
        if event.type in {'MOUSEMOVE', 'INBETWEEN_MOUSEMOVE'}:
            self._end = (event.mouse_region_x, event.mouse_region_y)
            self._region.tag_redraw()
            return {'RUNNING_MODAL'}
        if event.type in {'ESC', 'RIGHTMOUSE'} and event.value == 'PRESS':
            self._stop(context)
            return {'CANCELLED'}
        if event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
            self._end = (event.mouse_region_x, event.mouse_region_y)
            self._stop(context)
            (x0, y0), (x1, y1) = self._start, self._end
            poly = [(min(x0, x1), min(y0, y1)), (max(x0, x1), min(y0, y1)),
                    (max(x0, x1), max(y0, y1)), (min(x0, x1), max(y0, y1))]
            with context.temp_override(region=self._region):
                if apply_region(context, poly, click_mode(self.shift, self.ctrl), {}):
                    bpy.ops.ed.undo_push(message="Box Select")
            for area in context.screen.areas if context.screen else ():
                area.tag_redraw()
            return {'FINISHED'}
        return {'RUNNING_MODAL'}


classes = (ALLSET_OT_lattice_box,)


def begin_box(context):
    """Remember the lattice selection before Blender's box / lasso; fix the result once it ended."""
    if _view(context) is None:
        return False
    found = lattices(context)
    if not deformed(found):
        return False
    wm = context.window_manager
    _pending.append({
        "window": live_refs.pointer(context.window), "area": context.area.as_pointer(),
        "region": context.region.as_pointer(),
        "last": wm.operators[-1].as_pointer() if len(wm.operators) else 0,
        "snap": {ob.name: _selection(ob) for ob, _d, _o in found},
        "seen": False, "waited": 0.0, "box": None,
    })
    if not bpy.app.timers.is_registered(_watch):
        bpy.app.timers.register(_watch, first_interval=_TICK)
    return True


def _finish(entry):
    from . import joint_marquee, undo_pairs
    window = live_refs.window(entry["window"])
    if window is None:
        return
    op = joint_marquee._registered(entry)
    if op is not None:
        poly, mode = joint_marquee.region_of(op), op.properties.mode
    elif entry["box"] is not None:
        poly, mode = entry["box"]
    else:
        return
    if poly is None:
        return
    area = next((a for a in window.screen.areas if a.as_pointer() == entry["area"]), None)
    region = next((r for r in area.regions if r.as_pointer() == entry["region"]), None) if area else None
    if region is None:
        return
    with bpy.context.temp_override(window=window, area=area, region=region):
        if apply_region(bpy.context, poly, mode, entry["snap"]):
            if op is not None:
                undo_pairs.push(bpy.context.scene, "Select")      # one undo with Blender's box select step
            else:
                bpy.ops.ed.undo_push(message="Select")
            for a in window.screen.areas:
                a.tag_redraw()


def _watch():
    from . import joint_marquee
    for entry in list(_pending):
        running = joint_marquee._running(entry)
        entry["seen"] = entry["seen"] or running
        entry["waited"] += _TICK
        if entry["seen"] and not running:
            _pending.remove(entry)
            try:
                _finish(entry)
            except (ReferenceError, RuntimeError, AttributeError, KeyError) as e:
                print("allset: lattice marquee:", e)
        elif not entry["seen"] and entry["waited"] >= _GIVE_UP:
            _pending.remove(entry)
    return _TICK if _pending else None


def cancel_all():
    _pending.clear()
    if bpy.app.timers.is_registered(_watch):
        bpy.app.timers.unregister(_watch)
