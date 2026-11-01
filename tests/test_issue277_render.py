"""#277: Render > Render Current Frame (and the other kit render buttons) in a scene without a camera renders through
persp placed where the view looks from, like Maya, instead of Blender's "No camera found"; a scene camera the user
set is Blender's own render."""

import math
import os
from importlib import import_module

import bpy
from mathutils import Euler, Vector

import kit

rp = import_module(kit.MODULE + ".operators.render_persp")
units = import_module(kit.MODULE + ".operators.units")
framing = import_module(kit.MODULE + ".operators.framing")
menu_map = import_module(kit.MODULE + ".ui.menu_map")
shelf_map = import_module(kit.MODULE + ".ui.shelf_map")
outliner_sets = import_module(kit.MODULE + ".ui.outliner_sets")


def _clear():
    if bpy.context.active_object is not None and bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    bpy.context.scene.camera = None


def _view():
    space, rv3d = rp.find_view(bpy.context)
    assert space is not None and rv3d is not None, "factory screen has a 3D View"
    return space, rv3d


def _aim(rv3d, space, persp=True, lens=70.0):
    rv3d.view_perspective = 'PERSP' if persp else 'ORTHO'
    rv3d.view_location = Vector((0.0, 0.0, 0.0))
    rv3d.view_rotation = Euler((math.radians(60), 0.0, math.radians(45))).to_quaternion()
    rv3d.view_distance = 8.0
    space.lens = lens


def _cam(rv3d):
    return framing.view_matrix(rv3d.view_location, rv3d.view_rotation, rv3d.view_distance).inverted()


def _close(a, b, eps=1e-4):
    return all(abs(x - y) < eps for ra, rb in zip(a, b) for x, y in zip(ra, rb))


def _out(name):
    out = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(kit.__file__)), "..", "tmp", "test_env", name))
    if os.path.exists(out):
        os.remove(out)
    return out


def _small_render(sc, out):
    sc.render.engine = 'BLENDER_WORKBENCH'
    sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = 64, 36, 100
    sc.render.filepath = out


def _distinct_reds(path):
    img = bpy.data.images.load(path)
    try:
        return len({round(v, 3) for v in list(img.pixels)[0::4]})
    finally:
        bpy.data.images.remove(img)


def test_persp_made_on_demand_matches_view_and_is_reused():
    _clear()
    assert rp.persp_camera(create=False) is None
    space, rv3d = _view()
    _aim(rv3d, space)
    sc = bpy.context.scene
    assert rp.needs_camera(sc)
    ob = rp.render_camera(bpy.context)
    assert ob.name == "persp" and ob.data.name == "perspShape" and ob.get(rp.PROP), ob.name
    assert sc.camera == ob and rp.needs_camera(sc), "the kit persp follows the view at every render"
    assert _close(ob.matrix_world, _cam(rv3d)), "camera sees what the view sees"
    # viewport lens is on a 72 mm sensor: lens 70 = a 35 mm persp on a 36 mm film back
    assert ob.data.type == 'PERSP' and abs(ob.data.sensor_width - 36.0) < 1e-6 and abs(ob.data.lens - 35.0) < 1e-6
    clip = units.clip(sc)
    assert abs(ob.data.clip_start - clip["clip_start"]) < 1e-6 and abs(ob.data.clip_end - clip["clip_end"]) < 1e-3
    # no second Outliner row: linked to no collection, kept by a fake user
    assert not ob.users_collection and ob.name not in sc.objects and ob.use_fake_user
    assert ('CAMERA', "persp", "") in outliner_sets.default_entries()
    rv3d.view_distance = 20.0
    space.lens = 50.0
    again = rp.render_camera(bpy.context)
    assert again == ob and len([o for o in bpy.data.objects if o.get(rp.PROP)]) == 1
    assert _close(ob.matrix_world, _cam(rv3d)) and abs(ob.data.lens - 25.0) < 1e-6
    bpy.ops.outliner.orphans_purge(do_recursive=True)
    assert rp.persp_camera(create=False) == ob


def test_ortho_view():
    _clear()
    space, rv3d = _view()
    _aim(rv3d, space, persp=False)
    ob = rp.render_camera(bpy.context)
    assert ob.data.type == 'ORTHO'
    assert abs(ob.data.ortho_scale - rv3d.view_distance * 72.0 / space.lens) < 1e-4
    _aim(rv3d, space)


def test_user_scene_camera_is_blenders_render():
    _clear()
    sc = bpy.context.scene
    cam = bpy.data.objects.new("camera1", bpy.data.cameras.new("cameraShape1"))
    sc.collection.objects.link(cam)
    sc.camera = cam
    assert not rp.needs_camera(sc), "a camera the user set is kept"
    out = _out("issue277_user_cam.png")
    _small_render(sc, out)
    assert bpy.ops.allset.render(write_still=True) == {'FINISHED'}
    assert sc.camera == cam and rp.persp_camera(create=False) is None and os.path.exists(out)


def test_camera_view_local_camera():
    _clear()
    sc = bpy.context.scene
    space, rv3d = _view()
    cam2 = bpy.data.objects.new("camera2", bpy.data.cameras.new("cameraShape2"))
    sc.collection.objects.link(cam2)
    space.use_local_camera, space.camera = True, cam2
    rv3d.view_perspective = 'CAMERA'
    try:
        assert rp.render_camera(bpy.context) == cam2 and sc.camera == cam2
    finally:
        space.use_local_camera = False
        rv3d.view_perspective = 'PERSP'


def test_camera_view_through_persp_keeps_it_in_place():
    """Looking through persp (camera view, no local camera): the render leaves persp where it is."""
    _clear()
    sc = bpy.context.scene
    space, rv3d = _view()
    _aim(rv3d, space)
    rp.render_camera(bpy.context)
    persp = sc.camera
    placed = persp.matrix_world.copy()
    rv3d.view_location = Vector((5.0, 0.0, 0.0))     # the stored user view moves; camera view still shows persp
    rv3d.view_perspective = 'CAMERA'
    try:
        assert rp.render_camera(bpy.context) == persp and sc.camera == persp
        assert _close(persp.matrix_world, placed), "camera view must not move the camera it looks through"
    finally:
        rv3d.view_perspective = 'PERSP'


def test_render_without_camera_writes_an_image_through_the_view():
    _clear()
    sc = bpy.context.scene
    bpy.ops.mesh.primitive_cube_add(size=2.0)
    space, rv3d = _view()
    _aim(rv3d, space)
    out = _out("issue277_render.png")
    _small_render(sc, out)
    assert bpy.ops.allset.render(write_still=True) == {'FINISHED'}
    assert sc.camera is not None and sc.camera.get(rp.PROP)
    assert os.path.exists(out) and _distinct_reds(out) > 5, "cube visible"
    # the view looks away from the cube: the persp camera follows it
    rv3d.view_location = Vector((1000.0, 0.0, 0.0))
    os.remove(out)
    assert bpy.ops.allset.render(write_still=True) == {'FINISHED'}
    assert _distinct_reds(out) <= 2, "camera follows the view"
    rv3d.view_location = Vector((0.0, 0.0, 0.0))


def test_kit_new_scene_renders_through_its_startup_persp():
    sc_mod = import_module(kit.MODULE + ".operators.startup_cameras")
    _clear()
    sc = bpy.context.scene
    sc_mod.ensure(sc)
    startup = next((o for o in sc.objects if o.get(sc_mod.MARK) == "persp"), None)
    assert startup is not None and startup.hide_render
    assert sc.camera is None
    assert rp.render_camera(bpy.context) == startup and sc.camera == startup
    assert rp.persp_camera(create=False) == startup and not [o for o in bpy.data.objects if o.get(rp.PROP)]
    out = _out("issue277_startup.png")
    _small_render(sc, out)
    assert bpy.ops.allset.render(write_still=True) == {'FINISHED'}
    assert os.path.exists(out) and sc.camera == startup, "a hidden startup camera renders"


def test_render_items_use_the_kit_render():
    m = menu_map.MAP
    assert m["Render/Render Current Frame"] == "allset.render"
    assert m["Render/Redo Previous Render"] == "allset.render"
    assert m["Playback/Render Current Frame"] == "allset.render"
    assert m["Render/Render Sequence"] == ("allset.render", {"animation": True})
    assert m["Render/Batch Render"] == ("allset.render", {"animation": True})
    assert shelf_map.BY_COMMAND["RenderSequence"][0] == ("allset.render", {"animation": True})
    assert shelf_map.BY_COMMAND["BatchRender"][0] == ("allset.render", {"animation": True})
    for path, action in m.items():
        if path.startswith(("Render/", "Playback/Render")):
            assert "render.render" not in repr(action), (path, action)


def test_animation_without_camera_picks_persp():
    _clear()
    sc = bpy.context.scene
    space, rv3d = _view()
    _aim(rv3d, space)
    sc.frame_start = sc.frame_end = 1
    out = _out("issue277_seq_")
    _small_render(sc, out)
    assert bpy.ops.allset.render(animation=True) == {'FINISHED'}
    assert sc.camera is not None and sc.camera.get(rp.PROP)
    assert os.path.exists(out + "0001.png"), out
