# SPDX-License-Identifier: GPL-3.0-or-later
"""Engine-ready skeletons in kit FBX files (Issue #145).

Maya's FBX holds joints only (control curves don't go out). A Blender
rig made with Rigify keeps its deforming bones (DEF-*) under helper bones (ORG-, MCH-, controls), and Blender's
``use_armature_deform_only`` still writes every non-deforming ancestor of a deforming bone: a Rigify human went out
with 278 joints for its 160 deforming ones. Two passes over the written file:

1. ``deform_parents`` (Blender side) names each deforming bone's joint parent in the file: the nearest deforming
   ancestor, or the deforming twin of a helper ancestor (Rigify's ORG-x / MCH-x / x sit where DEF-x sits), else
   none (a root). Nearest-deforming-ancestor alone gave the Rigify human 96 roots.
   ``reparent`` (FBX side) computes every LimbNode's world matrix from the file (each take, each key), gives the
   re-parented joints local = W_parent^-1 W, and deletes the joints that don't stay (model, attribute, curves,
   bind pose entry, connections). Runs before ``fbx_rig.rewrite``'s Null fold / PreRotation, on the rest file too.
2. ``safe_names``: Maya reads characters outside [A-Za-z0-9_] as FBXASC<code> (DEF-spine.001 ->
   DEFFBXASC045spineFBXASC046001); they become "_" in model / attribute / geometry / material names.
"""

import re

from mathutils import Matrix

from . import fbx_rig

PREFIXES = ("ORG-", "MCH-", "DEF-")


# --- Blender side -------------------------------------------------------------------------------------------------

def _base(name):
    for p in PREFIXES:
        if name.startswith(p):
            return name[len(p):]
    return name


def deform_parents(arm):
    """{deforming bone name: joint parent name or None} for armature data ``arm`` (module doc, 1)."""
    bones = arm.bones
    deform = {b.name for b in bones if b.use_deform}
    out = {}
    for b in bones:
        if not b.use_deform:
            continue
        below = {c.name for c in b.children_recursive} | {b.name}
        parent, p = None, b.parent
        while p is not None:
            if p.use_deform:
                parent = p.name
                break
            base = _base(p.name)
            twin = next((n for n in ("DEF-" + base, base) if n in deform and n not in below), None)
            if twin is not None:
                parent = twin
                break
            p = p.parent
        out[b.name] = parent
    # a twin step can close a loop (never seen in Rigify rigs): such a joint becomes a root
    for name in list(out):
        seen, cur = set(), name
        while cur is not None and cur not in seen:
            seen.add(cur)
            cur = out.get(cur)
        if cur is not None:
            out[name] = None
    return out


def changes_anything(parents, arm):
    """The file needs ``reparent``: a non-deforming joint would be written or a parent changes."""
    for b in arm.bones:
        if b.name not in parents:
            continue
        if (b.parent.name if b.parent else None) != parents[b.name]:
            return True
    return False


# --- FBX side -----------------------------------------------------------------------------------------------------

_ATTRS = (b"Lcl Translation", b"Lcl Rotation", b"Lcl Scaling")
_DEFAULTS = {b"Lcl Translation": (0.0, 0.0, 0.0), b"Lcl Rotation": (0.0, 0.0, 0.0), b"Lcl Scaling": (1.0, 1.0, 1.0)}


def _compose(t, r, s):
    return (Matrix.Translation(t) @ fbx_rig.rot_matrix(r).to_4x4() @ Matrix.Diagonal((s[0], s[1], s[2], 1.0)))


def _decompose(m, compat):
    t, q, s = m.decompose()
    deg, e = fbx_rig.to_degrees(q.to_matrix(), compat)
    return t, deg, s, e


def _layers(index):
    """{layer uid: {(model uid, attr): curve node}} — one AnimationLayer per take."""
    nodes = {e.props[0] for e in index.objects.find(b"AnimationCurveNode")}
    out = {}
    for (uid, attr), lst in index.curve_nodes_all.items():
        for node in lst:
            layer = index.parent.get(node.props[0])
            if node.props[0] in nodes:
                out.setdefault(layer, {})[(uid, attr)] = node
    return out


def _node_values(index, node, default):
    """(times, [[x, y, z] per key]) of a curve node, None when its curves don't share their key times."""
    cs = index.curves.get(node.props[0], {})
    cs = [cs.get(k) for k in (b"d|X", b"d|Y", b"d|Z")]
    times = next((fbx_rig._times(c) for c in cs if c is not None), None)
    if times is None or any(c is not None and fbx_rig._times(c) != times for c in cs):
        return None
    vals = [list(fbx_rig._values(c).props[0]) if c is not None else [default[i]] * len(times)
            for i, c in enumerate(cs)]
    return times, [[vals[0][k], vals[1][k], vals[2][k]] for k in range(len(times))]


def reparent(index, parents):
    """Keep only the joints named in ``parents`` {joint name: parent joint name or None} and hang them there.

    Joints not in ``parents`` keep their place (other armatures). Returns (joints kept, joints removed, re-parented).
    Raises ValueError when the file's curves can't be re-composed (keys at different times)."""
    limbs = index.limbs()
    by_name = {fbx_rig.name_of(m): uid for uid, m in limbs.items()}
    named = {n for n in parents if n in by_name}
    if not named:
        return 0, 0, 0

    def top(uid):                     # the non-joint frame the joints of this armature live in (its Null / scene)
        p = index.parent.get(uid, 0)
        while p in limbs:
            p = index.parent.get(p, 0)
        return p

    # joints of the armatures concerned = the subtrees of the Nulls holding a named joint
    frames = {top(by_name[n]) for n in named}
    scope = {uid for uid in limbs if top(uid) in frames}
    # a skinned joint never goes (its cluster needs it)
    drop = {uid for uid in scope if fbx_rig.name_of(limbs[uid]) not in parents} - _clustered(index)
    new_parent = {}
    for uid in scope - drop:
        name = fbx_rig.name_of(limbs[uid])
        if name in parents:
            want = parents[name]
            p_uid = by_name.get(want, top(uid)) if want is not None else top(uid)
        else:
            p_uid = index.parent.get(uid, 0)
        while p_uid in drop:
            p_uid = index.parent.get(p_uid, 0)
        if p_uid != index.parent.get(uid, 0):
            new_parent[uid] = p_uid

    def worlds(local):
        cache = {}

        def w(uid):
            if uid not in limbs:
                return Matrix.Identity(4)
            if uid not in cache:
                cache[uid] = w(index.parent.get(uid, 0)) @ local(uid)
            return cache[uid]
        return w

    def default_local(uid):
        m = limbs[uid]
        return _compose(*(fbx_rig.get_vec(m, a, _DEFAULTS[a]) for a in _ATTRS))

    # defaults (the frame the file was written at)
    w0 = worlds(default_local)
    new_defaults = {}
    for uid, p in new_parent.items():
        new_defaults[uid] = (w0(p).inverted_safe() @ w0(uid)) if p in limbs else w0(uid)
    # every take
    new_keys = []                     # (node, values) to write
    for layer, nodes in _layers(index).items():
        vals = {}
        times = None
        for (uid, attr), node in nodes.items():
            if uid not in scope or attr not in _ATTRS:
                continue
            got = _node_values(index, node, fbx_rig.get_vec(limbs[uid], attr, _DEFAULTS[attr]))
            if got is None or (times is not None and got[0] != times):
                raise ValueError("FBX deform-only: the joints' keys are at different times")
            times = got[0]
            vals[(uid, attr)] = got[1]
        if times is None:
            continue
        for uid in new_parent:
            for attr in _ATTRS:
                if (uid, attr) not in nodes:
                    raise ValueError(f"FBX deform-only: {fbx_rig.name_of(limbs[uid])} has no {attr.decode()} curve")
        out = {uid: {a: [] for a in _ATTRS} for uid in new_parent}
        prev = {}
        for k in range(len(times)):
            def local(uid, k=k):
                tv = [vals[(uid, a)][k] if (uid, a) in vals else fbx_rig.get_vec(limbs[uid], a, _DEFAULTS[a])
                      for a in _ATTRS]
                return _compose(*tv)
            wk = worlds(local)
            for uid, p in new_parent.items():
                m = (wk(p).inverted_safe() @ wk(uid)) if p in limbs else wk(uid)
                t, deg, s, e = _decompose(m, prev.get(uid))
                prev[uid] = e
                out[uid][b"Lcl Translation"].append(t)
                out[uid][b"Lcl Rotation"].append(deg)
                out[uid][b"Lcl Scaling"].append(s)
        for uid, per in out.items():
            for attr, values in per.items():
                node = nodes[(uid, attr)]
                cs = index.curves.get(node.props[0], {})
                new_keys.append((node, [cs.get(k) for k in (b"d|X", b"d|Y", b"d|Z")], values))
    for node, cs, values in new_keys:
        if any(c is None for c in cs):
            raise ValueError("FBX deform-only: a joint curve set is incomplete")
        fbx_rig.write_keys(node, cs, values)
    for uid, m in new_defaults.items():
        t, deg, s, _e = _decompose(m, None)
        model = limbs[uid]
        fbx_rig.set_vec(model, b"Lcl Translation", t, b"Lcl Translation", b"", b"A")
        fbx_rig.set_vec(model, b"Lcl Rotation", deg, b"Lcl Rotation", b"", b"A")
        fbx_rig.set_vec(model, b"Lcl Scaling", s, b"Lcl Scaling", b"", b"A")
    # hierarchy: re-parented joints, and every other model under a dropped joint, to their new parents
    for c in index.conns.elems:
        if c.props[0] == b"OO" and c.props[1] in new_parent:
            c.props[2] = new_parent[c.props[1]]
    _remove(index, drop)
    return len(scope - drop), len(drop), len(new_parent)


def _cluster_links(index):
    """{cluster uid: joint uid} (the joint is the cluster's child in the connections)."""
    clusters = {d.props[0] for d in index.objects.find(b"Deformer") if d.props[2] == b"Cluster"}
    return {c.props[2]: c.props[1] for c in index.conns.elems if c.props[0] == b"OO" and c.props[2] in clusters}


def _clustered(index):
    """Joints with skin weights. Blender writes a cluster for every joint of the skinned mesh's armature, weightless
    ones included: those don't keep a joint."""
    weighted = set()
    for d in index.objects.find(b"Deformer"):
        if d.props[2] != b"Cluster":
            continue
        idx = d.first(b"Indexes")
        if idx is not None and len(idx.props[0]):
            weighted.add(d.props[0])
    return {j for cl, j in _cluster_links(index).items() if cl in weighted}


def _remove(index, drop):
    """Delete models ``drop`` with their node attributes, curve nodes, curves, bind pose entries and connections."""
    if not drop:
        return
    gone = set(drop)
    gone |= {cl for cl, j in _cluster_links(index).items() if j in drop}      # their (weightless) clusters
    for c in index.conns.elems:                       # attributes and curve nodes hanging on a dropped model
        if c.props[2] in drop and c.props[1] not in index.models:
            gone.add(c.props[1])
    for c in index.conns.elems:                       # curves of those curve nodes
        if c.props[2] in gone and c.props[1] not in index.models:
            gone.add(c.props[1])
    # children of a dropped joint that aren't joints (meshes parented to a bone): up to the nearest kept ancestor
    for c in index.conns.elems:
        if c.props[0] == b"OO" and c.props[2] in drop and c.props[1] in index.models and c.props[1] not in drop:
            p = c.props[2]
            while p in drop:
                p = index.parent.get(p, 0)
            c.props[2] = p
    index.conns.elems = [c for c in index.conns.elems if c.props[1] not in gone and c.props[2] not in gone]
    removed = {}
    keep = []
    for e in index.objects.elems:
        if e.props and e.props[0] in gone:
            removed[e.id] = removed.get(e.id, 0) + 1
        else:
            keep.append(e)
    index.objects.elems = keep
    for pose in index.objects.find(b"Pose"):
        pose.elems = [pn for pn in pose.elems if not (pn.id == b"PoseNode" and pn.first(b"Node") is not None
                                                      and pn.first(b"Node").props[0] in gone)]
        nb = pose.first(b"NbPoseNodes")
        if nb is not None:
            nb.props[0] = len(pose.find(b"PoseNode"))
    defs = index.tree.first(b"Definitions")
    if defs is not None:
        for ot in defs.find(b"ObjectType"):
            n, cnt = removed.get(ot.props[0]), ot.first(b"Count")
            if n and cnt is not None:
                cnt.props[0] = max(0, cnt.props[0] - n)
        total = defs.first(b"Count")
        if total is not None:
            total.props[0] = max(0, total.props[0] - sum(removed.values()))


# --- Maya-safe names ----------------------------------------------------------------------------------------------

_UNSAFE = re.compile(r"[^A-Za-z0-9_]")
_NAMED = (b"Model", b"NodeAttribute", b"Geometry", b"Material")


def maya_name(name):
    """``name`` with Maya's node-name characters only: DEF-spine.001 -> DEF_spine_001, 3d -> _3d."""
    out = _UNSAFE.sub("_", name)
    if not out or out[0].isdigit():
        out = "_" + out
    return out


def _split(prop):
    raw = prop.split(b"\x00\x01")
    return raw[0].decode("utf-8", "replace"), (b"\x00\x01" + raw[1]) if len(raw) > 1 else b""


def safe_names(tree):
    """Rename every model / attribute / geometry / material in ``tree`` to a Maya-safe name (models stay unique,
    an attribute / geometry follows its model). Returns {old: new} of the renamed models."""
    objects = tree.first(b"Objects")
    used, renamed = set(), {}
    models = objects.find(b"Model")
    for m in models:
        used.add(_split(m.props[1])[0])
    for m in models:
        name, tail = _split(m.props[1])
        new = maya_name(name)
        if new == name:
            continue
        used.discard(name)
        base, n = new, 1
        while new in used:
            new, n = f"{base}_{n}", n + 1
        used.add(new)
        renamed[name] = new
        m.props[1] = new.encode("utf-8") + tail
    for e in objects.elems:
        if e.id == b"Model" or e.id not in _NAMED or len(e.props) < 2 or not isinstance(e.props[1], bytes):
            continue
        name, tail = _split(e.props[1])
        new = renamed.get(name, maya_name(name))
        if new != name:
            e.props[1] = new.encode("utf-8") + tail
    return renamed


def rewrite_names(path):
    """``safe_names`` on the file at ``path`` (saved only when something changed). Returns the count renamed."""
    tree, version = fbx_rig.load(path)
    renamed = safe_names(tree)
    if renamed:
        fbx_rig.save(path, tree, version)
    return len(renamed)
