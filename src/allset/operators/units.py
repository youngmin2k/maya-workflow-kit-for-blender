# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya lengths in Blender units, and the optional "Maya Units": 1 BU = 1 cm.

Rule: a Maya length of 1 is one scene
display length unit, like Maya's current linear unit.
``maya_unit()`` gives it in BU; every creation path scales by it, so a Create cube,
``cmds.polyCube()`` and a cube imported from a Maya FBX are the same size.

Default: metres kept, lengths shown in cm (the app template sets
that, tools/make_startup.py). With the add-on preference on, the scenes of the
current file get ``scale_length = 0.01`` + cm and the 3D views Maya's camera
clip 0.1 / 10000 cm. Side effects (physics,
light falloff and importers assume 1 BU = 1 m).

The values before are kept per scene in the custom property
``allset_units_backup`` and come back when the option is turned off. New
files (no file path: the home file) get the units on load; saved files are
never changed behind the user's back.
"""

import json

import bpy
from bpy.app.handlers import persistent

BACKUP = "allset_units_backup"
UNITS = {"system": 'METRIC', "length_unit": 'CENTIMETERS', "scale_length": 0.01}
# Default camera clipping in Maya units.
CLIP = {"clip_start": 0.1, "clip_end": 10000.0}
# Maya's new-scene persp camera at (28, 21, 28) Y-up looking at the origin
# = Blender (28, -28, 21); used by tools/make_startup.py.
PERSP_EYE = (28.0, -28.0, 21.0)

_LENGTH_M = {'ADAPTIVE': 1.0, 'KILOMETERS': 1000.0, 'METERS': 1.0, 'CENTIMETERS': 0.01,
             'MILLIMETERS': 0.001, 'MICROMETERS': 1e-6, 'MILES': 1609.344, 'FEET': 0.3048,
             'INCHES': 0.0254, 'THOU': 2.54e-5}


def maya_unit(scene=None):
    """Blender units per Maya length unit (= one scene display length unit)."""
    us = (scene or bpy.context.scene).unit_settings
    if us.system == 'NONE':
        return 1.0
    return _LENGTH_M.get(us.length_unit, 1.0) / (us.scale_length or 1.0)


def grid_scale(scene=None):
    """Viewport grid scale that puts the finest perspective grid step on one Maya unit.

    Blender skips grid steps below the base unit (1 m) in user perspective views and
    divides the steps by ``scale_length``, so with cm
    shown the grid (and X-hold grid snap) was 1 m. The step is ``grid_scale /
    scale_length`` BU = ``grid_scale`` m, so grid_scale = metres per display unit.
    """
    us = (scene or bpy.context.scene).unit_settings
    if us.system == 'NONE':
        return 1.0
    return _LENGTH_M.get(us.length_unit, 1.0)


def clip(scene=None):
    """Maya camera clipping in BU for ``scene``."""
    k = maya_unit(scene)
    return {key: v * k for key, v in CLIP.items()}


def _views():
    for screen in bpy.data.screens:
        for area in screen.areas:
            for space in area.spaces:
                if space.type == 'VIEW_3D':
                    yield space


def is_applied(scene):
    return BACKUP in scene


def _rv3ds(space):
    yield space.region_3d
    yield from space.region_quadviews


def _scale_views(views, ratio):
    for space in views:
        for rv3d in _rv3ds(space):
            rv3d.view_location = rv3d.view_location * ratio
            rv3d.view_distance *= ratio


def apply_file(rescale_views=False):
    """Maya units on every scene and 3D view of the current file (backup kept once).

    ``rescale_views`` (new files): the views keep looking at the same Maya-unit scene,
    so the template's persp view (in cm) still frames a new pCube1.
    """
    views = list(_views())
    view_before = {k: getattr(views[0], k) for k in CLIP} if views else dict(CLIP)
    view_before["grid_scale"] = views[0].overlay.grid_scale if views else 1.0
    scene0 = bpy.context.scene
    k_before = maya_unit(scene0)
    for scene in bpy.data.scenes:
        us = scene.unit_settings
        if BACKUP not in scene:
            scene[BACKUP] = json.dumps({"units": {k: getattr(us, k) for k in UNITS},
                                        "view": view_before, "view_scale": 1.0})
        for key, value in UNITS.items():
            setattr(us, key, value)
    for space in views:
        for key, value in clip(scene0).items():
            setattr(space, key, value)
        space.overlay.grid_scale = grid_scale(scene0)
    ratio = maya_unit(scene0) / k_before
    if rescale_views and ratio != 1.0 and BACKUP in scene0:
        _scale_views(views, ratio)
        data = json.loads(scene0[BACKUP])
        data["view_scale"] = data.get("view_scale", 1.0) * ratio
        scene0[BACKUP] = json.dumps(data)


def restore_file():
    """Values from before ``apply_file`` (scenes without a backup are left alone)."""
    view = None
    view_scale = 1.0
    for scene in bpy.data.scenes:
        if BACKUP not in scene:
            continue
        data = json.loads(scene[BACKUP])
        us = scene.unit_settings
        for key in ("system", "length_unit", "scale_length"):  # length_unit depends on system
            setattr(us, key, data["units"][key])
        if view is None:
            view, view_scale = data["view"], data.get("view_scale", 1.0)
        del scene[BACKUP]
    if view:
        grid = view.pop("grid_scale", None)
        for space in _views():
            for key, value in view.items():
                setattr(space, key, value)
            if grid is not None:
                space.overlay.grid_scale = grid
        if view_scale != 1.0:
            _scale_views(list(_views()), 1.0 / view_scale)


def _enabled():
    from .. import preferences
    try:
        return preferences.get().maya_units
    except KeyError:
        return False


@persistent
def _on_load_post(_dummy):
    if _enabled() and not bpy.data.filepath:
        apply_file(rescale_views=True)


def register_handler():
    bpy.app.handlers.load_post.append(_on_load_post)


def unregister_handler():
    if _on_load_post in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_on_load_post)
