# SPDX-License-Identifier: GPL-3.0-or-later
"""Rig FBX import the way Maya 2026 reads it (Issue #133).

What Blender's FBX reader does with a Maya rig:

- it samples every bone at the union of its channels' key times and keys ``rotation_quaternion`` / ``location`` there
  with **linear** interpolation between the keys ($S/addons_core/io_scene_fbx/import_fbx.py:710-735, 851-890): Maya's
  cubic tangents are lost, so poses between keys are off (also after a kit export round trip);
- the armature object carries the axis / unit conversion (Rotate X 90, Scale 0.01) and the skinned mesh is its child
  (Rotate X -90, Scale 100);
- the Time Slider keeps Blender's range (Maya sets it to the file's range).

``fix_armature`` rebuilds that the Maya way from the file itself (Blender's bundled ``parse_fbx``, operators/fbx_rig):

1. Each Maya channel curve becomes an F-curve with the same keys and tangents: Maya 2026's ``auto`` tangent (FBX flags
   cubic + auto, no slopes stored) is Blender's Auto Clamped handle with the curve's Continuous Acceleration smoothing;
   user / break tangents (Maya linear, flat, spline,
   clamped, plateau, fixed are written that way) keep their slopes (value per second) as free handles at 1/3 of the
   span; linear / constant keys keep their interpolation. Weighted tangents are read as non-weighted.
2. The bone correction C (Blender bone axes in the FBX joint frame) is read at the earliest key frame, where Blender's
   linear sampling is still exact (every curve holds its first value before its first key). Then a bone's pose basis
   is B(t) = K . L(t) . C with L = T . Pre . R . S the FBX local matrix and K constant (rest and parent correction).
3. Rotation: when K . Pre = C^-1 and C is a signed axis permutation (a Maya rig bound at rotate 0 — the common case),
   B's rotation is R(t) with permuted axes, so the Maya rotate curves are copied 1:1 (same keys and tangents) into
   ``rotation_euler`` with the matching Euler order (Maya xyz -> Blender YXZ for bone Y = joint X). Otherwise the
   rotation is keyed every frame as continuous XYZ Euler (``rotation_display.euler_curve``): imported
   rotations are Euler, like Maya's FBX import (Quaternion = resample).
4. Translation: B's location is A . T(t) + b; copied 1:1 when A is a scaled signed permutation, else keyed every frame.
5. The conversion goes into the bones (armature object = identity, like a Maya skeleton), the skinned meshes leave the
   armature keeping their place (kit Bind Skin rule), the Time Slider = the file's time span.

A root joint under another node (a Maya group above the skeleton) is left to Blender's reader.
"""

import math

import bpy
from mathutils import Euler, Matrix, Vector

from . import fbx_rig

KTIME = 46186158000                   # FBX ticks per second
# FBX KeyAttrFlags (FbxAnimCurveDef)
_CONSTANT, _LINEAR, _CUBIC = 0x02, 0x04, 0x08
_AUTO, _TCB, _USER, _BREAK = 0x100, 0x200, 0x400, 0x800
# FBX RotationOrder enum -> axis application order (eEulerXYZ = X first)
_ORDERS = {0: "XYZ", 1: "XZY", 2: "YZX", 3: "YXZ", 4: "ZXY", 5: "ZYX"}
_AXES = "XYZ"
_SCRATCH = "allset_fbx_scratch"


# --- FBX curves -> key lists --------------------------------------------------------------------------------------

def _expand(per_attr, refs, width):
    out = []
    for i, n in enumerate(refs):
        out.extend([per_attr[i * width:(i + 1) * width]] * int(n))
    return out


def curve_keys(curve, fps):
    """[(frame, value, interp, left, right)] of an FBX AnimationCurve; left / right = None (auto) or a slope in
    value per frame."""
    times = [t / KTIME * fps for t in curve.first(b"KeyTime").props[0]]
    vals = list(curve.first(b"KeyValueFloat").props[0])
    flags_e = curve.first(b"KeyAttrFlags")
    data_e = curve.first(b"KeyAttrDataFloat")
    refs_e = curve.first(b"KeyAttrRefCount")
    n = len(times)
    if flags_e is None or refs_e is None:
        flags, data = [_CUBIC | _AUTO] * n, [[0.0] * 4] * n
    else:
        refs = list(refs_e.props[0])
        flags = [f[0] for f in _expand(list(flags_e.props[0]), refs, 1)]
        data = _expand(list(data_e.props[0]) if data_e is not None else [0.0] * 4 * len(refs), refs, 4)
    flags = (flags + [flags[-1] if flags else _CUBIC | _AUTO] * n)[:n]
    data = (data + [[0.0] * 4] * n)[:n]
    out = []
    for k in range(n):
        f = flags[k]
        interp = 'CONSTANT' if f & _CONSTANT else 'LINEAR' if f & _LINEAR else 'BEZIER'
        auto = bool(f & _CUBIC and f & (_AUTO | _TCB) and not f & (_USER | _BREAK))
        right = None if auto else data[k][0] / fps
        # a key's left slope is the previous key's NextLeftSlope unless the key itself is auto (a Maya fixed
        # tangent after an auto key keeps its slope on the auto key, tests/maya223 hand.rotateY)
        left = data[k - 1][1] / fps if k > 0 and not auto else None
        out.append([times[k], vals[k], interp, left, right])
    return out


def fill_fcurve(fc, keys, a=1.0, b=0.0):
    """Write ``keys`` (curve_keys) into F-curve ``fc`` as a * value + b (slopes x a)."""
    kp = fc.keyframe_points
    kp.clear()
    kp.add(len(keys))
    auto = False
    for i, (f, v, interp, left, right) in enumerate(keys):
        p = kp[i]
        p.co = (f, a * v + b)
        p.interpolation = interp
        prev_f = keys[i - 1][0] if i > 0 else f - 1.0
        next_f = keys[i + 1][0] if i + 1 < len(keys) else f + 1.0
        if left is None:
            p.handle_left_type = 'AUTO_CLAMPED'
            auto = True
        else:
            d = (f - prev_f) / 3.0
            p.handle_left_type = 'FREE'
            p.handle_left = (f - d, a * (v - left * d) + b)
        if right is None:
            p.handle_right_type = 'AUTO_CLAMPED'
            auto = True
        else:
            d = (next_f - f) / 3.0
            p.handle_right_type = 'FREE'
            p.handle_right = (f + d, a * (v + right * d) + b)
    if auto:
        fc.auto_smoothing = 'CONT_ACCEL'          # = Maya 2026 auto tangents (module docstring 1)
    fc.update()


# --- scratch evaluator (Blender's own F-curve maths, exact Maya curves) -------------------------------------------

class Scratch:
    """Maya channel curves on a throwaway object, evaluated with ``FCurve.evaluate``."""

    def __init__(self):
        self.ob = bpy.data.objects.new(_SCRATCH, None)
        self.curves = {}

    def add(self, name, keys, frame):
        from .. import compat
        self.ob[name] = 0.0
        self.ob.keyframe_insert(f'["{name}"]', frame=frame)
        fc = next(c for c in compat.id_fcurves(self.ob) if c.data_path == f'["{name}"]')
        fill_fcurve(fc, keys)
        self.curves[name] = fc
        return fc

    def value(self, name, frame, default):
        fc = self.curves.get(name)
        return fc.evaluate(frame) if fc is not None else default

    def close(self):
        ad = self.ob.animation_data
        action = ad.action if ad is not None else None
        bpy.data.objects.remove(self.ob)
        if action is not None and action.users == 0:
            bpy.data.actions.remove(action)


# --- the file -----------------------------------------------------------------------------------------------------

def _settings(tree):
    gs = tree.first(b"GlobalSettings")
    out = {}
    if gs is not None:
        for p in fbx_rig._p70(gs).elems:
            if p.props and len(p.props) > 4:
                out[p.props[0]] = p.props[4]
    return out


def file_fps(tree, scene):
    return scene.render.fps / (scene.render.fps_base or 1.0)


def time_span(tree, fps):
    """The file's Time Slider range (frames): GlobalSettings TimeSpan (Maya writes the playback range). Blender's
    FBX writer always writes 0 .. 1 s there (a kit file came back as 0-24), so that value defers to the
    first take's LocalStart / LocalStop."""
    s = _settings(tree)
    a, b = s.get(b"TimeSpanStart"), s.get(b"TimeSpanStop")
    if a is not None and b is not None and (a, b) == (0, KTIME):
        take = _take_span(tree)
        if take is not None:
            a, b = take
    if a is None or b is None or b <= a:
        return None
    return round(a / KTIME * fps), round(b / KTIME * fps)


def _take_span(tree):
    objects = tree.first(b"Objects")
    for st in objects.find(b"AnimationStack") if objects is not None else ():
        props = {p.props[0]: p.props[4] for p in fbx_rig._p70(st).elems if p.props and len(p.props) > 4}
        if b"LocalStop" in props:
            return props.get(b"LocalStart", 0), props[b"LocalStop"]
    return None


class Joint:
    """A LimbNode's channels: defaults, Maya key lists, PreRotation, rotate order."""

    ATTRS = ((b"Lcl Translation", "t", (0.0, 0.0, 0.0)), (b"Lcl Rotation", "r", (0.0, 0.0, 0.0)),
             (b"Lcl Scaling", "s", (1.0, 1.0, 1.0)))

    def __init__(self, index, uid, fps):
        m = index.models[uid]
        self.uid, self.name = uid, fbx_rig.name_of(m)
        self.default = {k: fbx_rig.get_vec(m, attr, d) for attr, k, d in self.ATTRS}
        self.pre = fbx_rig.get_vec(m, b"PreRotation")
        self.post = fbx_rig.get_vec(m, b"PostRotation")
        order = 0
        for p in fbx_rig._p70(m).elems:
            if p.props and p.props[0] == b"RotationOrder":
                order = int(p.props[4])
        self.order = _ORDERS.get(order, "XYZ")
        self.keys = {}                                  # "r0" -> curve_keys
        for attr, k, _d in self.ATTRS:
            _node, cs = index.channel(uid, attr)
            for i, c in enumerate(cs):
                if c is not None and c.first(b"KeyTime") is not None and len(c.first(b"KeyTime").props[0]):
                    self.keys[f"{k}{i}"] = curve_keys(c, fps)

    def channel_names(self, kind):
        return [n for n in (f"{kind}0", f"{kind}1", f"{kind}2") if n in self.keys]

    def first_frame(self):
        return min((ks[0][0] for ks in self.keys.values()), default=None)

    def frame_span(self, kind):
        names = self.channel_names(kind)
        if not names:
            return None
        return (min(self.keys[n][0][0] for n in names), max(self.keys[n][-1][0] for n in names))


def _rot(deg, order="XYZ"):
    return Euler([math.radians(a) for a in deg], order).to_matrix()


def joint_values(joint, scratch, frame):
    v = {}
    for k in "trs":
        d = joint.default[k]
        v[k] = Vector([scratch.value(f"{joint.uid}:{k}{i}", frame, d[i]) for i in range(3)])
    return v


def local_rotation(joint, r):
    """Rotation part of the FBX local matrix: Pre . R . Post^-1."""
    m = _rot(joint.pre) @ _rot(r, joint.order)
    if any(joint.post):
        m = m @ _rot(joint.post).inverted()
    return m


def local_matrix(joint, v):
    s = v["s"]
    return (Matrix.Translation(v["t"]) @ local_rotation(joint, v["r"]).to_4x4()
            @ Matrix.Diagonal((s.x, s.y, s.z, 1.0)))


def _signed_permutation(m3, tol=1e-4):
    """[(column j, sign)] per row i when ``m3`` (rows normalised) is a signed axis permutation, else None."""
    out = []
    used = set()
    for i in range(3):
        row = Vector(m3[i])
        n = row.length
        if n < 1e-9:
            return None
        row /= n
        j = max(range(3), key=lambda c: abs(row[c]))
        if abs(abs(row[j]) - 1.0) > tol or j in used:
            return None
        used.add(j)
        out.append((j, 1.0 if row[j] > 0 else -1.0))
    return out


# --- writing the bone channels ------------------------------------------------------------------------------------

def _bone_path(pb, prop):
    return f'pose.bones["{bpy.utils.escape_identifier(pb.name)}"].{prop}'


def _new_fcurve(arm, path, index, group):
    from .. import compat
    coll = compat.id_fcurve_collection(arm)
    fc = coll.find(path, index=index) if coll is not None else None
    if fc is None:
        arm.keyframe_insert(path, index=index, group=group)
        fc = next(c for c in compat.id_fcurves(arm) if c.data_path == path and c.array_index == index)
    return fc


def _clear_bone_curves(arm, pb):
    from .. import compat
    coll = compat.id_fcurve_collection(arm)
    if coll is None:
        return
    prefix = f'pose.bones["{bpy.utils.escape_identifier(pb.name)}"].'
    for fc in [c for c in coll if c.data_path.startswith(prefix)]:
        coll.remove(fc)


def _dense(arm, pb, prop, frames, values, interp='BEZIER'):
    for j in range(3):
        fc = _new_fcurve(arm, _bone_path(pb, prop), j, pb.name)
        kp = fc.keyframe_points
        kp.clear()
        kp.add(len(frames))
        for k, (f, v) in enumerate(zip(frames, values)):
            kp[k].co = (f, v[j])
            kp[k].interpolation = interp
            kp[k].handle_left_type = kp[k].handle_right_type = 'AUTO_CLAMPED'
        fc.update()


def _frames(span):
    a, b = span
    return list(range(math.floor(a + 1e-6), math.ceil(b - 1e-6) + 1))


# --- the fix ------------------------------------------------------------------------------------------------------

def has_skeleton(path):
    """True when the FBX file holds joints (LimbNode models)."""
    if fbx_rig.modules() is None:
        return False
    try:
        tree, _version = fbx_rig.load(path)
    except Exception:          # not a binary FBX Blender's parser reads: the reader reports it
        return False
    return bool(fbx_rig.Index(tree).limbs())


def _limb_parent(index, uid, limbs):
    p = index.parent.get(uid, 0)
    return p if p in limbs else (None if p not in index.models else False)


def fix_armature(context, arm, path):
    """Rebuild an imported armature's animation, axes and skin parenting the Maya way (module docstring).
    Returns a summary dict (``None`` when the file can't be read)."""
    if fbx_rig.modules() is None or arm.type != 'ARMATURE':
        return None
    tree, _version = fbx_rig.load(path)
    index = fbx_rig.Index(tree)
    scene = context.scene
    fps = file_fps(tree, scene)
    limbs = index.limbs()
    joints = {}
    for uid in limbs:
        j = Joint(index, uid, fps)
        if j.name in arm.pose.bones:
            joints[uid] = j
    if not joints:
        return None
    parents = {uid: _limb_parent(index, uid, limbs) for uid in joints}
    if any(p is False for p in parents.values()):
        return {"skipped": "root joint under another node"}
    scratch = Scratch()
    try:
        firsts = [f for f in (j.first_frame() for j in joints.values()) if f is not None]
        f0 = min(firsts) if firsts else scene.frame_current
        for j in joints.values():
            for name, keys in j.keys.items():
                scratch.add(f"{j.uid}:{name}", keys, f0)
        return _rebuild(context, arm, joints, parents, scratch, f0, tree, fps)
    finally:
        scratch.close()


def _world(joints, parents, scratch, uid, frame, cache):
    if uid in cache:
        return cache[uid]
    w = local_matrix(joints[uid], joint_values(joints[uid], scratch, frame))
    p = parents[uid]
    if p is not None:
        w = _world(joints, parents, scratch, p, frame, cache) @ w
    cache[uid] = w
    return w


def _rebuild(context, arm, joints, parents, scratch, f0, tree, fps):
    scene = context.scene
    frame_was = scene.frame_current
    # 2. bone corrections at f0 (Blender's own sampling is exact there), before anything moves
    scene.frame_set(math.floor(f0), subframe=f0 - math.floor(f0))
    cache = {}
    corr = {}
    for uid, j in joints.items():
        pb = arm.pose.bones[j.name]
        w = _world(joints, parents, scratch, uid, f0, cache).to_3x3().normalized()
        corr[uid] = w.transposed() @ pb.matrix.to_3x3().normalized()
    g = arm.matrix_world.copy()
    g_rot = g.to_3x3().normalized()
    s = g.to_scale()[0]
    # 5. skinned meshes leave the armature keeping their place; the conversion goes into the bones
    meshes = [o for o in arm.children if o.type == 'MESH']
    index = fbx_rig.Index(tree)
    for ob in meshes:
        mw = ob.matrix_world.copy()
        fw = model_world(index, ob.name)
        if fw is not None:
            # the mesh's place from the file (conversion @ its FBX world). Blender's reader parents a
            # skinned root mesh under the armature and, when the joints have no parent node (a file the kit wrote:
            # Maya layout), keeps the conversion on both -> 1/100 size turned 90 deg
            mw = g @ fw
        ob.parent = None
        ob.matrix_parent_inverse = Matrix.Identity(4)
        lin = mw.to_3x3()
        if ob.data.users == 1 and not _close3(lin, Matrix.Identity(3), 1e-6):
            ob.data.transform(lin.to_4x4(), shape_keys=True)      # Maya: rotate 0 / scale 1, points in place
            mw = Matrix.Translation(mw.translation)
        ob.matrix_world = mw
    _apply_conversion(context, arm, g)
    # 3./4. channels
    sparse_r = sparse_t = dense = 0
    for uid, j in joints.items():
        pb = arm.pose.bones[j.name]
        bone = pb.bone
        c = corr[uid]
        p = parents[uid]
        if p is None:
            k_rot = bone.matrix_local.to_3x3().normalized().transposed() @ g_rot
            a_t = k_rot * s
            b_t = bone.matrix_local.to_3x3().normalized().transposed() @ (g.translation - bone.matrix_local.translation)
        else:
            parent_bone = arm.pose.bones[joints[p].name].bone
            rest_rel = parent_bone.matrix_local.inverted() @ bone.matrix_local
            rr = rest_rel.to_3x3().normalized()
            k_rot = rr.transposed() @ corr[p].transposed()
            a_t = k_rot * s
            b_t = -(rr.transposed() @ rest_rel.translation)
        _clear_bone_curves(arm, pb)
        # rotation
        perm = _signed_permutation(c)          # row i of C = C^T e_i = Maya axis i in bone axes
        exact = perm is not None and _close3(k_rot @ _rot(j.pre), c.transposed()) and not any(j.post)
        rnames = j.channel_names("r")
        if exact:
            pb.rotation_mode = "".join(_AXES[perm[_AXES.index(ax)][0]] for ax in j.order)
            for i in range(3):
                col, sign = perm[i]
                name = f"r{i}"
                if name in j.keys:
                    fc = _new_fcurve(arm, _bone_path(pb, "rotation_euler"), col, pb.name)
                    fill_fcurve(fc, j.keys[name], a=sign * math.pi / 180.0)
                else:
                    pb.rotation_euler[col] = sign * math.radians(j.default["r"][i])
            sparse_r += bool(rnames)
        else:
            pb.rotation_mode = 'XYZ'
            span = j.frame_span("r")
            frames = _frames(span) if span else [f0]
            mats = [k_rot @ local_rotation(j, joint_values(j, scratch, f)["r"]) @ c for f in frames]
            from .. import rotation_display
            eul = rotation_display.euler_curve([m.to_quaternion() for m in mats], 'XYZ')
            if span:
                _dense(arm, pb, "rotation_euler", frames, eul)
                dense += 1
            pb.rotation_euler = eul[0]
        # translation
        tperm = _signed_permutation(_rows_normalised(a_t))
        tnames = j.channel_names("t")
        if tperm is not None:
            inv = {}                                      # Blender channel -> (Maya channel, factor)
            for row in range(3):
                col, sign = tperm[row]
                inv[row] = (col, a_t[row][col])
            for row in range(3):
                mi, fac = inv[row]
                name = f"t{mi}"
                if name in j.keys:
                    fc = _new_fcurve(arm, _bone_path(pb, "location"), row, pb.name)
                    fill_fcurve(fc, j.keys[name], a=fac, b=b_t[row])
                else:
                    pb.location[row] = fac * j.default["t"][mi] + b_t[row]
            sparse_t += bool(tnames)
        else:
            span = j.frame_span("t")
            frames = _frames(span) if span else [f0]
            locs = [a_t @ joint_values(j, scratch, f)["t"] + b_t for f in frames]
            if span:
                _dense(arm, pb, "location", frames, locs)
                dense += 1
            pb.location = locs[0]
        # scale (no sign, nearest axis)
        for i in range(3):
            col = max(range(3), key=lambda cc: abs(c[i][cc]))
            name = f"s{i}"
            if name in j.keys:
                fc = _new_fcurve(arm, _bone_path(pb, "scale"), col, pb.name)
                fill_fcurve(fc, j.keys[name])
            else:
                pb.scale[col] = j.default["s"][i]
    span = time_span(tree, fps)
    if span is not None:
        scene.frame_start, scene.frame_end = span
        if scene.use_preview_range:
            scene.frame_preview_start, scene.frame_preview_end = span
    scene.frame_set(frame_was if span is None else max(span[0], min(frame_was, span[1])))
    return {"joints": len(joints), "conversion": g, "meshes": meshes, "sparse_rotation": sparse_r, "sparse_translation": sparse_t, "dense": dense,
            "range": span}


def model_world(index, name):
    """World matrix of the FBX model called ``name`` (Blender may add ".001"), from its Lcl / Pre / Post values up
    the model hierarchy (file units and axes); None when absent."""
    base = name.split(".")[0] if name not in {fbx_rig.name_of(m) for m in index.models.values()} else name
    uid = next((u for u, m in index.models.items() if fbx_rig.name_of(m) == base and m.props[2] == b"Mesh"), None)
    if uid is None:
        return None

    def local(u):
        m = index.models[u]
        t = fbx_rig.get_vec(m, b"Lcl Translation")
        r = fbx_rig.rot_matrix(fbx_rig.get_vec(m, b"Lcl Rotation"))
        pre = fbx_rig.rot_matrix(fbx_rig.get_vec(m, b"PreRotation"))
        post = fbx_rig.rot_matrix(fbx_rig.get_vec(m, b"PostRotation"))
        sc = fbx_rig.get_vec(m, b"Lcl Scaling", (1.0, 1.0, 1.0))
        # FBX: T . Roff . Rp . Rpre . R . Rpost^-1 . Rp^-1 . Soff . Sp . S . Sp^-1
        roff, rp = (Matrix.Translation(fbx_rig.get_vec(m, n)) for n in (b"RotationOffset", b"RotationPivot"))
        soff, sp = (Matrix.Translation(fbx_rig.get_vec(m, n)) for n in (b"ScalingOffset", b"ScalingPivot"))
        return (Matrix.Translation(t) @ roff @ rp @ (pre @ r @ post.inverted_safe()).to_4x4() @ rp.inverted()
                @ soff @ sp @ Matrix.Diagonal((sc.x, sc.y, sc.z, 1.0)) @ sp.inverted())
    w = local(uid)
    p = index.parent.get(uid, 0)
    while p in index.models:
        w = local(p) @ w
        p = index.parent.get(p, 0)
    return w


def _rows_normalised(m3):
    return Matrix([Vector(r).normalized() if Vector(r).length > 1e-12 else Vector(r) for r in m3])


def _close3(a, b, tol=1e-4):
    return all(abs(a[i][k] - b[i][k]) < tol for i in range(3) for k in range(3))


def _apply_conversion(context, arm, g):
    """Move the armature object's matrix ``g`` into its bones (object = identity, world rest unchanged)."""
    if g == Matrix.Identity(4):
        return
    view_layer = context.view_layer
    prev_active = view_layer.objects.active
    prev_mode = arm.mode
    hidden = arm.hide_get(view_layer=view_layer) if arm.name in view_layer.objects else False
    if hidden:
        arm.hide_set(False, view_layer=view_layer)
    view_layer.objects.active = arm
    with context.temp_override(active_object=arm, object=arm, selected_objects=[arm],
                               selected_editable_objects=[arm]):
        bpy.ops.object.mode_set(mode='EDIT')
        for eb in arm.data.edit_bones:
            eb.transform(g, scale=True, roll=True)
        bpy.ops.object.mode_set(mode=prev_mode if prev_mode != 'EDIT' else 'OBJECT')
    arm.matrix_world = Matrix.Identity(4)
    if hidden:
        arm.hide_set(True, view_layer=view_layer)
    view_layer.objects.active = prev_active
