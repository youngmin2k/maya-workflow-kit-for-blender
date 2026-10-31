"""Channel Box INPUTS polyCube1 after Ctrl+D / Ctrl+G / Ctrl+Z / P.

tools/dogfood_session.py showed pCube1's INPUTS polyCube1 in 03 / 04 and not in 05. Its key sequence between them is
3 -> Alt+Shift+D -> 1 -> Ctrl+D -> Ctrl+G -> Ctrl+Z -> P. Here the same keys run twice in the Maya layout:

1. the exact dogfood order on pCube1, checking the creation node after every key — it has to survive 3 / 1 /
   Ctrl+D / Ctrl+G / Ctrl+Z / P and go only at Alt+Shift+D (Maya's Delete History removes polyCube1);
2. the same order without Alt+Shift+D on a fresh pCylinder1: polyCylinder1 stays through the whole session.

The Channel Box draws INPUTS from ``creation_inputs.has_node`` (= ``prim_history.node_of``), so that is what is read.
"""

import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, load_maya_layout, run, screenshot, setup, step, view3d, win  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


def ci():
    return import_module(MODULE + ".ui.creation_inputs")


def ph():
    return import_module(MODULE + ".operators.prim_history")


def centre():
    _a, region = view3d()
    ev('MOUSEMOVE', 'NOTHING', x=region.x + region.width // 2, y=region.y + region.height // 2)


def key(type, **mods):
    centre()
    ev(type, 'PRESS', **mods)
    ev(type, 'RELEASE', **mods)


def redraw():
    for a in win().screen.areas:
        a.tag_redraw()


def only(name):
    for o in bpy.context.scene.objects:
        o.select_set(o.name == name)
    bpy.context.view_layer.objects.active = bpy.data.objects[name]


def state(name):
    """(Channel Box shows the creation node, why not) for object ``name``."""
    ob = bpy.data.objects.get(name)
    if ob is None:
        return False, "no object"
    owner = ph().owner_of(ob)
    if owner is None:
        return False, f"no node on {ob.data.name if ob.data else None}"
    node = ph().node_dict(owner)
    sig = ph().signature(owner)
    return ci().has_node(ob), f"{node.get('name')} on {owner.name}, sig {'ok' if sig == node.get('sig') else 'CHANGED'}"


def expect(label, name, want):
    shown, why = state(name)
    print("G1", label, name, shown, why, flush=True)
    check(f"{label}: {name} INPUTS {'lists' if want else 'drops'} its creation node ({why})", shown == want)


@step
def s_setup():
    setup()
    load_maya_layout()


def make(kind, name, first):
    def s_make():
        bpy.ops.allset.keymap_activate()
        area, region = view3d()
        with bpy.context.temp_override(window=win(), area=area, region=region):
            if bpy.context.mode != 'OBJECT':
                bpy.ops.object.mode_set(mode='OBJECT')
            bpy.ops.allset.create(kind=kind)
            if bpy.context.mode != 'OBJECT':
                bpy.ops.object.mode_set(mode='OBJECT')
        C["name"] = name
        C["dup"] = None
        only(name)
        expect("created", name, True)
        key(first)
    s_make.__name__ = f"s_make_{name}"
    return s_make


def after(label, want, then=None):
    """Check the node after the previous key, then press the next one (``then`` = callable doing it)."""
    def fn():
        expect(label, C["name"], want)
        if then is not None:
            then()
    fn.__name__ = "s_" + label.replace(" ", "_").replace("+", "")
    return fn


def do_dup():
    key('D', ctrl=True)


def do_group():
    dup = bpy.context.active_object
    C["dup"] = dup.name
    check(f"Ctrl+D made a copy ({dup.name})", dup.name != C["name"])
    dup.location.x = 3
    bpy.data.objects[C["name"]].select_set(True)
    key('G', ctrl=True)


def do_undo():
    check("Ctrl+G made a group", any(o.type == 'EMPTY' and len(o.children) >= 2 for o in bpy.context.scene.objects))
    key('Z', ctrl=True)


def do_parent():
    # Maya's result field after Ctrl+Z = "Undo: <command>"
    text = import_module(MODULE + ".command_line")._result["text"]
    check(f"G2: result field after Ctrl+Z reads Maya's undo text ({text!r})",
          text.startswith("Undo: ") and "Group" in text)
    dup = bpy.data.objects[C["dup"]]
    dup.location.x = 3
    bpy.context.view_layer.update()
    only(C["dup"])
    bpy.data.objects[C["name"]].select_set(True)
    bpy.context.view_layer.objects.active = bpy.data.objects[C["name"]]
    key('P')


def check_parent():
    dup = bpy.data.objects[C["dup"]]
    check(f"P parented {dup.name} under {C['name']}", dup.parent is not None and dup.parent.name == C["name"])
    only(C["name"])
    redraw()


def sequence(kind, name, delete_history):
    step(make(kind, name, 'THREE'))
    if delete_history:
        step(after("3", True, lambda: key('D', alt=True, shift=True)))
        step(after("Alt+Shift+D", False, lambda: key('ONE')))
        want = False
    else:
        step(after("3", True, lambda: key('ONE')))
        want = True
    step(after("1", want, do_dup))
    step(after("Ctrl+D", want, do_group))
    step(after("Ctrl+G", want, do_undo))
    step(after("Ctrl+Z", want, do_parent))
    step(after("P", want, check_parent))
    step(redraw)
    step(after("redrawn", want))


sequence('CUBE', "pCube1", delete_history=True)


@step
def s_clear():
    if SHOTS:
        screenshot(os.path.join(SHOTS, "gui_step176_after_dogfood_order.png"))
    for o in list(bpy.context.scene.objects):
        bpy.data.objects.remove(o)


sequence('CYLINDER', "pCylinder1", delete_history=False)


@step
def s_shot():
    if SHOTS:
        screenshot(os.path.join(SHOTS, "gui_step176_no_delete_history.png"))


run()
