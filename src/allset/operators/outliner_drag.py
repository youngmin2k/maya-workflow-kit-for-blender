# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya Outliner drag: parent / reorder / unparent the Maya way.

Maya : MMB-drag an item onto another = parent under it,
between two items = move there (that row's parent, that place), onto empty space = to the world; the world
transform is kept and the local values are recomputed (= P). The drag does not
change the selection.

Blender: LMB drag & drop = ``OUTLINER_OT_parent_drop`` (Blender parenting: parent inverse)
or ``OUTLINER_OT_parent_clear`` (empty space); MMB does nothing. So
- the LMB drop is redone the Maya way: a depsgraph handler sees the drop as the newest registered operator, a
  timer undoes it and applies the same parent changes with ``parenting`` (one undo step);
- MMB is ``allset.outliner_drag``, a modal that finds the rows under the press / release with
  ``outliner.item_activate`` (the only Python hit test of the C tree) and puts the selection back.

Maya: MMB-drag a camera from the Outliner into a view panel = that panel looks through the camera (each panel has its
own camera); other items dropped on a panel do nothing. The modal keeps the window's mouse events after the cursor
leaves the Outliner, so a release outside it is mapped to the 3D View under it (any window, ``ui/hs_drag.view_under``)
and that view looks through the camera (``ui/panel_menus.look_through``).
"""

import json
import math

import bpy
import gpu
from bpy.app.handlers import persistent
from gpu_extras.batch import batch_for_shader
from mathutils import Matrix

from . import parenting

DROP_OPS = ("OUTLINER_OT_parent_drop", "OUTLINER_OT_parent_clear")
DRAG_PX = 3                      # movement before an MMB press becomes a drag (x UI scale)
ROW_PX = 20                      # Outliner row height = UI_UNIT_Y (x UI scale)
EDGE = 0.25                      # top / bottom quarter of a row = between rows
COLOR = (1.0, 1.0, 1.0, 0.9)

_seen = {"op": 0}
_draw = {"handler": None, "op": None}


# --- pure helpers (tested headless) -------------------------------------------------------------------

def zone(view_y, row_h):
    """Row index and drop zone for a View2D y in an Outliner (the tree starts at y 0 and grows down):
    'BEFORE' / 'AFTER' = the top / bottom quarter (between rows), 'ON' = the middle half."""
    d = -view_y / row_h
    i = math.floor(d)
    f = d - i
    if f < EDGE:
        return i, 'BEFORE'
    if f > 1.0 - EDGE:
        return i, 'AFTER'
    return i, 'ON'


def reordered(names, moved, ref, after):
    """``names`` with ``moved`` taken out and put before / after ``ref`` (kept in their order)."""
    moved = [n for n in names if n in set(moved) and n != ref]
    rest = [n for n in names if n not in set(moved)]
    if ref not in rest or not moved:
        return list(names)
    i = rest.index(ref) + (1 if after else 0)
    return rest[:i] + moved + rest[i:]


def drop_parent(target, where):
    """New parent for a drop: onto a row = that object, between rows = that row's parent, empty = world."""
    if target is None:
        return None
    return target if where == 'ON' else target.parent


# --- parenting -----------------------------------------------------------------------------------------

def _mode():
    return parenting._mode(bpy.context)


def set_parent_blender(child, parent):
    """Blender parenting keeping the world matrix (parent inverse = the parent's world inverse)."""
    world = child.matrix_world.copy()
    child.parent = parent
    child.matrix_parent_inverse = parent.matrix_world.inverted_safe()
    child.matrix_world = world


def reparent(objects, parent, mode=None):
    """Parent ``objects`` under ``parent`` (None = world) keeping them in place. Returns (moved, skipped)."""
    mode = mode or _mode()
    if parent is None:
        return [ob for ob in objects if ob.parent is not None and parenting.unparent([ob])], []
    if mode == 'BLENDER':
        done, cycles = [], []
        for ob in objects:
            if ob is parent:
                continue
            if parenting.is_ancestor(ob, parent):
                cycles.append(ob)
                continue
            set_parent_blender(ob, parent)
            done.append(ob)
        return done, cycles
    return parenting.parent_maya(objects, parent)


def _base_state(view_layer, ob):
    try:
        return ob.select_get(view_layer=view_layer), ob.hide_get(view_layer=view_layer)
    except RuntimeError:
        return None


def displayed(names):
    """Order Blender's unsorted Outliner draws a list in: the first item goes last (with and
    without the kit: objects linked Z, Y, X list as Y, X, Z; per collection with collection rows, over the
    whole view layer base list without)."""
    return list(names[1:]) + list(names[:1])


def linked(shown):
    """Inverse of ``displayed``: the list order that draws as ``shown``."""
    return list(shown[-1:]) + list(shown[:-1])


def _relink(col, new, view_layer):
    names = [ob.name for ob in col.objects]
    if new == names:
        return False
    first = next(k for k in range(len(names)) if names[k] != new[k])
    tail = [bpy.data.objects[n] for n in new[first:]]
    state = {ob.name: _base_state(view_layer, ob) for ob in tail}
    for ob in tail:
        col.objects.unlink(ob)
    for ob in tail:
        col.objects.link(ob)
    for ob in tail:
        st = state.get(ob.name)
        if st is None:
            continue
        try:
            ob.hide_set(st[1], view_layer=view_layer)
            ob.select_set(st[0], view_layer=view_layer)
        except RuntimeError:
            pass
    return True


def reorder(view_layer, moved, ref, after, by_collection=False):
    """Draw ``moved`` right before / after ``ref`` in an unsorted Outliner by linking objects again (Blender lists
    a collection's objects in link order, see ``displayed``); selection and hide state are put back. Without
    collection rows the order is the view layer's base list (collections in turn); ``by_collection`` = the
    Outliner shows collection rows (each collection its own list). Only collections that hold ``ref`` or a moved
    object change. Returns True if a link order changed."""
    moved_names = [ob.name for ob in moved]
    cols = {c.name: c for ob in (ref, *moved) for c in ob.users_collection
            if c.library is None and c.override_library is None}
    active = view_layer.objects.active
    changed = False
    if by_collection:
        for col in ref.users_collection:
            if col.name not in cols:
                continue
            names = [ob.name for ob in col.objects]
            shown = reordered(displayed(names), moved_names, ref.name, after)
            changed |= _relink(col, linked(shown), view_layer)
    else:
        bases = [ob.name for ob in view_layer.objects if ob is not None]
        want = linked(reordered(displayed(bases), moved_names, ref.name, after))
        rank = {n: i for i, n in enumerate(want)}
        for col in cols.values():
            names = [ob.name for ob in col.objects]
            new = sorted(names, key=lambda n: (rank.get(n, len(rank)), names.index(n)))
            changed |= _relink(col, new, view_layer)
    if active is not None:
        view_layer.objects.active = active
    return changed


# --- Outliner hit test ---------------------------------------------------------------------------------

def _save_selection(context):
    vl = context.view_layer
    act = vl.objects.active
    return ([ob.name for ob in context.selected_objects], act.name if act else None, vl.active_layer_collection)


def _restore_selection(context, saved):
    names, act, alc = saved
    vl = context.view_layer
    # an object operator tags the Outliner to re-sync its highlight from the objects (Python select_set
    # doesn't): deselect through one, then select by name
    try:
        bpy.ops.object.select_all(action='DESELECT')
    except RuntimeError:
        pass
    for ob in list(context.view_layer.objects):
        if ob is not None and ob.select_get() and ob.name not in names:
            ob.select_set(False)
    for n in names:
        ob = bpy.data.objects.get(n)
        if ob is not None:
            try:
                ob.select_set(True)
            except RuntimeError:
                pass
    vl.objects.active = bpy.data.objects.get(act) if act else None
    try:
        vl.active_layer_collection = alc
    except (TypeError, ReferenceError):
        pass


def hit_ids(context):
    """IDs of the Outliner row under the mouse (window event state), [] for empty space. Selects the row
    with ``outliner.item_activate`` and puts the selection back."""
    saved = _save_selection(context)
    try:
        bpy.ops.outliner.item_activate('INVOKE_DEFAULT', extend=False, deselect_all=True)
        ids = list(getattr(context, "selected_ids", None) or [])
    finally:
        _restore_selection(context, saved)
    return ids


def _first_object(ids):
    for i in ids:
        if isinstance(i, bpy.types.Object):
            return i
    return None


# --- MMB drag ------------------------------------------------------------------------------------------

def _inside(region, event):
    """True when the event's window position lies in ``region``."""
    x, y = event.mouse_x - region.x, event.mouse_y - region.y
    return 0 <= x < region.width and 0 <= y < region.height


def _rect(x0, y0, x1, y1, width=2.0):
    sh = gpu.shader.from_builtin('UNIFORM_COLOR')
    gpu.state.blend_set('ALPHA')
    gpu.state.line_width_set(width)
    batch = batch_for_shader(sh, 'LINE_LOOP', {"pos": ((x0, y0), (x1, y0), (x1, y1), (x0, y1))})
    sh.uniform_float("color", COLOR)
    batch.draw(sh)
    gpu.state.line_width_set(1.0)
    gpu.state.blend_set('NONE')


def _draw_drop():
    op = _draw["op"]
    region = bpy.context.region
    try:
        if op is None or not op.dragging or op.outside or region is None or region.as_pointer() != op.region_ptr:
            return
    except ReferenceError:
        return
    i, where = op.zone
    h = op.row_h
    _x, top = region.view2d.view_to_region(0, -i * h, clip=False)
    w = region.width
    if where == 'ON':
        _rect(2, top - h + 1, w - 3, top - 1)
    else:
        y = top if where == 'BEFORE' else top - h
        _rect(2, y - 1, w - 3, y + 1, width=1.0)


def _add_draw():
    if _draw["handler"] is None:
        _draw["handler"] = bpy.types.SpaceOutliner.draw_handler_add(_draw_drop, (), 'WINDOW', 'POST_PIXEL')


def remove_draw():
    if _draw["handler"] is not None:
        bpy.types.SpaceOutliner.draw_handler_remove(_draw["handler"], 'WINDOW')
        _draw["handler"] = None
    _draw["op"] = None


class ALLSET_OT_outliner_drag(bpy.types.Operator):
    """Maya Outliner middle-drag: drop onto an item = parent under it, between items = move there,
    onto empty space = to the world (kept in place)"""
    bl_idname = "allset.outliner_drag"
    bl_label = "Outliner Drag"
    bl_options = {'REGISTER', 'UNDO', 'INTERNAL'}

    @classmethod
    def poll(cls, context):
        sp, r = context.space_data, context.region
        return (context.mode == 'OBJECT' and sp is not None and sp.type == 'OUTLINER'
                and r is not None and r.type == 'WINDOW')

    def invoke(self, context, event):
        selected = {ob.name for ob in context.selected_objects}
        ob = _first_object(hit_ids(context))
        if ob is None:
            return {'PASS_THROUGH'}
        self.dragged = sorted(selected) if ob.name in selected else [ob.name]
        self.pressed = ob.name
        self.start = (event.mouse_region_x, event.mouse_region_y)
        self.scale = context.preferences.system.ui_scale or 1.0
        self.row_h = ROW_PX * self.scale
        self.region_ptr = context.region.as_pointer()
        self.dragging = False
        self.outside = False
        self.zone = (0, 'ON')
        _draw["op"] = self
        _add_draw()
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def _update(self, context, event):
        x, y = event.mouse_region_x, event.mouse_region_y
        if not self.dragging and math.hypot(x - self.start[0], y - self.start[1]) >= DRAG_PX * self.scale:
            self.dragging = True
        self.outside = not _inside(context.region, event)
        if self.dragging:
            _vx, vy = context.region.view2d.region_to_view(x, y)
            self.zone = zone(vy, self.row_h)
        context.region.tag_redraw()

    def _end(self, context):
        _draw["op"] = None
        context.region.tag_redraw()

    def modal(self, context, event):
        if event.type == 'MOUSEMOVE':
            self._update(context, event)
            return {'RUNNING_MODAL'}
        if event.type in {'ESC', 'RIGHTMOUSE'} and event.value == 'PRESS':
            self._end(context)
            return {'CANCELLED'}
        if event.type == 'MIDDLEMOUSE' and event.value == 'RELEASE':
            self._update(context, event)
            self._end(context)
            if not self.dragging:
                return {'CANCELLED'}
            if not _inside(context.region, event):
                return self.drop_on_view(context, event)
            return self.drop(context, _first_object(hit_ids(context)))
        return {'RUNNING_MODAL'}

    def drop_on_view(self, context, event):
        """Release outside the Outliner: a camera dropped on a 3D View = that view looks through it."""
        ob = bpy.data.objects.get(self.pressed)
        if ob is None or ob.type != 'CAMERA' or context.window is None:
            return {'CANCELLED'}
        from ..ui import hs_drag
        win = context.window
        found = hs_drag.view_under(hs_drag.screen_point((win.x, win.y), (event.mouse_x, event.mouse_y)),
                                   win.as_pointer())
        if found is None:
            return {'CANCELLED'}
        _win, area, _region, _xy = found
        from ..ui import panel_menus
        panel_menus.look_through(context, area, ob)
        area.tag_redraw()
        return {'FINISHED'}

    def drop(self, context, target):
        where = self.zone[1]
        objects = [bpy.data.objects[n] for n in self.dragged if n in bpy.data.objects]
        if target is not None and target.name in self.dragged and where == 'ON':
            return {'CANCELLED'}
        parent = drop_parent(target, where)
        context.view_layer.update()
        movers = [ob for ob in objects if ob is not target]
        changed = [ob for ob in movers if ob.parent is not parent]
        done, cycles = reparent(changed, parent)
        if cycles:
            self.report({'WARNING'}, "Skipped (the drop target is their descendant): "
                        + ", ".join(ob.name for ob in cycles))
        from ..ui import outliner_order
        if done and not context.space_data.use_filter_collection:
            outliner_order.to_end(done, context.scene)      # Maya: last among the new siblings
        ordered = False
        if target is not None and where != 'ON' and not context.space_data.use_sort_alpha:
            keep = [ob for ob in movers if ob not in cycles]
            # the Maya Outliner's order = creation order numbers (ui/outliner_order.py)
            ordered = not context.space_data.use_filter_collection and outliner_order.place(
                context.scene, context.view_layer, keep, target, where == 'AFTER', reordered)
            if not ordered:
                ordered = reorder(context.view_layer, keep, target, where == 'AFTER',
                                  by_collection=context.space_data.use_filter_collection)
        return {'FINISHED'} if done or ordered else {'CANCELLED'}


# --- LMB drop (Blender's drag) redone the Maya way ----------------------------------------------------

def _parents():
    return {ob.name: (ob.parent.name if ob.parent else None, ob.parent_type)
            for ob in bpy.data.objects if ob.library is None}


class ALLSET_OT_outliner_reparent(bpy.types.Operator):
    """Parent / unparent objects keeping them in place (an Outliner drop redone the Maya way)"""
    bl_idname = "allset.outliner_reparent"
    bl_label = "Parent"
    bl_options = {'REGISTER', 'UNDO', 'INTERNAL'}

    changes: bpy.props.StringProperty(options={'SKIP_SAVE'})     # JSON {child: parent or null}
    select: bpy.props.StringProperty(options={'SKIP_SAVE'})      # JSON [names] selected afterwards
    active: bpy.props.StringProperty(options={'SKIP_SAVE'})

    def execute(self, context):
        changes = json.loads(self.changes or "{}")
        context.view_layer.update()
        groups = {}
        for child, parent in changes.items():
            groups.setdefault(parent, []).append(child)
        from ..ui import outliner_order
        for parent, children in groups.items():
            obs = [bpy.data.objects[n] for n in children if n in bpy.data.objects]
            moved, _skipped = reparent(obs, bpy.data.objects.get(parent) if parent else None, mode='MAYA')
            outliner_order.to_end(moved, context.scene)      # Maya: last among the new siblings
        if self.select:
            _restore_selection(context, (json.loads(self.select), self.active or None,
                                         context.view_layer.active_layer_collection))
        return {'FINISHED'}


def _fix_in_place(context):
    for ob in context.selected_objects:
        if ob.parent is not None and ob.parent_type == 'OBJECT' and ob.matrix_parent_inverse != Matrix.Identity(4):
            parenting.set_parent_maya(ob, ob.parent)


def convert_drop():
    """Timer: undo the Outliner drop and apply its parent changes the Maya way (one undo step)."""
    ctx = bpy.context
    wm = ctx.window_manager
    win = next(iter(wm.windows), None)
    if win is None:
        return None
    with ctx.temp_override(window=win):
        if bpy.context.mode != 'OBJECT':
            return None
        post = _parents()
        sel = [ob.name for ob in bpy.context.selected_objects]
        act = bpy.context.view_layer.objects.active
        act = act.name if act else ""
        try:
            undone = bpy.ops.ed.undo() == {'FINISHED'}
        except RuntimeError:
            undone = False
        if not undone:
            _fix_in_place(bpy.context)
            return None
        pre = _parents()
        changes = {n: post[n][0] for n in post if n in pre and pre[n] != post[n]}
        if not changes or any(post[n][1] != 'OBJECT' for n in changes if post[n][0]):
            bpy.ops.ed.redo()          # nothing to redo the Maya way (e.g. a bone parent): keep Blender's drop
            return None
        bpy.ops.allset.outliner_reparent('EXEC_DEFAULT', True, changes=json.dumps(changes),
                                           select=json.dumps(sel), active=act)
    return None


def _last_op():
    ops = bpy.context.window_manager.operators
    return ops[-1] if len(ops) else None


@persistent
def _on_depsgraph(_scene, _depsgraph):
    op = _last_op()
    if op is None:
        return
    p = op.as_pointer()
    if p == _seen["op"]:
        return
    _seen["op"] = p
    if op.bl_idname in DROP_OPS and _mode() == 'MAYA':
        bpy.app.timers.register(convert_drop, first_interval=0.0)


def register_handlers():
    op = _last_op()
    _seen["op"] = op.as_pointer() if op is not None else 0
    if _on_depsgraph not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(_on_depsgraph)


def unregister_handlers():
    if _on_depsgraph in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(_on_depsgraph)
    if bpy.app.timers.is_registered(convert_drop):
        bpy.app.timers.unregister(convert_drop)
    remove_draw()


classes = (ALLSET_OT_outliner_drag, ALLSET_OT_outliner_reparent)
