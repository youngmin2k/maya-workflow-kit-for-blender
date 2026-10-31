"""#192: Maya Graph Editor first week — selected objects are listed before they have keys (a bare node row),
a node row also shows its shape's animated channels, the toolbar sits on its own row under the menus, tangent
handles show on selected keys only, S keys the selected objects (ui/editor_chrome.py, keymap/maya_patches.py)."""

import types
from importlib import import_module

import bpy

import kit

chrome = import_module(kit.MODULE + ".ui.editor_chrome")


def _clear():
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    for coll in (bpy.data.meshes, bpy.data.lights, bpy.data.actions):
        for d in list(coll):
            coll.remove(d)
    chrome._expanded.clear()
    chrome._pinned.clear()
    wm = bpy.context.window_manager
    for name, _label, _tip in chrome.FLAGS:
        setattr(wm, name, name in chrome.FLAGS_ON)


def _space():
    return types.SimpleNamespace(type='GRAPH_EDITOR', mode='FCURVES',
                                 dopesheet=types.SimpleNamespace(show_only_selected=True, show_hidden=True,
                                                                 filter_text="", filter_collection=None))


def _cube(name, keyed=False):
    ob = bpy.data.objects.new(name, bpy.data.meshes.new(name + "Shape"))
    bpy.context.scene.collection.objects.link(ob)
    if keyed:
        ob.keyframe_insert("location", index=0, frame=1)
    return ob


def _select(*obs):
    for ob in bpy.context.scene.objects:
        ob.select_set(ob in obs)
    if obs:
        bpy.context.view_layer.objects.active = obs[-1]


def _rows():
    return [(k, n.name, len(c)) for k, n, c in chrome.listed_nodes(bpy.context, _space())]


def test_unkeyed_selection_is_a_bare_node_row():
    _clear()
    cube = _cube("pCube1")
    _select(cube)
    assert _rows() == [("OBJECT", "pCube1", 0)], _rows()
    rows = chrome.rows(bpy.context, _space())
    assert [(k, n.name) for k, n, _fc in rows] == [("OBJECT", "pCube1")], "no channel rows before keys"
    cube.keyframe_insert("location", index=0, frame=1)
    assert _rows() == [("OBJECT", "pCube1", 1)]


def test_keyed_and_unkeyed_both_listed_nothing_selected_empty():
    _clear()
    a = _cube("pCube1", keyed=True)
    b = _cube("pSphere1")
    _select(a, b)
    assert _rows() == [("OBJECT", "pCube1", 1), ("OBJECT", "pSphere1", 0)], _rows()
    _select(b)
    assert _rows() == [("OBJECT", "pSphere1", 0)]
    _select()
    assert _rows() == []


def test_unselected_unkeyed_objects_stay_out():
    _clear()
    _cube("pCube1", keyed=True)
    _cube("pSphere1")
    _select()
    assert _rows() == []


def test_shape_channels_under_the_node_row():
    """Maya's node row also draws the animated channels of its shape (a light's intensity)."""
    _clear()
    light = bpy.data.objects.new("pointLight1", bpy.data.lights.new("pointLightShape1", 'POINT'))
    bpy.context.scene.collection.objects.link(light)
    light.data.keyframe_insert("energy", frame=1)
    _select(light)
    rows = chrome.listed_nodes(bpy.context, _space())
    assert len(rows) == 1 and rows[0][0] == "OBJECT"
    assert [fc.data_path for fc in rows[0][2]] == ["energy"], [fc.data_path for fc in rows[0][2]]
    light.keyframe_insert("location", index=0, frame=1)
    rows = chrome.listed_nodes(bpy.context, _space())
    assert [fc.data_path for fc in rows[0][2]] == ["location", "energy"]


def _graph_area():
    win = bpy.context.window_manager.windows[0]
    area = max(win.screen.areas, key=lambda a: a.width * a.height)
    area.type = 'GRAPH_EDITOR'
    area.spaces.active.mode = 'FCURVES'
    return win, area


def test_toolbar_row_and_selected_key_handles():
    win, area = _graph_area()
    sp = area.spaces.active
    sp.use_only_selected_keyframe_handles = False
    chrome._set_up.discard(area.as_pointer())
    assert not chrome.toolbar_row(area)
    assert chrome.setup_toolbar_row(win, area)
    assert sp.use_only_selected_keyframe_handles, "Maya View > Tangents = On Active Keys"
    assert sp.show_region_footer
    foot = next(r for r in area.regions if r.type == 'FOOTER')
    assert foot.alignment == 'TOP' and chrome.toolbar_row(area)
    assert not chrome.setup_toolbar_row(win, area), "once per editor: a later user choice stays"
    # Maya mode off: the footer goes back where Blender keeps it
    chrome.release_toolbar_rows()
    foot = next(r for r in area.regions if r.type == 'FOOTER')
    assert foot.alignment == 'BOTTOM' and not sp.show_region_footer
    area.type = 'VIEW_3D'


def test_toolbar_drawn_in_the_footer_not_the_header():
    funcs = bpy.types.GRAPH_HT_playback_controls._dyn_ui_initialize()
    assert funcs[0] is chrome._graph_footer
    funcs = bpy.types.DOPESHEET_HT_playback_controls._dyn_ui_initialize()
    assert funcs[0] is chrome._dope_footer


def test_s_keys_the_selected_objects_over_the_graph_editor():
    kc = kit.maya_kc()
    for km_name, ic_op in (("Graph Editor", "graph.keyframe_insert"), ("Dopesheet", "action.keyframe_insert")):
        km = kc.keymaps[km_name]
        items = [i for i in km.keymap_items if i.type == 'S' and i.value == 'PRESS' and not i.any
                 and not (i.shift or i.ctrl or i.alt) and i.active]
        ops = [i.idname for i in items]
        assert "allset.set_key" in ops and ic_op not in ops, (km_name, ops)
    _clear()
    cube = _cube("pCube1")
    _select(cube)
    win, area = _graph_area()
    region = next(r for r in area.regions if r.type == 'WINDOW')
    with bpy.context.temp_override(window=win, area=area, region=region):
        assert bpy.ops.allset.set_key() == {'FINISHED'}
    paths = {(fc.data_path, fc.array_index) for fc in kit.fcurves(cube)}
    assert len(paths) == 10, sorted(paths)          # Maya S: Visibility + Translate / Rotate / Scale
    assert _rows() == [("OBJECT", "pCube1", 10)]
    area.type = 'VIEW_3D'
