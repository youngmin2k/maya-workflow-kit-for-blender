"""Blender's own render keys in Maya mode: F12 = Render Image and Ctrl+F12 = Render Animation are render.render items
of the Maya keymap ("Screen"), IC's Ctrl+Alt+Enter Render Animation stays, and F12 stays Maya's UV selection mask in
the 3D View (object / edit mesh) and the UV Editor. Renders add no light of their own. The GUI side (F12 opens the
Render window) is tests/gui/gui_step214_f12.py."""

from importlib import import_module

import bpy

import kit

sw = import_module(kit.MODULE + ".switch")


def _items(km_name, idname, kc=None):
    km = (kc or kit.maya_kc()).keymaps.get(km_name)
    return [k for k in (km.keymap_items if km else ()) if k.idname == idname]


def _ev(k):
    return (k.type, k.value, k.shift, k.ctrl, k.alt)


def _f12_items():
    return {_ev(k): dict(animation=k.properties.animation, use_viewport=k.properties.use_viewport)
            for k in _items("Screen", "render.render") if k.active and k.type == 'F12'}


def test_blender_render_keys_in_maya_mode():
    screen = _f12_items()
    assert screen == {("F12", 'PRESS', False, False, False): {"animation": False, "use_viewport": True},
                      ("F12", 'PRESS', False, True, False): {"animation": True, "use_viewport": True}}, screen
    # the first plain F12 item of Screen is Blender's render (nothing kit-made in front of it)
    km = kit.maya_kc().keymaps["Screen"]
    first_f12 = next(k for k in km.keymap_items
                     if k.active and (k.type, k.ctrl, k.alt, k.shift) == ("F12", False, False, False))
    assert first_f12.idname == "render.render", first_f12.idname
    # IC's Ctrl+Alt+Enter Render Animation is Blender's render.render again
    se = [(_ev(k), k.properties.animation) for k in _items("Screen Editing", "render.render")
          if (k.type, k.ctrl, k.alt) == ("RET", True, True)]
    assert se == [(("RET", 'PRESS', False, True, True), True)], se
    assert not hasattr(bpy.types, "ALLSET_OT_render_blender")
    assert not [k for km in kit.maya_kc().keymaps for k in km.keymap_items if k.idname == "allset.render_blender"]


def test_maya_f12_uv_mask_keeps_the_3d_view_and_uv_editor():
    for km_name in ("Object Mode", "Mesh", "UV Editor"):
        uv = [k for k in _items(km_name, "allset.uv_component") if _ev(k) == ("F12", 'PRESS', False, False, False)]
        assert uv and uv[0].properties.mode == 'UV', km_name


def test_render_adds_no_light():
    sc = bpy.context.scene
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    bpy.ops.mesh.primitive_cube_add(size=2.0)
    cam = bpy.data.objects.new("camera1", bpy.data.cameras.new("camera1"))
    sc.collection.objects.link(cam)
    cam.location = (5.0, -5.0, 4.0)
    sc.camera = cam
    sc.render.engine = 'BLENDER_WORKBENCH'
    sc.render.resolution_x = sc.render.resolution_y = 16
    seen = []

    def pre(scene, *_a):
        seen.append([o.name for o in scene.objects if o.type == 'LIGHT'])
    bpy.app.handlers.render_pre.append(pre)
    try:
        assert bpy.ops.render.render() == {'FINISHED'}
    finally:
        bpy.app.handlers.render_pre.remove(pre)
    assert seen == [[]], seen
    assert not [o for o in bpy.data.objects if o.type == 'LIGHT']


def test_maya_mode_off_and_disable_take_the_kit_render_keys_away():
    def kit_f12():
        kcs = bpy.context.window_manager.keyconfigs
        return [k for k in _items("Screen", "render.render", kcs.addon) if k.type == 'F12'] if kcs.addon else []
    assert kit_f12()
    sw.set_mode(False, layout=False)
    try:
        assert not kit_f12()
    finally:
        sw.set_mode(True, layout=False)
    assert kit_f12()
    kit.disable()
    try:
        assert not kit_f12()
    finally:
        kit.enable()
    assert kit_f12()
