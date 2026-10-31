"""In a real UI: Maya selection modifiers on Dope Sheet keys and Node Editor nodes — click = only that,
Shift+click = toggle, Ctrl+click = deselect, Ctrl+Shift+click = add."""

import os
import sys

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import check, ev, run, step, setup, screenshot, view3d, win  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}
FRAMES = (1, 10, 20)
KEYS = {"ctrl": "LEFT_CTRL", "shift": "LEFT_SHIFT"}


def area():
    return C["area"]


def region():
    return next(r for r in area().regions if r.type == 'WINDOW')


def fcurve():
    ob = bpy.data.objects["Cube"]
    return ob.animation_data.action.layers[0].strips[0].channelbags[0].fcurves[0]


def selected_keys():
    return [round(k.co.x) for k in fcurve().keyframe_points if k.select_control_point]


def key_xy(frame):
    r = region()
    x = r.view2d.view_to_region(frame, 0, clip=False)[0]
    return r.x + int(x), C["y"]


def click(xy, *mods):
    def s1():
        ev('MOUSEMOVE', 'NOTHING', x=xy()[0], y=xy()[1])

    def s2():
        for m in mods:
            ev(KEYS[m], 'PRESS')
        x, y = xy()
        kw = {m: True for m in mods}
        ev('LEFTMOUSE', 'PRESS', x=x, y=y, **kw)
        ev('LEFTMOUSE', 'RELEASE', x=x, y=y, **kw)
        for m in mods:
            ev(KEYS[m], 'RELEASE')
    step(s1)
    step(s2)


@step
def s_setup():
    setup()
    ob = bpy.data.objects["Cube"]
    for o in bpy.context.view_layer.objects:
        o.select_set(o is ob)
    bpy.context.view_layer.objects.active = ob
    for f in FRAMES:
        ob.location.x = f * 0.1
        ob.keyframe_insert("location", index=0, frame=f)
    a, _r = view3d()
    C["area"] = a
    a.ui_type = 'DOPESHEET'


@step
def s_view():
    r = region()
    with bpy.context.temp_override(window=win(), area=area(), region=r):
        bpy.ops.action.view_all()
    for kp in fcurve().keyframe_points:
        kp.select_control_point = False
    # the rows under the scrub strip: try heights until a plain click selects key 10 alone
    C["ys"] = [r.y + r.height - int(d * bpy.context.preferences.system.ui_scale) for d in (40, 50, 60, 70, 30, 80)]


def probe(i):
    def s_move():
        if "y" in C or i >= len(C["ys"]):
            return
        r = region()
        x = r.x + int(r.view2d.view_to_region(10, 0, clip=False)[0])
        ev('MOUSEMOVE', 'NOTHING', x=x, y=C["ys"][i])

    def s_click():
        if "y" in C or i >= len(C["ys"]):
            return
        r = region()
        x = r.x + int(r.view2d.view_to_region(10, 0, clip=False)[0])
        ev('LEFTMOUSE', 'PRESS', x=x, y=C["ys"][i])
        ev('LEFTMOUSE', 'RELEASE', x=x, y=C["ys"][i])

    def s_look():
        if "y" in C or i >= len(C["ys"]):
            return
        if selected_keys() == [10]:
            C["y"] = C["ys"][i]
    step(s_move)
    step(s_click)
    step(s_look)


for _i in range(6):
    probe(_i)


@step
def s_plain():
    check(f"click on key 10 selects only it ({selected_keys()})", "y" in C and selected_keys() == [10])
    if "y" not in C:
        C["y"] = C["ys"][0]


click(lambda: key_xy(20), "shift")


@step
def s_shift():
    check(f"Shift+click adds key 20 ({selected_keys()})", selected_keys() == [10, 20])


click(lambda: key_xy(20), "shift")


@step
def s_shift_again():
    check(f"Shift+click again toggles key 20 off ({selected_keys()})", selected_keys() == [10])


click(lambda: key_xy(1), "ctrl", "shift")


@step
def s_ctrl_shift():
    check(f"Ctrl+Shift+click adds key 1 ({selected_keys()})", selected_keys() == [1, 10])


click(lambda: key_xy(10), "ctrl")


@step
def s_ctrl():
    check(f"Ctrl+click deselects key 10 ({selected_keys()})", selected_keys() == [1])
    if SHOTS:
        screenshot(os.path.join(SHOTS, "gui_step86_dopesheet.png"))
    # Node Editor: the cube's material
    mat = bpy.data.materials.get("Material") or bpy.data.materials.new("Material")
    mat.use_nodes = True
    nt = mat.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    for i, name in enumerate(("A", "B", "C")):
        n = nt.nodes.new("ShaderNodeValue")
        n.name = n.label = name
        n.location = (i * 300, 0)
        n.select = False
    ob = bpy.data.objects["Cube"]
    if not ob.data.materials:
        ob.data.materials.append(mat)
    ob.active_material = mat
    area().ui_type = 'ShaderNodeTree'


@step
def s_node_view():
    with bpy.context.temp_override(window=win(), area=area(), region=region()):
        bpy.ops.node.view_all()
        bpy.ops.node.select_all(action='DESELECT')


def node_xy(name):
    def at():
        n = bpy.data.materials["Material"].node_tree.nodes[name]
        s = bpy.context.preferences.system.ui_scale
        r = region()
        # the node header, a little inside its top-left corner (view space = location x UI scale)
        x, y = r.view2d.view_to_region((n.location.x + 40) * s, (n.location.y - 10) * s, clip=False)
        return r.x + int(x), r.y + int(y)
    return at


def nodes_selected():
    return sorted(n.name for n in bpy.data.materials["Material"].node_tree.nodes if n.select)


click(node_xy("A"))


@step
def s_node_plain():
    check(f"Node Editor click selects only A ({nodes_selected()})", nodes_selected() == ["A"])


click(node_xy("B"), "shift")


@step
def s_node_shift():
    check(f"Shift+click toggles B on ({nodes_selected()})", nodes_selected() == ["A", "B"])


click(node_xy("C"), "ctrl", "shift")


@step
def s_node_add():
    check(f"Ctrl+Shift+click adds C ({nodes_selected()})", nodes_selected() == ["A", "B", "C"])


click(node_xy("C"), "ctrl", "shift")


@step
def s_node_add_again():
    check(f"Ctrl+Shift+click on a selected node keeps it ({nodes_selected()})", nodes_selected() == ["A", "B", "C"])


click(node_xy("A"), "ctrl")


@step
def s_node_ctrl():
    check(f"Ctrl+click deselects A ({nodes_selected()})", nodes_selected() == ["B", "C"])
    if SHOTS:
        screenshot(os.path.join(SHOTS, "gui_step86_nodes.png"))
    area().ui_type = 'VIEW_3D'


run()
