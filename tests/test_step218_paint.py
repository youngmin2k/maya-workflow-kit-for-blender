"""Paint Skin Weights in Maya terms (Issue #126 A1 A2 A5 A6). Flood = Maya's formulas with
redistribution / locks / selected-vertex limit, Influences RMB = Maya's items, paint keys, Mode / Select Geometry.

The scene is rebuilt with Maya's vertex order (Blender index = Maya vertex id): polyCylinder
h 8 r 1 sx 20 sy 8 (caps are 20-gons, no centre vertex), rings at Maya y = 0..8 -> Blender z, joints at 0 / 4 / 8. The
bind is not redone: the "before" weights (the same on every vertex of a ring) are written into the groups."""

from importlib import import_module


import kit

joints = import_module(kit.MODULE + ".operators.joints")
skin = import_module(kit.MODULE + ".operators.skin")
wp = import_module(kit.MODULE + ".operators.weight_paint")
paint_weights = import_module(kit.MODULE + ".ui.paint_weights")
compat = import_module(kit.MODULE + ".compat")

SIDES, RINGS = 20, 9


def test_flood_blend_follows_brush_kind():
    # Blender's Blur brush = Maya Smooth (flood_settings), Average = Replace with the mean
    assert wp.maya_target('SMOOTH', 0.2, 0.9, 1.0, avg=0.4) == 0.4
    assert wp.redistribute({0: 0.5, 1: 0.5}, 1, 2.0, set(), {0, 1}) == {0: 0.0, 1: 1.0}
    # nothing unlocked to take the rest: the painted weight can't drop
    assert wp.redistribute({1: 1.0}, 1, 0.3, set(), {0, 1}) == {1: 1.0}
    assert wp.redistribute({0: 0.4, 1: 0.6}, 1, 0.0, {0}, {0, 1}) == {0: 0.4, 1: 0.6}


# --- A1: Influences RMB ------------------------------------------------------------------------------------


def test_sort_labels_and_natural_order():
    rna = wp.ALLSET_PG_weight_workspace.bl_rna.properties["sort"]
    assert [e.name for e in rna.enum_items] == ["Alphabetically", "By Hierarchy", "Flat"]
    assert rna.default == 'HIERARCHY'
    names = ["joint10", "joint2", "Joint1", "arm_b", "arm_a12", "arm_a3"]
    assert sorted(names, key=paint_weights.natural_key) == ["arm_a3", "arm_a12", "arm_b", "Joint1", "joint2",
                                                            "joint10"]


# --- A5 / A6: keys, Mode, Select Geometry, entry ------------------------------------------------------------

def _wp_items():
    return [k for k in kit.maya_kc().keymaps["Weight Paint"].keymap_items if k.active]


def _has(idname, type_, ctrl=False, alt=False, shift=False, **props):
    for k in _wp_items():
        if (k.idname == idname and k.type == type_ and k.value == 'PRESS' and bool(k.ctrl) == ctrl
                and bool(k.alt) == alt and bool(k.shift) == shift
                and all(getattr(k.properties, p) == v for p, v in props.items())):
            return True
    return False


def test_paint_keys():
    assert _has("allset.flood_weights", 'F', alt=True)
    assert not any(k.idname == "paint.weight_set" and k.type == 'F' and k.alt for k in _wp_items())
    assert _has("allset.paint_copy_vertex_weights", 'C', ctrl=True, alt=True)
    assert _has("allset.paint_paste_vertex_weights", 'V', ctrl=True, alt=True)
    assert _has("allset.skin_paint_mode", 'PERIOD', ctrl=True, step=1)
    assert _has("allset.skin_paint_mode", 'COMMA', ctrl=True, step=-1)
    assert _has("allset.paint_reflection", 'R', alt=True)


