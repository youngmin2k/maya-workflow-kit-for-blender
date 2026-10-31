"""Step 54: create paths in Maya units, light power x maya_unit^2, and the shared "not in Blender"
notices. GUI: tests/gui/gui_step54_units_notices.py."""

import math
import types
from importlib import import_module

import bpy

import kit

create = import_module(kit.MODULE + ".operators.create")
units = import_module(kit.MODULE + ".operators.units")
menu_map = import_module(kit.MODULE + ".ui.menu_map")
menu_sets = import_module(kit.MODULE + ".ui.menu_sets")
shelf_map = import_module(kit.MODULE + ".ui.shelf_map")
notices = import_module(kit.MODULE + ".ui.notices")
mm = import_module(kit.MODULE + ".marking.menus")

# The three unit setups: Maya Workflow Kit template (m, cm shown), Maya Units (1 BU = 1 cm), factory m.
SETUPS = {
    "template": dict(system='METRIC', length_unit='CENTIMETERS', scale_length=1.0),   # maya_unit 0.01
    "maya units": dict(system='METRIC', length_unit='CENTIMETERS', scale_length=0.01),  # 1
    "factory": dict(system='METRIC', length_unit='METERS', scale_length=1.0),          # 1
}
# FX creation (force fields, quick smoke) runs Blender's operators at real size and isn't listed here.
RAW_CREATE = {"object.armature_add", "object.text_add", "object.empty_image_add", "object.light_add"}


def _units(name):
    us = bpy.context.scene.unit_settings
    for key, value in SETUPS[name].items():
        setattr(us, key, value)
    return units.maya_unit()


def _fresh():
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)


def _make(kind):
    assert bpy.ops.allset.create(kind=kind) == {'FINISHED'}, kind
    return bpy.context.view_layer.objects.active


def test_create_paths_in_maya_units():
    expect = {"template": 0.01, "maya units": 1.0, "factory": 1.0}
    for setup, want_k in expect.items():
        _fresh()
        k = _units(setup)
        assert abs(k - want_k) < 1e-6 * want_k, (setup, k)
        joint = _make('JOINT')
        bone = joint.data.bones[0]
        assert abs(bone.length - k) < 1e-5 * k and bone.name == "joint1" and joint.name == "skeleton1", setup
        assert joint.pose.bones[0].rotation_mode == 'XYZ'
        text = _make('TEXT')
        assert abs(text.data.size - k) < 1e-5 * k and text.name == "typeMesh1", (setup, text.data.size)
        plane = _make('IMAGE_PLANE')
        assert plane.empty_display_type == 'IMAGE' and abs(plane.empty_display_size - k) < 1e-5 * k
        assert plane.name == "imagePlane1"


def test_light_power_scaled_by_maya_unit_squared():
    for setup in SETUPS:
        _fresh()
        k = _units(setup)
        # step 137: Maya intensity 1 / No Decay, power matched to Maya renders (operators/lights.py):
        # still x maya_unit^2, now 4 pi^2 x 100 (point / spot, matched at 10 units) and pi^2 x 9.87 (area)
        pi2 = math.pi ** 2
        for kind, base in (('POINT_LIGHT', 4 * pi2 * 100), ('SPOT_LIGHT', 4 * pi2 * 100), ('AREA_LIGHT', pi2 * 9.87)):
            ob = _make(kind)
            assert abs(ob.data.energy - base * k * k) < 1e-5 * base * k * k, (setup, kind, ob.data.energy)
        sun = _make('DIRECTIONAL_LIGHT')
        assert abs(sun.data.energy - math.pi) < 1e-6, "sun light: no distance falloff, not scaled (Maya 1 = pi)"


def _actions():
    for path, action in menu_map.MAP.items():
        yield path, action
    for key, (action, _icon) in shelf_map.BY_COMMAND.items():
        yield f"shelf {key}", action
    for name, menu in mm.MENUS.items():
        for path, _label, action in mm.walk(menu, name):
            yield path, action


def test_no_raw_create_operator_left():
    bad = []
    for path, action in _actions():
        s = menu_map.normalize(action) if not isinstance(action, mm.Sub) else None
        if s is not None and s[1] in RAW_CREATE:
            bad.append((path, s[1]))
    assert not bad, bad


def test_notices_are_real_menu_paths_with_a_line():
    paths = {path for path, _it in menu_sets.iter_items()}
    missing = sorted(set(notices.NOTICES) - paths)
    assert not missing, missing
    for path, (substitute, line) in notices.NOTICES.items():
        assert substitute and line.startswith("Blender") or "Blender" in line, (path, line)
    want = {"Windows/Animation Editors/Trax Editor": "NLA",
            # step 197: Relationship Editors > Character Sets is real (operators/character_sets.py)
            "Windows/General Editors/Hypergraph: Connections": "Drivers", "Skeleton/HumanIK": "Rigify",
            "Windows/General Editors/Namespace Editor": "ns:", "File/Create Reference...": "Library Override",
            "File/Set Project...": "projects", "Modify/Evaluate Nodes/nucleuses": "nucleus",
            "Windows/Rendering Editors/Light Editor": "Light Editor", "Create/Lights/Point Light": "square"}
    for path, word in want.items():
        assert word in " ".join(notices.NOTICES[path]), (path, word)


class _Rec:
    def __init__(self):
        self.log = []

    def operator(self, idname, text=None, **kw):
        props = types.SimpleNamespace()
        self.log.append((idname, text, props))
        return props

    def menu(self, idname, text=None, **kw):
        self.log.append(("menu", idname, text))


def test_notice_in_tooltip_and_help_line():
    # an item with a substitute draws through allset.menu_item (its tooltip carries the notice)
    rec = _Rec()
    menu_sets.draw_item(rec, "Windows/Animation Editors/Trax Editor", "Trax Editor")
    assert rec.log[0][0] == "allset.menu_item" and rec.log[0][2].item == "Windows/Animation Editors/Trax Editor"
    props = types.SimpleNamespace(item="Windows/Animation Editors/Trax Editor")
    tip = menu_sets.ALLSET_OT_menu_item.description(bpy.context, props)
    assert "NLA" in tip and "Trax" in tip, tip
    assert "NLA" in notices.current(), "the Help Line shows the notice while the tooltip is up"
    # a greyed item keeps allset.menu_unavailable, tooltip with the notice
    rec = _Rec()
    # (Batch Render until step 152, which maps it)
    path = "Windows/General Editors/Namespace Editor"
    menu_sets.draw_item(rec, path, "Namespace Editor")
    assert rec.log[0][0] == "allset.menu_unavailable", rec.log
    tip = menu_sets.ALLSET_OT_menu_unavailable.description(bpy.context, types.SimpleNamespace(item=path))
    assert "Namespace Editor" in tip and "namespaces" in tip, tip
    # items without a notice run the same action through allset.menu_item (step 108: Blender prints no shortcut
    # of its own beside it)
    rec = _Rec()
    menu_sets.draw_item(rec, "Create/Polygon Primitives/Cube", "Cube")
    assert rec.log[0][0] == "allset.menu_item" and rec.log[0][2].item == "Create/Polygon Primitives/Cube"
    assert menu_map.spec("Create/Polygon Primitives/Cube")[1] == "allset.create"
    # every notice gets into its item's tooltip
    for path in notices.NOTICES:
        cls = menu_sets.ALLSET_OT_menu_item if path in menu_map.MAP else menu_sets.ALLSET_OT_menu_unavailable
        tip = cls.description(bpy.context, types.SimpleNamespace(item=path))
        assert notices.NOTICES[path][1] in tip, path
