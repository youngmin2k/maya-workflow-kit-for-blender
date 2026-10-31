# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya Outliner order on Blender's Outliner: startup cameras first, then every list in creation order
(#117).

Maya lists DAG nodes in creation order. The Maya Outliner shows objects unsorted
(``use_sort_alpha`` off, ui/maya_outliner.setup), so Blender builds its rows from the view layer's bases (= the
collection's link order) and then calls ``outliner_collections_children_sort`` on the top list and every child list:
a C ``qsort`` whose comparator says "equal" for all of them (only TE_CHILD_NOT_IN_COLLECTION differs; Blender
4.5 / 5.0 source, editors/space_outliner/outliner_tree.cc). ``qsort`` isn't stable: the Windows CRT short sort
(lists of 2-8, CUTOFF 8) swaps the first element with the last one, then the new first with the one before ... so a
list shows rotated left by one (persp, top, front, side, pCube1, pSphere1 -> top, front, side, pCube1,
pSphere1, persp); its quicksort (9 and more) leaves an all-equal list as it is. Only the top list is affected (child
lists draw in link order). Python can't change the sort, so the kit links the top list rotated right by one
(``base_for``) and Blender's rotation puts it back; children are linked in creation order.

Creation order = the object ID property ``allset_dag_order`` (given when the kit first sees an object, in link
order; startup cameras 0-3). Only on Windows, only while a Maya Outliner with sort off is shown, only when every
object of the view layer is in one collection, and never while a Blender modal operator runs, in edit / pose mode or in a
local view (relinking drops local-view bits). Relinking keeps each object's select / hide state and the active one.
"""

import sys

import bpy

ORDER = "allset_dag_order"
INTERVAL = 0.25
_state = {"busy": False}


def rotates_small_lists():
    """True where Blender's qsort rotates an all-equal list of 2-8 (the Windows CRT)."""
    return sys.platform == "win32"


def display_order(base, rotate=True):
    """What Blender shows for one sibling list linked as ``base`` (pure)."""
    if rotate and 2 <= len(base) <= 8:
        return list(base[1:]) + [base[0]]
    return list(base)


def base_for(desired, rotate=True):
    """The link order that Blender shows as ``desired`` (inverse of ``display_order``, pure)."""
    if rotate and 2 <= len(desired) <= 8:
        return [desired[-1]] + list(desired[:-1])
    return list(desired)


def sibling_lists(objects, key):
    """{parent or None: [children sorted by ``key``]} among ``objects`` (a parent outside them = top level)."""
    names = {o.name for o in objects}
    groups = {}
    for ob in objects:
        parent = ob.parent if ob.parent is not None and ob.parent.name in names else None
        groups.setdefault(parent.name if parent else None, []).append(ob)
    for obs in groups.values():
        obs.sort(key=key)
    return groups


def wanted_links(objects, key, rotate=True):
    """The whole link order: the top list pre-rotated, then each parent's children as they are — Blender's sort only
    rotates the top list (child lists drew in link order in the GUI, gui_step82 / gui_step211; an object's subtree
    doesn't end in an object element, so ``outliner_collections_children_sort`` leaves it). Pure but for ``.name`` /
    ``.parent``."""
    groups = sibling_lists(objects, key)
    out = base_for(groups.pop(None, []), rotate)
    for parent in sorted(groups):
        out += groups[parent]
    return out


def _maya_outliner_shown(context):
    from .maya_outliner import is_maya_outliner
    for win in context.window_manager.windows:
        for area in win.screen.areas:
            sp = area.spaces.active
            if area.type == 'OUTLINER' and is_maya_outliner(sp) and not sp.use_sort_alpha:
                return True
    return False


def _blocked(context):
    for win in context.window_manager.windows:
        # Blender's own modals (transform, box select, file browser ...); the kit's window modals stay up for long
        if any(not op.bl_idname.startswith("ALLSET_OT") for op in win.modal_operators):
            return True
        for area in win.screen.areas:
            if area.type == 'VIEW_3D' and area.spaces.active.local_view is not None:
                return True
    return False


def number_new(objects, rotate=True):
    """Give objects without ``allset_dag_order`` the next numbers in link order (Blender appends new objects, so link
    order is creation order; the rotated rows of an unsynced scene are Blender's sort, not the user's).

    A duplicate carries its original's number (Blender copies ID properties, #217): of the objects sharing a number
    the oldest ID (lowest ``session_uid``) keeps it and the others count as new — Maya puts a duplicate last among its
    siblings. Two equal numbers have no fixed order, so the sync would relink them for ever."""
    holder = {}
    for ob in objects:
        n = ob.get(ORDER)
        if n is not None and (n not in holder or ob.session_uid < holder[n].session_uid):
            holder[n] = ob
    top = max(-1, max(holder, default=-1))
    for ob in objects:
        n = ob.get(ORDER)
        if n is None or holder[n] is not ob:
            top += 1
            ob[ORDER] = top


def to_end(objects, scene):
    """Maya puts a re-parented node last among its new siblings: give ``objects`` the next numbers."""
    others = list(scene.objects)
    number_new(others)
    top = max((o.get(ORDER, -1) for o in others), default=-1)
    for ob in objects:
        top += 1
        ob[ORDER] = top


def place(scene, view_layer, moved, ref, after, reordered):
    """Maya Outliner MMB between rows: ``moved`` right before / after ``ref`` among ``ref``'s siblings (creation
    order numbers swapped among that list), then linked so it shows. ``reordered`` = outliner_drag.reordered.
    Returns False when the scene isn't one the kit orders (several collections ...)."""
    if not _orderable(scene):
        return False
    number_new(list(scene.objects), rotates_small_lists())
    sib = sibling_lists(list(scene.objects), key=lambda o: o.get(ORDER, 0))
    group = next((g for g in sib.values() if ref in g), None)
    if group is None:
        return False
    names = [o.name for o in group]
    shown = reordered(names, [o.name for o in moved], ref.name, after)
    values = sorted(o.get(ORDER, 0) for o in group)
    for name, v in zip(shown, values):
        bpy.data.objects[name][ORDER] = v
    sync(scene, view_layer)
    return True


def _orderable(scene):
    objects = list(scene.objects)
    in_scene = {scene.collection, *scene.collection.children_recursive}
    owners = [[c for c in o.users_collection if c in in_scene] for o in objects]
    return bool(objects) and len({c for cs in owners for c in cs}) == 1 and all(len(cs) == 1 for cs in owners)


def _relink(coll, order, view_layer):
    current = list(coll.objects)
    k = 0
    while k < len(order) and k < len(current) and current[k] == order[k]:
        k += 1
    tail = order[k:]
    if not tail:
        return False
    state = {o: (o.select_get(view_layer=view_layer), o.hide_get(view_layer=view_layer)) for o in tail}
    active = view_layer.objects.active
    for o in tail:
        coll.objects.unlink(o)
    for o in tail:
        coll.objects.link(o)
    for o, (sel, hid) in state.items():
        o.hide_set(hid, view_layer=view_layer)
        o.select_set(sel, view_layer=view_layer)
    if active is not None and active.name in view_layer.objects:
        view_layer.objects.active = active
    return True


def sync(scene, view_layer, rotate=None):
    """Number new objects and link them so the Maya Outliner shows Maya's order. Returns True when it relinked."""
    rotate = rotates_small_lists() if rotate is None else rotate
    objects = list(scene.objects)
    if not objects or any(o.mode != 'OBJECT' for o in objects):
        return False
    # the scene's own collections (kit sets / display layers are collections outside the scene)
    if not _orderable(scene):
        return False
    in_scene = {scene.collection, *scene.collection.children_recursive}
    coll = next(c for c in objects[0].users_collection if c in in_scene)
    if len(coll.objects) != len(objects):
        return False
    number_new(list(coll.objects), rotate)
    order = wanted_links(objects, key=lambda o: o.get(ORDER, 0), rotate=rotate)
    return _relink(coll, order, view_layer)


def _tick():
    if _state["busy"]:
        return INTERVAL
    context = bpy.context
    try:
        if not rotates_small_lists() or context.window_manager is None or not _maya_outliner_shown(context) \
                or _blocked(context):
            return INTERVAL
        # #191: the order only changes with the structure; sync walks every object (0.25 s timer)
        from .outliner import structure_version
        version = (structure_version(), context.scene.as_pointer())
        if version == _state.get("synced") or context.mode != 'OBJECT':
            return INTERVAL
        _state["busy"] = True
        sync(context.scene, context.view_layer, rotate=True)
        _state["synced"] = version
    except (AttributeError, ReferenceError, RuntimeError):
        pass
    finally:
        _state["busy"] = False
    return INTERVAL


def register():
    if not bpy.app.timers.is_registered(_tick):
        bpy.app.timers.register(_tick, first_interval=INTERVAL, persistent=True)


def unregister():
    if bpy.app.timers.is_registered(_tick):
        bpy.app.timers.unregister(_tick)
