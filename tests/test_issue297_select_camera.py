"""#297: View > Select Camera in a scene made in Blender mode.

Only a new scene made in Maya mode had the startup cameras persp / top / front / side, so in a Blender scene Select
Camera found no camera in a perspective or top / front / side view (and the toolbar button was greyed). Now the
scene gets the startup cameras on the first Select Camera, like every Maya scene has them."""

from importlib import import_module

import bpy
from mathutils import Euler

import kit
from test_step37_panel_menus import Ctx, _space

pm = import_module(kit.MODULE + ".ui.panel_menus")
sc = import_module(kit.MODULE + ".operators.startup_cameras")


def _selected():
    return sorted(o.name for o in bpy.context.view_layer.objects if o is not None and o.select_get())


def test_select_camera_works_in_a_blender_scene():
    bpy.ops.wm.read_homefile()
    assert not sc.names(bpy.context.scene)                  # a Blender scene: no startup cameras
    space = _space()
    rv3d = space.region_3d
    rv3d.view_perspective = 'PERSP'
    ctx = Ctx(space)
    assert pm.has_panel_camera(ctx)                         # the toolbar button is not greyed
    n_obs = len(bpy.data.objects)
    bpy.data.objects["Cube"].select_set(True)
    assert pm.apply(ctx, "SELECT_CAMERA")
    lead = bpy.context.view_layer.objects.active
    assert lead is not None and lead.get(sc.MARK) == "persp", lead
    assert "Cube" not in _selected(), _selected()
    assert len(bpy.data.objects) == n_obs + 4
    assert sorted(sc.names(bpy.context.scene)) == sorted(sc.NAMES)
    # the scene's own camera and objects are untouched; the startup cameras are hidden and don't render
    assert bpy.context.scene.camera == bpy.data.objects["Camera"]
    assert all(ob.hide_viewport and ob.hide_render for ob in sc.cameras(bpy.context.scene))
    # the next use selects the same camera: nothing made twice
    for name, rot in (("top", (0, 0, 0)), ("front", (90, 0, 0)), ("side", (90, 0, 90))):
        rv3d.view_perspective = 'ORTHO'
        rv3d.view_rotation = Euler([a * 3.141592653589793 / 180 for a in rot]).to_quaternion()
        assert pm.apply(ctx, "SELECT_CAMERA"), name
        assert bpy.context.view_layer.objects.active.get(sc.MARK) == name
    assert len(bpy.data.objects) == n_obs + 4
    rv3d.view_perspective = 'PERSP'


def test_a_view_without_a_camera_makes_nothing():
    """An orthographic view at an angle has no Maya camera: nothing is made, the item reports it."""
    bpy.ops.wm.read_homefile()
    space = _space()
    rv3d = space.region_3d
    rv3d.view_perspective = 'ORTHO'
    rv3d.view_rotation = Euler((0.5, 0.2, 0.7)).to_quaternion()
    ctx = Ctx(space)
    n_obs = len(bpy.data.objects)
    assert not pm.has_panel_camera(ctx)
    assert not pm.apply(ctx, "SELECT_CAMERA")
    assert len(bpy.data.objects) == n_obs
    rv3d.view_perspective = 'PERSP'
