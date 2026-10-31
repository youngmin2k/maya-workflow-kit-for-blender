"""Kit bugs the manual-checks sweep found (tests/gui/gui_manual_sweep.py) — headless regressions.
Set Driven Key keys 1 cm apart in a cm scene, Channel Box custom attributes clamped to Min / Max, J / Alt+J render
slot keys, the "Maya Pivot" Move axis follows the lead."""

import math
from importlib import import_module

import bpy
from mathutils import Matrix, Quaternion

import kit

sdk = import_module(kit.MODULE + ".operators.driven_key")
units = import_module(kit.MODULE + ".operators.units")
pivot = import_module(kit.MODULE + ".operators.pivot")
cb = import_module(kit.MODULE + ".ui.channel_box")


def _clear():
    st = bpy.context.window_manager.allset_sdk
    st.open = False
    st.driven.clear()
    st.driver.object = None
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    for me in list(bpy.data.meshes):
        bpy.data.meshes.remove(me)


def _select(*obs):
    for o in bpy.context.scene.objects:
        o.select_set(False)
    for o in obs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = obs[-1]


def _empty(name):
    ob = bpy.data.objects.new(name, None)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def _cm_scene():
    us = bpy.context.scene.unit_settings
    us.system, us.length_unit, us.scale_length = 'METRIC', 'CENTIMETERS', 1.0
    assert abs(units.maya_unit() - 0.01) < 1e-9


def _ry(ob):
    bpy.context.view_layer.update()
    return math.degrees(ob.rotation_euler[1])


def test_sdk_keys_one_cm_apart_stay_apart():
    """Blender merges F-curve keys less than 0.01 apart in x: a 1 cm driver step in the cm template (0.01 BU) used
    to collapse the keys into one."""
    _clear()
    _cm_scene()
    loc, cube = _empty("locator1"), _empty("pCube1")
    bpy.ops.allset.sdk_window()
    _select(loc)
    cb.set_selected_channels(["tx"])
    assert bpy.ops.allset.sdk_load(which='DRIVER') == {'FINISHED'}
    _select(cube)
    cb.set_selected_channels(["ry"])
    assert bpy.ops.allset.sdk_load(which='DRIVEN') == {'FINISHED'}
    for cm, deg in ((0, 0), (1, 45), (2, 90)):
        loc.location.x = cm * 0.01
        _select(cube)
        cb.apply_entry("ry", str(deg))
        assert bpy.ops.allset.sdk_key() == {'FINISHED'}
    fc = sdk.sdk_fcurve(cube, "ry")
    xs = [round(kp.co.x, 6) for kp in fc.keyframe_points]
    assert xs == [0.0, 1.0, 2.0], f"curve x in cm, three keys: {xs}"
    assert sdk.fcurve_scale(fc) == 100.0
    bpy.ops.allset.sdk_close()
    loc.location.x = 0.01
    assert abs(_ry(cube) - 45) < 1e-3, _ry(cube)
    loc.location.x = 0.015
    assert 45 < _ry(cube) < 90


def test_sdk_rotation_driver_keeps_raw_x():
    assert sdk.curve_scale("rx") == 1.0 and sdk.curve_scale("cp:curl") == 1.0


def test_custom_attribute_entry_is_clamped():
    _clear()
    ob = _empty("ctrl")
    _select(ob)
    assert bpy.ops.allset.add_attribute(long_name="fingerCurl", data_type='FLOAT', use_min=True, minimum=-2,
                                          use_max=True, maximum=5, default=0) == {'FINISHED'}
    cb.set_value(ob, "cp:fingerCurl", 9.0)
    assert ob["fingerCurl"] == 5.0
    cb.set_value(ob, "cp:fingerCurl", -7.0)
    assert ob["fingerCurl"] == -2.0
    cb.apply_entry("cp:fingerCurl", "+=100")
    assert ob["fingerCurl"] == 5.0
    bpy.ops.allset.add_attribute(long_name="free", data_type='FLOAT', default=0)
    cb.set_value(ob, "cp:free", 1e6)
    assert ob["free"] == 1e6, "no limits: nothing clamped"


def test_render_slot_keys():
    km = kit.maya_kc().keymaps["Image"]
    items = [(i.alt, i.properties.reverse) for i in km.keymap_items
             if i.active and i.idname == "image.cycle_render_slot" and i.type == 'J' and not (i.ctrl or i.shift)]
    assert sorted(items) == [(False, False), (True, True)], items


def test_maya_pivot_axis_follows_the_lead():
    _clear()
    us = bpy.context.scene.unit_settings
    us.system, us.scale_length = 'METRIC', 1.0
    a, b, c = _empty("a"), _empty("b"), _empty("c")
    a[pivot.PROP] = tuple(Quaternion((0, 0, 1), math.radians(30)))
    c[pivot.PROP] = tuple(Quaternion((0, 0, 1), math.radians(60)))
    _select(a)
    bpy.context.view_layer.update()
    pivot.follow_lead(bpy.context, bpy.context.scene)
    turned = Quaternion((0, 0, 1), math.radians(30)).to_matrix()
    assert pivot.set_custom_orientation(bpy.context, turned)
    slot = bpy.context.scene.transform_orientation_slots[pivot.MOVE_SLOT]
    assert slot.type == pivot.ORIENT_NAME
    _select(c)
    pivot.follow_lead(bpy.context, bpy.context.scene)
    angle = Matrix(slot.custom_orientation.matrix).to_quaternion().angle
    assert slot.type == pivot.ORIENT_NAME and abs(math.degrees(angle) - 60) < 1e-3, math.degrees(angle)
    _select(b)
    pivot.follow_lead(bpy.context, bpy.context.scene)
    assert slot.type == 'LOCAL', "a lead without a turned pivot: Object axes"
