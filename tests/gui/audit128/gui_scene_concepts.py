"""Audit 128 repro (scene lane): Maya scene concepts a Maya user touches in the first minutes.
- Create menu kinds get Maya node names (pSphere1, nurbsCircle1, joint1, camera1, pointLight1, locator1, null1).
- Maya has ONE Visibility attribute: Channel Box Visibility, h / Shift+H and Display > Show All all read and
  write it; a Display Layer's V is a separate override (turning the layer back on does not show an object whose
  own visibility is off).
- Channel Box typing with two objects selected sets the value on both (Maya: every selected node).
PASSes when Maya-like."""

import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sim import MODULE, check, run, setup, step, view3d, win, load_maya_layout  # noqa: E402

GUI_TIMEOUT = 240
C = {}


def ov(fn, *a, **kw):
    area, region = view3d()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        return fn(*a, **kw)


def visible(ob):
    return ob.visible_get()


@step
def s_setup():
    setup()
    bpy.ops.allset.make_maya(open_layout=False)
    load_maya_layout()


@step
def s_create():
    bpy.ops.allset.keymap_activate()
    expect = {"SPHERE": "pSphere1", "NURBS_CIRCLE": "nurbsCircle1", "JOINT": "joint1", "CAMERA": "camera1",
              "POINT_LIGHT": "pointLight1", "LOCATOR": "locator1", "EMPTY_GROUP": "null1", "TEXT": "typeMesh1",
              "CV_CURVE": "curve1", "NURBS_SQUARE": "nurbsSquare1", "PLANE": "pPlane1"}
    for kind, name in expect.items():
        before = set(bpy.data.objects.keys())
        try:
            ov(bpy.ops.allset.create, kind=kind)
        except Exception as ex:
            check(f"Create {kind}: raised {ex!r}", False)
            continue
        new = sorted(set(bpy.data.objects.keys()) - before)
        print("AUDIT create", kind, new)
        check(f"Create {kind}: Maya name {name} ({new})", name in new)
    for ob in list(bpy.context.scene.objects):
        if ob.name not in ("Camera", "Light"):
            bpy.data.objects.remove(ob)


@step
def s_vis():
    ov(bpy.ops.allset.create, kind='CUBE')
    ov(bpy.ops.allset.create, kind='CUBE')
    a, b = [o for o in bpy.context.scene.objects if o.name.startswith("pCube")][:2]
    C["a"], C["b"] = a.name, b.name
    cb = import_module(MODULE + ".ui.channel_box")
    # h on a (selected only a)
    for o in bpy.context.scene.objects:
        o.select_set(False)
    a.select_set(True)
    bpy.context.view_layer.objects.active = a
    ov(bpy.ops.allset.visibility, action='TOGGLE')
    vis_attr = not a.hide_viewport
    print("AUDIT after h: visible", visible(a), "CB visibility attr (hide_viewport)", vis_attr)
    check(f"h hides pCube: Channel Box Visibility shows off like Maya (visible={visible(a)}, CB v={vis_attr})",
          not visible(a) and not vis_attr)
    ov(bpy.ops.allset.visibility, action='SHOW_LAST')
    # Channel Box Visibility 0 on b, then Display > Show All / Shift+H must show it
    cb.set_value(b, "v", False)
    print("AUDIT CB v=0: visible", visible(b))
    try:
        # what the Maya menu Display > Show runs (the kit item, no longer Blender's hide_view_clear)
        ov(bpy.ops.allset.menu_item, item="Display/Show")
    except Exception as ex:
        print("AUDIT Display > Show", ex)
    check(f"Channel Box Visibility 0, then Display > Show > All shows it again (visible={visible(b)})", visible(b))
    cb.set_value(b, "v", True)


@step
def s_layer():
    le = import_module(MODULE + ".ui.layer_editor")
    a = bpy.data.objects[C["a"]]
    b = bpy.data.objects[C["b"]]
    sc = bpy.context.scene
    coll = le.new_layer(sc, [a, b])
    cb = import_module(MODULE + ".ui.channel_box")
    cb.set_value(a, "v", False)           # a's own visibility off
    coll.allset_layer.visible = False
    coll.allset_layer.visible = True       # layer back on
    print("AUDIT layer off/on: a visible", visible(a), "b visible", visible(b))
    check(f"layer V off/on keeps an object whose own Visibility is 0 hidden (a visible={visible(a)})", not visible(a))
    check(f"layer V off/on shows the other member again (b visible={visible(b)})", visible(b))
    a.display_type = 'BOUNDS'
    coll.allset_layer.display_type = "TEMPLATE"
    coll.allset_layer.display_type = "NORMAL"
    check(f"layer Template -> Normal keeps the object's own display type (a {a.display_type})",
          a.display_type == 'BOUNDS')


@step
def s_multi_cb():
    a = bpy.data.objects[C["a"]]
    b = bpy.data.objects[C["b"]]
    for o in bpy.context.scene.objects:
        o.select_set(False)
    a.hide_viewport = False
    b.hide_viewport = False
    a.select_set(True)
    b.select_set(True)
    bpy.context.view_layer.objects.active = b
    cbp = bpy.context.scene.allset_cb
    try:
        cbp.tx_text = "7"
    except Exception as ex:
        check(f"CB tx_text raised {ex!r}", False)
        return
    print("AUDIT CB tx 7 with two selected:", a.location.x, b.location.x)
    check(f"Channel Box Translate X = 7 with two cubes selected sets both ({a.location.x:.3f}, {b.location.x:.3f})",
          abs(a.location.x - b.location.x) < 1e-6 and abs(b.location.x) > 1e-6)


run()
