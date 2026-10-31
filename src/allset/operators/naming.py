# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya-style names: ``pCube1`` / ``pCubeShape1``.

Maya numbers a new node with a trailing integer and renames the shape to match
the transform. The number is one past the highest ``<base>N`` that exists, gaps are not filled (
sets / layers / anim layers / characters / bookmarks too);
Blender names are unique per datablock type, so it must be free for both the
object and its data.

#93: Maya names are unique among nodes that exist. Deleting a Blender object leaves its mesh with zero
users until the file is saved or purged, so that orphan held ``pCubeShape1`` and the next cube became ``pCube2``.
An orphan (local, no users, no fake user — Blender drops it on save anyway) whose name the kit wants is removed first.
"""

import re

import bpy

_TRAIL = re.compile(r"^(.*?)(\d+)$")


def base_name(name):
    """``pCube12`` -> ``pCube``; ``Cube.001`` -> ``Cube``; ``foo`` -> ``foo``."""
    name = re.sub(r"\.\d{3,}$", "", name)
    m = _TRAIL.match(name)
    return m.group(1) if m and m.group(1) else name


def next_number(base, taken, shape_taken=(), shape_base=None):
    """Maya's ``<base>#`` number: one more than the highest N of a taken name that starts with ``base`` + digits, then
    up past any ``shape_base+N`` already taken. Maya doesn't fill gaps (pCube2 / pCube3 left ->
    pCube4; pCube10 -> pCube11; pCube1x -> pCube2; a renamed shape pCubeShape6 doesn't count)."""
    shape_base = shape_base or f"{base}Shape"
    pattern = re.compile(re.escape(base) + r"(\d+)")
    n = 1 + max((int(m.group(1)) for name in taken if (m := pattern.match(name))), default=0)
    while f"{base}{n}" in taken or f"{shape_base}{n}" in shape_taken:
        n += 1
    return n


def orphan(idb):
    """True for local data nothing uses and Blender won't save (users 0, no fake user)."""
    return idb.users == 0 and not idb.use_fake_user and idb.library is None


def drop_orphans(coll, *bases):
    """Remove orphans in ``coll`` named ``<base><N>`` (or ``<base><N>.001``) so the names are free again."""
    for idb in [d for d in coll if orphan(d) and any(base_name(d.name) == b for b in bases)]:
        coll.remove(idb)


def _collection_for(data):
    if isinstance(data, bpy.types.Mesh):
        return bpy.data.meshes
    if isinstance(data, bpy.types.Curve):
        return bpy.data.curves
    if isinstance(data, bpy.types.Light):
        return bpy.data.lights
    if isinstance(data, bpy.types.Camera):
        return bpy.data.cameras
    return None


def apply_maya_name(ob, base, rename_data=True):
    """Rename ``ob`` to ``base<N>`` and its (single-user) data to ``base Shape<N>``."""
    data = ob.data if rename_data and ob.data is not None and ob.data.users == 1 else None
    coll = _collection_for(data) if data is not None else None
    drop_orphans(bpy.data.objects, base)
    if coll is not None:
        drop_orphans(coll, f"{base}Shape")
    taken = {o.name for o in bpy.data.objects if o is not ob}
    shape_taken = {d.name for d in coll if d is not data} if coll is not None else ()
    n = next_number(base, taken, shape_taken)
    ob.name = f"{base}{n}"
    if coll is not None:
        data.name = f"{base}Shape{n}"
    return n
