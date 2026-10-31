# SPDX-License-Identifier: GPL-3.0-or-later
"""Tidy files saved by older kit versions when they are opened (temporary — remove in 0.11.0).

Older versions rendered Render > Render Current Frame / Render Sequence through a kit camera ``persp`` (ID property
``allset_persp``, in no collection, kept by a fake user, made the scene camera) and added a ``defaultLight`` sun
(ID property ``allset_default_light``) while a scene without lights rendered. Render items now call Blender's
render, so a file that still has them is cleaned once when it is loaded:

- a kit ``persp`` render camera in no collection stops being the scene camera and is deleted when nothing else
  uses it (not a parent of another object);
- every leftover ``defaultLight`` object and its light data are deleted;
- the stored camera Renderable values of the old Render Sequence option are dropped.
"""

import bpy
from bpy.app.handlers import persistent

PERSP = "allset_persp"
DEFAULT_LIGHT = "allset_default_light"
RENDERABLE = "allset_renderable_on"


def _persp_cameras():
    """The old kit render cameras still in no collection (one a user linked into the scene is theirs now)."""
    return [ob for ob in bpy.data.objects if ob.get(PERSP) and ob.type == 'CAMERA' and not ob.users_collection]


def _used_elsewhere(ob):
    if ob.users_collection:
        return True
    if any(sc.camera == ob for sc in bpy.data.scenes):
        return True
    return any(o.parent == ob for o in bpy.data.objects)


def _remove_object(ob):
    data = ob.data
    bpy.data.objects.remove(ob)
    if data is not None and data.users == 0:
        if isinstance(data, bpy.types.Camera):
            bpy.data.cameras.remove(data)
        elif isinstance(data, bpy.types.Light):
            bpy.data.lights.remove(data)


def clean():
    """Clean the open file; returns what was done ({kind: count})."""
    done = {"scene_camera": 0, "persp": 0, "default_light": 0, "props": 0}
    for ob in [o for o in bpy.data.objects if o.get(DEFAULT_LIGHT)]:
        _remove_object(ob)
        done["default_light"] += 1
    for data in [d for d in bpy.data.lights if d.get(DEFAULT_LIGHT) and d.users == 0]:
        bpy.data.lights.remove(data)
    persp = _persp_cameras()
    for sc in bpy.data.scenes:
        if sc.camera is not None and sc.camera in persp:
            sc.camera = None
            done["scene_camera"] += 1
    for ob in persp:
        if not _used_elsewhere(ob):
            _remove_object(ob)
            done["persp"] += 1
    for cam in bpy.data.cameras:
        if RENDERABLE in cam.keys():
            del cam[RENDERABLE]
            done["props"] += 1
    return done


@persistent
def _on_load(*_args):
    try:
        done = clean()
    except (AttributeError, ReferenceError, RuntimeError):
        return
    if done["scene_camera"] or done["persp"] or done["default_light"]:
        print("Maya Workflow Kit: removed the render camera / default light an older version left in this file "
              f"({done})")


def register():
    if _on_load not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(_on_load)


def unregister():
    if _on_load in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_on_load)
