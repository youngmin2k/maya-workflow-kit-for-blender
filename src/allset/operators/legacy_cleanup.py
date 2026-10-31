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

Older versions also had Create > Lights > Ambient Light / Volume Light (kit point lights kept in step by handlers,
the ambient light adding "Maya Ambient" nodes to the World), a kit Light Editor whose Isolate kept the other lights'
visibility in the scene, and an Illuminates by Default switch on lights:

- the World's "Maya Ambient" nodes are taken out (the World's own output linked back; a World the kit made for
  them is removed when nothing else uses it);
- a kit Ambient / Volume Light becomes a plain kit point light with the same Maya intensity, No Decay;
- a Light Editor Isolate still on is undone (the other lights' visibility comes back);
- the Illuminates by Default value is dropped (Blender's light linking collections stay as they are).
"""

import bpy
from bpy.app.handlers import persistent

from .. import compat

PERSP = "allset_persp"
DEFAULT_LIGHT = "allset_default_light"
RENDERABLE = "allset_renderable_on"
# Ambient / Volume Light: ID properties on the light data, the volume light's nodes, the World's ambient nodes
LIGHT_KIND = "allset_light_kind"
LIGHT_INTENSITY = "allset_maya_intensity"
LIGHT_PROPS = (LIGHT_KIND, LIGHT_INTENSITY, "allset_ambient_shade")
VOLUME_NODES_ON = "allset_volume_nodes"
VOLUME_NODES = ("Maya Volume Falloff", "Maya Volume Ray Length", "Maya Volume r/R", "Maya Volume 1 - r/R",
                "Maya Volume Strength")
WORLD_ADD = "Maya Ambient Add"
WORLD_NODES = ("Maya Ambient", "Maya Ambient Ray", "Maya Ambient Not Camera", WORLD_ADD)
WORLD_MADE, WORLD_NODES_ON = "allset_ambient_world", "allset_ambient_world_nodes"
LIGHT_ISOLATE = "allset_light_isolate"
ILLUMINATES = "allset_illuminates_by_default"


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


def _clean_world(world):
    """Take the old ambient nodes out of ``world``; True when there were any."""
    tree = world.node_tree
    if tree is None or not any(tree.nodes.get(n) for n in WORLD_NODES):
        return False
    add = tree.nodes.get(WORLD_ADD)
    original = add.inputs[0].links[0].from_socket if add is not None and add.inputs[0].is_linked else None
    targets = [lk.to_socket for lk in add.outputs[0].links] if add is not None else []
    for name in WORLD_NODES:
        node = tree.nodes.get(name)
        if node is not None:
            tree.nodes.remove(node)
    if original is not None:
        for sock in targets:
            tree.links.new(original, sock)
    if world.get(WORLD_NODES_ON):
        compat.release_world_nodes(world)
    return True


def _clean_worlds():
    n = 0
    for world in list(bpy.data.worlds):
        if _clean_world(world):
            n += 1
        made = bool(world.get(WORLD_MADE))
        for key in (WORLD_MADE, WORLD_NODES_ON):
            if key in world.keys():
                del world[key]
        if made:
            for sc in bpy.data.scenes:
                if sc.world == world:
                    sc.world = None
            if world.users == 0:
                bpy.data.worlds.remove(world)
    return n


def _clean_light(light):
    """An old Ambient / Volume Light -> a plain kit point light with its Maya intensity (No Decay)."""
    if LIGHT_KIND not in light.keys():
        return False
    value = light.get(LIGHT_INTENSITY, 1.0)
    intensity = float(value) if isinstance(value, (int, float)) else 1.0
    tree = light.node_tree
    if tree is not None:
        for name in VOLUME_NODES:
            node = tree.nodes.get(name)
            if node is not None:
                tree.nodes.remove(node)
    if light.get(VOLUME_NODES_ON):
        from . import lights
        light[lights.NODES_PROP] = True       # the kit turned the nodes on: the Decay Rate rule may turn them off
    for key in (*LIGHT_PROPS, VOLUME_NODES_ON):
        if key in light.keys():
            del light[key]
    if light.type == 'POINT':
        from . import lights
        lights.apply(light, intensity, 0)
    return True


def _undo_isolate(scene):
    state = scene.get(LIGHT_ISOLATE)
    if state is None:
        return False
    saved = state.to_dict().get("saved", {}) if hasattr(state, "to_dict") else {}
    for name, values in saved.items():
        ob = scene.objects.get(name)
        if ob is not None and len(values) == 2:
            ob.hide_render, ob.hide_viewport = bool(values[0]), bool(values[1])
    del scene[LIGHT_ISOLATE]
    return True


def clean():
    """Clean the open file; returns what was done ({kind: count})."""
    done = {"scene_camera": 0, "persp": 0, "default_light": 0, "props": 0, "ambient_world": 0, "maya_lights": 0,
            "isolate": 0}
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
    done["ambient_world"] = _clean_worlds()
    for light in bpy.data.lights:
        if _clean_light(light):
            done["maya_lights"] += 1
    for sc in bpy.data.scenes:
        if _undo_isolate(sc):
            done["isolate"] += 1
    for ob in bpy.data.objects:
        if ILLUMINATES in ob.keys():
            del ob[ILLUMINATES]
            done["props"] += 1
    return done


@persistent
def _on_load(*_args):
    try:
        done = clean()
    except (AttributeError, ReferenceError, RuntimeError):
        return
    if any(done[k] for k in ("scene_camera", "persp", "default_light", "ambient_world", "maya_lights", "isolate")):
        print(f"Maya Workflow Kit: tidied what an older version left in this file ({done})")


def register():
    if _on_load not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(_on_load)


def unregister():
    if _on_load in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_on_load)
