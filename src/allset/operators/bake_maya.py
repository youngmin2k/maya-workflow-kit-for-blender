# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya Key > Bake Simulation (Edit > Keys > Bake Simulation, shelf, option window).

Maya 2026 rules of ``bakeResults`` and the menu's default flags:

1. every keyable transform channel of a baked node gets a key on each sample;
2. samples = start, start + step, … ≤ end (``step2``: 1 3 5 7 9 on 1–10);
3. existing keys inside [start, end] that are not samples are removed (sz 2.5 / 6, every case);
4. Keep unbaked keys on = keys outside the range stay (sx 20), off = removed (``pok_off``); constraints are never
   deleted;
5. baking always disconnects the constraint from the baked channels, Disable implicit control on or off
   (``dic_off.pos_after_driver_moved``); the constraint node stays;
6. Disable implicit control = IK: baking chain joints without the handle sets ikBlend 0 when on, keeps 1 when off;
   baking the handle too leaves ikBlend alone.

Kit translation: Blender's ``nla.bake`` (visual keying, current action, constraints kept) writes the samples, then the
Maya rules run on the baked F-curves. Rule 5 = **mute** every non-IK constraint on a baked object / pose bone (Blender
has no disconnect; the constraint stays and shows as off) and every driver on a baked channel (a driver would win over
the baked curve; Maya's bake replaces any input connection). Limit constraints stay: Maya's transform
limits are attributes, not constraint nodes. Rule 6 = an IK constraint (kit IK handle, operators/skin.py)
whose chain holds a baked bone and whose target is not baked gets influence 0 (ikBlend = influence).
Visibility (rule 1) is not baked: Maya visibility = ``hide_viewport``, which no constraint drives.
"""

import bpy
from bpy.props import BoolProperty, IntProperty

from .. import compat, results

# Blender channels the bake writes (nla.bake channel types LOCATION / ROTATION / SCALE; PROPS = '["..."]' paths)
_TRANSFORM = ("location", "rotation_euler", "rotation_quaternion", "rotation_axis_angle", "scale")
# kit-internal ID properties (allset_*) are bookkeeping, never Maya channels: their baked curves are dropped
_KIT_PROP = ('["allset', '["_')
_EPS = 1e-4


def time_slider_range(scene):
    """Maya Time Slider = the playback range: the preview range while it is on."""
    if scene.use_preview_range:
        return scene.frame_preview_start, scene.frame_preview_end
    return scene.frame_start, scene.frame_end


def samples(start, end, step):
    """Maya sample frames: start, start + step, … ≤ end."""
    step = max(1, int(step))
    return list(range(int(start), int(end) + 1, step))


def keep_key(x, start, end, step, keep_unbaked):
    """Maya rules 3 / 4: a key at frame ``x`` survives the bake."""
    if x < start - _EPS or x > end + _EPS:
        return keep_unbaked
    k = (x - start) / max(1, step)
    return abs(k - round(k)) < _EPS


def _channel(path, prefix):
    """True when ``path`` is a baked channel of the owner whose paths start with ``prefix``."""
    if not path.startswith(prefix):
        return False
    rest = path[len(prefix):]
    if prefix == "" and rest.startswith("pose."):
        return False
    if rest in _TRANSFORM:
        return True
    return rest.startswith('["') and not rest.startswith(_KIT_PROP)


def _prefix(owner):
    return "" if isinstance(owner, bpy.types.Object) else owner.path_from_id() + "."


def _trim(fcurve, start, end, step, keep_unbaked):
    points = fcurve.keyframe_points
    drop = [i for i, kp in enumerate(points) if not keep_key(kp.co[0], start, end, step, keep_unbaked)]
    for i in reversed(drop):
        points.remove(points[i], fast=True)
    if drop:
        fcurve.update()
    return len(drop)


def _ik_chain(pb, con):
    """Pose bones an IK constraint on ``pb`` moves (chain_count 0 = up to the root)."""
    chain, b = [], pb
    while b is not None and (con.chain_count == 0 or len(chain) < con.chain_count):
        chain.append(b)
        b = b.parent
    return chain


def bake(context, objects=None, bones=None, start=1, end=10, step=1, keep_unbaked=True, disable_implicit=True):
    """Bake ``objects`` (object mode) or ``bones`` (pose bones, pose mode) the Maya way; returns a summary dict.

    The caller makes exactly these nodes selected (``nla.bake`` only bakes the selection)."""
    objects, bones = list(objects or ()), list(bones or ())
    pose = bool(bones)
    owners = bones if pose else objects
    ids = {pb.id_data for pb in bones} if pose else set(objects)
    from . import anim_layers
    layered = [idb for idb in ids if anim_layers.has_layers(idb)]
    for idb in layered:
        # Issue #143: bake onto BaseAnimation (the active action is the shown layer at influence 0,
        # anim_layers.show) — then solved below so base + layers give the baked result (Maya 2026: the pose doesn't
        # change and the layers stay)
        anim_layers.show_base(idb)
    before = {}
    for idb in ids:
        before[idb] = {(fc.data_path, fc.array_index) for fc in compat.id_fcurves(idb)}
    res = bpy.ops.nla.bake('EXEC_DEFAULT', frame_start=int(start), frame_end=int(end), step=max(1, int(step)),
                           only_selected=True, visual_keying=True, clear_constraints=False, clear_parents=False,
                           use_current_action=True, clean_curves=False, bake_types={'POSE'} if pose else {'OBJECT'},
                           # Blender refuses custom-property keys of NLA-layered data ("Due to the NLA stack
                           # setup ..." per key); a layered rig bakes its transforms only
                           channel_types={'LOCATION', 'ROTATION', 'SCALE'} | (set() if layered else {'PROPS'}))
    if res != {'FINISHED'}:
        if layered:
            anim_layers.show(context.scene)
        return None
    prefixes = {}
    for o in owners:
        prefixes.setdefault(o.id_data, []).append(_prefix(o))
    for idb in ids:
        coll = compat.id_fcurve_collection(idb)
        for fc in list(compat.id_fcurves(idb)):
            path = fc.data_path
            mine = any(_channel(path, p) for p in prefixes.get(idb, ()))
            if not mine:
                # curves the bake made for something Maya doesn't bake (kit ID properties, armature-level props)
                if (path, fc.array_index) not in before[idb] and coll is not None:
                    coll.remove(fc)
                continue
            _trim(fc, start, end, step, keep_unbaked)
    # rule 5: the constraint (and any driver) no longer drives the baked channels
    muted = drivers = iks = 0
    for o in owners:
        for con in o.constraints:
            if con.type == 'IK' or con.type.startswith("LIMIT_"):
                continue
            if not con.mute:
                con.mute = True
                muted += 1
    for idb in ids:
        ad = idb.animation_data
        for fc in (ad.drivers if ad is not None else ()):
            if not fc.mute and any(_channel(fc.data_path, p) for p in prefixes.get(idb, ())):
                fc.mute = True
                drivers += 1
    # rule 6: Disable implicit control = IK handles whose chain was baked without the handle
    if pose and disable_implicit:
        baked = {(pb.id_data, pb.name) for pb in bones}
        for arm in ids:
            for pb in arm.pose.bones:
                for con in pb.constraints:
                    if con.type != 'IK' or con.influence == 0.0:
                        continue
                    if not any((arm, b.name) in baked for b in _ik_chain(pb, con)):
                        continue
                    t = con.target
                    if t is not None and t.type == 'ARMATURE' and con.subtarget:
                        target_baked = (t, con.subtarget) in baked
                    else:
                        target_baked = False      # pose-mode bakes never include the handle object
                    if not target_baked:
                        from . import ik_fk
                        ik_fk.set_blend(arm, pb, con, 0.0)      # Ik Blend 0 (drives the Influence)
                        iks += 1
    for idb in layered:
        anim_layers.settle_base(context.scene, idb, [_prefix(o) for o in owners if o.id_data == idb])
    if layered:
        anim_layers.show(context.scene)
    context.scene.frame_set(context.scene.frame_current)     # show the baked pose (nla.bake leaves the last sample)
    return {"nodes": len(owners), "muted": muted, "drivers": drivers, "ik": iks}


class ALLSET_OT_bake_simulation(bpy.types.Operator):
    """Maya Bake Simulation: key every transform channel of the selection on each sampled frame; constraints stop
    driving the baked channels (muted, kept)"""
    bl_idname = "allset.bake_simulation"
    bl_label = "Bake Simulation"
    bl_options = {'UNDO'}         # Maya has no redo panel; the option window holds the values

    hierarchy_below: BoolProperty(name="Hierarchy: Below", default=False, options={'SKIP_SAVE'})
    use_time_slider: BoolProperty(name="Time Slider", default=True, options={'SKIP_SAVE'})
    start: IntProperty(name="Start", default=1, options={'SKIP_SAVE'})
    end: IntProperty(name="End", default=10, options={'SKIP_SAVE'})
    sample_by: IntProperty(name="Sample by", default=1, min=1, options={'SKIP_SAVE'})
    keep_unbaked: BoolProperty(name="Keep unbaked keys", default=True, options={'SKIP_SAVE'})
    disable_implicit: BoolProperty(name="Disable implicit control", default=True, options={'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        return context.mode in ('OBJECT', 'POSE')

    def execute(self, context):
        from ..ui.channel_box import bone_selected, set_bone_selected
        scene = context.scene
        start, end = time_slider_range(scene) if self.use_time_slider else (self.start, self.end)
        if end < start:
            self.report({'ERROR'}, "Bake Simulation: the end time is before the start time.")
            return {'CANCELLED'}
        extra_bones, extra_obs = [], []
        try:
            if context.mode == 'POSE':
                bones = list(context.selected_pose_bones or ())
                if self.hierarchy_below:
                    have = set(bones)
                    for pb in list(bones):
                        for c in pb.children_recursive:
                            if c not in have:
                                have.add(c)
                                bones.append(c)
                                if not bone_selected(c):
                                    set_bone_selected(c, True)
                                    extra_bones.append(c)
                if not bones:
                    self.report({'ERROR'}, "Select joints (bones) to bake.")
                    return {'CANCELLED'}
                out = bake(context, bones=bones, start=start, end=end, step=self.sample_by,
                           keep_unbaked=self.keep_unbaked, disable_implicit=self.disable_implicit)
            else:
                objects = list(context.selected_editable_objects)
                if self.hierarchy_below:
                    from .freeze import hierarchy
                    for o in hierarchy(objects):
                        if o not in objects:
                            objects.append(o)
                            if not o.select_get():
                                o.select_set(True)
                                extra_obs.append(o)
                if not objects:
                    self.report({'ERROR'}, "Select objects to bake.")
                    return {'CANCELLED'}
                out = bake(context, objects=objects, start=start, end=end, step=self.sample_by,
                           keep_unbaked=self.keep_unbaked, disable_implicit=self.disable_implicit)
        finally:
            for pb in extra_bones:
                set_bone_selected(pb, False)
            for o in extra_obs:
                o.select_set(False)
        if out is None:
            self.report({'WARNING'}, "Nothing to bake.")
            return {'CANCELLED'}
        text = "Baked %d node(s), frames %d–%d; constraints disconnected (muted): %d" % (
            out["nodes"], start, end, out["muted"])
        if out["drivers"]:
            text += "; drivers muted: %d" % out["drivers"]
        if out["ik"]:
            text += "; IK handles disabled: %d" % out["ik"]
        results.result(self, text)
        return {'FINISHED'}


classes = (ALLSET_OT_bake_simulation,)
