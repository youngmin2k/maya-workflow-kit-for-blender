"""#97: Channel Box Channels menu complete (Breakdown / Mute All, Sync Graph Editor / Timeline, Cut / Copy /
Paste Selected, Freeze, Select Connection, layers notice), SHAPES rows as channels (light Intensity / Color keyable,
spot Cone Angle / Penumbra Angle), muted state, Bind Skin INPUTS = skinCluster1.
GUI: tests/gui/gui_step158_cb_menus.py."""

import math
import types
from importlib import import_module

import bpy
from mathutils import Vector

import kit

cb = import_module(kit.MODULE + ".ui.channel_box")
cbc = import_module(kit.MODULE + ".ui.cb_channels")
lights = import_module(kit.MODULE + ".operators.lights")
time_slider = import_module(kit.MODULE + ".ui.time_slider")
attribute_editor = import_module(kit.MODULE + ".ui.attribute_editor")
joints = import_module(kit.MODULE + ".operators.joints")
notices = import_module(kit.MODULE + ".ui.notices")
preferences = import_module(kit.MODULE + ".preferences")


def _clear():
    if bpy.context.active_object is not None and bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    for coll in (bpy.data.meshes, bpy.data.armatures, bpy.data.lights, bpy.data.actions):
        for d in list(coll):
            coll.remove(d)
    us = bpy.context.scene.unit_settings
    us.system, us.length_unit, us.scale_length = 'METRIC', 'METERS', 1.0    # maya_unit() = 1
    cb.set_selected_channels([])


def _cube():
    _clear()
    bpy.ops.mesh.primitive_cube_add()
    return bpy.context.active_object


def _keys(ob, path, index):
    fc = next((f for f in kit.fcurves(ob) if f.data_path == path and f.array_index == index), None)
    return [] if fc is None else [(round(k.co.x, 4), round(k.co.y, 4)) for k in fc.keyframe_points]


def _key(ob, index, pairs):
    for t, v in pairs:
        ob.location[index] = v
        ob.keyframe_insert("location", index=index, frame=t)


def _menu_items():
    log = []

    class Rec:
        def __getattr__(self, name):
            def call(*a, **kw):
                props = types.SimpleNamespace()
                log.append((name, a, kw, props))
                return props if name == "operator" else Rec()
            return call

    cb.ALLSET_MT_cb_channels.draw(types.SimpleNamespace(layout=Rec()), bpy.context)
    return log


# --- the menu ---------------------------------------------------------------------------------------------------

def test_channels_menu_has_every_maya_item_in_order():
    log = _menu_items()
    texts = [e[2].get("text") or getattr(getattr(bpy.ops, e[1][0].split(".")[0]), e[1][0].split(".")[1])
             .get_rna_type().name for e in log if e[0] in ("operator",)]
    props = [e[2].get("text") for e in log if e[0] == "prop"]
    menus = [e[1][0] for e in log if e[0] == "menu"]
    want = ["Key Selected", "Key All Keyable", "Breakdown Selected", "Breakdown All", "Mute Selected", "Mute All",
            "Unmute Selected", "Unmute All", "Cut Selected", "Copy Selected", "Paste Selected", "Delete Selected",
            "Duplicate Values", "Break Connections", "Select Connection", "Lock Selected", "Unlock Selected",
            "Hide Selected", "Lock and Hide Selected", "Show All Channels", "Make Selected Nonkeyable",
            "Make Selected Keyable", "Add to Selected Layers", "Remove From Selected Layers"]
    got = [t for t in texts if t in want]
    assert got == want, got
    assert props == ["Sync Selection in Graph Editor", "Sync Timeline Display"], props
    assert menus == ["ALLSET_MT_cb_freeze"]
    # Add to / Remove From Selected Layers run allset.anim_layer_attrs (no notice any more)
    ops = [e[1][0] for e in log if e[0] == "operator"]
    assert ops.count("allset.anim_layer_attrs") == 2, ops


def test_freeze_submenu():
    _cube()
    ob = bpy.context.active_object
    ob.location = (1, 2, 3)
    ob.rotation_euler = (0.3, 0, 0)
    log = []

    class Rec:
        def operator(self, idname, text=""):
            p = types.SimpleNamespace()
            log.append((idname, text, p))
            return p

    cb.ALLSET_MT_cb_freeze.draw(types.SimpleNamespace(layout=Rec()), bpy.context)
    assert [t for _i, t, _p in log] == ["Translate", "Rotate", "Scale", "All"]
    t = log[0][2]
    assert (t.translate, t.rotate, t.scale) == (True, False, False)
    assert bpy.ops.allset.freeze_transform(translate=True, rotate=False, scale=False) == {'FINISHED'}
    assert tuple(ob.location) == (0, 0, 0) and abs(ob.rotation_euler.x - 0.3) < 1e-6


# --- all-channel commands ---------------------------------------------------------------------------------------

def test_breakdown_all_and_mute_all():
    ob = _cube()
    bpy.context.scene.frame_set(5)
    assert bpy.ops.allset.cb_breakdown_all() == {'FINISHED'}
    curves = kit.fcurves(ob)
    assert len(curves) == 10, [f.data_path for f in curves]      # T / R / S + Visibility
    assert all(f.keyframe_points[0].type == 'BREAKDOWN' for f in curves)
    assert bpy.ops.allset.cb_mute_all(mute=True) == {'FINISHED'}
    assert all(f.mute for f in kit.fcurves(ob))
    assert cb.channel_state(ob, "tx") == 'MUTED'
    bpy.ops.allset.cb_mute_all(mute=False)
    assert not any(f.mute for f in kit.fcurves(ob))


# --- Cut / Copy / Paste Selected (Maya) ------------------------------------------------


def test_cut_selected_removes_the_curves():
    ob = _cube()
    _key(ob, 0, ((1, 0.0), (10, 5.0)))
    _key(ob, 1, ((1, 0.0), (10, 5.0)))
    cb.set_selected_channels(["tx"])
    assert bpy.ops.allset.cb_clipboard(action="CUT") == {'FINISHED'}
    assert _keys(ob, "location", 0) == [] and len(_keys(ob, "location", 1)) == 2
    assert cbc.clipboard()[0][0] == "tx"
    cb.set_selected_channels([])
    assert bpy.ops.allset.cb_clipboard(action="COPY") == {'CANCELLED'}, "nothing selected: Maya warns"


# --- Select Connection ------------------------------------------------------------------------------------------

def test_select_connection():
    ob = _cube()
    bpy.ops.object.empty_add()
    target = bpy.context.active_object
    target.name = "locator1"
    for o in bpy.context.scene.objects:
        o.select_set(o == ob)
    bpy.context.view_layer.objects.active = ob
    dr = ob.driver_add("location", 1).driver
    var = dr.variables.new()
    var.targets[0].id = target
    var.targets[0].data_path = "location.x"
    _key(ob, 0, ((1, 0.0), (10, 5.0)))
    cb.set_selected_channels(["ty"])
    assert bpy.ops.allset.cb_select_connection() == {'FINISHED'}
    assert bpy.context.active_object == target and not ob.select_get()
    for o in bpy.context.scene.objects:
        o.select_set(o == ob)
    bpy.context.view_layer.objects.active = ob
    cb.set_selected_channels(["tx"])
    assert bpy.ops.allset.cb_select_connection() == {'FINISHED'}
    sel = [(f.data_path, f.array_index) for f in kit.fcurves(ob) if f.select]
    assert sel == [("location", 0)], sel
    cb.set_selected_channels(["sx"])
    assert bpy.ops.allset.cb_select_connection() == {'CANCELLED'}


# --- Sync Graph Editor / Timeline -------------------------------------------------------------------------------

def test_sync_graph_editor_and_timeline():
    p = preferences.get()
    try:
        ob = _cube()
        _key(ob, 0, ((1, 0.0), (10, 5.0)))
        _key(ob, 1, ((3, 0.0), (20, 5.0)))
        p.cb_sync_graph = True
        cb.set_selected_channels(["ty"])
        assert [(f.array_index, f.select) for f in kit.fcurves(ob)] == [(0, False), (1, True)]
        # S keys only the selected channels
        bpy.context.scene.frame_set(30)
        assert bpy.ops.allset.set_key() == {'FINISHED'}
        assert _keys(ob, "location", 1)[-1][0] == 30 and _keys(ob, "location", 0)[-1][0] == 10
        assert not any(f.data_path == "scale" for f in kit.fcurves(ob))
        p.cb_sync_graph = False
        p.cb_sync_timeline = True
        assert [f for f, _b in time_slider.key_frames([ob])] == [3, 20, 30]
        p.cb_sync_timeline = False
        assert [f for f, _b in time_slider.key_frames([ob])] == [1, 3, 10, 20, 30]
    finally:
        p.cb_sync_graph = p.cb_sync_timeline = False


# --- SHAPES rows as channels -------------------------------------------------------------------------------------

def _light(kind='POINT'):
    _clear()
    bpy.ops.allset.create(kind=kind)
    return bpy.context.active_object


def test_light_intensity_and_color_are_keyable_channels():
    ob = _light('POINT_LIGHT')
    keys = cb.drawn_keys(ob)
    assert "sh:allset_intensity" in keys and "sh:maya:colorR" in keys and "sh:maya:coneAngle" not in keys, keys
    assert cb.channel_label("sh:allset_intensity") == "Intensity"
    cb.set_selected_channels(["sh:allset_intensity", "sh:maya:colorR"])
    bpy.context.scene.frame_set(1)
    assert bpy.ops.allset.cb_key_selected() == {'FINISHED'}
    paths = sorted((f.data_path, f.array_index) for f in kit.fcurves(ob.data))
    assert paths == [("color", 0), ("energy", 0)], paths
    assert cb.channel_state(ob, "sh:allset_intensity") == 'KEYED'
    # a typed value through the channel goes to the light (Maya intensity 2 = twice the power)
    e1 = ob.data.energy
    cb.set_value(ob, "sh:allset_intensity", 2.0)
    assert abs(ob.data.energy - 2 * e1) < 1e-4 and abs(cb.get_value(ob, "sh:allset_intensity") - 2.0) < 1e-6
    assert bpy.ops.allset.cb_mute(mute=True) == {'FINISHED'}
    assert cb.channel_state(ob, "sh:maya:colorR") == 'MUTED'
    assert bpy.ops.allset.cb_delete_keys() == {'FINISHED'}
    assert not kit.fcurves(ob.data)


def test_spot_cone_and_penumbra_rows():
    ob = _light('SPOT_LIGHT')
    light = ob.data
    rows = [n for kind, n, _t, _i in cb.wanted_rows(ob) if kind == "SHAPE"]
    assert rows[-2:] == ["maya:coneAngle", "maya:penumbraAngle"], rows
    cone, pen = lights.cone_penumbra(light)
    assert abs(cone - 40.0) < 1e-4 and abs(pen) < 1e-6, (cone, pen)      # defaults 40 / 0
    cb.set_value(ob, "sh:maya:penumbraAngle", 5.0)
    assert abs(math.degrees(light.spot_size) - 50.0) < 1e-4 and abs(light.spot_blend - 0.2) < 1e-6
    assert abs(cb.get_value(ob, "sh:maya:coneAngle") - 40.0) < 1e-4
    cb.set_value(ob, "sh:maya:penumbraAngle", -5.0)
    assert abs(math.degrees(light.spot_size) - 40.0) < 1e-4 and abs(light.spot_blend - 0.25) < 1e-6
    assert abs(cb.get_value(ob, "sh:maya:penumbraAngle") + 5.0) < 1e-4
    cb.set_selected_channels(["sh:maya:coneAngle"])
    assert bpy.ops.allset.cb_key_selected() == {'FINISHED'}
    assert sorted(f.data_path for f in kit.fcurves(light)) == ["spot_blend", "spot_size"]


def test_shape_rows_are_selectable_cells():
    ob = _light('POINT_LIGHT')
    cb.rebuild_rows(bpy.context)
    rows = bpy.context.scene.allset_cb.rows
    i = next(i for i, r in enumerate(rows) if r.kind == "SHAPE" and r.name == "allset_intensity")
    assert cb.cell_key(f"allset_cb.rows[{i}].sel", bpy.context.scene) == ("sh:allset_intensity", "NAME")
    rows[i].sel = True
    assert "sh:allset_intensity" in cb.selected_channels() and rows[i].sel


# --- #97 Bind Skin INPUTS name -----------------------------------------------------------------------------------

def test_bind_skin_inputs_is_skin_cluster():
    _clear()
    arm = joints.new_skeleton(bpy.context)
    parent = None
    for p in ((0, 0, 4), (0, 0, 0)):
        parent = joints.add_joint(arm, Vector(p), parent, length=0.5)
    joints.finish(bpy.context, arm, ["joint1", "joint2"])
    bpy.ops.object.mode_set(mode='OBJECT')
    meshes = []
    for x in (0.0, 3.0):
        bpy.ops.mesh.primitive_cube_add(location=(x, 0, 2))
        meshes.append(bpy.context.active_object)
    for mesh in meshes:
        for o in bpy.context.scene.objects:
            o.select_set(o in (arm, mesh))
        bpy.context.view_layer.objects.active = mesh
        assert bpy.ops.allset.bind_skin() == {'FINISHED'}
    names = [next(m.name for m in me.modifiers if m.type == 'ARMATURE') for me in meshes]
    assert names == ["skinCluster1", "skinCluster2"], names      # Maya: skinCluster1 / skinCluster2
    md = next(m for m in meshes[0].modifiers if m.type == 'ARMATURE')
    assert attribute_editor.modifier_node(meshes[0], md) == ("skinCluster1", "skinCluster")
    # Blender's own bind (Heat Map) gets the next name too
    bpy.ops.mesh.primitive_cube_add(location=(6, 0, 2))
    third = bpy.context.active_object
    for o in bpy.context.scene.objects:
        o.select_set(o in (arm, third))
    assert bpy.ops.allset.bind_skin(bind_method='HEAT_MAP') == {'FINISHED'}
    assert next(m.name for m in third.modifiers if m.type == 'ARMATURE') == "skinCluster3"
