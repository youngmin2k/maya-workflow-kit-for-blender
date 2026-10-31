"""Maya UV Editor display keys (4 / 5 / 6 / 8 / 9 / Ctrl+1) and Move UV Shell
(src/allset/ui/uv_display.py). GUI: tests/gui/gui_step155_uv.py."""

from importlib import import_module

import bmesh
import bpy

import kit

uvd = import_module(kit.MODULE + ".ui.uv_display")
uvt = import_module(kit.MODULE + ".operators.uv_tools")
compat = import_module(kit.MODULE + ".compat")


def _clear():
    if bpy.context.active_object is not None and bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)


def _two_quads(split):
    """Two quads sharing an edge; ``split``: the right quad's UVs moved off (two shells), else one shell."""
    me = bpy.data.meshes.new("two")
    me.from_pydata([(0, 0, 0), (1, 0, 0), (2, 0, 0), (0, 1, 0), (1, 1, 0), (2, 1, 0)], [],
                   [(0, 1, 4, 3), (1, 2, 5, 4)])
    me.uv_layers.new(name="UVMap")
    ob = bpy.data.objects.new("two", me)
    bpy.context.collection.objects.link(ob)
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.mode_set(mode='EDIT')
    bm = bmesh.from_edit_mesh(me)
    uv = bm.loops.layers.uv.active
    for f in bm.faces:
        right = f.calc_center_median().x > 1.0
        for loop in f.loops:
            x = loop.vert.co.x * 0.4 + (0.1 if split and right else 0.0)
            loop[uv].uv = (x, loop.vert.co.y * 0.4)
        f.select_set(True)
    bmesh.update_edit_mesh(me)
    return ob


def _uv_area():
    scr = bpy.context.window.screen
    a = next(a for a in scr.areas if a.type in ('VIEW_3D', 'IMAGE_EDITOR'))
    a.ui_type = 'UV'
    return a, next(r for r in a.regions if r.type == 'WINDOW')


def _segments(ob, synced=True):
    bm = bmesh.from_edit_mesh(ob.data)
    uv = bm.loops.layers.uv.active
    return uvd.border_segments(bm, uv, uvd.shown_faces(bm, synced))


def test_border_segments_two_shells():
    _clear()
    ob = _two_quads(split=False)
    one = _segments(ob)
    assert len(one) == 6, f"one shell: 6 outline edges, got {len(one)}"
    _clear()
    ob = _two_quads(split=True)
    bm = bmesh.from_edit_mesh(ob.data)
    assert len(uvt.islands(bm, bm.loops.layers.uv.active)) == 2
    two = _segments(ob)
    assert len(two) == 8, f"two shells: 4 + 4 border sides (the shared edge on both), got {len(two)}"
    # the shared edge's right side sits 0.1 to the right of its left side
    xs = sorted({round(p[0], 4) for s in two for p in s})
    assert xs == [0.0, 0.4, 0.5, 0.9], xs
    # without UV Sync Selection only selected faces are drawn
    bm = bmesh.from_edit_mesh(ob.data)
    bm.faces.ensure_lookup_table()
    bm.faces[1].select_set(False)
    bm.faces[0].select_set(True)
    assert len(uvd.border_segments(bm, bm.loops.layers.uv.active, uvd.shown_faces(bm, False))) == 4


def test_to_region():
    px = uvd.to_region([(0.0, 0.0), (1.0, 1.0), (0.5, 0.25)], (10, 20), (110, 220))
    assert px.tolist() == [[10, 20], [110, 220], [60, 70]], px.tolist()


def test_display_ops():
    _clear()
    ob = _two_quads(split=True)
    a, r = _uv_area()
    sp = a.spaces.active
    wm = bpy.context.window_manager
    assert wm.allset_uv_texture_borders and not wm.allset_uv_shell_borders, "default: texture borders on"
    with bpy.context.temp_override(area=a, region=r):
        bpy.ops.allset.uv_display(mode='SHELL_BORDERS')
        assert wm.allset_uv_shell_borders
        bpy.ops.allset.uv_display(mode='SHELL_BORDERS')
        assert not wm.allset_uv_shell_borders
        bpy.ops.allset.uv_display(mode='TEXTURE_BORDERS')
        assert not wm.allset_uv_texture_borders
        bpy.ops.allset.uv_display(mode='TEXTURE_BORDERS')
        assert wm.allset_uv_texture_borders
        bpy.ops.allset.uv_display(mode='WIREFRAME')
        assert not sp.uv_editor.show_faces, "4 = UVs as wireframe (no faces)"
        bpy.ops.allset.uv_display(mode='SHADED')
        assert sp.uv_editor.show_faces and sp.uv_editor.uv_face_opacity == 1.0
        # 6: no image anywhere -> nothing shown; then a material image shows and toggles off / on
        bpy.ops.allset.uv_display(mode='IMAGE')
        assert sp.image is None
        img = bpy.data.images.new("tex155", 8, 8)
        mat = bpy.data.materials.new("m155")
        mat.use_nodes = True
        node = mat.node_tree.nodes.new('ShaderNodeTexImage')
        node.image = img
        ob.active_material = mat     # (the kit gave the new mesh lambert1 in slot 0)
        bpy.ops.allset.uv_display(mode='IMAGE')
        assert sp.image == img, "6 shows the material's texture"
        bpy.ops.allset.uv_display(mode='IMAGE')
        assert sp.image is None, "6 again hides it"
        bpy.ops.allset.uv_display(mode='IMAGE')
        assert sp.image == img, "6 again shows the remembered image"
    # display ops push no undo step and open no redo panel
    assert not {'UNDO', 'REGISTER'} & set(bpy.types.ALLSET_OT_uv_display.bl_options)


def test_isolate_sync_and_nosync():
    _clear()
    ob = _two_quads(split=True)
    ts = bpy.context.scene.tool_settings
    ts.use_uv_select_sync = True
    bm = bmesh.from_edit_mesh(ob.data)
    bm.faces.ensure_lookup_table()
    for el in (*bm.verts, *bm.edges, *bm.faces):
        el.select = False
    bm.faces[0].select_set(True)
    bmesh.update_edit_mesh(ob.data)
    wm = bpy.context.window_manager
    bpy.ops.allset.uv_isolate()
    bm = bmesh.from_edit_mesh(ob.data)
    bm.faces.ensure_lookup_table()
    assert wm.allset_uv_isolate and [f.hide for f in bm.faces] == [False, True], "sync: the other face hidden"
    bpy.ops.allset.uv_isolate()
    bm = bmesh.from_edit_mesh(ob.data)
    bm.faces.ensure_lookup_table()
    assert not wm.allset_uv_isolate and [f.hide for f in bm.faces] == [False, False]
    assert [f.select for f in bm.faces] == [True, False], "selection kept"

    # without sync (the kit's UV mode): all faces selected, UVs of face 1 selected -> face 0 deselected
    uvt.set_component(bpy.context, 'UV')
    bm = bmesh.from_edit_mesh(ob.data)
    bm.faces.ensure_lookup_table()
    uv = bm.loops.layers.uv.active
    for f in bm.faces:
        for loop in f.loops:
            compat.set_uv_vert_selected(loop, uv, f.index == 1)
    bmesh.update_edit_mesh(ob.data)
    bpy.ops.allset.uv_isolate()
    bm = bmesh.from_edit_mesh(ob.data)
    bm.faces.ensure_lookup_table()
    assert [f.select for f in bm.faces] == [False, True] and not any(f.hide for f in bm.faces)
    bpy.ops.allset.uv_isolate()
    bm = bmesh.from_edit_mesh(ob.data)
    bm.faces.ensure_lookup_table()
    uv = bm.loops.layers.uv.active
    assert [f.select for f in bm.faces] == [True, True]
    assert [all(compat.uv_vert_selected(l, uv) for l in f.loops) for f in bm.faces] == [False, True], "UVs kept"

    # nothing selected: a warning, nothing hidden
    for f in bm.faces:
        for loop in f.loops:
            compat.set_uv_vert_selected(loop, uv, False)
    bmesh.update_edit_mesh(ob.data)
    try:
        bpy.ops.allset.uv_isolate()
    except RuntimeError:
        pass
    assert not wm.allset_uv_isolate


def test_move_shell():
    _clear()
    _two_quads(split=True)
    ts = bpy.context.scene.tool_settings
    ts.use_uv_select_sync = True
    bpy.ops.allset.uv_move_shell()
    assert compat.uv_island_mode(ts) and not ts.use_uv_select_sync, "UV shell selection"


def test_unregister_clean():
    kit.disable()
    wm = bpy.types.WindowManager
    assert not hasattr(wm, "allset_uv_shell_borders") and not hasattr(bpy.types, "ALLSET_OT_uv_display")
    assert uvd._invalidate not in bpy.app.handlers.depsgraph_update_post
    assert not uvd._handle
