"""#283: the Channel Box name line renames the lead in place, like Maya's name field: Maya's name rule, a taken name
gets the lowest free number, the shape follows."""

from importlib import import_module

import bpy

import kit

cb = import_module(kit.MODULE + ".ui.channel_box")


def _cube(name):
    bpy.ops.mesh.primitive_cube_add()
    ob = bpy.context.active_object
    ob.name = name
    ob.data.name = name + "Shape"
    return ob


def test_rename_lead_like_maya():
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    a = _cube("pCube1")
    _cube("box1")
    assert cb.rename_lead(a, "box") == "box"
    assert a.name == "box" and a.data.name == "boxShape"
    assert cb.rename_lead(a, "box1") == "box2"            # taken: the lowest free number
    assert a.data.name == "boxShape2"
    assert cb.rename_lead(a, "my box") == "my_box"         # spaces -> "_"
    assert cb.rename_lead(a, "1box") is None and a.name == "my_box"   # Maya's rule: no leading digit
    assert cb.rename_lead(a, "my_box") is None             # unchanged


def test_name_proxy_renames_the_lead():
    a = bpy.data.objects["my_box"]
    for ob in bpy.context.view_layer.objects:
        ob.select_set(ob == a)
    bpy.context.view_layer.objects.active = a
    cb_props = bpy.context.scene.allset_cb
    assert cb_props.lead_name == "my_box"
    cb_props.lead_name = "crate"
    assert a.name == "crate" and cb_props.lead_name == "crate"
