"""#25: Hypershade window in Maya's layout — split plan vs the Maya layout, pane markers, pane
content, current material from a pane. GUI: tests/gui/gui_step131_hypershade.py."""

from importlib import import_module

import bpy

import kit
from test_step67_render import Rec, _clear, _sphere, swatches

hs = import_module(kit.MODULE + ".ui.hypershade")
layout = import_module(kit.MODULE + ".ui.hypershade_layout")
maya_dock = import_module(kit.MODULE + ".ui.maya_dock")
tool_dock = import_module(kit.MODULE + ".ui.tool_dock")
editor_chrome = import_module(kit.MODULE + ".ui.editor_chrome")
menu_map = import_module(kit.MODULE + ".ui.menu_map")
material = import_module(kit.MODULE + ".operators.material")


def test_plan_reproduces_maya_rects():
    w, h = layout.MAYA_SIZE
    rects = layout.simulate(layout.plan(h, layout.MAYA_RECTS["MENU"][3]), w, h)
    for role in layout.ROLES:
        assert all(abs(a - b) <= 1 for a, b in zip(rects[role], layout.MAYA_RECTS[role])), (role, rects[role])
    # another window size / header height keeps Maya's proportions below the strip
    rects = layout.simulate(layout.plan(700, 30), 1100, 700)
    assert rects["MENU"][3] == 30
    assert max(layout.compare(rects, 1100, 700).values()) < 0.005
    # Browser top-left, Viewer top-right, Create left of Graph, Property Editor under the Viewer
    b, v, c, g, p = (rects[k] for k in ("BROWSER", "VIEWER", "CREATE", "GRAPH", "PROPERTY"))
    assert b[0] == 0 and v[0] > b[0] and c[1] > b[1] and g[0] > c[0] and p[1] > v[1] and p[0] == v[0]


def _props_area():
    area = bpy.context.window_manager.windows[0].screen.areas[0]
    old = area.ui_type
    area.ui_type = 'PROPERTIES'
    return area, old


def test_pane_marker_round_trip():
    area, old = _props_area()
    try:
        for name in hs.PANE_FLAGS:
            if not hs.set_pane(area, name):
                return       # background: a fresh Properties space may have no tab list (GUI test covers it)
            assert hs.pane(area) == name
            assert maya_dock.role(area) is None and not tool_dock.is_dock(area), "not a Maya dock / Tool Settings"
        space = area.spaces.active
        space.show_properties_material = True
        assert hs.pane(area) is None, "any other tab flag = a user's Properties editor"
    finally:
        area.spaces.active.show_region_header = True
        area.ui_type = old


def test_pane_content():
    _clear()
    ob = _sphere()
    wm = bpy.context.window_manager
    blinn = material.new_material('BLINN')
    blinn.use_fake_user = True
    wm.allset_hs_material = blinn.name
    wm.allset_hs_filter = ""
    rec = Rec()
    hs.draw_browser(rec, bpy.context)
    greyed = [p.item for i, p in rec.ops() if i == "allset.menu_unavailable"]
    for t in hs.MAYA_ONLY_TABS:
        assert f"Hypershade/Browser/{t}" in greyed
    assert swatches(rec) >= {blinn.name}
    wm.allset_hs_filter = "blin"
    rec = Rec()
    hs.draw_browser(rec, bpy.context)
    assert swatches(rec) == {blinn.name}
    wm.allset_hs_filter = ""
    # Create: Maya's categories -> Hypershade Create menu items (mapped ones run, the rest greyed)
    for key, label, _subs in hs.CREATE_CATEGORIES:
        assert hs.create_items(key), key
    tex = [label for label, _p in hs.create_items('TEX2D')]
    assert tex[:3] == ["Bulge", "Checker", "Cloth"] and "File" in tex
    assert [label for label, _p in hs.create_items('FAVORITES')][:3] == ["Standard Surface", "Blinn", "Lambert"]
    assert menu_map.MAP["Hypershade/Create/2D Textures/Checker"][0] == "allset.hs_node"
    wm.allset_hs_create_cat = 'LIGHTS'
    rec = Rec()
    hs.draw_create(rec, bpy.context)
    items = {p.item for i, p in rec.ops() if i in ("allset.menu_item", "allset.menu_unavailable")}
    assert "Hypershade/Create/Lights/Point Light" in items and "Hypershade/Bins" in items
    wm.allset_hs_create_cat = 'MAYA'
    # Material Viewer: shape / world controls + the preview of the current material
    rec = Rec()
    hs.draw_viewer(rec, bpy.context)
    calls = [e[0] for e in rec.log]
    if bpy.context.scene.render.engine != 'BLENDER_WORKBENCH':
        assert "template_preview" in calls
    assert any(e[0] == "prop" and e[1][1] == "preview_render_type" for e in rec.log)
    # Property Editor: Maya's node tab + "blinn: name" row + AE sections
    rec = Rec()
    hs.draw_property_editor(rec, bpy.context)
    assert any(i == "allset.hs_noop" for i, _p in rec.ops())
    assert ob is not None


def test_graph_toolbar_and_menu_targets():
    keys = [it[0] for it in editor_chrome.ICONS["Hypershade"] if isinstance(it, tuple)]
    assert keys[:3] == ["show_inputs", "show_inputs_outputs", "show_outputs"]
    for it in editor_chrome.ICONS["Hypershade"]:
        if isinstance(it, tuple) and it[2] is None:
            assert it[0] in editor_chrome.NOTICES, it[0]
    assert menu_map.MAP["Hypershade/View/Frame All"] == ("allset.hs_graph", {"action": "FRAME_ALL"})
    assert menu_map.MAP["Hypershade/Window/Material Viewer..."] == "allset.hypershade"


def test_graph_network_selection():
    _clear()
    mat = material.new_material('BLINN')
    tree = mat.node_tree
    tex = tree.nodes.new('ShaderNodeTexChecker')
    bsdf = next(n for n in tree.nodes if n.type == 'BSDF_PRINCIPLED')
    out = next(n for n in tree.nodes if n.type == 'OUTPUT_MATERIAL')
    tree.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    assert hs._linked(tree, [bsdf], True) >= {tex}
    assert out in hs._linked(tree, [bsdf], False)
    assert tex not in hs._linked(tree, [bsdf], False)


def test_show_from_a_pane_uses_the_graph():
    # no Hypershade window headless: show() from a non-node context still makes the material current
    _clear()
    ob = _sphere()
    mat = material.new_material('PHONG')
    ob.data.materials.append(mat)
    area, old = _props_area()
    try:
        with bpy.context.temp_override(area=area, space_data=area.spaces.active):
            hs.show(bpy.context, mat)
        assert bpy.context.window_manager.allset_hs_material == mat.name
        assert ob.active_material == mat
    finally:
        area.ui_type = old
