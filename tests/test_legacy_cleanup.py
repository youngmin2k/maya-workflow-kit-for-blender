"""Files saved by older versions are tidied when they are opened (operators/legacy_cleanup.py, temporary): the
kit's old render camera ``persp`` (no collection, fake user, scene camera) stops being the scene camera and goes, a
leftover ``defaultLight`` goes, the old camera Renderable values are dropped; the file opens without errors and
the user's own objects stay."""

import os
from importlib import import_module

import bpy

import kit

lc = import_module(kit.MODULE + ".operators.legacy_cleanup")


def _path(name):
    return os.path.join(bpy.app.tempdir, name)


def _old_file(name, persp_in_collection=False):
    """A scene the way an older version saved it after a kit render (built here with plain data)."""
    bpy.ops.wm.read_homefile(use_empty=True)
    sc = bpy.context.scene
    bpy.ops.mesh.primitive_cube_add(size=2.0)
    cube = bpy.context.active_object.name
    mine = bpy.data.objects.new("shotCam", bpy.data.cameras.new("shotCamShape"))
    sc.collection.objects.link(mine)
    mine.data[lc.RENDERABLE] = True
    persp = bpy.data.objects.new("persp", bpy.data.cameras.new("perspShape"))
    persp[lc.PERSP] = True
    persp.use_fake_user = True
    persp.data[lc.RENDERABLE] = False
    if persp_in_collection:
        sc.collection.objects.link(persp)
    sc.camera = persp
    light = bpy.data.objects.new("defaultLight", bpy.data.lights.new("defaultLight", 'SUN'))
    light[lc.DEFAULT_LIGHT] = True
    light.data[lc.DEFAULT_LIGHT] = True
    sc.collection.objects.link(light)
    light.parent = persp
    path = _path(name)
    bpy.ops.wm.save_as_mainfile(filepath=path)
    return path, cube


def test_old_file_is_cleaned_on_open():
    path, cube = _old_file("legacy_render.blend")
    bpy.ops.wm.read_homefile(use_empty=True)
    assert lc._on_load in bpy.app.handlers.load_post
    bpy.ops.wm.open_mainfile(filepath=path)
    sc = bpy.context.scene
    assert sc.camera is None, sc.camera
    assert "persp" not in bpy.data.objects and "perspShape" not in bpy.data.cameras
    assert not [o for o in bpy.data.objects if o.get(lc.DEFAULT_LIGHT)]
    assert not [d for d in bpy.data.lights if d.get(lc.DEFAULT_LIGHT)]
    assert not [c for c in bpy.data.cameras if lc.RENDERABLE in c.keys()]
    assert cube in bpy.data.objects and "shotCam" in bpy.data.objects, "the user's objects stay"
    # once cleaned there is nothing left to do
    assert lc.clean() == {"scene_camera": 0, "persp": 0, "default_light": 0, "props": 0}


def test_persp_linked_into_the_scene_is_kept():
    path, _cube = _old_file("legacy_render_linked.blend", persp_in_collection=True)
    bpy.ops.wm.open_mainfile(filepath=path)
    sc = bpy.context.scene
    assert "persp" in bpy.data.objects and sc.camera == bpy.data.objects["persp"], "a linked camera is the user's"
    assert "defaultLight" not in bpy.data.objects


def test_handler_follows_maya_mode_and_disable():
    sw = import_module(kit.MODULE + ".switch")
    sw.set_mode(False, layout=False)
    try:
        assert lc._on_load not in bpy.app.handlers.load_post
    finally:
        sw.set_mode(True, layout=False)
    assert lc._on_load in bpy.app.handlers.load_post
    kit.disable()
    try:
        assert not [h for h in bpy.app.handlers.load_post if getattr(h, "__module__", "").endswith("legacy_cleanup")]
    finally:
        kit.enable()
