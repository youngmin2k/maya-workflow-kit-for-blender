"""Viewport: panel toolbar toggles turn off again (#10), IPR off keeps the shading (#24), F in a
camera view moves the camera (#9), UV checker toggle (#13). GUI side: tests/gui/gui_step129_*.py."""

from importlib import import_module

import bpy
from bpy_extras.object_utils import world_to_camera_view

import kit
from test_step37_panel_menus import Ctx, _space

pm = import_module(kit.MODULE + ".ui.panel_menus")
pt = import_module(kit.MODULE + ".ui.panel_toolbar")
sl = import_module(kit.MODULE + ".ui.status_line")
view = import_module(kit.MODULE + ".operators.view")
mi = import_module(kit.MODULE + ".operators.menu_items")
maya_grid = import_module(kit.MODULE + ".ui.maya_grid")


def _click(ctx, key):
    """What a toolbar click does (ALLSET_OT_panel_set.execute with toggle=True)."""
    if key in pm.TOGGLE_OFF and pm.state(ctx, key):
        key = pm.TOGGLE_OFF[key]
    return pm.apply(ctx, key)


def _camera_view(space):
    cam = bpy.data.objects.new("camera129", bpy.data.cameras.new("camera129"))
    bpy.context.scene.collection.objects.link(cam)
    space.camera = cam
    space.use_local_camera = True
    space.region_3d.view_perspective = 'CAMERA'
    return cam


def _snapshot(space, cam):
    sh, ov = space.shading, space.overlay
    vs = bpy.context.scene.view_settings
    return (sh.type, sh.light, sh.color_type, sh.show_shadows, sh.show_cavity, sh.show_xray, sh.use_dof,
            ov.show_wireframes, ov.show_xray_bone, maya_grid.visible(space), tuple(cam.lock_location),
            tuple(cam.lock_rotation), cam.data.show_sensor, cam.data.show_passepartout, cam.data.show_safe_areas,
            round(vs.exposure, 4), round(vs.gamma, 4), vs.view_transform)


def test_every_toolbar_toggle_comes_back():
    """Maya iconTextCheckBox: click = on, click again = the state it started from (here headless: set / prop
    buttons; Isolate needs a real area, gui_step129_panel_toolbar clicks it)."""
    space = _space()
    cam = _camera_view(space)
    ctx = Ctx(space)
    space.shading.type = 'SOLID'
    bpy.context.scene.view_settings.exposure = 1.5
    bpy.context.scene.view_settings.gamma = 2.2
    keys = [(label, kind, data) for group in pt.TOOLBAR for _g, kind, data, label in group if kind in ("set", "prop")]
    keys += [("Exposure", "set", "EXPOSURE"), ("Gamma", "set", "GAMMA"), ("Colour management", "set", "CM_ENABLE")]
    bad = []
    for label, kind, data in keys:
        if data in ("ISOLATE", "SELECT_CAMERA"):
            continue
        before = _snapshot(space, cam)
        for i in range(2):
            if kind == "set":
                assert _click(ctx, data), (label, i)
            else:
                owner = pm._owner(space, bpy.context, data[0])
                setattr(owner, data[1], not getattr(owner, data[1]))
            if i == 0:
                mid = _snapshot(space, cam)
        after = _snapshot(space, cam)
        print(f"{label:28} {before != mid!s:5} {after == before!s:5}")
        if mid == before or after != before:
            bad.append((label, before, mid, after))
    assert not bad, bad


def test_wire_smooth_lights_are_maya_toggles():
    space = _space()
    ctx = Ctx(space)
    sh = space.shading
    sh.type = 'SOLID'
    _click(ctx, "SHADE_WIRE")
    assert sh.type == 'WIREFRAME'
    _click(ctx, "SHADE_WIRE")
    assert sh.type == 'SOLID'          # Maya: Wireframe off = smooth shaded
    _click(ctx, "SHADE_SMOOTH")
    assert sh.type == 'WIREFRAME'      # Maya: Smooth Shade All off = wireframe
    _click(ctx, "SHADE_SMOOTH")
    assert sh.type == 'SOLID'
    _click(ctx, "LIGHT_ALL")
    assert pm.state(ctx, "LIGHT_ALL")
    _click(ctx, "LIGHT_ALL")
    assert not pm.state(ctx, "LIGHT_ALL") and pm.state(ctx, "LIGHT_DEFAULT")
    # the Shading menu stays a radio list: Wireframe twice stays Wireframe
    pm.apply(ctx, "SHADE_WIRE")
    pm.apply(ctx, "SHADE_WIRE")
    assert sh.type == 'WIREFRAME'
    sh.type = 'SOLID'


def test_camera_buttons_need_a_camera_view():
    space = _space()
    space.region_3d.view_perspective = 'PERSP'
    ctx = Ctx(space)
    for key in ("CAMERA_LOCK", "FILM_GATE", "GATE_MASK", "SAFE_TITLE", "SELECT_CAMERA"):
        assert not pm.apply(ctx, key), key
        assert key in pm.FAILS


def test_select_camera_selects_the_looked_through_camera():
    space = _space()
    cam = _camera_view(space)
    ctx = Ctx(space)
    assert pm.apply(ctx, "SELECT_CAMERA")
    assert cam.select_get() and bpy.context.view_layer.objects.active == cam
    space.region_3d.view_perspective = 'PERSP'


def test_ipr_off_gives_the_previous_shading_back():
    space = _space()
    for start in ('WIREFRAME', 'MATERIAL', 'SOLID'):
        space.shading.type = start
        sl.ipr_toggle(space)
        assert space.shading.type == 'RENDERED'
        sl.ipr_toggle(space)
        assert space.shading.type == start, (start, space.shading.type)
    space.shading.type = 'SOLID'


def test_frame_in_camera_view_moves_the_camera():
    scene = bpy.context.scene
    mesh = bpy.data.meshes.new("box129")
    import bmesh
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=2.0)
    bm.to_mesh(mesh)
    bm.free()
    box = bpy.data.objects.new("box129", mesh)
    scene.collection.objects.link(box)
    box.location = (5.0, 3.0, 1.0)
    cam = bpy.data.objects.new("cam129f", bpy.data.cameras.new("cam129f"))
    scene.collection.objects.link(cam)
    cam.location = (0.0, -20.0, 2.0)
    cam.rotation_euler = (1.5708, 0.0, 0.0)
    bpy.context.view_layer.update()
    rot0 = cam.matrix_world.to_quaternion()
    pts = [box.matrix_world @ v.co for v in mesh.vertices]
    assert view.frame_camera(bpy.context, cam, pts)
    bpy.context.view_layer.update()
    assert cam.matrix_world.to_quaternion().rotation_difference(rot0).angle < 1e-4   # orientation kept
    uv = [world_to_camera_view(scene, cam, p) for p in pts]
    xs, ys = [p.x for p in uv], [p.y for p in uv]
    assert min(xs) > -0.01 and max(xs) < 1.01 and min(ys) > -0.01 and max(ys) < 1.01, (xs, ys)
    fill = max(max(xs) - min(xs), max(ys) - min(ys))
    assert abs(fill - 0.95) < 0.02, fill                          # Maya's fit factor on the tighter axis
    centre = ((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2)
    assert abs(centre[0] - 0.5) < 0.01 and abs(centre[1] - 0.5) < 0.01, centre
    # a Maya-locked camera doesn't move
    cam.lock_location = cam.lock_rotation = (True,) * 3
    m0 = cam.matrix_world.copy()
    box.location.x += 4.0
    bpy.context.view_layer.update()
    assert not view.frame_camera(bpy.context, cam, [box.matrix_world @ v.co for v in mesh.vertices])
    assert cam.matrix_world == m0


def test_uv_checker_toggles_off():
    from bpy.types import Material  # noqa: F401
    scene = bpy.context.scene
    mesh = bpy.data.meshes.new("plane129")
    mesh.from_pydata([(0, 0, 0), (1, 0, 0), (1, 1, 0)], [], [(0, 1, 2)])
    own = bpy.data.materials.new("own129")
    mesh.materials.append(own)
    ob = bpy.data.objects.new("plane129", mesh)
    scene.collection.objects.link(ob)
    bare = bpy.data.objects.new("bare129", bpy.data.meshes.new("bare129"))
    scene.collection.objects.link(bare)
    for o in scene.objects:
        o.select_set(o in (ob, bare))
    bpy.context.view_layer.objects.active = ob
    assert not mi.checker_on(bpy.context)
    assert bpy.ops.allset.checker_toggle() == {'FINISHED'}
    assert mi.checker_on(bpy.context)
    assert ob.material_slots[0].material.get(mi.CHECKER_MAT) and mesh.materials[0] == own
    assert bare.material_slots[0].material.get(mi.CHECKER_MAT)
    assert bpy.ops.allset.checker_toggle() == {'FINISHED'}
    assert not mi.checker_on(bpy.context)
    assert ob.material_slots[0].link == 'DATA' and ob.material_slots[0].material == own
    assert all(not (s.material and s.material.get(mi.CHECKER_MAT)) for s in bare.material_slots)
    assert all(s.link == 'DATA' for s in bare.material_slots)
