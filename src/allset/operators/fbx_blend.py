# SPDX-License-Identifier: GPL-3.0-or-later
"""Blend shapes in the FBX the way Maya 2026 writes them (Issue #144).

Blender's writer gives every shape key its own BlendShapeChannel, so a kit in-between (a hidden key
``<target>_ib<w>`` plus the ``<target>_ibfix`` copy, operators/blend_shapes_227.py) reached Maya / engines as extra
targets, and the BlendShape deformer was named after the mesh. Maya writes one channel per target holding its
in-between shapes, FullWeights = the in-between weights x 100 then 100 (bulge items 5500 / 6000),
and the deformer is the blendShape node.

``rewrite`` (after Blender's writer): each in-between's Shape moves under its
target's channel in weight order, the helper channels / fix shapes go, FullWeights = Maya's, the deformer takes the
Key's Maya name (``blendShapeN``).
"""

import array

from . import fbx_rig


def _text(v):
    return v.decode("utf-8", "replace") if isinstance(v, bytes) else str(v)


def rewrite(path, objects):
    """Rewrite the blend shapes of ``objects`` (exported meshes) in the FBX at ``path``. Returns the number of
    in-betweens folded into their targets."""
    from . import blend_shapes_227 as bs
    keys = {}
    for ob in objects:
        key = getattr(getattr(ob, "data", None), "shape_keys", None) if ob.type == 'MESH' else None
        if key is not None and len(key.key_blocks) > 1:
            keys[ob.name] = key
    if not keys:
        return 0
    tree, version = fbx_rig.load(path)
    objs, conns = tree.first(b"Objects"), tree.first(b"Connections")
    ids = {e.props[0]: e for e in objs.elems if e.props}
    parent_of = {}
    children = {}
    for c in conns.elems:
        if c.props[0] == b"OO":
            parent_of.setdefault(c.props[1], c.props[2])
            children.setdefault(c.props[2], []).append(c.props[1])
    drop = set()
    folded = 0
    for d in [e for e in objs.find(b"Deformer") if e.props[2] == b"BlendShape"]:
        geom = ids.get(parent_of.get(d.props[0]))
        model = ids.get(parent_of.get(geom.props[0])) if geom is not None else None
        key = keys.get(fbx_rig.name_of(model)) if model is not None else None
        if key is None:
            continue
        if key.name.startswith("blendShape"):
            tail = d.props[1][d.props[1].index(b"\x00\x01"):] if b"\x00\x01" in d.props[1] else b""
            d.props[1] = key.name.encode("utf-8") + tail
        chans = {fbx_rig.name_of(ids[u]): ids[u] for u in children.get(d.props[0], ())
                 if u in ids and ids[u].props[2] == b"BlendShapeChannel"}

        def shape_of(ch):
            return next((ids[u] for u in children.get(ch.props[0], ()) if u in ids and ids[u].props[2] == b"Shape"),
                        None)
        for ch in chans.values():                   # Maya: one full weight per shape (Blender writes one per vertex)
            fw = ch.first(b"FullWeights")
            if fw is not None and len(fw.props[0]) != 1:
                fw.props[0] = array.array('d', [100.0])
        for target, items in bs.inbetweens(key).items():
            ch_t = chans.get(target)
            s_t = shape_of(ch_t) if ch_t is not None else None
            if s_t is None:
                continue
            shapes, weights = [], []
            for w, _name in items:
                ch_ib = chans.get(bs.ib_name(target, w))
                s_ib = shape_of(ch_ib) if ch_ib is not None else None
                if s_ib is None:
                    continue
                shapes.append(s_ib)
                weights.append(100.0 * w)
                drop.add(ch_ib.props[0])
                folded += 1
            fix = chans.get(bs.fix_name(target))
            if fix is not None:
                drop.add(fix.props[0])
                s_fix = shape_of(fix)
                if s_fix is not None:
                    drop.add(s_fix.props[0])
            moved = {s.props[0] for s in shapes} | {s_t.props[0]}
            conns.elems = [c for c in conns.elems if not (c.props[0] == b"OO" and c.props[1] in moved)]
            for s in shapes + [s_t]:
                conns.elems.append(fbx_rig.Elem(b"C", [b"OO", s.props[0], ch_t.props[0]], b"SLL"))
            fw = ch_t.first(b"FullWeights")
            if fw is not None:
                fw.props[0] = array.array('d', weights + [100.0])
    if not drop:
        if keys:
            fbx_rig.save(path, tree, version)
        return 0
    # the dropped channels' DeformPercent animation goes with them
    gone = set(drop)
    for c in conns.elems:
        if c.props[2] in drop and c.props[0] == b"OP" and ids.get(c.props[1]) is not None \
                and ids[c.props[1]].id == b"AnimationCurveNode":
            gone.add(c.props[1])
            gone.update(u for u in children.get(c.props[1], ()))
    for c in conns.elems:
        if c.props[0] == b"OP" and c.props[2] in gone and ids.get(c.props[1]) is not None \
                and ids[c.props[1]].id == b"AnimationCurve":
            gone.add(c.props[1])
    removed = {}
    keep = []
    for e in objs.elems:
        if e.props and e.props[0] in gone:
            removed[e.id] = removed.get(e.id, 0) + 1
            continue
        keep.append(e)
    objs.elems = keep
    conns.elems = [c for c in conns.elems if c.props[1] not in gone and c.props[2] not in gone]
    defs = tree.first(b"Definitions")
    if defs is not None:
        for ot in defs.find(b"ObjectType"):
            n, cnt = removed.get(ot.props[0]), ot.first(b"Count")
            if n and cnt is not None:
                cnt.props[0] -= n
        total = defs.first(b"Count")
        if total is not None:
            total.props[0] -= sum(removed.values())
    fbx_rig.save(path, tree, version)
    return folded
