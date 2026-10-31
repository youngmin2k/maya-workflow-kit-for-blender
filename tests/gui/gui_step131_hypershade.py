"""#25: in a real UI: pSphere1 with blinn1 (a checker on its Color) and pCube1 with lambert1 -> Windows >
Rendering Editors > Hypershade -> a new window in the Maya Hypershade layout: menu strip, Browser top-left, Material
Viewer top-right, Create bottom-left, Graph centre, Property Editor bottom-right, proportions within 4 % of the
expected layout -> pick blinn1, Input and Output Connections -> screenshot ->
open again from the main window = one Hypershade window (the old one closes)."""

import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, run, setup, step, win, load_maya_layout, view3d  # noqa: E402

GUI_TIMEOUT = 240
SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


def mod(name):
    return import_module(MODULE + name)


def shot(name, window=None):
    if SHOTS:
        with bpy.context.temp_override(window=window or win()):
            bpy.ops.screen.screenshot(filepath=os.path.join(SHOTS, name))


def redraw():
    for w in bpy.context.window_manager.windows:
        for a in w.screen.areas:
            a.tag_redraw()


def again(fn, cond, limit=60):
    C.setdefault(fn.__name__, 0)
    if not cond() and C[fn.__name__] < limit:
        C[fn.__name__] += 1
        sys.modules["sim"]._steps.insert(0, fn)
        redraw()
        return True
    return False


def ready():
    hs = mod(".ui.hypershade")
    for w in bpy.context.window_manager.windows[1:]:
        panes = {hs.pane(a): a for a in w.screen.areas if hs.pane(a)}
        if len(panes) == 4 and hs.graph_area(w.screen) is not None and hs.menu_area(w.screen) is not None:
            return w, panes
    return None, None


def rects(w, panes):
    """{role: (x, y, w, h)} y down, window px."""
    hs = mod(".ui.hypershade")
    areas = dict(panes)
    areas["GRAPH"] = hs.graph_area(w.screen)
    areas["MENU"] = hs.menu_area(w.screen)
    x0 = min(a.x for a in w.screen.areas)
    y0 = min(a.y for a in w.screen.areas)
    width = max(a.x + a.width for a in w.screen.areas) - x0
    height = max(a.y + a.height for a in w.screen.areas) - y0
    out = {k: (a.x - x0, height - (a.y - y0 + a.height), a.width, a.height) for k, a in areas.items()}
    return out, width, height


@step
def s_setup():
    setup()
    bpy.ops.allset.make_maya(open_layout=False)
    load_maya_layout()


@step
def s_scene():
    m = mod(".operators.material")
    area, region = view3d()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        bpy.ops.allset.create(kind='CUBE')
        bpy.ops.allset.create(kind='SPHERE')
    sphere = bpy.context.active_object
    blinn = m.new_material('BLINN')
    tree = blinn.node_tree
    tex = tree.nodes.new('ShaderNodeTexChecker')
    tex.location = (-400, 200)
    bsdf = next(n for n in tree.nodes if n.type == 'BSDF_PRINCIPLED')
    tree.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    sphere.data.materials.clear()
    sphere.data.materials.append(blinn)
    bpy.context.scene.render.engine = 'BLENDER_EEVEE_NEXT' if 'BLENDER_EEVEE_NEXT' in {
        e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items} else 'BLENDER_EEVEE'
    C["n0"] = len(bpy.context.window_manager.windows)
    menu_map = mod(".ui.menu_map")
    modal = mod(".marking.modal")
    with bpy.context.temp_override(window=win(), area=area, region=region):
        C["open"] = modal.run_action(bpy.context, menu_map.MAP["Windows/Rendering Editors/Hypershade"])


@step
def s_layout():
    if again(s_layout, lambda: ready()[0] is not None):
        return
    w, panes = ready()
    check(f"Hypershade window with 4 panes + menu strip + Graph ({C['open']})", w is not None)
    if w is None:
        return
    layout = mod(".ui.hypershade_layout")
    r, width, height = rects(w, panes)
    C["rects"] = (r, width, height)
    print("hypershade rects", width, height, r)
    diff = layout.compare(r, width, height)
    print("hypershade vs maya", diff)
    hs = mod(".ui.hypershade")
    strip = hs.menu_area(w.screen)
    print("strip regions", [(rg.type, rg.x, rg.y, rg.width, rg.height) for rg in strip.regions],
          strip.spaces.active.show_region_header)
    check(f"panes where Maya puts them, proportions within 4 % of Maya's layout ({diff})",
          diff and max(diff.values()) <= 0.04)
    b, v, c, g, p, m = (r[k] for k in ("BROWSER", "VIEWER", "CREATE", "GRAPH", "PROPERTY", "MENU"))
    check("menu strip across the top, one header high", m[1] == 0 and m[2] >= width - 2 and m[3] <= 40)
    check("Browser top-left, Material Viewer top-right, Create under the Browser, Graph right of Create, "
          "Property Editor under the Material Viewer",
          b[0] == 0 and v[0] > b[0] and abs(v[1] - b[1]) <= 2 and c[1] > b[1] and g[0] > c[0]
          and p[1] > v[1] and abs(p[0] - v[0]) <= 2)
    C["w"] = w
    redraw()


@step
def s_pick():
    w = C.get("w")
    if w is None:
        return
    hs = mod(".ui.hypershade")
    browser = next(a for a in w.screen.areas if hs.pane(a) == 'BROWSER')
    region = next(r for r in browser.regions if r.type == 'WINDOW')
    with bpy.context.temp_override(window=w, area=browser, region=region, space_data=browser.spaces.active):
        bpy.ops.allset.hs_pick(material="blinn1")
    graph = hs.graph_area(w.screen)
    tree = graph.spaces.active.edit_tree
    check(f"Browser pick shows blinn1 in the Graph ({tree and tree.name})",
          tree is not None and tree == bpy.data.materials["blinn1"].node_tree)
    region = next(r for r in graph.regions if r.type == 'WINDOW')
    with bpy.context.temp_override(window=w, area=graph, region=region, space_data=graph.spaces.active):
        for n in tree.nodes:
            n.select = n.type == 'BSDF_PRINCIPLED'
        bpy.ops.allset.hs_graph(action='BOTH')
    sel = {n.type for n in tree.nodes if n.select}
    check(f"Input and Output Connections selects the network ({sorted(sel)})",
          {'TEX_CHECKER', 'BSDF_PRINCIPLED', 'OUTPUT_MATERIAL'} <= sel)
    redraw()


@step
def s_wait():
    redraw()


@step
def s_shot():
    w = C.get("w")
    if w is not None:
        shot("gui_step131_hypershade.png", w)
    area, region = view3d()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        bpy.ops.allset.hypershade()


@step
def s_reopen():
    hs = mod(".ui.hypershade")
    if again(s_reopen, lambda: len(hs.hypershade_windows()) == 1 and ready()[0] is not None
             and ready()[0] != C.get("w")):
        return
    check(f"opening it again from the main window leaves one Hypershade window "
          f"({len(hs.hypershade_windows())})", len(hs.hypershade_windows()) == 1)


@step
def s_close():
    wm = bpy.context.window_manager
    while len(wm.windows) > 1:
        w = wm.windows[-1]
        with bpy.context.temp_override(window=w):
            bpy.ops.wm.window_close()


run()
