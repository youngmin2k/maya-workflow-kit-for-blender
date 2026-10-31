"""Channel Box text entry (Maya display, relative +=/-=/*=//=), edits on every selected
object (custom attributes, SHAPES, INPUTS too) and every selected channel; AE material type
labels and lambert/blinn/phong sections.
"""

import math
from importlib import import_module

import bpy

import kit

cb_mod = import_module(kit.MODULE + ".ui.channel_box")
entry = import_module(kit.MODULE + ".ui.cb_entry")
ae = import_module(kit.MODULE + ".ui.attribute_editor")
ae_layout = import_module(kit.MODULE + ".ui.ae_layout")
material = import_module(kit.MODULE + ".operators.material")


def _scene(n=2, cm=True):
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    us = bpy.context.scene.unit_settings
    us.system, us.scale_length = 'METRIC', 1.0
    us.length_unit = 'CENTIMETERS' if cm else 'METERS'
    us.system_rotation = 'DEGREES'
    obs = []
    for i in range(n):
        bpy.ops.mesh.primitive_cube_add(location=(i * 0.1, 0, 0))
        obs.append(bpy.context.active_object)
    for ob in obs:
        ob.select_set(True)
    bpy.context.view_layer.objects.active = obs[0] if obs else None
    bpy.context.window_manager.allset_cb_selected = ""
    cb_mod.rebuild_rows()
    return obs


def P():
    return bpy.context.scene.allset_cb


def test_display_format():
    sc = bpy.context.scene
    _scene(1)
    assert entry.format_value(0.015, "LENGTH", sc) == "1.5", entry.format_value(0.015, "LENGTH", sc)
    assert entry.format_value(-0.0000001, "LENGTH", sc) == "0"
    assert entry.format_value(math.radians(45), "ROTATION", sc) == "45"
    assert entry.format_value(1.0, "NONE", sc) == "1"
    assert entry.format_value(True, "BOOL", sc) == "on"
    assert entry.format_value(7, "INT", sc) == "7"
    sc.unit_settings.length_unit = 'METERS'
    assert entry.format_value(0.015, "LENGTH", sc) == "0.015"


def test_parse_absolute_and_relative():
    sc = bpy.context.scene
    _scene(1)

    def p(text, old, kind):
        return entry.parse_entry(text, old, kind, sc)
    assert abs(p("5", 0.0, "LENGTH") - 0.05) < 1e-9          # 5 cm
    assert abs(p("5 m", 0.0, "LENGTH") - 5.0) < 1e-6
    assert abs(p("+=5", 0.1, "LENGTH") - 0.15) < 1e-9
    assert abs(p("-=2", 0.1, "LENGTH") - 0.08) < 1e-9
    assert abs(p("*=2", 0.1, "LENGTH") - 0.2) < 1e-9
    assert abs(p("/=2", 0.1, "LENGTH") - 0.05) < 1e-9
    assert abs(p("+=90", 0.0, "ROTATION") - math.pi / 2) < 1e-6
    assert abs(p("*= 3", 2.0, "NONE") - 6.0) < 1e-9
    assert p("off", True, "BOOL") is False and p("1", False, "BOOL") is True
    assert p("+=2", 3, "INT") == 5
    for bad in ("", "abc", "/=0", "+="):
        try:
            p(bad, 1.0, "NONE")
        except (ValueError, SyntaxError, TypeError):
            continue
        raise AssertionError(f"{bad!r} accepted")


def test_relative_entry_per_object_on_all_selected():
    a, b = _scene(2)
    a.location.x, b.location.x = 0.10, 0.30   # 10 cm, 30 cm
    assert P().tx_text == "10", P().tx_text   # lead = a, shown in cm without unit
    P().tx_text = "+=5"
    assert abs(a.location.x - 0.15) < 1e-6 and abs(b.location.x - 0.35) < 1e-6, (a.location.x, b.location.x)
    P().sx_text = "*=2"
    assert abs(a.scale.x - 2) < 1e-6 and abs(b.scale.x - 2) < 1e-6
    P().tx_text = "1"
    assert abs(a.location.x - 0.01) < 1e-6 and abs(b.location.x - 0.01) < 1e-6
    P().tx_text = "nonsense"
    assert abs(a.location.x - 0.01) < 1e-6, "bad text leaves the value"
    P().v_text = "off"
    assert a.hide_viewport and b.hide_viewport
    P().v_text = "on"


def test_entry_applies_to_selected_channels():
    a, b = _scene(2)
    cb_mod.set_selected_channels(["rx", "ry", "rz"])
    P().ry_text = "+=30"
    for ob in (a, b):
        assert all(abs(math.degrees(v) - 30) < 1e-4 for v in ob.rotation_euler), tuple(ob.rotation_euler)
    P().tx_text = "4"   # not a selected channel: only Translate X
    assert all(abs(math.degrees(v) - 30) < 1e-4 for v in a.rotation_euler)
    assert abs(a.location.x - 0.04) < 1e-6


def test_locked_channel_kept():
    a, b = _scene(2)
    b.lock_location[0] = True
    b.location.x = 0.5
    P().tx_text = "+=1"
    assert abs(b.location.x - 0.5) < 1e-6 and abs(a.location.x - 0.01) < 1e-6


def test_custom_attribute_rows_reach_other_objects():
    a, b = _scene(2)
    a["speed"] = 2.0
    b["speed"] = 5.0
    cb_mod.rebuild_rows()
    row = cb_mod.row_for(bpy.context, a, "CUSTOM", "speed")
    assert row is not None and row.text == "2", (row, row and row.text)
    row.text = "+=1"
    assert a["speed"] == 3.0 and b["speed"] == 6.0, (a["speed"], b["speed"])


def test_shape_rows_reach_other_cameras():
    _scene(0)
    cams = []
    for i in range(2):
        ob = bpy.data.objects.new(f"camera{i + 1}", bpy.data.cameras.new(f"cameraShape{i + 1}"))
        bpy.context.scene.collection.objects.link(ob)
        ob.select_set(True)
        cams.append(ob)
    cams[1].data.lens = 35
    bpy.context.view_layer.objects.active = cams[0]
    cb_mod.rebuild_rows()
    row = cb_mod.row_for(bpy.context, cams[0], "SHAPE", "lens")
    assert row is not None and row.text == "50", row and row.text
    row.text = "+=10"
    assert (cams[0].data.lens, cams[1].data.lens) == (60, 45), (cams[0].data.lens, cams[1].data.lens)


def test_input_rows_reach_same_modifier_type():
    a, b = _scene(2)
    for ob in (a, b):
        m = ob.modifiers.new("bevel", 'BEVEL')
        m.segments = 1
    b.modifiers["bevel"].name = "polyBevel2"
    cb_mod.set_open(a, cb_mod.mod_node(a.modifiers[0]))   # click the node name
    cb_mod.rebuild_rows()
    row = cb_mod.row_for(bpy.context, a, "INPUT", "segments", 'BEVEL', 0)
    assert row is not None and row.text == "1", row and row.text
    row.text = "3"
    assert a.modifiers[0].segments == 3 and b.modifiers[0].segments == 3


def test_rows_follow_the_lead_and_draw():
    a, b = _scene(2)
    a["x1"] = 1.0
    cb_mod.rebuild_rows()
    assert [r.name for r in P().rows] == ["x1"]
    bpy.context.view_layer.objects.active = b
    assert cb_mod.row_for(bpy.context, b, "CUSTOM", "x1") is None, "stale rows are not used"
    cb_mod.rebuild_rows()
    assert len(P().rows) == 0


def test_ae_material_type_labels_and_sections():
    ob, = _scene(1)
    expect = {'LAMBERT': ("lambert", "Common Material Attributes"),
              'BLINN': ("blinn", "Specular Shading"),
              'PHONG': ("phong", "Specular Shading"),
              'STANDARD_SURFACE': ("standardSurface", "Base"),
              'SURFACE': ("surfaceShader", "Surface Shader Attributes")}
    for kind, (node, section) in expect.items():
        mat = material.new_material(kind)
        assert ae.material_type(mat) == node, (kind, ae.material_type(mat))
        ob.data.materials.clear()
        ob.data.materials.append(mat)
        tab = next(t for t in ae.tabs(ob) if t[0] == "MAT:0")
        assert tab[2] == node, tab
        sections, name = ae.sections_for(ob, "MAT:0")
        assert name == node and any(s.name == section for s in sections), (kind, [s.name for s in sections])
    lam = material.new_material('LAMBERT')
    assert lam.name.startswith("lambert") and ae_layout.LAMBERT[0].open
    plain = bpy.data.materials.new("noNodes")
    # Blender 5.x: every new material has a Principled node tree
    assert ae.material_type(plain) == "standardSurface"
    principled = bpy.data.materials.new("fromBlender")
    principled.use_nodes = True
    assert ae.material_type(principled) == "standardSurface"


def test_disable_removes_handlers():
    _scene(1)
    kit.disable()
    try:
        assert not any(getattr(f, "__module__", "").endswith("channel_box")
                       for f in bpy.app.handlers.depsgraph_update_post)
    finally:
        kit.enable()
