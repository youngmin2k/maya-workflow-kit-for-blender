"""#106: main line: Skin / Constrain items wired, option windows, normal / tangent constraints named like
Maya nodes in Channel Box INPUTS, the skin weight-sum helper hidden from INPUTS."""

from importlib import import_module

import bpy

import kit

menu_map = import_module(kit.MODULE + ".ui.menu_map")
notices = import_module(kit.MODULE + ".ui.notices")
ow = import_module(kit.MODULE + ".operators.option_windows")
cb = import_module(kit.MODULE + ".ui.channel_box")

WIRED = {
    "Skin/Move Weights to Influences": "allset.move_skin_weights",
    "Skin/Export Weight Maps...": "allset.export_weight_maps",
    "Skin/Import Weights Maps...": "allset.import_weight_maps",
    "Skin/Substitute Geometry": "allset.substitute_geometry",
    "Skin/Bake Deformation to Skin Weights...": "allset.bake_deformation",
    "Constrain/Normal": "allset.normal_constraint",
    "Constrain/Tangent": "allset.tangent_constraint",
    "Constrain/Remove Target": "allset.remove_constraint_target",
    "Constrain/Set Rest Position": "allset.set_constraint_rest",
    "Constrain/Modify Constrained Axis...": "allset.modify_constraint_axes",
}


def test_items_wired():
    for path, op in WIRED.items():
        assert menu_map.MAP[path] == op, path
        assert path not in notices.NOTICES, path
    modes = {p: menu_map.MAP[f"Skin/Normalize Weights/{p}"] for p in (
        "Disable Weight Normalization", "Enable Weight Normalization", "Enable Weight Post Normalization")}
    assert [v[1]["mode"] for v in modes.values()] == ['NONE', 'INTERACTIVE', 'POST']


def test_option_windows():
    want = {"normal_constraint": ("Normal Constraint Options", "Add"),
            "tangent_constraint": ("Tangent Constraint Options", "Add"),
            "remove_constraint_target": ("Remove Target Options", "Remove"),
            "modify_constraint_axes": ("Modify Constrained Axis Options", "Modify"),
            "substitute_geometry": ("Substitute Geometry Options", "Substitute Geometry")}
    for key, (title, action) in want.items():
        w = ow._BY_KEY[key]
        assert (w.title, w.action) == (title, action), key
    d = ow._BY_KEY["substitute_geometry"].defaults()
    assert d == {"reweight_distance": 1.0, "disable_non_skin": False, "retain_old": False}
    d = ow._BY_KEY["normal_constraint"].defaults()
    assert d["aim_vector"] == (1.0, 0.0, 0.0) and d["world_up_type"] == "Vector" and d["weight"] == 1.0


def test_normal_constraint_maya_node_name():
    bpy.ops.object.select_all(action='DESELECT')
    bpy.ops.mesh.primitive_plane_add(size=4)
    plane = bpy.context.object
    plane.name = "pPlane1"
    bpy.ops.object.empty_add(location=(0.3, 0.2, 1.0))
    loc = bpy.context.object
    loc.name = "locator1"
    plane.select_set(True)
    loc.select_set(True)
    bpy.context.view_layer.objects.active = loc
    assert bpy.ops.allset.normal_constraint() == {'FINISHED'}
    con = loc.constraints[-1]
    assert cb.constraint_node_name(loc, con) == "locator1_normalConstraint1", cb.constraint_node_name(loc, con)
    assert cb.weight_name(con) == "pPlane1W0", cb.weight_name(con)
