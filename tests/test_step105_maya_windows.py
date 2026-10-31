"""Hypershade and Script Editor look — Maya menu bars like Maya 2022's, Render Settings = Blender's render
tab, the new Create shader kinds, the Browser tabs, Script Editor run / echo."""

from importlib import import_module

import bpy

import kit

data = import_module(kit.MODULE + ".ui.editor_menu_data")
menu_map = import_module(kit.MODULE + ".ui.menu_map")
menu_sets = import_module(kit.MODULE + ".ui.menu_sets")
notices = import_module(kit.MODULE + ".ui.notices")
hs = import_module(kit.MODULE + ".ui.hypershade")
se = import_module(kit.MODULE + ".ui.script_editor")
material = import_module(kit.MODULE + ".operators.material")
attribute_editor = import_module(kit.MODULE + ".ui.attribute_editor")
ae_layout = import_module(kit.MODULE + ".ui.ae_layout")

# Maya 2022 menu bars of these windows
MAYA_BARS = {"Hypershade": ["File", "Edit", "View", "Create", "Tabs", "Graph", "Window", "Options", "Help"],
             "Script Editor": ["File", "Edit", "History", "Command", "Tabs", "Help"]}


def _clear():
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    for m in list(bpy.data.materials):
        bpy.data.materials.remove(m)


def test_menu_bars_match_maya_and_are_honest():
    for editor, titles in MAYA_BARS.items():
        assert [t for t, _ in data.EDITORS[editor]] == titles, editor
    leaves = {}
    for path, it in menu_sets.iter_items():
        if path.split("/", 1)[0] in MAYA_BARS and (not menu_sets.sub_items(path, it) or path in menu_map.MAP):
            leaves[path] = path in menu_map.MAP
    print("leaves", len(leaves), "mapped", sum(leaves.values()))
    assert len(leaves) == 357 + 59, len(leaves)     # Hypershade / Script Editor
    assert not [p for p, m in leaves.items() if not m and notices.greyed_notice(p) is None]
    assert sum(leaves.values()) >= 150
    for name in ("Hypershade", "Script Editor"):
        assert hasattr(bpy.types, menu_sets.editor_menu_idname(name, 0))


def test_render_settings_is_blenders_render_tab():
    """Render Settings opens Blender's Properties > Render (no kit window, no Maya menu bar of its own)."""
    assert "Render Settings" not in data.EDITORS
    for path in ("Render/Render Settings...", "Windows/Rendering Editors/Render Settings", "Playback/Render Settings"):
        assert menu_map.MAP[path] == "allset.render_settings", path
    assert not hasattr(bpy.types.Scene, "allset_rs_size")


def test_create_list_maya_shaders():
    _clear()
    assert [material.MATERIALS[k][1] for k in hs.CREATE] == [
        "Anisotropic", "Blinn", "Lambert", "Layered Shader", "Phong", "Phong E", "Ramp Shader", "Standard Surface",
        "Surface Shader", "Use Background"]
    for kind in hs.CREATE:
        mat = material.new_material(kind)
        name = attribute_editor.material_type(mat)
        assert name == material.MATERIALS[kind][0] and name in ae_layout.BY_KIND, (kind, name)
    types_ = {n.type for n in bpy.data.materials["rampShader1"].node_tree.nodes}
    assert {'LAYER_WEIGHT', 'VALTORGB', 'BSDF_PRINCIPLED'} <= types_
    out = next(n for n in bpy.data.materials["layeredShader1"].node_tree.nodes if n.type == 'OUTPUT_MATERIAL')
    assert out.inputs["Surface"].links[0].from_node.type == 'MIX_SHADER'
    out = next(n for n in bpy.data.materials["useBackground1"].node_tree.nodes if n.type == 'OUTPUT_MATERIAL')
    assert out.inputs["Surface"].links[0].from_node.type == 'HOLDOUT'


def test_browser_tabs_and_edit_commands():
    _clear()
    wm = bpy.context.window_manager
    a = material.new_material('BLINN')
    a.use_fake_user = True
    b = material.new_material('PHONG')
    b.use_fake_user = True
    wm.allset_hs_material = b.name
    assert bpy.ops.allset.hs_node(node_type='ShaderNodeTexChecker', label="Checker") == {'FINISHED'}
    assert bpy.ops.allset.hs_node(node_type='ShaderNodeMapping', label="2d Placement") == {'FINISHED'}
    ctx = bpy.context
    wm.allset_hs_sort = 'NAME'
    names = [it[1] for it in hs.browser_items(ctx, 'MATERIALS')]
    assert "blinn1" in names and "phong1" in names
    assert [it[1] for it in hs.browser_items(ctx, 'TEXTURES')] == ["Checker"]
    assert [it[1] for it in hs.browser_items(ctx, 'UTILITIES')] == ["2d Placement"]
    assert {it[1] for it in hs.browser_items(ctx, 'SHADING_GROUPS')} >= {"blinn1SG", "phong1SG"}
    wm.allset_hs_reverse = True
    rev = [it[1] for it in hs.browser_items(ctx, 'MATERIALS')]
    wm.allset_hs_reverse = False
    assert rev == sorted(rev, key=str.lower, reverse=True)
    # Delete Unused Nodes keeps lambert1 (Maya) and used materials
    lam = material.default_material()
    me = bpy.data.meshes.new("m")
    ob = bpy.data.objects.new("o", me)
    bpy.context.scene.collection.objects.link(ob)
    me.materials.append(a)
    assert bpy.ops.allset.hs_edit(action='DELETE_UNUSED') == {'FINISHED'}
    left = {m.name for m in bpy.data.materials}
    assert lam.name in left and "blinn1" in left and "phong1" not in left, left


def test_script_editor_runs_python_and_refuses_mel():
    py = se.ensure_texts()
    assert py.name.startswith("Python") and {t.get(se.LANG_PROP) for t in se.script_texts()} == {"MEL", "Python"}
    py.clear()
    py.write("x = 20\nx + 22")
    _echo, res = se.run_text(py, py.as_string())
    assert not res.error and "42" in res.text, res
    mel = next(t for t in se.script_texts() if t.get(se.LANG_PROP) == "MEL")
    _echo, res = se.run_text(mel, "polyCube;")
    assert res.error and "MEL" in res.text
    py.clear()
    py.write("abc def")
    py.current_line_index, py.current_character = 0, 0
    py.select_end_line_index, py.select_end_character = 0, 3
    assert se.selected_text(py) == "abc"


def test_headers_patched():
    assert "draw_collapsible" in bpy.types.NODE_MT_editor_menus.__dict__
    for name, fn in (("INFO_HT_header", se._info_header),
                     ("TEXT_HT_header", se._text_header)):
        assert getattr(bpy.types, name).draw._draw_funcs[0] is fn, name
