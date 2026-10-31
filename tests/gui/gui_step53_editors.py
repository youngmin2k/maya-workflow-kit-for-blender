"""In a real UI: with Maya Workflow Kit on (Maya keymap active), the other editors keep their own basic
operation (Maya add-ons that break Graph Editor navigation).

- Text Editor: typing inserts text, including the keys the kit binds elsewhere (z = undo, h = hide,
  q / w / e / r = tools, Space = hotbox).
- Graph Editor: Alt+MMB drag pans, Alt+RMB drag zooms, A frames all, LMB click selects a key.
- Node Editor: Alt+MMB drag pans, LMB click selects a node.
Screenshots: gui_step53_text.png, gui_step53_graph.png, gui_step53_node.png."""

import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, run, setup, screenshot, step, view3d, win  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


def shot(name):
    if SHOTS:
        screenshot(os.path.join(SHOTS, name))


def area():
    return C["area"]


def region():
    return next(r for r in area().regions if r.type == 'WINDOW')


def centre():
    r = region()
    return r.x + r.width // 2, r.y + r.height // 2


def view_at_centre():
    r = region()
    return tuple(r.view2d.region_to_view(r.width / 2, r.height / 2))


def redraw():
    for a in win().screen.areas:
        a.tag_redraw()


@step
def s_setup():
    setup()
    bpy.ops.allset.keymap_activate()
    check("Maya keymap active", sys.modules["sim"].maya_keys())
    C["area"], _r = view3d()
    # --- Text Editor
    text = bpy.data.texts.new("probe")
    area().type = 'TEXT_EDITOR'
    area().spaces.active.text = text
    C["text"] = text
    redraw()


@step
def s_text_hover():
    x, y = centre()
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)


@step
def s_text_type():
    for key, ch in (('A', 'a'), ('Z', 'z'), ('H', 'h'), ('SPACE', ' '), ('Q', 'q'), ('W', 'w'), ('E', 'e'),
                    ('R', 'r'), ('F', 'f')):
        ev(key, 'PRESS', unicode=ch)
        ev(key, 'RELEASE')


@step
def s_text_check():
    body = C["text"].as_string()
    check(f"Text Editor: typing inserts every key, even z / h / Space / q w e r / f ({body!r})",
          body == "azh qwerf")
    check("no hotbox / marking menu opened over the Text Editor", not import_module(MODULE + ".marking.draw").ACTIVE)
    shot("gui_step53_text.png")
    # --- Graph Editor: a cube with two keys on X location
    bpy.ops.mesh.primitive_cube_add()
    ob = bpy.context.active_object
    for frame, x in ((1, 0.0), (40, 6.0)):
        ob.location.x = x
        ob.keyframe_insert("location", index=0, frame=frame)
    area().type = 'GRAPH_EDITOR'
    area().ui_type = 'FCURVES'
    redraw()


@step
def s_graph_frame():
    x, y = centre()
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
    ev('A', 'PRESS', x=x, y=y)
    ev('A', 'RELEASE', x=x, y=y)


@step
def s_graph_framed():
    r = region()
    fc = bpy.context.active_object.animation_data.action.fcurves[0] if hasattr(
        bpy.context.active_object.animation_data.action, "fcurves") else None
    if fc is None:   # Blender 5.x layered actions
        bag = bpy.context.active_object.animation_data.action.layers[0].strips[0].channelbag(
            bpy.context.active_object.animation_data.action_slot)
        fc = bag.fcurves[0]
    C["fc"] = fc
    ok = True
    for kp in fc.keyframe_points:
        px, py = r.view2d.view_to_region(kp.co.x, kp.co.y, clip=False)
        ok &= 0 <= px <= r.width and 0 <= py <= r.height
    check("Graph Editor: A frames all keys (both keys inside the view)", ok)
    for kp in fc.keyframe_points:
        kp.select_control_point = False
    kp = fc.keyframe_points[1]
    px, py = r.view2d.view_to_region(kp.co.x, kp.co.y, clip=False)
    C["key"] = (r.x + px, r.y + py)
    ev('MOUSEMOVE', 'NOTHING', x=C["key"][0], y=C["key"][1])


@step
def s_graph_click():
    ev('LEFTMOUSE', 'PRESS', x=C["key"][0], y=C["key"][1])
    ev('LEFTMOUSE', 'RELEASE', x=C["key"][0], y=C["key"][1])


@step
def s_graph_clicked():
    sel = [kp.select_control_point for kp in C["fc"].keyframe_points]
    check(f"Graph Editor: LMB click selects that key only ({sel})", sel == [False, True])
    x, y = centre()
    C["v0"] = view_at_centre()
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
    ev('LEFT_ALT', 'PRESS', x=x, y=y)
    ev('MIDDLEMOUSE', 'PRESS', x=x, y=y, alt=True)


@step
def s_graph_pan_move():
    x, y = centre()
    for i in range(1, 6):
        ev('MOUSEMOVE', 'NOTHING', x=x + 20 * i, y=y + 10 * i, alt=True)


@step
def s_graph_pan_release():
    x, y = centre()
    ev('MIDDLEMOUSE', 'RELEASE', x=x + 100, y=y + 50, alt=True)
    ev('LEFT_ALT', 'RELEASE', x=x + 100, y=y + 50)


@step
def s_graph_panned():
    v1 = view_at_centre()
    check(f"Graph Editor: Alt+MMB drag pans the view ({C['v0']} -> {v1})", v1[0] < C["v0"][0] - 1e-3)
    r = region()
    C["w0"] = r.view2d.region_to_view(r.width, 0)[0] - r.view2d.region_to_view(0, 0)[0]
    x, y = centre()
    ev('LEFT_ALT', 'PRESS', x=x, y=y)
    ev('RIGHTMOUSE', 'PRESS', x=x, y=y, alt=True)


@step
def s_graph_zoom_move():
    x, y = centre()
    for i in range(1, 6):
        ev('MOUSEMOVE', 'NOTHING', x=x + 25 * i, y=y, alt=True)


@step
def s_graph_zoom_release():
    x, y = centre()
    ev('RIGHTMOUSE', 'RELEASE', x=x + 125, y=y, alt=True)
    ev('LEFT_ALT', 'RELEASE', x=x + 125, y=y)


@step
def s_graph_zoomed():
    r = region()
    w1 = r.view2d.region_to_view(r.width, 0)[0] - r.view2d.region_to_view(0, 0)[0]
    check(f"Graph Editor: Alt+RMB drag zooms ({C['w0']:.1f} -> {w1:.1f} frames wide)", abs(w1 - C["w0"]) > 0.5)
    shot("gui_step53_graph.png")
    # --- Node Editor (Shader): the cube's material
    ob = bpy.context.active_object
    mat = bpy.data.materials.new("probeMaterial")
    mat.use_nodes = True
    ob.data.materials.append(mat)
    # the new cube may already have lambert1 (the kit's default material): show this material's tree
    ob.active_material_index = len(ob.material_slots) - 1
    area().type = 'NODE_EDITOR'
    area().ui_type = 'ShaderNodeTree'
    for n in mat.node_tree.nodes:
        n.select = False
    C["mat"] = mat
    redraw()


@step
def s_node_frame():
    x, y = centre()
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
    ev('HOME', 'PRESS', x=x, y=y)
    ev('HOME', 'RELEASE', x=x, y=y)


@step
def s_node_framed():
    redraw()


@step
def s_node_pick():
    # The node's centre on screen: node locations are in view units scaled by the UI scale.
    r = region()
    node = next(n for n in C["mat"].node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
    k = bpy.context.preferences.system.ui_scale
    loc = node.location
    cx = (loc.x + node.width / 2) * k
    cy = (loc.y - 20) * k            # the header row, under the top edge
    px, py = r.view2d.view_to_region(cx, cy, clip=False)
    C["node"] = node
    C["nxy"] = (r.x + int(px), r.y + int(py))
    ev('MOUSEMOVE', 'NOTHING', x=C["nxy"][0], y=C["nxy"][1])


@step
def s_node_click():
    ev('LEFTMOUSE', 'PRESS', x=C["nxy"][0], y=C["nxy"][1])
    ev('LEFTMOUSE', 'RELEASE', x=C["nxy"][0], y=C["nxy"][1])


@step
def s_node_clicked():
    tree = C["mat"].node_tree
    check(f"Node Editor: LMB click selects the node ({[n.name for n in tree.nodes if n.select]})",
          C["node"].select and tree.nodes.active == C["node"])
    x, y = centre()
    C["v0"] = view_at_centre()
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
    ev('LEFT_ALT', 'PRESS', x=x, y=y)
    ev('MIDDLEMOUSE', 'PRESS', x=x, y=y, alt=True)


@step
def s_node_pan_move():
    x, y = centre()
    for i in range(1, 6):
        ev('MOUSEMOVE', 'NOTHING', x=x + 20 * i, y=y + 10 * i, alt=True)


@step
def s_node_pan_release():
    x, y = centre()
    ev('MIDDLEMOUSE', 'RELEASE', x=x + 100, y=y + 50, alt=True)
    ev('LEFT_ALT', 'RELEASE', x=x + 100, y=y + 50)


@step
def s_node_panned():
    v1 = view_at_centre()
    check(f"Node Editor: Alt+MMB drag pans the view ({C['v0']} -> {v1})", v1[0] < C["v0"][0] - 1e-3)
    shot("gui_step53_node.png")


run()
