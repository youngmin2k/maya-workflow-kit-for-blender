# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya's startup cameras persp / top / front / side as hidden camera objects of a new Maya scene (#117).

Maya 2022: a new scene's top DAG nodes are persp, top, front, side
(visibility off, ``cmds.camera(query=True, startupCamera=True)`` true), then the user's nodes in creation order; the
Outliner lists them in that order and greys them (hidden). ``cmds.delete("persp")`` fails with "Non-deletable node
'persp' cannot be deleted.".

Blender's Outliner is C: Python can't put rows above its object rows, so the kit-drawn camera rows
(ui/outliner_sets.py) followed the user's objects. Real hidden cameras linked before any user object are Blender rows
in Maya's order once the Maya Outliner lists objects unsorted (``use_sort_alpha`` off, ui/maya_outliner.setup);
selecting one in the Outliner makes it the lead like Maya (Channel Box shows ``persp``, Visibility off). They don't
render (``hide_render``), aren't drawn (``hide_viewport`` = Maya Visibility) and the kit's exports leave them out
(``excluded``). Only a kit new Maya scene gets them; other files keep the drawn rows.
"""

import math

import bpy
from mathutils import Euler, Matrix

from . import units

MARK = "allset_startup_camera"
NAMES = ("persp", "top", "front", "side")
MAYA_LENS, MAYA_FILM_MM, MAYA_ORTHO_WIDTH = 35.0, 36.0, 30.0
# Maya new-scene values (Y-up, Maya units): translate, rotate (XYZ degrees), orthographic
MAYA = {
    "persp": ((28.0, 21.0, 28.0), (-27.938352729602, 45.0, 0.0), False),
    "top": ((0.0, 1000.1, 0.0), (-90.0, 0.0, 0.0), True),
    "front": ((0.0, 0.0, 1000.1), (0.0, 0.0, 0.0), True),
    "side": ((1000.1, 0.0, 0.0), (0.0, 90.0, 0.0), True),
}
# Maya Y-up world -> Blender Z-up world: (x, y, z) -> (x, -z, y). Both cameras look down local -Z with +Y up.
Y_UP_TO_Z_UP = Matrix.Rotation(math.radians(90.0), 4, 'X')


def is_startup(ob):
    return ob is not None and ob.type == 'CAMERA' and bool(ob.get(MARK))


def cameras(scene=None):
    """The scene's startup camera objects, in Maya order."""
    objs = scene.objects if scene is not None else bpy.data.objects
    found = {ob.get(MARK): ob for ob in objs if is_startup(ob)}
    return [found[n] for n in NAMES if n in found]


def names(scene):
    """Names of the startup cameras the scene really has (ui/outliner_sets.py draws the others)."""
    return {ob.get(MARK) for ob in scene.objects if is_startup(ob)}


def maya_matrix(name, unit):
    t, r, _ortho = MAYA[name]
    m = Euler(tuple(math.radians(a) for a in r), 'XYZ').to_matrix().to_4x4()
    m.translation = [c * unit for c in t]
    return Y_UP_TO_Z_UP @ m


def ensure(scene, view_layer=None):
    """Give ``scene`` Maya's four startup cameras (first in its first collection) when it has none; returns them."""
    if names(scene):
        return cameras(scene)
    unit = units.maya_unit(scene)
    target = scene.collection.children[0] if len(scene.collection.children) else scene.collection
    clip = units.clip(scene)
    made = []
    for name in NAMES:
        data = bpy.data.cameras.new(f"{name}Shape")
        data.lens, data.sensor_width = MAYA_LENS, MAYA_FILM_MM
        data.clip_start, data.clip_end = clip["clip_start"], clip["clip_end"]
        if MAYA[name][2]:
            data.type = 'ORTHO'
            data.ortho_scale = MAYA_ORTHO_WIDTH * unit
        ob = bpy.data.objects.new(name, data)
        ob[MARK] = name
        ob["allset_dag_order"] = NAMES.index(name) - len(NAMES)    # before everything (ui/outliner_order.py)
        ob.matrix_world = maya_matrix(name, unit)
        ob.hide_render = True
        made.append(ob)
    # Blender lists a collection's objects in link order: link the cameras ahead of anything already there
    _relink_first(target, made, view_layer or bpy.context.view_layer)
    for ob in made:
        ob.hide_viewport = True          # Maya startup cameras: visibility off
    from ..ui import outliner_order
    outliner_order.sync(scene, view_layer or bpy.context.view_layer)
    return made


def _relink_first(coll, first, view_layer):
    """Link ``first`` into ``coll`` ahead of its other objects; the others keep their select / hide state."""
    old = [o for o in coll.objects if o not in first]
    state = {o: (o.select_get(view_layer=view_layer), o.hide_get(view_layer=view_layer)) for o in old
             if o.name in view_layer.objects}
    active = view_layer.objects.active
    for o in old:
        coll.objects.unlink(o)
    for o in list(first) + old:
        if o.name not in coll.objects:
            coll.objects.link(o)
    for o, (sel, hid) in state.items():
        o.hide_set(hid, view_layer=view_layer)
        o.select_set(sel, view_layer=view_layer)
    if active is not None and active.name in view_layer.objects:
        view_layer.objects.active = active


class excluded:
    """Context manager: the startup cameras are out of the scene while a kit export runs (Maya's exporters leave the
    startup cameras out), then linked back ahead of the other objects."""

    def __init__(self, scene, view_layer):
        self.scene, self.view_layer = scene, view_layer
        self.links = {}

    def __enter__(self):
        for ob in cameras(self.scene):
            for coll in list(ob.users_collection):
                self.links.setdefault(coll, []).append(ob)
                coll.objects.unlink(ob)
        return self

    def __exit__(self, *exc):
        for coll, obs in self.links.items():
            _relink_first(coll, obs, self.view_layer)
        return False
