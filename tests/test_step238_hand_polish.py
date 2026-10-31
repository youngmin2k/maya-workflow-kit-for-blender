"""Issue #146: rig and animation hand polish.

③-6 Enable IK Solver is a Maya check item (the menu shows the state), ③-8 Paint Skin Weights starts on the first
influence (Maya: joint1 hilited), ③-17 an animated FBX sets the
Time Slider to the file's range, chain ④ SDK: a blend shape weight typed
and keyed before msgbus runs isn't overwritten by its driver.
"""

import os
from importlib import import_module

import bpy

import kit
import test_step223_ik_fk as IK
import test_step226_sdk as SDK
import test_step58_skin as SKIN

ik_fk = import_module(kit.MODULE + ".operators.ik_fk")
skin = import_module(kit.MODULE + ".operators.skin")
sdk = import_module(kit.MODULE + ".operators.driven_key")
cb = import_module(kit.MODULE + ".ui.channel_box")
menu_map = import_module(kit.MODULE + ".ui.menu_map")
menu_sets = import_module(kit.MODULE + ".ui.menu_sets")

OUT = os.path.join(os.environ.get("ALLSET_TEST_OUT", bpy.app.tempdir), "step238")


def check(ok, msg):
    if not ok:
        raise AssertionError(msg)


def test_enable_ik_solver_is_a_check_item():
    arm, handle, con = IK._arm()
    wm = bpy.context.window_manager
    ik_fk._STATE["on"] = False
    check(menu_map.normalize(menu_map.MAP["Key/IK/FK Keys/Enable IK Solver"])[0] == "prop", "prop kind")
    owner, attr = menu_sets.prop_owner(bpy.context, "window_manager.allset_ik_solver")
    check(owner == wm and attr == "allset_ik_solver", (owner, attr))
    check(not wm.allset_ik_solver, "factory off (Maya ikFKSwitchState 0)")
    IK._select(handle)
    menu_sets.set_prop(bpy.context, "window_manager.allset_ik_solver", {})     # = clicking the menu item
    check(wm.allset_ik_solver and handle["ikBlend"] == 1.0, "first click: on, Ik Blend 1")
    menu_sets.set_prop(bpy.context, "window_manager.allset_ik_solver", {})
    IK._update()
    check(not wm.allset_ik_solver and handle["ikBlend"] == 0.0 and con.influence == 0.0, "second click: off")
    # nothing selected: Maya flips the check and reports its error (no exception reaches the menu)
    IK._select()
    wm.allset_ik_solver = True
    check(wm.allset_ik_solver, "the check flipped with nothing selected")
    ik_fk._STATE["on"] = False


def test_paint_skin_weights_starts_on_the_first_influence():
    arm, cyl = SKIN._bound()
    check(cyl.vertex_groups.active.name != "joint1", "Bind Skin leaves the last made group active (the setup)")
    for ob in bpy.context.selected_objects:
        ob.select_set(False)
    cyl.select_set(True)
    bpy.context.view_layer.objects.active = cyl
    check(bpy.ops.allset.paint_skin_weights() == {'FINISHED'}, "enter")
    check(cyl.vertex_groups.active.name == "joint1", f"first influence {cyl.vertex_groups.active.name}")
    cyl.vertex_groups.active_index = cyl.vertex_groups["joint3"].index        # the artist picks joint3
    bpy.ops.allset.paint_skin_weights()                                         # leave
    bpy.ops.allset.paint_skin_weights()                                         # and come back
    check(cyl.vertex_groups.active.name == "joint3", "Maya keeps the picked influence")
    bpy.ops.allset.paint_skin_weights()
    check(skin.first_influence(cyl).name == "joint1", "hierarchy order")


def test_animated_fbx_sets_the_time_slider():
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    sc = bpy.context.scene
    sc.frame_start, sc.frame_end = 1, 20
    bpy.ops.mesh.primitive_cube_add()
    cube = bpy.context.active_object
    cube.name = "pCube1"
    for f, x in ((1, 0.0), (20, 2.0)):
        cube.location.x = x
        cube.keyframe_insert("location", frame=f)
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, "anim.fbx")
    check(bpy.ops.allset.file_export_all('EXEC_DEFAULT', filepath=path, export_type='FBX') == {'FINISHED'}, "export")
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    for a in list(bpy.data.actions):
        bpy.data.actions.remove(a)
    sc.frame_start, sc.frame_end = 0, 250                  # the scene's own range before the import
    check(bpy.ops.allset.file_import('EXEC_DEFAULT', filepath=path, import_type='FBX') == {'FINISHED'}, "import")
    check((sc.frame_start, sc.frame_end) == (1, 20), f"Time Slider {sc.frame_start}-{sc.frame_end}")


def test_sdk_typed_weight_survives_an_update_before_key():
    SDK._clear()
    me = bpy.data.meshes.new("pSphere1")
    me.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)])
    head = bpy.data.objects.new("pSphere1", me)
    bpy.context.scene.collection.objects.link(head)
    head.shape_key_add(name="Basis")
    head.shape_key_add(name="bulge").value = 0.0
    key = me.shape_keys
    key.name = "blendShape1"
    drv = SDK._empty("ctrl", curl=0)
    bpy.ops.allset.sdk_window()
    SDK._load_driver(drv, "cp:curl")
    SDK._select(head)
    cb.set_selected_channels([])
    bpy.ops.allset.sdk_load(which='DRIVEN')
    bpy.ops.allset.sdk_pick(which='NODE', index=1)
    bpy.ops.allset.sdk_pick(which='DRIVEN', key="bs:bulge")
    bpy.ops.allset.sdk_key()                                    # (0, 0)
    fc = sdk.sdk_fcurve(key, "bs:bulge")
    cb.set_value(drv, "cp:curl", 90.0)
    bpy.context.view_layer.update()
    key.key_blocks["bulge"].value = 1.0                         # typed (Shape Editor slider), no msgbus pass yet
    bpy.context.view_layer.update()                             # e.g. the driver joint posed in the same tick
    check(abs(key.key_blocks["bulge"].value - 1.0) < 1e-6 and fc.mute,
          f"the driver didn't write over the typed weight ({key.key_blocks['bulge'].value}, mute {fc.mute})")
    bpy.ops.allset.sdk_key()                                    # (90, 1)
    check(not fc.mute, "Key unmutes")
    cb.set_value(drv, "cp:curl", 45.0)
    check(abs(SDK._read(key, "bs:bulge") - 0.5) < 1e-3, SDK._read(key, "bs:bulge"))
    # posing the driver alone keeps following the driver (nothing typed)
    cb.set_value(drv, "cp:curl", 90.0)
    bpy.context.view_layer.update()
    check(not fc.mute and abs(SDK._read(key, "bs:bulge") - 1.0) < 1e-3, "driven value follows the driver")
    bpy.ops.allset.sdk_close()
