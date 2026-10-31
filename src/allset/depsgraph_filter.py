# SPDX-License-Identifier: GPL-3.0-or-later
"""#191: cheap tests on a depsgraph update, so handlers that scan the whole scene skip updates that can't
change what they look at. Blender's ``depsgraph.updates`` per kind of edit (5.2):

- move / rotate / scale, playback: the Object (or its data) with ``is_updated_transform``;
- mesh / curve edits: the data (or the evaluated Object) with ``is_updated_geometry``;
- rename, custom properties, parent pointer written from Python: the Object with no flag;
- selection, active object, ``hide_set``: the Scene only;
- parent / unparent: Scene + Objects; add / delete / link / hide_viewport: Scene + Collection + Objects;
- edit-mode bone add / rename: the Armature data.

Each test reads only the few entries of ``depsgraph.updates`` (no scene walk)."""

import bpy


def only_motion(depsgraph):
    """True when every update is a transform or geometry change of a non-Scene / non-Collection ID — nothing that
    adds, removes, renames, re-parents, hides or selects."""
    if depsgraph is None:
        return False
    seen = False
    for u in depsgraph.updates:
        seen = True
        if isinstance(u.id, (bpy.types.Scene, bpy.types.Collection)):
            return False
        if not (u.is_updated_transform or u.is_updated_geometry):
            return False
    return seen


def only_scene(depsgraph):
    """True when the update is the Scene alone (selection, active object, ``hide_set``)."""
    if depsgraph is None:
        return False
    seen = False
    for u in depsgraph.updates:
        seen = True
        if not isinstance(u.id, bpy.types.Scene):
            return False
    return seen


def outliner_skip(depsgraph):
    """The kit Outliner's rows (names, parents, membership, bones) can't change: motion only, or the Scene alone. An
    Armature data update (edit-mode bones) always counts."""
    if depsgraph is None:
        return False
    for u in depsgraph.updates:
        if isinstance(u.id, bpy.types.Armature):
            return False
    return only_scene(depsgraph) or only_motion(depsgraph)


def structure_changed(depsgraph):
    """Objects may have been added or removed: a Scene or Collection update."""
    if depsgraph is None:
        return True
    return depsgraph.id_type_updated('SCENE') or depsgraph.id_type_updated('COLLECTION')
