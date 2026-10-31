"""Issue #271: a blendShape target weight in the Channel Box INPUTS is a channel like Translate X — it can be
selected, keyed with Channels > Key Selected (and Breakdown / Mute / Delete), shows its keyed / animated state,
takes typed values and the MMB slider on every selected mesh with the same target, like Maya. Its animation lives
on the mesh's Key datablock (Blender's shape key value), where the Graph Editor shows it."""

from importlib import import_module
from types import SimpleNamespace

import bpy

import kit

cb = import_module(kit.MODULE + ".ui.channel_box")
cbc = import_module(kit.MODULE + ".ui.cb_channels")
compat = import_module(kit.MODULE + ".compat")


def _fresh():
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    cb.reset_open()
    cb.set_selected_channels([])
    bpy.context.scene.frame_set(1)


def _base(name, x=0.0):
    bpy.ops.mesh.primitive_cube_add(location=(x, 0.0, 0.0))
    ob = bpy.context.active_object
    ob.name = name
    ob.shape_key_add(name="Basis")
    kb = ob.shape_key_add(name="smile")
    kb.data[0].co.z += 1.0
    ob.shape_key_add(name="frown")
    return ob


def _scene():
    _fresh()
    a = _base("pCube1")
    b = _base("pCube2", 3.0)
    for ob in (a, b):
        ob.select_set(True)
    bpy.context.view_layer.objects.active = a
    cb.set_open(a, cb.blend_shape_node(a.data.shape_keys))     # INPUTS nodes start collapsed
    cb.rebuild_rows()
    return a, b


def _row(name):
    return next(r for r in bpy.context.scene.allset_cb.rows if r.kind == "BLEND" and r.name == name)


def test_weight_rows_are_channels():
    a, b = _scene()
    row = _row("smile")
    key = cb.row_key(row)
    assert cb.is_blend_key(key), key
    assert cb.has_channel(a, key) and cb.has_channel(b, key)
    assert not cb.has_channel(a, cb.BLEND_PREFIX + "Basis")     # the base shape is no target
    assert cb.channel_label(key) == "smile"
    assert key in cb.drawn_keys(a)
    assert [r.name for r in bpy.context.scene.allset_cb.rows if r.kind == "BLEND"] == ["smile", "frown"]
    row.sel = True
    assert cb.selected_channels() == [key] and row.sel
    i = list(bpy.context.scene.allset_cb.rows).index(row)
    assert cb.cell_key(f"allset_cb.rows[{i}].text", bpy.context.scene) == (key, "VALUE")
    assert cb.cell_key(f"allset_cb.rows[{i}].sel", bpy.context.scene) == (key, "NAME")
    assert cb.field_owner(bpy.context, key) == (row, "text")
    cb.set_selected_channels([])


def test_collapsed_node_has_no_weight_channels():
    a, _b = _scene()
    cb.set_open(a, cb.blend_shape_node(a.data.shape_keys), False)
    cb.rebuild_rows()
    assert not [r for r in bpy.context.scene.allset_cb.rows if r.kind == "BLEND"]
    assert cb.BLEND_PREFIX + "smile" not in cb.drawn_keys(a)


def test_key_selected_keys_the_weight_on_every_selected_mesh():
    a, b = _scene()
    key = cb.row_key(_row("smile"))
    cb.set_selected_channels([key])
    assert cb.channel_state(a, key) is None
    a.data.shape_keys.key_blocks["smile"].value = 0.25
    b.data.shape_keys.key_blocks["smile"].value = 0.75
    assert bpy.ops.allset.cb_key_selected() == {'FINISHED'}
    for ob, v in ((a, 0.25), (b, 0.75)):
        fc = cb.fcurve(ob, key)
        assert fc is not None and fc.data_path == 'key_blocks["smile"].value', fc
        assert fc in list(compat.id_fcurves(ob.data.shape_keys))       # on the Key datablock
        assert len(fc.keyframe_points) == 1 and abs(fc.keyframe_points[0].co.y - v) < 1e-6
        assert cb.channel_state(ob, key) == 'KEYED'
        # the other target stays unkeyed
        assert cb.fcurve(ob, cb.BLEND_PREFIX + "frown") is None
    bpy.context.scene.frame_set(10)
    assert cb.channel_state(a, key) == 'ANIMATED'
    a.data.shape_keys.key_blocks["smile"].value = 1.0
    assert bpy.ops.allset.cb_key_selected() == {'FINISHED'}
    assert len(cb.fcurve(a, key).keyframe_points) == 2
    bpy.context.scene.frame_set(1)
    assert abs(a.data.shape_keys.key_blocks["smile"].value - 0.25) < 1e-6     # the key animates the weight
    cb.set_selected_channels([])


def test_breakdown_mute_delete_and_auto_key_helpers():
    a, _b = _scene()
    key = cb.BLEND_PREFIX + "frown"
    assert cb.keyframe(a, key, 'BREAKDOWN')
    fc = cb.fcurve(a, key)
    assert fc.keyframe_points[0].type == 'BREAKDOWN'
    assert cb.auto_keys(a, key)          # already keyed: Auto Key keys it on change
    cb.set_selected_channels([key])
    assert bpy.ops.allset.cb_mute(mute=True) == {'FINISHED'}
    assert fc.mute and cb.channel_state(a, key) == 'MUTED'
    assert bpy.ops.allset.cb_delete_keys() == {'FINISHED'}
    assert cb.fcurve(a, key) is None and cb.channel_state(a, key) is None
    cb.set_selected_channels([])


def test_copy_paste_and_select_connection():
    a, _b = _scene()
    src = cb.BLEND_PREFIX + "smile"
    kbs = a.data.shape_keys.key_blocks
    for frame, v in ((1, 0.0), (10, 1.0)):
        bpy.context.scene.frame_set(frame)
        kbs["smile"].value = v
        assert cb.keyframe(a, src)
    cb.set_selected_channels([src])
    assert cbc.copy_selected(bpy.context) == 1
    assert cbc.connection(a, src) == ("CURVE", cb.fcurve(a, src))
    dst = cb.BLEND_PREFIX + "frown"
    cb.set_selected_channels([dst])
    bpy.context.scene.frame_set(20)
    assert cbc.paste_selected(bpy.context)
    fc = cb.fcurve(a, dst)
    assert fc is not None and [round(k.co.x) for k in fc.keyframe_points] == [20, 29], list(fc.keyframe_points)
    bpy.context.scene.frame_set(1)
    cb.set_selected_channels([])


def test_typed_value_and_slider_on_every_selected_mesh():
    a, b = _scene()
    row = _row("smile")
    row.text = "0.4"
    for ob in (a, b):
        assert abs(ob.data.shape_keys.key_blocks["smile"].value - 0.4) < 1e-6
    assert row.text.startswith("0.4"), row.text
    key = cb.row_key(row)
    assert abs(cb.get_value(a, key) - 0.4) < 1e-6
    cb.set_selected_channels([key])
    pairs = cb.slider_targets(bpy.context)
    assert (a, key) in pairs and (b, key) in pairs, pairs
    cb.slider_apply({p: 0.4 for p in pairs}, 20)          # 20 px x 0.01
    for ob in (a, b):
        assert abs(ob.data.shape_keys.key_blocks["smile"].value - 0.6) < 1e-6
    cb.set_selected_channels([])


def test_drawn_row_is_a_selectable_channel():
    """Drawn: the weight's name is the channel's select toggle and the value its text field."""
    a, _b = _scene()
    log = []

    class Rec:
        def __getattr__(self, name):
            if name in ("row", "column", "split", "box"):
                return lambda *args, **kw: Rec()
            if name in ("prop", "label", "operator", "menu"):
                return lambda *args, **kw: log.append((name, args, kw)) or SimpleNamespace()
            return lambda *args, **kw: None

        def __setattr__(self, name, value):
            pass

    cb.draw_blend_shape(cb.Lines(Rec()), bpy.context, a, a.data.shape_keys)
    sels = [(args[0].name, kw.get("text")) for n, args, kw in log
            if n == "prop" and len(args) > 1 and args[1] == "sel" and isinstance(args[0], cb.ALLSET_PG_cb_row)]
    assert sels == [("smile", "smile"), ("frown", "frown")], sels
    texts = [args[0].name for n, args, kw in log
             if n == "prop" and len(args) > 1 and args[1] == "text" and isinstance(args[0], cb.ALLSET_PG_cb_row)]
    assert texts == ["smile", "frown"], texts
