# SPDX-License-Identifier: GPL-3.0-or-later
"""Rig FBX the way Maya 2026 writes it (Issue #132).

Blender's FBX writer puts the rest orientation (and the current frame's pose) of every joint into ``Lcl Rotation`` and
writes the armature object as a ``Null`` (Lcl Rotation -90 X / Lcl Scaling 100 for the kit's Y-up cm preset), joint
translations in metres under it. Maya writes a joint's orientation as ``PreRotation`` (= jointOrient) with rotate 0
at rest, translations in cm, no extra node. ``rewrite`` turns the
first into the second with Blender's bundled ``io_scene_fbx.parse_fbx`` / ``encode_bin`` (same module 4.5 - 5.2):

1. Fold each armature ``Null`` (rotation R_N, uniform scale s, translation T_N) into its root joints: root
   t' = T_N + R_N (s t), R' = R_N R; every joint translation (default and curve keys) x s; the bone world matrices
   of the bind pose / skin clusters lose the scale (their rotation part / s), cluster ``Transform`` follows
   (TransformLink^-1 @ mesh world). The Null, its attribute and connections go.
2. PreRotation = the joint's rest rotation, read from a second export of the same objects at the rest pose
   (``rest_rotations``): the writer's own axis conventions, never the current frame.
   Lcl Rotation default and keys become Pre^-1 R(t), compat Euler (``rotation_display.euler_curve``'s rule).

3. Joints whose Maya frame a bone can't take (``joints.MAYA_FRAME``: an oriented end joint lines up with
   the world, a Behavior-mirrored joint points X back up the chain) turn their frame by Q_j (joint axes). The local
   matrix becomes Q_p^-1 L Q_j (Q_p = the parent joint's turn): PreRotation = Q_p^-1 R_rest Q_j, Lcl Rotation =
   Q_j^-1 R_rest^-1 R(t) Q_j, Lcl Translation = Q_p^-1 t; models under a turned joint get Q_p^-1 on rotation and
   translation; skin clusters / bind pose of a turned joint: TransformLink Q_j, Transform = Q_j^-1 Transform. The
   joints' world positions and the skinned mesh don't change.

An animated armature object (curves on the Null) keeps its Null: only item 2 runs.
"""

import array
import math

from mathutils import Euler, Matrix, Vector

_ADD = {ord('B'): "add_bool", ord('C'): "add_char", ord('Z'): "add_int8", ord('Y'): "add_int16",
        ord('I'): "add_int32", ord('L'): "add_int64", ord('F'): "add_float32", ord('D'): "add_float64",
        ord('R'): "add_bytes", ord('S'): "add_string", ord('i'): "add_int32_array", ord('l'): "add_int64_array",
        ord('f'): "add_float32_array", ord('d'): "add_float64_array", ord('b'): "add_bool_array",
        ord('c'): "add_byte_array"}


def modules():
    """(parse_fbx, encode_bin) of Blender's bundled FBX add-on, or None (works with the add-on disabled)."""
    try:
        from io_scene_fbx import encode_bin, parse_fbx
    except ImportError:
        return None
    return parse_fbx, encode_bin


class Elem:
    """A mutable FBX element (parse_fbx gives tuples)."""
    __slots__ = ("id", "props", "types", "elems")

    def __init__(self, id_, props=None, types=b"", elems=None):
        self.id, self.props, self.types, self.elems = id_, list(props or ()), bytearray(types), list(elems or ())

    @classmethod
    def of(cls, e):
        return cls(e.id, e.props, e.props_type, [cls.of(c) for c in e.elems])

    def find(self, id_):
        return [c for c in self.elems if c.id == id_]

    def first(self, id_):
        return next((c for c in self.elems if c.id == id_), None)


def _encode(encode_bin, e):
    n = encode_bin.FBXElem(e.id)
    for p, t in zip(e.props, e.types):
        getattr(n, _ADD[t])(p)
    n.elems = [_encode(encode_bin, c) for c in e.elems]
    return n


def load(path):
    parse_fbx, _enc = modules()
    root, version = parse_fbx.parse(path)
    return Elem.of(root), version


def save(path, tree, version):
    _parse, encode_bin = modules()
    out = encode_bin.FBXElem(b"")
    out.elems = [_encode(encode_bin, c) for c in tree.elems]
    encode_bin.write(path, out, version)


# --- Properties70 -----------------------------------------------------------------------------------------------

def _p70(model):
    p = model.first(b"Properties70")
    if p is None:
        p = Elem(b"Properties70")
        model.elems.append(p)
    return p


def get_vec(model, name, default=(0.0, 0.0, 0.0)):
    for p in _p70(model).elems:
        if p.props and p.props[0] == name:
            return Vector([float(x) for x in p.props[4:7]])
    return Vector(default)


def set_vec(model, name, value, kind=b"Vector3D", sub=b"Vector", flag=b""):
    for p in _p70(model).elems:
        if p.props and p.props[0] == name:
            break
    else:
        p = Elem(b"P")
        _p70(model).elems.append(p)
    p.props = [name, kind, sub, flag] + [float(x) for x in value]
    p.types = bytearray(b"SSSS" + b"D" * len(value))


def set_int(model, name, value, kind=b"int", sub=b"Integer"):
    for p in _p70(model).elems:
        if p.props and p.props[0] == name:
            p.props[4] = int(value)
            return
    _p70(model).elems.append(Elem(b"P", [name, kind, sub, b"", int(value)], b"SSSSI"))


def name_of(model):
    return model.props[1].split(b"\x00\x01")[0].decode("utf-8", "replace")


# --- tree index ---------------------------------------------------------------------------------------------------

class Index:
    def __init__(self, tree):
        self.tree = tree
        self.objects = tree.first(b"Objects")
        self.conns = tree.first(b"Connections")
        self.models = {m.props[0]: m for m in self.objects.find(b"Model")}
        self.parent = {}                      # child uid -> parent uid (OO)
        self.curve_nodes = {}                 # (model uid, b"Lcl Rotation") -> curve node
        self.curve_nodes_all = {}             # every take's curve node (Game Exporter clips = takes)
        self.curves = {}                      # curve node uid -> {b"d|X": curve elem}
        nodes = {e.props[0]: e for e in self.objects.find(b"AnimationCurveNode")}
        curves = {e.props[0]: e for e in self.objects.find(b"AnimationCurve")}
        for c in self.conns.elems:
            kind, a, b = c.props[0], c.props[1], c.props[2]
            if kind == b"OO":
                self.parent.setdefault(a, b)
            elif kind == b"OP" and a in nodes and b in self.models:
                self.curve_nodes[(b, c.props[3])] = nodes[a]
                self.curve_nodes_all.setdefault((b, c.props[3]), []).append(nodes[a])
            elif kind == b"OP" and a in curves and b in nodes:
                self.curves.setdefault(b, {})[c.props[3]] = curves[a]

    def limbs(self):
        return {uid: m for uid, m in self.models.items() if m.props[2] == b"LimbNode"}

    def channel(self, uid, attr):
        """[curve elem X, Y, Z] (None where absent) of a model's Lcl attribute, and its curve node."""
        node = self.curve_nodes.get((uid, attr))
        if node is None:
            return None, [None, None, None]
        cs = self.curves.get(node.props[0], {})
        return node, [cs.get(k) for k in (b"d|X", b"d|Y", b"d|Z")]


def _values(curve):
    return curve.first(b"KeyValueFloat") if curve is not None else None


def _times(curve):
    t = curve.first(b"KeyTime") if curve is not None else None
    return list(t.props[0]) if t is not None else None


def channel_keys_all(index, uid, attr, default):
    """``channel_keys`` of the attribute's curve node in every take (a file with several takes has one each)."""
    out = []
    for node in index.curve_nodes_all.get((uid, attr), []):
        one = _node_keys(index, node, default)
        if one is not None:
            out.append(one)
    return out


def _node_keys(index, node, default):
    cs = index.curves.get(node.props[0], {})
    cs = [cs.get(k) for k in (b"d|X", b"d|Y", b"d|Z")]
    if not any(cs):
        return None
    times = next((_times(c) for c in cs if c is not None), None)
    if any(c is not None and _times(c) != times for c in cs):
        return None
    vals = [list(_values(c).props[0]) if c is not None else [default[i]] * len(times) for i, c in enumerate(cs)]
    return times, [Vector((vals[0][k], vals[1][k], vals[2][k])) for k in range(len(times))], node, cs


def channel_keys(index, uid, attr, default):
    """(times, [Vector per key]) of a model's animated attribute; None when it has no full curve set."""
    node, cs = index.channel(uid, attr)
    if node is None or not any(cs):
        return None
    times = next((_times(c) for c in cs if c is not None), None)
    if any(c is not None and _times(c) != times for c in cs):
        return None                       # keys at different times: not re-composable (simplify factor > 0)
    vals = [list(_values(c).props[0]) if c is not None else [default[i]] * len(times) for i, c in enumerate(cs)]
    return times, [Vector((vals[0][k], vals[1][k], vals[2][k])) for k in range(len(times))], node, cs


def write_keys(node, cs, values):
    for i, c in enumerate(cs):
        if c is None:
            continue
        v = _values(c)
        v.props[0] = array.array('f', [float(x[i]) for x in values])
    p70 = node.first(b"Properties70")
    if p70 is not None:
        for p in p70.elems:
            i = {b"d|X": 0, b"d|Y": 1, b"d|Z": 2}.get(p.props[0] if p.props else None)
            if i is not None and values:
                p.props[4] = float(values[0][i])


def rot_matrix(deg):
    return Euler([math.radians(a) for a in deg], 'XYZ').to_matrix()


def to_degrees(m3, compat=None):
    e = m3.to_euler('XYZ', compat) if compat is not None else m3.to_euler('XYZ')
    return Vector([math.degrees(a) for a in e]), e


# --- rest rotations -----------------------------------------------------------------------------------------------

def rest_rotations(index):
    """{joint name: (rest rotation matrix incl. a folded Null for roots, rest translation)} from a rest export."""
    out = {}
    for uid, m in index.limbs().items():
        r = rot_matrix(get_vec(m, b"Lcl Rotation"))
        par = index.models.get(index.parent.get(uid))
        if par is not None and par.props[2] == b"Null":
            r = rot_matrix(get_vec(par, b"Lcl Rotation")) @ r
        out[name_of(m)] = r
    return out


# --- the rewrite --------------------------------------------------------------------------------------------------

def _uniform(scale):
    return abs(scale.x - scale.y) < 1e-6 * abs(scale.x) and abs(scale.x - scale.z) < 1e-6 * abs(scale.x)


def _subtree(index, uid):
    kids = {}
    for c, p in index.parent.items():
        kids.setdefault(p, []).append(c)
    out, todo = [], list(kids.get(uid, ()))
    while todo:
        u = todo.pop()
        out.append(u)
        todo.extend(kids.get(u, ()))
    return out


def _armature_nulls(index):
    limbs = index.limbs()
    out = []
    for uid, m in index.models.items():
        if m.props[2] != b"Null":
            continue
        if any(index.parent.get(l) == uid for l in limbs):
            out.append((uid, m, _moves(index, uid)))
    return out


def _moves(index, uid):
    """The model's curves change over time (the writer bakes constant curves for every object too)."""
    for attr in (b"Lcl Translation", b"Lcl Rotation", b"Lcl Scaling"):
        cs = [c for node in index.curve_nodes_all.get((uid, attr), [])
              for c in index.curves.get(node.props[0], {}).values()]
        for c in cs:
            vals = _values(c)
            if vals is not None and len(vals.props[0]) and max(vals.props[0]) - min(vals.props[0]) > 1e-6:
                return True
    return False


def _scale_matrix_array(arr, s):
    vals = list(arr)
    for i in (0, 1, 2, 4, 5, 6, 8, 9, 10):
        vals[i] /= s
    return vals


def _mat(arr):
    v = list(arr)
    return Matrix([v[0:4], v[4:8], v[8:12], v[12:16]]).transposed()      # FBX arrays are column-major


def _arr(m):
    return [f for col in m.transposed() for f in col]


def fold_null(index, uid, null):
    """Fold an armature Null into its root joints (see the module doc). Returns the number of roots."""
    t_n = get_vec(null, b"Lcl Translation")
    r_n = rot_matrix(get_vec(null, b"Lcl Rotation"))
    s_vec = get_vec(null, b"Lcl Scaling", (1.0, 1.0, 1.0))
    s = s_vec.x
    limbs = index.limbs()
    inside = [u for u in _subtree(index, uid) if u in limbs]
    roots = [u for u in inside if index.parent.get(u) == uid]
    # every joint translation x s (defaults and curve keys)
    for u in inside:
        m = index.models[u]
        set_vec(m, b"Lcl Translation", get_vec(m, b"Lcl Translation") * s, b"Lcl Translation", b"", b"A")
        for keys in channel_keys_all(index, u, b"Lcl Translation", get_vec(m, b"Lcl Translation")):
            if u not in roots:
                times, vals, node, cs = keys
                write_keys(node, cs, [v * s for v in vals])
    # roots take the Null's rotation / translation
    for u in roots:
        m = index.models[u]
        t = get_vec(m, b"Lcl Translation")                       # already x s
        r = rot_matrix(get_vec(m, b"Lcl Rotation"))
        set_vec(m, b"Lcl Translation", t_n + r_n @ t, b"Lcl Translation", b"", b"A")
        set_vec(m, b"Lcl Rotation", to_degrees(r_n @ r)[0], b"Lcl Rotation", b"", b"A")
        for tk in channel_keys_all(index, u, b"Lcl Translation", get_vec(m, b"Lcl Translation")):
            times, vals, node, cs = tk
            write_keys(node, cs, [t_n + r_n @ (v * s) for v in vals])
        for rk in channel_keys_all(index, u, b"Lcl Rotation", get_vec(m, b"Lcl Rotation")):
            times, vals, node, cs = rk
            out, prev = [], None
            for v in vals:
                deg, prev = to_degrees(r_n @ rot_matrix(v), prev)
                out.append(deg)
            write_keys(node, cs, out)
    # bone world matrices in the bind pose and skin clusters lose the scale
    names = {u for u in inside}
    for pose in index.objects.find(b"Pose"):
        for pn in pose.find(b"PoseNode"):
            node = pn.first(b"Node")
            mat = pn.first(b"Matrix")
            if node is not None and mat is not None and node.props[0] in names:
                mat.props[0] = array.array('d', _scale_matrix_array(mat.props[0], s))
        pose.elems = [pn for pn in pose.elems if not (pn.id == b"PoseNode" and pn.first(b"Node") is not None
                                                      and pn.first(b"Node").props[0] == uid)]
        nb = pose.first(b"NbPoseNodes")
        if nb is not None:
            nb.props[0] = len(pose.find(b"PoseNode"))
    clusters = {d.props[0]: d for d in index.objects.find(b"Deformer") if d.props[2] == b"Cluster"}
    link = {}
    for c in index.conns.elems:
        if c.props[0] == b"OO" and c.props[2] in clusters and c.props[1] in names:
            link[c.props[2]] = c.props[1]
    for cid, d in clusters.items():
        if cid not in link:
            continue
        tl, tr = d.first(b"TransformLink"), d.first(b"Transform")
        if tl is None or tr is None:
            continue
        old_link = _mat(tl.props[0])
        mesh_world = old_link @ _mat(tr.props[0])
        new_link = _mat(_scale_matrix_array(tl.props[0], s))
        tl.props[0] = array.array('d', _arr(new_link))
        tr.props[0] = array.array('d', _arr(new_link.inverted_safe() @ mesh_world))
    # roots to the scene root, the Null gone (with its attribute and its constant curves)
    attr = {c.props[1] for c in index.conns.elems if c.props[0] in (b"OO", b"OP") and c.props[2] == uid
            and c.props[1] not in index.models}
    for a in list(attr):
        attr.update(index.curves.get(a, {}) and {cv.props[0] for cv in index.curves[a].values()})
    conns = []
    for c in index.conns.elems:
        a, b = c.props[1], c.props[2]
        if c.props[0] == b"OO" and a in roots and b == uid:
            c.props[2] = 0
        elif a == uid or b == uid or a in attr:
            continue
        conns.append(c)
    index.conns.elems = conns
    index.objects.elems = [e for e in index.objects.elems if e.props[0] not in attr and e.props[0] != uid]
    return len(roots)


def _turn_keys(index, uid, attr, fn):
    m = index.models[uid]
    default = get_vec(m, attr)
    for rk in channel_keys_all(index, uid, attr, default):
        times, vals, node, cs = rk
        out, prev = [], None
        for v in vals:
            res = fn(v, prev)
            if isinstance(res, tuple):
                res, prev = res
            out.append(res)
        write_keys(node, cs, out)


def apply_prerotation(index, rest, turns=None):
    """PreRotation = rest rotation, Lcl Rotation (default and keys) = Pre^-1 R — with the frame turns of
    ``turns`` {joint name: Q} (module doc, 3). Returns the joints changed."""
    n = 0
    turns = turns or {}
    limbs = index.limbs()
    by_uid = {uid: turns.get(name_of(m)) for uid, m in limbs.items()}
    for uid, m in index.models.items():
        qj = by_uid.get(uid)
        par = index.parent.get(uid)
        qp = by_uid.get(par) if par in limbs else None
        qpi = qp.inverted() if qp is not None else None
        if uid not in limbs:
            if qpi is None:
                continue                              # a model under a turned joint follows the turn
            set_vec(m, b"Lcl Translation", qpi @ get_vec(m, b"Lcl Translation"), b"Lcl Translation", b"", b"A")
            set_vec(m, b"Lcl Rotation", to_degrees(qpi @ rot_matrix(get_vec(m, b"Lcl Rotation")))[0],
                    b"Lcl Rotation", b"", b"A")
            _turn_keys(index, uid, b"Lcl Translation", lambda v, _p: qpi @ v)
            _turn_keys(index, uid, b"Lcl Rotation", lambda v, p: to_degrees(qpi @ rot_matrix(v), p))
            continue
        r_rest = rest.get(name_of(m))
        if r_rest is None:
            continue
        pre = r_rest
        if qpi is not None:
            pre = qpi @ pre
        if qj is not None:
            pre = pre @ qj
        inv = pre.inverted_safe()

        def local(r, qpi=qpi, qj=qj, inv=inv):
            out = qpi @ r if qpi is not None else r
            return inv @ out @ qj if qj is not None else inv @ out
        set_vec(m, b"PreRotation", to_degrees(pre)[0])
        set_int(m, b"RotationActive", 1, b"bool", b"")
        set_vec(m, b"Lcl Rotation", to_degrees(local(rot_matrix(get_vec(m, b"Lcl Rotation"))))[0],
                b"Lcl Rotation", b"", b"A")
        _turn_keys(index, uid, b"Lcl Rotation", lambda v, p, local=local: to_degrees(local(rot_matrix(v)), p))
        if qpi is not None:
            set_vec(m, b"Lcl Translation", qpi @ get_vec(m, b"Lcl Translation"), b"Lcl Translation", b"", b"A")
            _turn_keys(index, uid, b"Lcl Translation", lambda v, _p, qpi=qpi: qpi @ v)
        n += 1
    return n


def turn_skin(index, turns):
    """Skin clusters and bind pose of the turned joints follow their frames (module doc, 3)."""
    uids = {uid: turns[name_of(m)].to_4x4() for uid, m in index.limbs().items() if name_of(m) in turns}
    if not uids:
        return
    for pose in index.objects.find(b"Pose"):
        for pn in pose.find(b"PoseNode"):
            node, mat = pn.first(b"Node"), pn.first(b"Matrix")
            if node is not None and mat is not None and node.props[0] in uids:
                mat.props[0] = array.array('d', _arr(_mat(mat.props[0]) @ uids[node.props[0]]))
    clusters = {d.props[0]: d for d in index.objects.find(b"Deformer") if d.props[2] == b"Cluster"}
    for c in index.conns.elems:
        if c.props[0] == b"OO" and c.props[2] in clusters and c.props[1] in uids:
            d, q4 = clusters[c.props[2]], uids[c.props[1]]
            tl, tr = d.first(b"TransformLink"), d.first(b"Transform")
            if tl is None or tr is None:
                continue
            tl.props[0] = array.array('d', _arr(_mat(tl.props[0]) @ q4))
            tr.props[0] = array.array('d', _arr(q4.inverted_safe() @ _mat(tr.props[0])))


KTIME = 46186158000            # FBX ticks per second


def set_time_span(path, start, end, fps):
    """GlobalSettings TimeSpan = the Time Slider range like Maya writes it (Blender's writer puts 0 .. 1 s there)."""
    tree, version = load(path)
    gs = tree.first(b"GlobalSettings")
    p70 = _p70(gs) if gs is not None else None
    if p70 is None:
        return False
    vals = {b"TimeSpanStart": int(round(start / fps * KTIME)), b"TimeSpanStop": int(round(end / fps * KTIME))}
    have = {p.props[0]: p for p in p70.elems if p.props}
    for name, v in vals.items():
        if name in have:
            have[name].props[4] = v
        else:
            p70.elems.append(Elem(b"P", [name, b"KTime", b"Time", b"", v], b"SSSSL"))
    save(path, tree, version)
    return True


def rewrite(path, rest_path, turns=None, parents=None):
    """Rewrite the rig FBX at ``path`` the Maya way; ``rest_path`` = the same export at the rest pose; ``turns`` =
    {joint name: Q} (joints.maya_frames); ``parents`` = {joint name: parent name or None}: only those joints stay,
    hung there (``fbx_skeleton.reparent``). Returns (joints given a PreRotation, Nulls folded)."""
    tree, version = load(path)
    rest_tree, _v = load(rest_path)
    index, rest_index = Index(tree), Index(rest_tree)
    if parents:
        from . import fbx_skeleton
        fbx_skeleton.reparent(index, parents)
        fbx_skeleton.reparent(rest_index, parents)
        index, rest_index = Index(tree), Index(rest_tree)
    rest = rest_rotations(rest_index)
    folded = 0
    for uid, null, animated in _armature_nulls(index):
        s = get_vec(null, b"Lcl Scaling", (1.0, 1.0, 1.0))
        if animated or not _uniform(s):
            continue
        fold_null(index, uid, null)
        folded += 1
        index = Index(tree)
    turns = {k: v for k, v in (turns or {}).items()}
    joints = apply_prerotation(index, rest, turns)
    turn_skin(index, turns)
    save(path, tree, version)
    return joints, folded


# --- evaluation (tests, and a self-check of the written file) ------------------------------------------------------

def world_matrices(index, sample=None):
    """{joint name: world Matrix} from the file's values: T . Pre . R . S down the OO hierarchy; ``sample`` = key
    index to read from the curves instead of the defaults."""
    out = {}

    def local(uid):
        m = index.models[uid]
        t, r, s = get_vec(m, b"Lcl Translation"), get_vec(m, b"Lcl Rotation"), get_vec(m, b"Lcl Scaling", (1, 1, 1))
        if sample is not None:
            for attr, cur in ((b"Lcl Translation", t), (b"Lcl Rotation", r), (b"Lcl Scaling", s)):
                keys = channel_keys(index, uid, attr, cur)
                if keys is not None:
                    cur[:] = keys[1][min(sample, len(keys[1]) - 1)]
        pre = rot_matrix(get_vec(m, b"PreRotation"))
        return (Matrix.Translation(t) @ (pre @ rot_matrix(r)).to_4x4()
                @ Matrix.Diagonal((s.x, s.y, s.z, 1.0)))

    def world(uid):
        p = index.parent.get(uid, 0)
        w = local(uid)
        return world(p) @ w if p in index.models else w

    for uid, m in index.limbs().items():
        out[name_of(m)] = world(uid)
    return out
