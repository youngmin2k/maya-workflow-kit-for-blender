"""Graph Editor tangent toolbar, Shift+S keyframe / tangent marking menu, Graph Editor G / D, Maya Auto Key
(only keyed channels), Playblast. GUI: tests/gui/gui_step70_graph.py."""

import types
from importlib import import_module

import bpy

import kit

time_keys = import_module(kit.MODULE + ".operators.time_keys")
graph_keys = import_module(kit.MODULE + ".operators.graph_keys")
playblast = import_module(kit.MODULE + ".operators.playblast")
taphold = import_module(kit.MODULE + ".operators.taphold")
graph_editor = import_module(kit.MODULE + ".ui.graph_editor")
channel_box = import_module(kit.MODULE + ".ui.channel_box")
menu_map = import_module(kit.MODULE + ".ui.menu_map")
shelf_map = import_module(kit.MODULE + ".ui.shelf_map")
mm = import_module(kit.MODULE + ".marking.menus")
patches = import_module(kit.MODULE + ".keymap.maya_patches")
mapping = import_module(kit.MODULE + ".keymap.mapping")


def _cube_with_keys():
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    bpy.ops.mesh.primitive_cube_add()
    ob = bpy.context.active_object
    sc = bpy.context.scene
    sc.frame_start, sc.frame_end, sc.use_preview_range = 1, 120, False
    for frame, x in ((1, 0.0), (24, 5.0)):
        ob.location.x = x
        ob.keyframe_insert("location", index=0, frame=frame)
    sc.frame_set(1)
    return ob


def _graph_area():
    area = bpy.context.window_manager.windows[0].screen.areas[0]
    old = area.ui_type
    area.ui_type = 'FCURVES'
    region = next(r for r in area.regions if r.type == 'WINDOW')
    return area, region, old


def _keys(ob):
    return list(kit.fcurves(ob)[0].keyframe_points)


# --- tangents ---------------------------------------------------------------------------------------

def test_tangent_table():
    t = time_keys.TANGENTS
    assert t["LINEAR"] == ("LINEAR", None) and t["STEPPED"] == ("CONSTANT", None)
    assert t["SPLINE"] == ("BEZIER", 'AUTO') and t["AUTO"] == ("BEZIER", 'AUTO_CLAMPED')
    assert t["STEPPED_NEXT"] == ("CONSTANT", None) and t["BREAK"] == (None, 'FREE') and t["UNIFY"] == (None, 'ALIGNED')
    for kind in [k for k, _i in graph_editor.TANGENT_BUTTONS] + [k for k, _i in graph_editor.HANDLE_BUTTONS]:
        assert kind in t and kind in time_keys.TANGENT_LABELS, kind
    tip = graph_keys.ALLSET_OT_set_tangent.description(bpy.context, types.SimpleNamespace(kind="LINEAR"))
    assert tip.startswith("Linear tangents = Blender Linear"), tip


def test_tangent_on_selected_keys_in_graph_editor():
    """Keys are re-read after every operator: a KeyframePoint held across operator calls can go stale."""
    ob = _cube_with_keys()

    def k(i):
        return _keys(ob)[i]

    for kp in _keys(ob):
        kp.select_control_point = False
    k(1).select_control_point = True
    area, region, old = _graph_area()
    try:
        with bpy.context.temp_override(area=area, region=region):
            assert bpy.ops.allset.set_tangent(kind="LINEAR") == {'FINISHED'}
            assert k(1).interpolation == 'LINEAR' and k(0).interpolation == 'BEZIER', "only the selected key"
            bpy.ops.allset.set_tangent(kind="BREAK")
            assert k(1).handle_left_type == 'FREE' and k(1).interpolation == 'LINEAR', "Break keeps the interpolation"
            k(0).select_control_point = True
            bpy.ops.allset.set_tangent(kind="FLAT")
            assert k(0).handle_left_type == 'ALIGNED' and abs(k(0).handle_right.y - k(0).co.y) < 1e-6
            # D in the Graph Editor = Auto
            bpy.ops.allset.set_tangent(kind="AUTO")
            assert k(0).handle_left_type == 'AUTO_CLAMPED' and k(1).interpolation == 'BEZIER'
            # Keys > Convert to Breakdown / Delete on the selected keys
            k(0).select_control_point = False
            bpy.ops.allset.key_edit(action="TO_BREAKDOWN")
            assert k(1).type == 'BREAKDOWN' and k(0).type == 'KEYFRAME'
            bpy.ops.allset.key_edit(action="DELETE")
            assert len(_keys(ob)) == 1 and _keys(ob)[0].co.x == 1
    finally:
        area.ui_type = old


def test_tangent_outside_graph_editor_uses_current_time():
    ob = _cube_with_keys()
    bpy.context.scene.frame_set(24)
    assert bpy.ops.allset.set_tangent(kind="STEPPED") == {'FINISHED'}
    k0, k1 = _keys(ob)
    assert k1.interpolation == 'CONSTANT' and k0.interpolation == 'BEZIER'
    bpy.ops.allset.set_tangent(kind="STEPPED_NEXT")       # reported, Stepped used
    assert _keys(ob)[1].interpolation == 'CONSTANT'


def test_toolbar_draw():
    icons = set(bpy.types.UILayout.bl_rna.functions["operator"].parameters["icon"].enum_items.keys())
    for _k, icon in graph_editor.TANGENT_BUTTONS + graph_editor.HANDLE_BUTTONS:
        assert icon in icons, icon
    assert {'GHOST_ENABLED', 'GHOST_DISABLED'} <= icons
    log = []

    class Rec:
        def __getattr__(self, name):
            def call(*a, **kw):
                props = types.SimpleNamespace()
                log.append((name, a, kw, props))
                return props if name == "operator" else Rec()
            return call

    space = types.SimpleNamespace(type='GRAPH_EDITOR', mode='FCURVES')
    graph_editor.draw_toolbar(types.SimpleNamespace(layout=Rec()), types.SimpleNamespace(space_data=space))
    ops = [(e[1][0], getattr(e[3], "kind", None)) for e in log if e[0] == "operator"]
    assert [k for i, k in ops if i == "allset.set_tangent"] == \
        ["AUTO", "SPLINE", "CLAMPED", "LINEAR", "FLAT", "STEPPED", "PLATEAU", "BREAK", "UNIFY"], ops
    assert ("graph.ghost_curves_create", None) in ops
    assert graph_editor.draw_toolbar in bpy.types.GRAPH_HT_header._dyn_ui_initialize()


# --- marking menu / keys ---------------------------------------------------------------------------

def test_tangent_marking_menu():
    menu = mm.MENUS["KEY_TANGENT"]
    keys, tans = menu.radial["W"][1], menu.radial["E"][1]
    assert menu.radial["W"][0] == "Keys" and menu.radial["E"][0] == "Tangents"
    assert tans.radial["S"] == ("Linear", ("allset.set_tangent", {"kind": "LINEAR"}))
    assert tans.radial["N"][0] == "Spline" and tans.radial["SW"][0] == "Stepped Next" and len(tans.radial) == 8
    assert keys.radial["N"] == ("Delete Keys", ("allset.key_edit", {"action": "DELETE"})) and len(keys.radial) == 8
    assert "key_tangent" in taphold.binding_names()


def test_keymap():
    added = {(km, idname, ev["type"], bool(ev.get("shift"))): props for km, idname, ev, props, _s in patches.ADDED}
    assert added[("Graph Editor", "anim.scene_range_frame", "G", False)] == {}
    assert added[("Graph Editor", "allset.set_tangent", "D", False)] == {"kind": "AUTO"}
    for km in ("Object Mode", "Pose", "Graph Editor", "Dopesheet"):
        assert added[(km, "allset.tap_hold", "S", True)] == {"binding": "key_tangent"}, km
    kc = kit.maya_kc()
    om = kc.keymaps["Object Mode"]
    assert not [i for i in om.keymap_items if i.idname == "anim.keyframe_insert" and i.type == 'S' and i.shift]
    for rtc in ("graphEditor:GraphEditorFramePlaybackRange", "graphEditor:TangentAuto", "KeyframeTangentMarkingMenu"):
        assert mapping.ENTRIES[rtc]["status"] == "KIT", rtc


# --- Auto Key ------------------------------------------------------------------------------------------

def test_auto_key_only_keyed_channels():
    """The kit's own Auto Key (Scene.allset_auto_key, operators/auto_key.py); Blender's Only Insert
    Available preference is never written."""
    prefs = bpy.context.preferences
    factory = type(prefs.edit).bl_rna.properties["use_keyframe_insert_available"].default
    assert prefs.edit.use_keyframe_insert_available == factory
    ob = _cube_with_keys()
    assert channel_box.auto_keys(ob, "tx") and not channel_box.auto_keys(ob, "rx")
    # the Channel Box proxy with Auto Key on: keyed channel gets a key, an unkeyed one doesn't
    sc = bpy.context.scene
    assert not sc.allset_auto_key, "off by default (Maya's Auto Key button starts off)"
    sc.allset_auto_key = True
    try:
        sc.frame_set(50)
        sc.allset_cb.tx = 2.0
        sc.allset_cb.rx = 0.5
        fcs = kit.fcurves(ob)
        assert [kp.co.x for kp in fcs.find("location", index=0).keyframe_points] == [1, 24, 50]
        assert fcs.find("rotation_euler", index=0) is None
        # a move outside the Channel Box (viewport, Python): the depsgraph handler keys it, unkeyed channels stay
        auto_key = import_module(kit.MODULE + ".operators.auto_key")
        sc.frame_set(60)
        ob.location.x = 5.0
        ob.rotation_euler.x = 0.3
        assert [fc.data_path for fc, _v in auto_key.changed_curves(ob, 60)] == ["location"]
        assert auto_key.key_changed(ob, 60) == 1
        assert [kp.co.x for kp in fcs.find("location", index=0).keyframe_points] == [1, 24, 50, 60]
        assert fcs.find("rotation_euler", index=0) is None
        assert auto_key.changed_curves(ob, 60) == [], "nothing left to key"
    finally:
        sc.allset_auto_key = False
    assert prefs.edit.use_keyframe_insert_available == factory and not sc.tool_settings.use_keyframe_insert_auto


# --- Playblast --------------------------------------------------------------------------------------------

def test_playblast_settings_and_restore():
    sc = bpy.context.scene
    sc.render.filepath, sc.render.resolution_percentage = "//renders/", 100
    sc.render.image_settings.file_format = 'PNG'
    sc.use_preview_range = False
    saved = playblast.save_settings(sc)
    playblast.apply_settings(sc, 'MOVIE', 70, 0.5)
    assert sc.render.filepath.startswith(playblast.output_dir()) and sc.render.resolution_percentage == 50
    assert sc.render.image_settings.file_format == 'FFMPEG' and sc.render.ffmpeg.codec == 'H264'
    playblast.restore_settings(sc, saved)
    assert (sc.render.filepath, sc.render.resolution_percentage, sc.render.image_settings.file_format) == \
        ("//renders/", 100, 'PNG')
    playblast.apply_settings(sc, 'IMAGE', 40, 1.0, frames=(5, 9))
    assert sc.render.image_settings.file_format == 'JPEG' and sc.render.image_settings.quality == 40
    assert sc.use_preview_range and playblast.playback_range(sc) == (5, 9)
    playblast.restore_settings(sc, saved)
    assert not sc.use_preview_range
    # menus / shelf / option box
    assert menu_map.MAP["Windows/Playblast"] == ("v3d", "allset.playblast", {})
    assert menu_map.MAP["Playback/Playblast"] == ("v3d", "allset.playblast", {})
    assert shelf_map.BY_COMMAND["PlayblastWindow"][0] == ("v3d", "allset.playblast", {})
    props = bpy.ops.allset.playblast.get_rna_type().properties
    assert "option_box" in props and props["quality"].default == 70 and abs(props["scale"].default - 0.5) < 1e-6
