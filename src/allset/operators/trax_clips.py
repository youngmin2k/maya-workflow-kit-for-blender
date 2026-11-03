# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya Trax clips on Blender's NLA.

Maya's Trax Editor turns a character's keys into a *source clip* and places *clip instances* of it on tracks: move,
duplicate, trim, scale, cycle and blend them, reuse a source many times. Blender's NLA holds the same thing:

- source clip = an Action marked ``allset_clip_source`` (fake user, Maya name ``clip1Source``); one source of several
  objects (a character set, a selection or a hierarchy) = one Action with a slot per object;
- clip instance = one NLA strip per member object, all named like the instance (``clip1``), each on a kit clip track
  (``Clip Track N``) of its object; scale / cycle (repeat) / hold = the strip's own settings;
- every new clip or instance goes on a new track (like Maya). The first strip of the bottom clip track holds before
  and after, the others hold forward only: a clip keeps its last value until a later clip takes over;
- blend = the upper strip's blend in / out over the part where the two clips overlap (linear).

Animation layers (operators/anim_layers.py) are NLA tracks too: clip tracks always stay below the layer tracks, so
the layer stack applies on top of the clips (BaseAnimation only replaces the channels it has keys on). Objects whose
keys live in animation layers are left out of Create Clip.

Like Maya: Create Clip takes the current character's channels (with its subcharacters), else the selection's keyed
channels (with the hierarchy below) and makes a character set for them (``pCube1Ch``, ``multiCh`` for several
objects); clips are named ``clip1`` / ``clip1Source`` counting up one past the highest clip name; the keys leave the
objects unless Leave keys in timeline is on; the time range is the animation curves' key range by default.
"""

import math

import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, StringProperty

from .. import compat, results  # noqa: F401  (compat also read by tests)
from . import anim_layers as al
from .naming import next_number

SOURCE = "allset_clip_source"
CHARACTER = "allset_clip_character"
TRACK = "Clip Track"
SOURCE_SUFFIX = "Source"
RANGES = ("Selected", "Time Slider", "Animation curve", "Start/End")
SCHEDULE = ("Put clip in Trax Editor and Visor", "Put clip in Visor only")
MSG_NOTHING = "Select objects with keys or set a current character."
MSG_NO_COMMON = "Blends cannot be made between clips that have no common channels."     # Maya's error text
MSG_NO_OVERLAP = "Blender blends clips only where they overlap: move the clips so they overlap."
MSG_SELECT_CLIP = "Select a clip in the Trax Editor."


# --- data -----------------------------------------------------------------------------------------------------

def is_source(act):
    return act is not None and bool(act.get(SOURCE))


def sources():
    return [a for a in bpy.data.actions if is_source(a)]


def is_clip_strip(st):
    return is_source(st.action)


def is_clip_track(tr):
    if tr.name.startswith(TRACK):
        return all(is_clip_strip(st) for st in tr.strips)
    return bool(tr.strips) and all(is_clip_strip(st) for st in tr.strips)


def clip_tracks(ob):
    ad = ob.animation_data
    return [tr for tr in ad.nla_tracks if is_clip_track(tr)] if ad is not None else []


def clip_strips(scene):
    """(object, track, strip) of every clip instance strip in the scene."""
    out = []
    for ob in scene.objects:
        for tr in clip_tracks(ob):
            out.extend((ob, tr, st) for st in tr.strips)
    return out


def instances(scene, name):
    return [(ob, tr, st) for ob, tr, st in clip_strips(scene) if st.name == name]


def instance_names(scene):
    names = []
    for _ob, _tr, st in clip_strips(scene):
        if st.name not in names:
            names.append(st.name)
    return names


def taken_names(scene):
    return set(instance_names(scene)) | {a.name for a in bpy.data.actions}


def clip_name(scene, wanted="clip1"):
    """Maya node naming: the wanted name while free, else its stem one past the highest taken number."""
    taken = taken_names(scene)
    wanted = (wanted or "clip1").strip()
    if wanted not in taken and wanted + SOURCE_SUFFIX not in taken:
        return wanted
    base = wanted.rstrip("0123456789") or "clip"
    n = next_number(base, taken)
    while f"{base}{n}" in taken or f"{base}{n}{SOURCE_SUFFIX}" in taken:
        n += 1
    return f"{base}{n}"


def slot_object(act, slot):
    """The object a source slot animates: one using it, else the object named like the slot."""
    users = getattr(slot, "users", None)
    if callable(users):
        for idb in users():
            if isinstance(idb, bpy.types.Object):
                return idb
    for ob in bpy.data.objects:
        ad = ob.animation_data
        if ad is None:
            continue
        for tr in ad.nla_tracks:
            if any(st.action == act and st.action_slot == slot for st in tr.strips):
                return ob
    return bpy.data.objects.get(slot.name_display)


def source_objects(act):
    out = []
    for slot in act.slots:
        ob = slot_object(act, slot)
        if ob is not None:
            out.append((ob, slot))
    return out


def channels_of(act, slot):
    return {(fc.data_path, fc.array_index) for fc in compat.action_fcurves(act, slot)}


# --- the clips' value of a channel (what the animation layers above start from) ---------------------------------

def _action_time(st, frame):
    """Action time the strip plays at scene ``frame`` (held at its ends), like Blender's NLA strip time."""
    a0, a1 = st.action_frame_start, st.action_frame_end
    if frame <= st.frame_start:
        return a0
    if frame >= st.frame_end:
        return a1
    t = (frame - st.frame_start) / max(st.scale, 1e-6)
    span = a1 - a0
    if span <= 0:
        return a0
    k = math.fmod(t, span)
    return a1 if (k < 1e-6 and t > 0) else a0 + k


def _blend_weight(st, frame):
    w = st.influence if st.use_animated_influence else 1.0
    if st.blend_in > 0 and frame < st.frame_start + st.blend_in:
        w *= max(0.0, (frame - st.frame_start) / st.blend_in)
    if st.blend_out > 0 and frame > st.frame_end - st.blend_out:
        w *= max(0.0, (st.frame_end - frame) / st.blend_out)
    return w


def stack_value(ob, path, index, frame, start):
    """The value ``ob``'s clip tracks give one channel at ``frame`` (from ``start``), None when no clip animates it."""
    acc, hit = start, False
    for tr in clip_tracks(ob):
        if tr.mute:
            continue
        pick = None
        for st in tr.strips:
            if st.mute or st.action is None:
                continue
            inside = st.frame_start <= frame <= st.frame_end
            held = (st.extrapolation == 'HOLD' and frame < st.frame_start) or \
                (st.extrapolation in ('HOLD', 'HOLD_FORWARD') and frame > st.frame_end)
            if inside or held:
                pick = st
                if inside:
                    break
        if pick is None:
            continue
        fc = next((f for f in compat.action_fcurves(pick.action, pick.action_slot)
                   if f.data_path == path and f.array_index == index), None)
        if fc is None:
            continue
        hit = True
        x = fc.evaluate(_action_time(pick, frame))
        w = _blend_weight(pick, frame) if pick.frame_start <= frame <= pick.frame_end else 1.0
        acc = (1.0 - w) * acc + w * x if pick.blend_type == 'REPLACE' else acc + w * x
    return acc if hit else None


# --- tracks -----------------------------------------------------------------------------------------------------

def _track_name(ob):
    have = {tr.name for tr in ob.animation_data.nla_tracks}
    n = 1
    while f"{TRACK} {n}" in have:
        n += 1
    return f"{TRACK} {n}"


def new_track(scene, ob):
    """A new clip track above ``ob``'s clip tracks and below its animation layer tracks."""
    ad = ob.animation_data_create()
    mine = clip_tracks(ob)
    layered = al.tracks(ob)
    tr = ad.nla_tracks.new(prev=mine[-1]) if mine else ad.nla_tracks.new()
    tr.name = _track_name(ob)
    if layered and not mine:
        # nla_tracks.new() adds on top: stack the layer tracks above it again (their settings kept)
        al.order_tracks(ob, [e.name for e in al.layers(scene)] or [al.BASE], force=True)
        al.sync(scene)
        tr = next(t for t in ad.nla_tracks if t.name == tr.name)
    return tr


def settle(ob):
    """Hold rules: the first strip of the bottom clip track holds both ways, every other clip strip holds forward."""
    first = True
    for tr in clip_tracks(ob):
        for st in tr.strips:
            want = 'HOLD' if first else 'HOLD_FORWARD'
            if st.extrapolation != want:
                st.extrapolation = want
            first = False
    ob.update_tag(refresh={'TIME'})


def remove_empty_tracks(ob):
    ad = ob.animation_data
    if ad is None:
        return 0
    gone = [tr for tr in ad.nla_tracks if not tr.strips and tr.name not in al.tracks(ob)]
    for tr in gone:
        ad.nla_tracks.remove(tr)
    return len(gone)


def place(scene, ob, act, slot, name, start, like=None):
    """One instance strip of ``act`` (``slot``) for ``ob`` at ``start`` on a new clip track."""
    tr = new_track(scene, ob)
    st = tr.strips.new(name, int(math.floor(start)), act)
    st.action_slot = slot
    a0, a1 = act.frame_range
    if like is not None:
        a0, a1 = like.action_frame_start, like.action_frame_end
    st.action_frame_start, st.action_frame_end = a0, a1
    if like is not None:
        st.scale, st.repeat = like.scale, like.repeat
        st.blend_type, st.influence, st.mute = like.blend_type, like.influence, like.mute
    st.frame_start_ui = start
    st.use_auto_blend = False
    st.blend_in = st.blend_out = 0.0
    settle(ob)
    return st


# --- Create Clip -------------------------------------------------------------------------------------------------

def _keyed(fc):
    return len(fc.keyframe_points) > 0


def gather(context, hierarchy=True, subcharacters=True):
    """({object: set of (data path, index)}, character set or None, skipped layered objects)."""
    from . import character_sets as cs
    scene = context.scene
    ks = cs.current(scene)
    want, skipped = {}, []
    if ks is not None:
        paths = cs.all_paths(scene, ks) if subcharacters else list(ks.paths)
        for p in paths:
            if isinstance(p.id, bpy.types.Object):
                want.setdefault(p.id, set()).add((p.data_path, p.array_index))
        obs = list(want)
    else:
        obs = list(context.selected_objects)
        if hierarchy:
            for ob in list(obs):
                obs.extend(c for c in ob.children_recursive if c not in obs)
    out = {}
    for ob in obs:
        if al.has_layers(ob):
            skipped.append(ob)
            continue
        fcs = [fc for fc in compat.id_fcurves(ob) if _keyed(fc)]
        if ks is not None:
            fcs = [fc for fc in fcs if (fc.data_path, fc.array_index) in want[ob]
                   or (fc.data_path, -1) in want[ob]]
        if fcs:
            out[ob] = {(fc.data_path, fc.array_index) for fc in fcs}
    return out, ks, skipped


def _copy_curve(src, dst):
    pts = src.keyframe_points
    dst.keyframe_points.add(len(pts))
    for a, b in zip(dst.keyframe_points, pts):
        a.co = b.co
        a.interpolation = b.interpolation
        a.handle_left_type, a.handle_right_type = b.handle_left_type, b.handle_right_type
        a.handle_left, a.handle_right = b.handle_left, b.handle_right
        a.easing = b.easing
        a.type = b.type
    dst.extrapolation = src.extrapolation
    dst.color_mode = src.color_mode
    dst.update()


def time_range(context, mode, start, end, curves):
    scene = context.scene
    if mode == "Start/End":
        return float(start), float(end)
    if mode == "Selected":
        wm = context.window_manager
        if getattr(wm, "allset_time_range_on", False):
            a, b = wm.allset_time_range
            return float(a), float(b)
        mode = "Time Slider"
    if mode == "Time Slider":
        if scene.use_preview_range:
            return float(scene.frame_preview_start), float(scene.frame_preview_end)
        return float(scene.frame_start), float(scene.frame_end)
    times = [kp.co[0] for fc in curves for kp in fc.keyframe_points]
    return (min(times), max(times)) if times else (float(scene.frame_start), float(scene.frame_end))


def character_for(scene, members, ks):
    """The clip's character: the current one, else a new character set of the clip channels (``<obj>Ch`` /
    ``multiCh``) that doesn't become current."""
    from . import character_sets as cs
    if ks is not None:
        return ks.bl_label
    obs = list(members)
    base = f"{obs[0].name}Ch" if len(obs) == 1 else "multiCh"
    taken = {k.bl_label for k in scene.keying_sets}
    name = base if base not in taken else cs.next_name(taken, base)
    keep = cs.current(scene)
    new = scene.keying_sets.new(idname="", name=name)
    new.bl_label = name
    for ob, chans in members.items():
        cs.add_members(new, [(ob, p, i) for p, i in sorted(chans)])
    cs.set_current(scene, keep)
    return name


def create_clip(context, name="clip1", leave_keys=False, schedule=True, range_mode="Animation curve", start=0.0,
                end=10.0, hierarchy=True, subcharacters=True):
    """Maya Create Clip: returns (instance name or None, source action, skipped objects); raises RuntimeError."""
    scene = context.scene
    members, ks, skipped = gather(context, hierarchy, subcharacters)
    if not members:
        raise RuntimeError(MSG_NOTHING)
    curves = {ob: [fc for fc in compat.id_fcurves(ob) if (fc.data_path, fc.array_index) in chans]
              for ob, chans in members.items()}
    r0, r1 = time_range(context, range_mode, start, end, [fc for fcs in curves.values() for fc in fcs])
    if r1 <= r0:
        r1 = r0 + 1.0
    inst = clip_name(scene, name)
    act = bpy.data.actions.new(inst + SOURCE_SUFFIX)
    act[SOURCE] = 1
    act[CHARACTER] = character_for(scene, members, ks)
    act.use_fake_user = True
    act.use_frame_range = True
    act.frame_start, act.frame_end = r0, r1
    layer = act.layers.new("Layer")
    kstrip = layer.strips.new(type='KEYFRAME')
    slots = {}
    for ob, fcs in curves.items():
        slot = act.slots.new(id_type='OBJECT', name=ob.name)
        slots[ob] = slot
        bag = kstrip.channelbag(slot, ensure=True)
        for fc in fcs:
            nf = bag.fcurves.new(fc.data_path, index=fc.array_index)
            if fc.group is not None:
                grp = bag.groups.get(fc.group.name) or bag.groups.new(fc.group.name)
                nf.group = grp
            _copy_curve(fc, nf)
        if not leave_keys:
            _remove_curves(ob, fcs)
    if schedule:
        for ob in curves:
            place(scene, ob, act, slots[ob], inst, r0)
    return (inst if schedule else None), act, skipped


def _remove_curves(ob, fcs):
    ad = ob.animation_data
    coll = compat.id_fcurve_collection(ob)
    if coll is None:
        return
    for fc in fcs:
        coll.remove(fc)
    if not len(coll):
        old = ad.action
        ad.action = None
        if old is not None and old.users == 0 and not old.use_fake_user:
            bpy.data.actions.remove(old)


# --- clip commands -----------------------------------------------------------------------------------------------

def selected_instances(scene):
    """Names of instances with a selected member strip (the Trax selection), in time order."""
    found = {}
    for _ob, _tr, st in clip_strips(scene):
        if st.select:
            found.setdefault(st.name, st.frame_start)
    return sorted(found, key=found.get)


def insert_instance(scene, act, frame, like=None):
    """A new instance of the source ``act`` at ``frame`` for every object it animates (Library > Insert Clip)."""
    name = clip_name(scene, "clip1")
    made = []
    for ob, slot in source_objects(act):
        ref = like.get(ob) if like else None
        made.append(place(scene, ob, act, slot, name, frame, like=ref))
    return name if made else None


def duplicate(scene, name):
    rows = instances(scene, name)
    if not rows:
        return None
    act = rows[0][2].action
    like = {ob: st for ob, _tr, st in rows}
    end = max(st.frame_end for _o, _t, st in rows)
    return insert_instance(scene, act, end, like=like)


def _local(st, frame):
    """Action time of scene ``frame`` inside one repeat of the strip."""
    return st.action_frame_start + (frame - st.frame_start) / max(st.scale, 1e-6)


def trim(scene, name, frame, before):
    n = 0
    for ob, _tr, st in instances(scene, name):
        if not (st.frame_start < frame < st.frame_end) or st.repeat != 1.0:
            continue
        t = _local(st, frame)
        if before:
            st.action_frame_start = t
            st.frame_start_ui = frame
        else:
            st.action_frame_end = t
        settle(ob)
        n += 1
    return n


def split(scene, name, frame):
    """Split each member strip at ``frame``: the right part is a new instance (next clip name)."""
    rows = [r for r in instances(scene, name) if r[2].frame_start < frame < r[2].frame_end and r[2].repeat == 1.0]
    if not rows:
        return None
    new = clip_name(scene, "clip1")
    for ob, tr, st in rows:
        t, a1 = _local(st, frame), st.action_frame_end
        scale, slot = st.scale, st.action_slot
        st.action_frame_end = t
        right = tr.strips.new(new, int(math.ceil(st.frame_end)), st.action)
        right.action_slot = slot
        right.action_frame_start, right.action_frame_end = t, a1
        right.scale = scale
        right.frame_start_ui = st.frame_end
        right.blend_type, right.influence, right.mute = st.blend_type, st.influence, st.mute
        settle(ob)
    return new


def toggle_enable(scene, names):
    rows = [r for n in names for r in instances(scene, n)]
    on = any(not st.mute for _o, _t, st in rows)
    for ob, _tr, st in rows:
        st.mute = on
        ob.update_tag(refresh={'TIME'})
    return not on


def blend(scene, a, b):
    """Maya Create Blend between instances ``a`` and ``b``: the upper strip blends in (or out) over the overlap."""
    ra, rb = instances(scene, a), instances(scene, b)
    common = 0
    for ob, tra, sa in ra:
        for ob2, trb, sb in rb:
            if ob2 != ob:
                continue
            if not channels_of(sa.action, sa.action_slot) & channels_of(sb.action, sb.action_slot):
                continue
            common += 1
            tracks = list(ob.animation_data.nla_tracks)
            lo, hi = (sa, sb) if tracks.index(tra) < tracks.index(trb) else (sb, sa)
            s0, s1 = max(lo.frame_start, hi.frame_start), min(lo.frame_end, hi.frame_end)
            if s1 <= s0:
                raise RuntimeError(MSG_NO_OVERLAP)
            hi.use_auto_blend = False
            if hi.frame_start >= lo.frame_start:
                hi.blend_in = s1 - s0
            else:
                hi.blend_out = s1 - s0
            ob.update_tag(refresh={'TIME'})
    if not common:
        raise RuntimeError(MSG_NO_COMMON)
    return common


def delete_instance(scene, name):
    for ob, tr, st in instances(scene, name):
        tr.strips.remove(st)
        remove_empty_tracks(ob)
        settle(ob)


def delete_source(scene, act):
    for name in [st.name for _o, _t, st in clip_strips(scene) if st.action == act]:
        delete_instance(scene, name)
    bpy.data.actions.remove(act)


def enabled_range(scene):
    rows = [st for _o, _t, st in clip_strips(scene) if not st.mute]
    if not rows:
        return None
    return min(st.frame_start for st in rows), max(st.frame_end for st in rows)


# --- operators ---------------------------------------------------------------------------------------------------

def _redraw(context):
    for win in context.window_manager.windows:
        for area in win.screen.areas:
            area.tag_redraw()


class ALLSET_OT_trax_create_clip(bpy.types.Operator):
    """Turn the current character's (or the selected objects') keys into a clip on the Trax tracks"""
    bl_idname = "allset.trax_create_clip"
    bl_label = "Create Clip"
    bl_options = {'UNDO'}

    clip_name: StringProperty(name="Name", default="clip1", options={'SKIP_SAVE'})
    leave_keys: BoolProperty(name="Leave keys in timeline", default=False, options={'SKIP_SAVE'})
    visor_only: BoolProperty(name="Put clip in Visor only", default=False, options={'SKIP_SAVE'})
    time_range: EnumProperty(name="Time range", items=[(r, r, "") for r in RANGES], default="Animation curve",
                             options={'SKIP_SAVE'})
    start: FloatProperty(name="Start", default=0.0, options={'SKIP_SAVE'})
    end: FloatProperty(name="End", default=10.0, options={'SKIP_SAVE'})
    hierarchy: BoolProperty(name="Include Hierarchy", default=True, options={'SKIP_SAVE'})
    subcharacters: BoolProperty(name="Include subcharacters in clip", default=True, options={'SKIP_SAVE'})

    def execute(self, context):
        try:
            inst, act, skipped = create_clip(context, self.clip_name, self.leave_keys, not self.visor_only,
                                             self.time_range, self.start, self.end, self.hierarchy,
                                             self.subcharacters)
        except RuntimeError as exc:
            self.report({'WARNING'}, str(exc))
            return {'CANCELLED'}
        if skipped:
            self.report({'WARNING'}, "Keys in animation layers stay there: " + ", ".join(o.name for o in skipped))
        results.result(self, inst or act.name)
        _redraw(context)
        return {'FINISHED'}


class _OnSelected:
    bl_options = {'UNDO'}
    clip: StringProperty(name="Clip", options={'SKIP_SAVE', 'HIDDEN'},
                         description="Instance name (empty = the selected clips)")

    def names(self, context):
        return [self.clip] if self.clip else selected_instances(context.scene)


class ALLSET_OT_trax_clip_edit(_OnSelected, bpy.types.Operator):
    """Edit the selected Trax clips (Maya Trax Edit / Modify menu commands)"""
    bl_idname = "allset.trax_clip_edit"
    bl_label = "Edit Clips"

    action: EnumProperty(items=[("DUPLICATE", "Duplicate", "A new instance right after the clip"),
                                ("SPLIT", "Split", "Split the clip at the current time"),
                                ("TRIM_BEFORE", "Trim Before", "Cut the clip before the current time"),
                                ("TRIM_AFTER", "Trim After", "Cut the clip after the current time"),
                                ("ENABLE", "Enable/Disable", "Mute or unmute the clips"),
                                ("DELETE", "Delete", "Delete the clip instances"),
                                ("BLEND", "Blend", "Blend the two selected clips where they overlap")],
                         options={'SKIP_SAVE'})

    def execute(self, context):
        scene = context.scene
        names = self.names(context)
        if not names or (self.action == 'BLEND' and len(names) != 2):
            self.report({'WARNING'}, "Select two clips to blend." if self.action == 'BLEND' else MSG_SELECT_CLIP)
            return {'CANCELLED'}
        f = scene.frame_current
        out = []
        try:
            if self.action == 'BLEND':
                blend(scene, names[0], names[1])
                out = names
            for n in names if self.action != 'BLEND' else ():
                if self.action == 'DUPLICATE':
                    out.append(duplicate(scene, n))
                elif self.action == 'SPLIT':
                    out.append(split(scene, n, f))
                elif self.action in ('TRIM_BEFORE', 'TRIM_AFTER'):
                    if trim(scene, n, f, self.action == 'TRIM_BEFORE'):
                        out.append(n)
                elif self.action == 'DELETE':
                    delete_instance(scene, n)
                    out.append(n)
            if self.action == 'ENABLE':
                out = [f"{n} {'enabled' if toggle_enable(scene, names) else 'disabled'}" for n in names[:1]]
        except RuntimeError as exc:
            self.report({'WARNING'}, str(exc))
            return {'CANCELLED'}
        out = [o for o in out if o]
        if not out and self.action != 'DELETE':
            self.report({'WARNING'}, "The current time is not inside the selected clips.")
            return {'CANCELLED'}
        results.result(self, " ".join(out))
        _redraw(context)
        return {'FINISHED'}


class ALLSET_OT_trax_insert_clip(bpy.types.Operator):
    """Place a new instance of this source clip at the current time (Maya Library > Insert Clip)"""
    bl_idname = "allset.trax_insert_clip"
    bl_label = "Insert Clip"
    bl_options = {'UNDO'}

    source: StringProperty(name="Source Clip", options={'SKIP_SAVE'})

    def execute(self, context):
        act = bpy.data.actions.get(self.source)
        if not is_source(act):
            self.report({'WARNING'}, f"No source clip {self.source}")
            return {'CANCELLED'}
        name = insert_instance(context.scene, act, context.scene.frame_current)
        if name is None:
            self.report({'WARNING'}, f"The objects of {self.source} are gone")
            return {'CANCELLED'}
        results.result(self, name)
        _redraw(context)
        return {'FINISHED'}


class ALLSET_OT_trax_delete_source(bpy.types.Operator):
    """Delete this source clip and all its instances"""
    bl_idname = "allset.trax_delete_source"
    bl_label = "Delete Source Clip"
    bl_options = {'UNDO'}

    source: StringProperty(name="Source Clip", options={'SKIP_SAVE'})
    every: BoolProperty(name="All Clips", options={'SKIP_SAVE'}, description="Every clip in the scene "
                        "(Edit > Delete All by Type > Clips)")

    def execute(self, context):
        acts = sources() if self.every else [a for a in (bpy.data.actions.get(self.source),) if is_source(a)]
        for act in acts:
            delete_source(context.scene, act)
        results.result(self, f"{len(acts)} clips deleted")
        _redraw(context)
        return {'FINISHED'}


class ALLSET_OT_trax_tracks(bpy.types.Operator):
    """Trax track commands"""
    bl_idname = "allset.trax_tracks"
    bl_label = "Trax Tracks"
    bl_options = {'UNDO'}

    action: EnumProperty(items=[("REMOVE_EMPTY", "Remove Empty Tracks", "Delete tracks without clips"),
                                ("RANGE", "Enabled Clips", "Set the playback range to the enabled clips")],
                         options={'SKIP_SAVE'})

    def execute(self, context):
        scene = context.scene
        if self.action == 'RANGE':
            r = enabled_range(scene)
            if r is None:
                self.report({'WARNING'}, "No enabled clips")
                return {'CANCELLED'}
            scene.use_preview_range = True
            scene.frame_preview_start, scene.frame_preview_end = int(math.floor(r[0])), int(math.ceil(r[1]))
            results.result(self, f"{scene.frame_preview_start} {scene.frame_preview_end}")
        else:
            n = sum(remove_empty_tracks(ob) for ob in scene.objects)
            results.result(self, f"{n} tracks removed")
        _redraw(context)
        return {'FINISHED'}


class ALLSET_OT_trax_activate_keys(bpy.types.Operator):
    """Edit the selected clip's keys in place, or stop editing them (Maya Activate/Deactivate Keys)"""
    bl_idname = "allset.trax_activate_keys"
    bl_label = "Activate/Deactivate Keys"
    bl_options = {'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.area is not None and context.area.type == 'NLA_EDITOR'

    def execute(self, context):
        scene = context.scene
        if scene.is_nla_tweakmode:
            return bpy.ops.nla.tweakmode_exit()
        picked = [(ob, tr) for ob, tr, st in clip_strips(scene) if st.select]
        if not picked:
            self.report({'WARNING'}, MSG_SELECT_CLIP)
            return {'CANCELLED'}
        for ob, tr in picked:
            ob.animation_data.nla_tracks.active = tr     # Blender edits the selected strip of the active track
        try:
            return bpy.ops.nla.tweakmode_enter()
        except RuntimeError as exc:
            self.report({'WARNING'}, str(exc).splitlines()[0])
            return {'CANCELLED'}


classes = (ALLSET_OT_trax_create_clip, ALLSET_OT_trax_clip_edit, ALLSET_OT_trax_insert_clip,
           ALLSET_OT_trax_delete_source, ALLSET_OT_trax_tracks, ALLSET_OT_trax_activate_keys)
