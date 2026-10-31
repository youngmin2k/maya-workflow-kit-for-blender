# SPDX-License-Identifier: GPL-3.0-or-later
"""``maya.cmds`` scene / DAG commands of the kit's look-alike (Issue #115): delete, rename, objExists,
listRelatives, parent, group, duplicate, spaceLocator.

Maya's behaviour: return
values, names, selection after each command, world positions kept. They go through the kit's own operations —
``parenting``, ``group``, ``duplicate``, ``dag.delete_hierarchy``, ``create`` — so a script
gives what the menus give.
"""

import bpy
from mathutils import Matrix, Vector

from .cmds_shim import (_Flags, _flatten, _object, _objects, _selection, _select_only, _is_shape_name,
                        _long_name, _view_layer, channel_keys, set_name, shape_of, type_matches,
                        unique_name, _to_bu)


# --- delete / rename / objExists -----------------------------------------------------------------------------------

def _history_owner(name):
    """(object, owner) whose kit creation node is called ``name`` (polyCube1, makeNurbCircle1), else None."""
    from ..operators import prim_history
    for ob in bpy.context.scene.objects:
        owner = prim_history.owner_of(ob)
        if owner is not None and prim_history.node_dict(owner).get("name") == name:
            return ob, owner
    return None


def delete(*args, **kwargs):
    """``delete`` = the nodes and everything below them (Maya DAG rule); ``-ch`` = Edit > Delete by Type >
    History (the object stays); a creation node's name (polyCube1) deletes only that history. Returns None."""
    f = _Flags("delete", kwargs)
    ch = f.get("constructionHistory", "ch", False)
    f.done()
    context = bpy.context
    names = list(_flatten(args))
    nodes = [n for n in names if not isinstance(n, bpy.types.Object) and _history_owner(str(n)) is not None
             and bpy.data.objects.get(str(n)) is None]
    if nodes:
        from ..operators import prim_history
        for n in nodes:
            prim_history.drop(_history_owner(str(n))[0])
        names = [n for n in names if n not in nodes]
        if not names:
            return None
    obs = _objects(names)
    if ch:
        from ..operators import history
        history.delete_history(context, obs)
        return None
    from ..operators import dag
    dag.delete_hierarchy(context, obs)
    _view_layer()
    return None


def rename(*args, **kwargs):
    """``rename [object] newName``: Maya increments a taken name (hero -> hero1) and renames the shape with it
    (pCube1 -> box10 gives boxShape10, -> hero gives heroShape). Returns the new name."""
    f = _Flags("rename", kwargs)
    ignore_shape = f.get("ignoreShape", "is", False)
    f.done()
    names = list(_flatten(args))
    if len(names) == 1:
        sel = _selection()
        if not sel:
            raise RuntimeError("rename: Nothing selected")
        ob, new = sel[-1], names[0]
    elif len(names) == 2:
        ob, new = _object(names[0]), names[1]
    else:
        raise ValueError("rename: expected [object] newName")
    return set_name(ob, new, shape=not ignore_shape)


def objExists(name, **kwargs):
    """True for an object, a shape, a kit creation node (polyCube1) or an attribute (``pCube1.tx``)."""
    _Flags("objExists", kwargs).done()
    name = str(name)
    if "." in name.rsplit("|", 1)[-1]:
        node, attr = name.rsplit("|", 1)[-1].split(".", 1)
        try:
            ob = _object(node)
        except (ValueError, RuntimeError):
            return False
        return channel_keys(ob, attr) is not None or attr in ("rotateOrder", "ro", "worldMatrix", "matrix")
    try:
        _object(name)
    except (ValueError, RuntimeError):
        return _history_owner(name) is not None
    return True


# --- listRelatives ---------------------------------------------------------------------------------------------------

def _children(ob):
    """Maya children of a transform: its shape first, then the child transforms."""
    out = [('S', ob)] if shape_of(ob) else []
    return out + [('T', c) for c in ob.children]


def _branch(item):
    """``item`` after everything under it (the order of Maya's ``listRelatives -ad``)."""
    kind, ob = item
    if kind == 'S':
        return [item]
    out = []
    for c in _children(ob):
        out += _branch(c)
    return out + [item]


def _name(item, full):
    kind, ob = item
    if kind == 'S':
        return f"{_long_name(ob)}|{shape_of(ob)}" if full else shape_of(ob)
    return _long_name(ob) if full else ob.name


def listRelatives(*args, **kwargs):
    f = _Flags("listRelatives", kwargs)
    parent_ = f.get("parent", "p", False)
    all_parents = f.get("allParents", "ap", False)
    all_desc = f.get("allDescendents", "ad", False)
    f.get("children", "c", False)
    shapes = f.get("shapes", "s", False)
    full = f.get("fullPath", "f", False)
    f.get("path", "pa", False)
    f.get("noIntermediate", "ni", False)
    typ = f.get("type", "typ")
    f.done()
    names = list(_flatten(args))
    if names:
        items = [('S' if _is_shape_name(n) else 'T', _object(n)) for n in names]
    else:
        items = [('T', o) for o in _selection()]
    out = []
    for kind, ob in items:
        if parent_ or all_parents:
            if kind == 'S':                      # a shape's parent is its transform
                rel = [('T', ob)]
            else:
                rel = [('T', ob.parent)] if ob.parent is not None else []
        elif kind == 'S':
            rel = []
        elif shapes:
            rel = [('S', ob)] if shape_of(ob) else []
        elif all_desc:
            rel = [it for c in _children(ob) for it in _branch(c)]
        else:
            rel = _children(ob)
        if typ is not None:
            types = typ if isinstance(typ, (list, tuple)) else [typ]
            rel = [it for it in rel if any(type_matches(t, it[0], it[1]) for t in types)]
        for it in rel:
            n = _name(it, full)
            if n not in out:
                out.append(n)
    return out or None  # Maya returns None when there is nothing


# --- parent / group ------------------------------------------------------------------------------------------------

def parent(*args, **kwargs):
    """``parent child... parent`` / ``parent -w child...``: world positions kept (``-r``: local values kept), the
    children end up selected; returns their names."""
    from ..operators import parenting
    f = _Flags("parent", kwargs)
    world = f.get("world", "w", False)
    relative = f.get("relative", "r", False)
    f.get("absolute", "a", False)
    shape = f.get("shape", "s", False)
    f.done()
    names = list(_flatten(args))
    if shape:
        return _parent_shape(names, relative)
    obs = [_object(n) for n in names] if names else _selection()
    if world:
        if not obs:
            raise RuntimeError("parent: Nothing selected")
        parenting.unparent(obs, preserve=not relative)
        children = obs
    else:
        if len(obs) < 2:
            raise RuntimeError("parent: Not enough objects or values.")
        children, target = obs[:-1], obs[-1]
        _view_layer()
        done, cycles = parenting.parent_maya(children, target, preserve=not relative)
        if cycles:
            raise RuntimeError(f"Cannot parent components or objects in the underworld: '{cycles[0].name}' is "
                               f"above '{target.name}'.")
        children = done
    _view_layer()
    _select_only(children)
    return [o.name for o in children]


def _shape_target(name):
    """A joint (pose bone) or an object for ``parent -s``'s last argument."""
    if isinstance(name, bpy.types.Object):
        return name
    short = str(name).rsplit("|", 1)[-1]
    if bpy.data.objects.get(short) is None:
        from .cmds_rig import find_joint
        found = find_joint(short)
        if found is not None:
            arm, bone = found
            return arm.pose.bones[bone.name]
    return _object(name)


def _parent_shape(names, relative):
    """``parent -s [-r] curveShape... joint|curve``: the curve
    shapes become the joint's control shape (bone Custom Shape) or join the target curve. Returns the shape names."""
    from ..operators import control_shapes
    if names:
        sources, target = [_object(n) for n in names[:-1]], _shape_target(names[-1]) if len(names) > 1 else None
    else:
        sel = _selection()
        sources, target = sel[:-1], sel[-1] if sel else None
        if target is not None and target.type == 'ARMATURE' and target.mode == 'POSE' and target.data.bones.active:
            target = target.pose.bones[target.data.bones.active.name]      # the selected joint
    if target is None or not sources:
        raise RuntimeError("parent: Not enough objects or values.")
    out = []
    for ob in sources:
        if ob.type != 'CURVE':
            raise RuntimeError(f"parent: {ob.name} has no curve shape to move.")
        out.append(ob.data.name)
        try:
            control_shapes.parent_shape(ob, target, relative=bool(relative))
        except ValueError as ex:
            raise RuntimeError(str(ex))
    _view_layer()
    return out


def _empty(context, kind, name):
    from ..operators import create
    ob = create.create(context, kind)
    if name:
        set_name(ob, name, shape=False)
    return ob


def group(*args, **kwargs):
    """``group`` = Ctrl+G: a new transform at the origin of the common parent (``-w`` world, ``-p`` under a given
    node), the objects under it keeping their world positions; ``-em`` = an empty group ``nullN``. The group is
    selected; returns its name."""
    from ..operators import parenting
    from ..operators.group import common_parent
    f = _Flags("group", kwargs)
    empty = f.get("empty", "em", False)
    name = f.get("name", "n")
    world = f.get("world", "w", False)
    under = f.get("parent", "p")
    f.get("absolute", "a", False)
    f.get("relative", "r", False)
    f.done()
    context = bpy.context
    obs = [] if empty else ([_object(n) for n in _flatten(args)] or _selection())
    target = _object(under) if under else None if world else (common_parent(obs) if obs else None)
    grp = _empty(context, 'EMPTY_GROUP', None)
    from ..operators import naming
    if name:
        set_name(grp, name, shape=False)
    elif not empty:
        grp.name = f"group{naming.next_number('group', {o.name for o in bpy.data.objects if o is not grp})}"
    if obs and obs[0].users_collection and grp.users_collection != obs[0].users_collection:
        for c in list(grp.users_collection):
            c.objects.unlink(grp)
        obs[0].users_collection[0].objects.link(grp)
    if target is not None:
        grp.parent = target
        grp.matrix_parent_inverse = Matrix.Identity(4)
    grp.matrix_basis = Matrix.Identity(4)
    _view_layer()
    for ob in obs:
        parenting.set_parent_maya(ob, grp)
    _view_layer()
    _select_only([grp])
    return grp.name


# --- duplicate / spaceLocator ---------------------------------------------------------------------------------------

def _preorder(ob):
    out = []
    for c in ob.children:
        out += [c] + _preorder(c)
    return out


def duplicate(*args, **kwargs):
    """``duplicate`` = Ctrl+D: each root with everything under it, without its creation node, Maya names (one past
    the highest number; a shape not named ``<base>Shape<N>`` becomes ``<copy>Shape``). Returns the copies' roots
    and, without ``-rr``, the transforms under them; they end up selected. Maya allows the same child name
    under two parents, Blender doesn't: copied children get new numbers (pCube1 under rig1 -> pCube2)."""
    from ..operators import duplicate as dup
    import re
    f = _Flags("duplicate", kwargs)
    name = f.get("name", "n")
    roots_only = f.get("returnRootsOnly", "rr", False)
    f.get("renameChildren", "rc", False)
    f.get("inputConnections", "ic", False)
    f.get("upstreamNodes", "un", False)
    f.done()
    obs = _objects(args)
    out, made = [], []
    for root in dup.selected_roots(obs):
        sources = [root] + _preorder(root)
        new = dup.copy_subtree(root)
        copies = [new] + _preorder(new)
        for src, cp in zip(sources, copies):
            sh = shape_of(src)
            base = re.sub(r"\d+$", "", src.name)
            if cp.data is not None and sh is not None and not re.fullmatch(re.escape(base) + r"Shape\d+", sh) \
                    and cp.data.users == 1:
                cp.data.name = f"{cp.name}Shape"       # Maya: box -> box1 / box1Shape
        if name:
            set_name(new, name)
        made.append(new)
        out.append(new.name)
        if not roots_only:
            out += [c.name for c in _preorder(new)]
    _view_layer()
    _select_only(made)
    return out


def spaceLocator(*args, **kwargs):
    """``spaceLocator`` = Create > Locator (``locatorN`` / ``locatorShapeN``, selected). ``-p`` is the shape's
    local position: the kit puts it into the pivot offset (``delta_location``), so translate stays 0 and the
    locator draws there (Maya rotates it about the transform's origin, the kit about the locator)."""
    f = _Flags("spaceLocator", kwargs)
    name = f.get("name", "n")
    pos = f.get("position", "p")
    f.get("absolute", "a", False)
    f.get("relative", "r", False)
    f.done()
    if args:
        raise TypeError("spaceLocator takes no objects")
    ob = _empty(bpy.context, 'LOCATOR', name)
    if pos is not None:
        ob.delta_location = Vector([_to_bu(float(x)) for x in pos])
    _view_layer()
    _select_only([ob])
    return [ob.name]


__all__ = ["delete", "rename", "objExists", "listRelatives", "parent", "group", "duplicate", "spaceLocator",
           "unique_name"]
