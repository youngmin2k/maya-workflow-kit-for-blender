# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya Visualize > Create Animation Snapshot / Update Snapshot.

Maya rules (Maya 2022):
- Visualize > Create Animation Snapshot with the factory options: Time range Start/End 1 – 10, Increment 1,
  Update "Fast (update only when keyframes change)".
- Result: a top-level group ``snapshot<N>Group`` with one child per sampled frame, ``transform<N>_<k>`` /
  ``transform<N>_Shape<k>`` (k = 1 ..), meshes in **world space** under identity transforms (a child of an animated
  group lands where it was in the world). Frames = start, start + increment, ... up to end (1 – 10 by 3 = 1, 4, 7, 10).
- One group per selected geometry; a selected group snapshots the geometry under it. Nothing with geometry selected
  = error "No geometry found to create snapshot." (a locator, an empty selection).
- The current time and the selection don't change. Deleting the source keeps the copies.
- Update: the snapshot follows key edits on its own (Fast) or every change (Slow); a non-animated edit (scale typed
  in) shows only after Visualize > Update Snapshot, which works with the group, a copy or the
  source selected and warns "Select motion trails or snapshots to update." with nothing relevant selected.

Kit: the copies are ordinary mesh objects (Blender has no snapshot node); the group Empty keeps the record (ID
properties: the source object pointer, range, increment, update style). Copies are made by sampling the evaluated
object at each frame (``scene.frame_set`` loop, the current frame restored). The kit's smooth-preview modifiers are
left out like Maya's worldMesh (display only). Fast / Slow updates rebuild from a timer after a
depsgraph update that touches the source's Action (Fast) or the source itself (Slow); Modify > Evaluate Nodes >
Snapshots off stops them (``Scene.allset_eval.snapshot``, Maya Modify > Evaluate Nodes > Snapshots).
"""

import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty
from bpy.app.handlers import persistent

from .. import results
from .. import undo_steps

GEOMETRY = {'MESH', 'CURVE', 'SURFACE', 'FONT', 'META'}
RECORD = "allset_snapshot"             # group Empty ID prop: {"start", "end", "increment", "update"}
SOURCE = "allset_snapshot_source"      # group Empty ID prop: the source object (ID pointer)
NO_GEOMETRY = "No geometry found to create snapshot."           #
NOTHING_TO_UPDATE = "Select motion trails or snapshots to update."  #
UPDATE_STYLES = ("demand", "animCurve", "force")                 # Maya -update values (On demand / Fast / Slow)
FACTORY = {"time_slider": False, "start": 1.0, "end": 10.0, "increment": 1.0, "update": "animCurve"}
EPS = 1e-6

_busy = []          # a rebuild is sampling frames: ignore its own depsgraph updates / frame changes
_pending = set()    # session_uid of snapshot groups waiting for a rebuild


# --- pure rules ---------------------------------------------------------------------------------------------------

def sample_frames(start, end, increment):
    """Maya's snapshot frames: start, start + increment, ... while <= end."""
    if increment <= 0:
        increment = 1.0
    out, i = [], 0
    while True:
        f = start + i * increment
        if f > end + EPS:
            break
        out.append(round(f, 6))
        i += 1
    return out


def next_number(names):
    """Lowest N >= 1 with neither ``snapshot<N>Group`` nor ``transform<N>_1`` taken."""
    n = 1
    while f"snapshot{n}Group" in names or f"transform{n}_1" in names:
        n += 1
    return n


# --- sampling -----------------------------------------------------------------------------------------------------

def geometry_of(objects):
    """The geometry objects a snapshot is made of: selected geometry, or the geometry under a selected group."""
    out, seen = [], set()

    def add(ob):
        if ob.session_uid not in seen and ob.type in GEOMETRY and not is_snapshot_part(ob):
            seen.add(ob.session_uid)
            out.append(ob)
    for ob in objects:
        if ob.type in GEOMETRY:
            add(ob)
        else:
            for child in ob.children_recursive:
                add(child)
    return out


def is_snapshot_part(ob):
    return RECORD in ob or (ob.parent is not None and RECORD in ob.parent)


class _NoPreview:
    """Turn the kit's smooth-preview modifiers off while sampling (Maya's worldMesh is the base mesh)."""

    def __init__(self, objects):
        from .display import is_preview
        self.mods = [m for ob in objects for m in getattr(ob, "modifiers", ()) if is_preview(m) and m.show_viewport]

    def __enter__(self):
        for m in self.mods:
            m.show_viewport = False

    def __exit__(self, *exc):
        for m in self.mods:
            m.show_viewport = True


def sample(context, sources, frames):
    """{source session_uid: [world-space Mesh per frame]} — new mesh datablocks; the current frame comes back."""
    scene = context.scene
    keep = (scene.frame_current, scene.frame_subframe)
    out = {ob.session_uid: [] for ob in sources}
    _busy.append(True)
    try:
        with _NoPreview(sources):
            for f in frames:
                whole = int(f // 1)
                scene.frame_set(whole, subframe=f - whole)
                dg = context.evaluated_depsgraph_get()
                for ob in sources:
                    ev = ob.evaluated_get(dg)
                    me = bpy.data.meshes.new_from_object(ev, preserve_all_data_layers=True, depsgraph=dg)
                    mw = ev.matrix_world.copy()
                    me.transform(mw)
                    if mw.determinant() < 0:
                        me.flip_normals()
                    out[ob.session_uid].append(me)
    finally:
        scene.frame_set(keep[0], subframe=keep[1])
        _busy.pop()
    return out


# --- create / update ----------------------------------------------------------------------------------------------

def _record(grp):
    rec = dict(FACTORY)
    raw = grp.get(RECORD)
    if raw is not None:
        rec.update({k: raw[k] for k in raw.keys()})
    return rec


def create(context, objects, start, end, increment, update="animCurve"):
    """Make one snapshot group per geometry object. Returns the groups, or raises ValueError(NO_GEOMETRY)."""
    from . import naming
    sources = geometry_of(objects)
    if not sources:
        raise ValueError(NO_GEOMETRY)
    frames = sample_frames(start, end, increment)
    meshes = sample(context, sources, frames)
    groups = []
    for ob in sources:
        names = {o.name for o in bpy.data.objects}
        n = next_number(names)
        naming.drop_orphans(bpy.data.meshes, f"transform{n}_Shape")
        collection = ob.users_collection[0] if ob.users_collection else context.collection
        grp = bpy.data.objects.new(f"snapshot{n}Group", None)
        grp.empty_display_type = 'PLAIN_AXES'
        grp.empty_display_size = 0.0          # Maya draws nothing for the group transform
        collection.objects.link(grp)
        grp[RECORD] = {"start": float(start), "end": float(end), "increment": float(increment), "update": update}
        grp[SOURCE] = ob
        for k, me in enumerate(meshes[ob.session_uid], 1):
            me.name = f"transform{n}_Shape{k}"
            copy = bpy.data.objects.new(f"transform{n}_{k}", me)
            collection.objects.link(copy)
            copy.parent = grp
        groups.append(grp)
    _dirty()
    return groups


def copies_of(grp):
    """The group's copies in frame order (``transform<N>_<k>`` by k)."""
    def key(ob):
        tail = ob.name.rsplit("_", 1)[-1]
        return int(tail) if tail.isdigit() else 1 << 30
    return sorted(grp.children, key=key)


def rebuild(context, grp):
    """Sample the source again over the recorded range and swap every copy's mesh (Maya Update Snapshot). Returns
    False when the source is gone."""
    src = grp.get(SOURCE)
    if src is None or src.name not in context.scene.objects:
        return False
    rec = _record(grp)
    frames = sample_frames(rec["start"], rec["end"], rec["increment"])
    meshes = sample(context, [src], frames)[src.session_uid]
    copies = copies_of(grp)
    n = grp.name[len("snapshot"):-len("Group")] if grp.name.startswith("snapshot") and grp.name.endswith("Group") else "1"
    collection = grp.users_collection[0] if grp.users_collection else context.collection
    for k, me in enumerate(meshes, 1):
        if k <= len(copies):
            ob = copies[k - 1]
            old = ob.data
            ob.data = me
            name = old.name
            if old.users == 0:
                bpy.data.meshes.remove(old)
            me.name = name
        else:
            me.name = f"transform{n}_Shape{k}"
            ob = bpy.data.objects.new(f"transform{n}_{k}", me)
            collection.objects.link(ob)
            ob.parent = grp
    for ob in copies[len(meshes):]:
        old = ob.data
        bpy.data.objects.remove(ob)
        if old is not None and old.users == 0:
            bpy.data.meshes.remove(old)
    return True


def groups_for(objects):
    """Snapshot groups named by a selection: the groups, the groups of selected copies, snapshots of a source."""
    out, seen = [], set()

    def add(grp):
        if grp.session_uid not in seen:
            seen.add(grp.session_uid)
            out.append(grp)
    sel = {ob.session_uid for ob in objects}
    for ob in objects:
        if RECORD in ob:
            add(ob)
        elif ob.parent is not None and RECORD in ob.parent:
            add(ob.parent)
    for grp in all_groups():
        src = grp.get(SOURCE)
        if src is not None and src.session_uid in sel:
            add(grp)
    return out


def all_groups():
    return [ob for ob in bpy.data.objects if RECORD in ob]


# --- automatic updates (Fast / Slow) ------------------------------------------------------------------------------

_watch = {}          # source session_uid -> [(group session_uid, update style)]
_watch_dirty = [True]


@persistent
def _dirty(*_args):
    _watch_dirty[0] = True


def _watched():
    if _watch_dirty[0]:
        _watch.clear()
        for grp in all_groups():
            src = grp.get(SOURCE)
            if src is not None:
                _watch.setdefault(src.session_uid, []).append((grp.session_uid, _record(grp)["update"]))
        _watch_dirty[0] = False
    return _watch


def evaluating(scene):
    """Modify > Evaluate Nodes > Snapshots; on when the switch doesn't exist."""
    ev = getattr(scene, "allset_eval", None)
    return getattr(ev, "snapshot", True) if ev is not None else True


@persistent
def _on_depsgraph(scene, depsgraph):
    if _busy or not _watched() or not evaluating(scene):
        return
    actions = set()
    touched = set()
    for update in depsgraph.updates:
        idb = update.id
        if isinstance(idb, bpy.types.Action):
            actions.add(idb.original.session_uid)
        elif isinstance(idb, bpy.types.Object) and (update.is_updated_transform or update.is_updated_geometry):
            touched.add(idb.original.session_uid)
    if not actions and not touched:
        return
    by_uid = {ob.session_uid: ob for ob in scene.objects}
    for src_uid, groups in _watch.items():
        src = by_uid.get(src_uid)
        if src is None:
            continue
        ad = src.animation_data
        keyed = ad is not None and ad.action is not None and ad.action.session_uid in actions
        for grp_uid, style in groups:
            if (style == "animCurve" and keyed) or (style == "force" and (keyed or src_uid in touched)):
                _pending.add(grp_uid)
    if _pending and not bpy.app.timers.is_registered(_rebuild_pending):
        bpy.app.timers.register(_rebuild_pending, first_interval=0.2)


def _transforming():
    wm = bpy.context.window_manager
    for win in wm.windows if wm else ():
        for op in win.modal_operators:
            if op.bl_idname.startswith("TRANSFORM_OT") or op.bl_idname.startswith("transform."):
                return True
    return False


def _rebuild_pending():
    """Timer: rebuild the waiting groups once nothing is being dragged / played."""
    if not _pending:
        return None
    context = bpy.context
    screen = getattr(context, "screen", None)
    if (screen is not None and screen.is_animation_playing) or _transforming():
        return 0.3
    uids = set(_pending)
    _pending.clear()
    for grp in [ob for ob in bpy.data.objects if ob.session_uid in uids and RECORD in ob]:
        try:
            rebuild(context, grp)
        except (RuntimeError, ReferenceError):
            pass
    return None


# --- operators ----------------------------------------------------------------------------------------------------

@undo_steps.no_redo_panel
class ALLSET_OT_animation_snapshot(bpy.types.Operator):
    """Copy the selected geometry at sampled frames into a snapshot group (Maya Visualize > Create Animation
    Snapshot)"""
    bl_idname = "allset.animation_snapshot"
    bl_label = "Create Animation Snapshot"
    bl_options = {'REGISTER', 'UNDO'}

    time_slider: BoolProperty(name="Time Slider", default=False, options={'SKIP_SAVE'})
    start: FloatProperty(name="Start time", default=1.0, options={'SKIP_SAVE'})
    end: FloatProperty(name="End time", default=10.0, options={'SKIP_SAVE'})
    increment: FloatProperty(name="Increment", default=1.0, min=0.0001, options={'SKIP_SAVE'})
    update: EnumProperty(name="Update", items=[("demand", "On demand", ""),
                                               ("animCurve", "Fast (update only when keyframes change)", ""),
                                               ("force", "Slow (always update)", "")],
                         default="animCurve", options={'SKIP_SAVE'})

    def execute(self, context):
        # Maya: "the current time and the selection don't change" — only an edited mesh / curve leaves Edit mode so
        # the copies see its edits; joints keep Pose mode (#155 H3-4: the snapshot used to drop it)
        if context.mode.startswith('EDIT'):
            bpy.ops.object.mode_set(mode='OBJECT')
        start, end = self.start, self.end
        if self.time_slider:
            from .playblast import playback_range
            start, end = playback_range(context.scene)
        try:
            groups = create(context, list(context.selected_objects), start, end, self.increment, self.update)
        except ValueError as ex:
            self.report({'ERROR'}, str(ex))
            return {'CANCELLED'}
        results.result(self, " ".join(g.name for g in groups))
        return {'FINISHED'}


@undo_steps.no_redo_panel
class ALLSET_OT_update_snapshot(bpy.types.Operator):
    """Sample the snapshots' sources again (Maya Visualize > Update Snapshot)"""
    bl_idname = "allset.update_snapshot"
    bl_label = "Update Snapshot"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        groups = groups_for(list(context.selected_objects))
        if not groups:
            self.report({'WARNING'}, NOTHING_TO_UPDATE)
            return {'CANCELLED'}
        done = [g.name for g in groups if rebuild(context, g)]
        results.result(self, " ".join(done))
        return {'FINISHED'}


classes = (ALLSET_OT_animation_snapshot, ALLSET_OT_update_snapshot)

_HANDLERS = (("depsgraph_update_post", _on_depsgraph), ("load_post", _dirty), ("undo_post", _dirty),
             ("redo_post", _dirty))


def register_handlers():
    for name, fn in _HANDLERS:
        getattr(bpy.app.handlers, name).append(fn)
    _dirty()


def unregister_handlers():
    for name, fn in _HANDLERS:
        lst = getattr(bpy.app.handlers, name)
        if fn in lst:
            lst.remove(fn)
    if bpy.app.timers.is_registered(_rebuild_pending):
        bpy.app.timers.unregister(_rebuild_pending)
    _pending.clear()
    _watch.clear()
    _busy.clear()
