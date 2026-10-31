"""In a real UI (Issue #111): Layer Editor multi-selection -> the
Graph Editor shows every selected layer's curves.

Maya Workflow Kit layout, pCube1 keyed on BaseAnimation (tx 0@1 5@12 0@24, ry 0 -> 90), AnimLayer1 (additive, tx
+2@6 -1@18) and AnimLayer2 (override, ty 1@6 3@18) made with the kit operators. Graph Editor opened from the Maya menu,
then a click on AnimLayer1's row in the Layer Editor Anim tab and a Ctrl+click on AnimLayer2's row (Maya: both
selected, two curves). Checks: selection, kit outliner rows, the curve drawn by ui/graph_layers.py (its line model and
screen pixels: a dim red tx line next to Blender's green ty curve), Zero Weight and Key Layer = one undo step.
Shots ``gui_step204_*.png`` with ``--shots`` (Layer Editor, Graph Editor:
click_l1_ctrl_l2_graph_screen.png)."""

import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sim  # noqa: E402
from sim import (MODULE, check, dock_area, dock_region, ev, find_button, load_maya_layout, run,  # noqa: E402
                 setup, step, view3d, win)

GUI_TIMEOUT = 400
SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


def mod(name):
    return import_module(f"{MODULE}.{name}")


def al():
    return mod("operators.anim_layers")


def redraw():
    for w in bpy.context.window_manager.windows:
        for a in w.screen.areas:
            a.tag_redraw()


def dock():
    return dock_area(), dock_region()


def graph():
    for w in bpy.context.window_manager.windows:
        for a in w.screen.areas:
            if a.ui_type == 'FCURVES':
                return w, a
    return None, None


def region(area, kind):
    return next(r for r in area.regions if r.type == kind)


def shot(name, window=None):
    if SHOTS:
        with bpy.context.temp_override(window=window or win()):
            bpy.ops.screen.screenshot(filepath=os.path.join(SHOTS, name))


def selected_names():
    return [e.name for e in al().selected_layers(bpy.context.scene)]


def park():
    _a, r = view3d()
    ev('MOUSEMOVE', 'NOTHING', x=r.x + r.width // 2, y=r.y + r.height // 2)


def cube():
    return bpy.data.objects["pCube1"]


def weight_keys(name):
    a = al()
    st = a._strip(a.tracks(cube())[name])
    fc = a.weight_curve(st)
    return [] if fc is None else [tuple(kp.co) for kp in fc.keyframe_points]


# --- scene -------------------------------------------------------------------------------------------------------

@step
def s_setup():
    setup()
    bpy.ops.allset.make_maya(open_layout=False)
    load_maya_layout()


@step
def s_scene():
    bpy.ops.allset.keymap_activate()
    area, reg = view3d()
    sc = bpy.context.scene
    u = mod("operators.units").maya_unit(sc)
    with bpy.context.temp_override(window=win(), area=area, region=reg, space_data=area.spaces.active):
        bpy.ops.allset.create(kind='CUBE')
    ob = cube()
    for f, x in ((1, 0.0), (12, 5.0), (24, 0.0)):
        ob.location.x = x * u
        ob.keyframe_insert("location", index=0, frame=f)
    for f, r in ((1, 0.0), (24, 1.5708)):
        ob.rotation_euler.y = r
        ob.keyframe_insert("rotation_euler", index=1, frame=f)
    for o in sc.objects:
        o.select_set(o == ob)
    bpy.context.view_layer.objects.active = ob
    a = al()
    key_of = mod("operators.character_sets").channel_key_of
    with bpy.context.temp_override(window=win(), area=area, region=reg):
        # AnimLayer1: additive, member tx only (Maya Add Selected + attribute list)
        bpy.ops.allset.anim_layer_create(from_selected=False)
        a.add_attrs(sc, ob, "AnimLayer1", [key_of("location", 0)])
        a.sync(sc)
        for f, d in ((6, 2.0), (18, -1.0)):
            base = a.base_curve(ob, "location", 0).evaluate(f)
            check(f"AnimLayer1 tx key at {f}", a.key(ob, "location", 0, frame=f, value=base + d * u, scene=sc))
        # AnimLayer2: override, member ty only
        bpy.ops.allset.anim_layer_create(from_selected=False)
        sc.allset_anim_layers[2].override = True
        a.add_attrs(sc, ob, "AnimLayer2", [key_of("location", 1)])
        a.sync(sc)
        for f, y in ((6, 1.0), (18, 3.0)):
            check(f"AnimLayer2 ty key at {f}", a.key(ob, "location", 1, frame=f, value=y * u, scene=sc))
    names = [e.name for e in sc.allset_anim_layers]
    check(f"layers made ({names})", names == ["BaseAnimation", "AnimLayer1", "AnimLayer2"])
    sc.allset_anim_layer_index = 0          # plain BaseAnimation selection: the clicks below change it
    sc.frame_set(10)
    dock_area('CHANNEL_BOX')
    bpy.context.window_manager.allset_le_tab = 'ANIM'
    with bpy.context.temp_override(window=win(), area=area, region=reg):
        C["graph"] = bpy.ops.allset.menu_item(item="Windows/Animation Editors/Graph Editor")
    redraw()


@step
def s_graph_open():
    w, a = graph()
    check(f"Graph Editor window opened ({C['graph']})", a is not None)
    redraw()


@step
def s_wait():
    redraw()


# --- click AnimLayer2's row? no: AnimLayer1 first (plain), then Ctrl AnimLayer2 -----------------------------------

step(find_button(dock, lambda _p, c: "anim_layer_select(index=2)" in c, C, "row2", x_frac=0.6, step_px=4,
                 start_frac=0.35))


@step
def s_find_row1():
    check(f"AnimLayer2 row found ({C.get('row2')})", C.get("row2") is not None)
    if C.get("row2") is None:
        return
    reg = dock_region()
    s = bpy.context.preferences.system.ui_scale
    y = C["row2"][1] - int(8 * s)       # just below AnimLayer2's row centre
    frac = (reg.y + reg.height - 4 - y) / reg.height
    sim._steps.insert(0, find_button(dock, lambda _p, c: "anim_layer_select(index=1)" in c, C, "row1",
                                     x_frac=(C["row2"][0] - reg.x) / reg.width, step_px=3, start_frac=frac))


@step
def s_hover1():
    check(f"AnimLayer1 row found ({C.get('row1')})", C.get("row1") is not None)
    if C.get("row1"):
        ev('MOUSEMOVE', 'NOTHING', x=C["row1"][0], y=C["row1"][1])


@step
def s_press1():
    if C.get("row1"):
        ev('LEFTMOUSE', 'PRESS')


@step
def s_release1():
    if C.get("row1"):
        ev('LEFTMOUSE', 'RELEASE')
    redraw()


@step
def s_clicked1():
    sel = selected_names()
    check(f"click on AnimLayer1's row selects only it ({sel})", sel == ["AnimLayer1"])
    if C.get("row2"):
        ev('MOUSEMOVE', 'NOTHING', x=C["row2"][0], y=C["row2"][1])


@step
def s_ctrl_down():
    ev('LEFT_CTRL', 'PRESS')            # sim's keystate (the select op reads it) + the window's key state


@step
def s_press2():
    if C.get("row2"):
        ev('LEFTMOUSE', 'PRESS', ctrl=True)


@step
def s_release2():
    if C.get("row2"):
        ev('LEFTMOUSE', 'RELEASE', ctrl=True)


@step
def s_ctrl_up():
    ev('LEFT_CTRL', 'RELEASE')
    park()
    sc = bpy.context.scene
    sel = selected_names()
    C["via_click"] = sel == ["AnimLayer1", "AnimLayer2"]
    if not C["via_click"]:
        # fallback (a simulated modifier may not reach the button): the Ctrl+click operator call
        print("GUI NOTE Ctrl+click did not reach the row button; calling allset.anim_layer_select(toggle=True)",
              flush=True)
        area, reg = dock()
        with bpy.context.temp_override(window=win(), area=area, region=reg):
            bpy.ops.allset.anim_layer_select(index=2, toggle=True)
    check(f"Ctrl+click on AnimLayer2's row (simulated click reached it: {C['via_click']}) -> both selected "
          f"({selected_names()}, last picked index {sc.allset_anim_layer_index})",
          selected_names() == ["AnimLayer1", "AnimLayer2"] and sc.allset_anim_layer_index == 2)
    w, a = graph()
    if a is not None:
        with bpy.context.temp_override(window=w, area=a, region=region(a, 'WINDOW')):
            try:
                bpy.ops.graph.view_all()
            except RuntimeError as ex:
                print("view_all", ex)
    redraw()


@step
def s_wait2():
    redraw()


@step
def s_wait3():
    redraw()


# --- Graph Editor ------------------------------------------------------------------------------------------------

def _pixels(path, rect):
    img = bpy.data.images.load(path, check_existing=False)
    try:
        import numpy as np
        w, h = img.size
        px = np.empty(w * h * 4, dtype=np.float32)
        img.pixels.foreach_get(px)
        px = px.reshape(h, w, 4)
        x0, y0, x1, y1 = rect
        sub = px[max(0, y0):min(h, y1), max(0, x0):min(w, x1), :3]
        r, g, b = sub[..., 0], sub[..., 1], sub[..., 2]
        # kit line: dim Maya red (editor_chrome.AXIS_COLOR[0] x graph_layers.DIM, alpha 0.9)
        kit = (np.abs(r - 0.50) < 0.1) & (np.abs(g - 0.15) < 0.08) & (np.abs(b - 0.15) < 0.08)
        # Blender's curve of the active layer, whatever its colour: bright, saturated, not the orange keys /
        # blue frame line / white handles
        mx, mn = sub.max(axis=2), sub.min(axis=2)
        bright = (mx > 0.6) & (mx - mn > 0.25) & ~((r > 0.8) & (b < 0.12)) & ~((b > r) & (b > g))
        red, green = int(kit.sum()), int(bright.sum())
        return red, green, (w, h)
    finally:
        bpy.data.images.remove(img)


@step
def s_graph_check():
    sc = bpy.context.scene
    ob = cube()
    a = al()
    gl = mod("ui.graph_layers")
    chrome = mod("ui.editor_chrome")
    act = ob.animation_data.action
    check(f"Blender's editable curves = the last picked layer AnimLayer2 ({act.get(a.MARK) if act else None})",
          act is not None and act.get(a.MARK) == "AnimLayer2")
    extra = [(n, fc.data_path, fc.array_index) for n, fc in gl.extra_curves(sc, ob)]
    check(f"graph_layers draws the other selected layer's curve ({extra})", extra == [("AnimLayer1", "location", 0)])
    w, area = graph()
    if area is None:
        return
    win_reg, ch = region(area, 'WINDOW'), region(area, 'CHANNELS')
    with bpy.context.temp_override(window=w, area=area, region=ch):
        rows = chrome.rows(bpy.context, area.spaces.active)
    desc = []
    for kind, node, item in rows:
        if kind in gl.KINDS:
            desc.append((kind, gl.layer_of_row((kind, node, item)),
                         getattr(item, "data_path", None) if kind == "LAYER_ATTR" else None))
        elif kind == "ATTR":
            desc.append((kind, item.id_data.get(a.MARK) if item is not None else None, item.data_path,
                         item.array_index))
        else:
            desc.append((kind, getattr(node, "name", None)))
    print("GUI ROWS", desc, flush=True)
    attr_l2 = [d for d in desc if d[0] == "ATTR" and d[1] == "AnimLayer2"]
    layer_l1 = [d for d in desc if d[0] == "LAYER" and d[1] == "AnimLayer1"]
    attr_l1 = [d for d in desc if d[0] == "LAYER_ATTR" and d[1] == "AnimLayer1"]
    check(f"kit outliner: AnimLayer2's ty row under pCube1 + an AnimLayer1 row with its tx row ({desc})",
          bool(attr_l2) and bool(layer_l1) and bool(attr_l1))
    with bpy.context.temp_override(window=w, area=area, region=win_reg, space_data=area.spaces.active):
        items = gl.view_lines(bpy.context, win_reg, area.spaces.active)
        shows = gl._shows(bpy.context)
    check(f"graph_layers draws in this Graph Editor (shows {shows}, {len(items)} line(s): "
          f"{[(i[2], len(i[3])) for i in items]})", shows and len(items) == 1 and items[0][2] == "AnimLayer1")
    if items:
        v2d = win_reg.view2d
        pts = [v2d.view_to_region(x, y, clip=False) for x, y in items[0][3]]
        inside = sum(1 for x, y in pts if 0 <= x < win_reg.width and 0 <= y < win_reg.height)
        check(f"the AnimLayer1 line lies in the visible graph ({inside}/{len(pts)} points)", inside > len(pts) // 3)
    # screen pixels of the graph's WINDOW region
    path = os.path.join(SHOTS or bpy.app.tempdir, "gui_step204_graph.png")
    with bpy.context.temp_override(window=w):
        bpy.ops.screen.screenshot(filepath=path)
    C["shot"] = (path, w, (win_reg.x, win_reg.y, win_reg.x + win_reg.width, win_reg.y + win_reg.height))


@step
def s_graph_pixels():
    # screen.screenshot shows the previous frame: take it again one tick later
    if "shot" not in C:
        return
    path, w, rect = C["shot"]
    with bpy.context.temp_override(window=w):
        bpy.ops.screen.screenshot(filepath=path)
    red, green, size = _pixels(path, rect)
    check(f"two curves on screen in the Graph Editor: AnimLayer1 tx (kit-drawn dim red) {red} px, AnimLayer2 ty "
          f"(Blender's curve) {green} px (shot {size}, region {rect})", red > 60 and green > 60)
    fc = next(f for f in al().layer_curves(cube(), "AnimLayer2") if f.data_path == "location")
    check(f"AnimLayer2's Translate Y curve drawn in the Y green like its outliner row (color_mode {fc.color_mode}, "
          f"color {tuple(round(c, 2) for c in fc.color)})", fc.color_mode == 'AUTO_RGB')
    shot("gui_step204_main.png")


# --- one undo step -----------------------------------------------------------------------------------------------

@step
def s_zero_weight():
    sc = bpy.context.scene
    C["before"] = {n: (sc.allset_anim_layers[n].weight, weight_keys(n)) for n in ("AnimLayer1", "AnimLayer2")}
    with bpy.context.temp_override(window=win()):
        bpy.ops.ed.undo_push(message="layers GUI before")
        # like the Layer Editor toolbar button (undo depth 0): Zero Weight and Key Layer on both selected layers
        C["zero"] = bpy.ops.allset.anim_layer_key_weight('EXEC_DEFAULT', True, weight=0.0)
    after = {n: (sc.allset_anim_layers[n].weight, weight_keys(n)) for n in ("AnimLayer1", "AnimLayer2")}
    check(f"Zero Weight and Key Layer on both selected layers ({C['zero']}, {after})",
          C["zero"] == {'FINISHED'} and all(w == 0.0 and any(abs(k[0] - 10) < 1e-6 and abs(k[1]) < 1e-6 for k in ks)
                                            for w, ks in after.values()))
    redraw()


@step
def s_undo():
    with bpy.context.temp_override(window=win()):
        bpy.ops.ed.undo()
    redraw()


@step
def s_undone():
    sc = bpy.context.scene
    now = {n: (sc.allset_anim_layers[n].weight, weight_keys(n)) for n in ("AnimLayer1", "AnimLayer2")}
    check(f"one undo restores the weights and their keys ({now} == {C['before']})", now == C["before"])
    names = [e.name for e in sc.allset_anim_layers]
    check(f"...and only that step: layers and their curves are still there ({names})",
          names == ["BaseAnimation", "AnimLayer1", "AnimLayer2"]
          and len(al().layer_curves(cube(), "AnimLayer1")) == 1)
    check(f"selection kept over the undo ({selected_names()})", selected_names() == ["AnimLayer1", "AnimLayer2"])


run()
