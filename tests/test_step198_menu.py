"""#105: main line: Graph Editor menu items wired (Retime / buffers / weights / Add Key / Select Unsnapped /
Set Curve Colors), Default Tangent Weight on curves the kit keys, curve colour rules, sidebar hidden once."""

from importlib import import_module

import bpy

import kit

gm = import_module(kit.MODULE + ".operators.graph_menu_198")
gw = import_module(kit.MODULE + ".operators.graph_weights")
gkm = import_module(kit.MODULE + ".operators.graph_key_menu")
emm = import_module(kit.MODULE + ".ui.editor_menu_map")
menu_map = import_module(kit.MODULE + ".ui.menu_map")
notices = import_module(kit.MODULE + ".ui.notices")
chrome = import_module(kit.MODULE + ".ui.editor_chrome")
preferences = import_module(kit.MODULE + ".preferences")

GE = "Graph Editor"
WIRED = {
    "Edit/Transformation Tools/Retime Tool": "allset.retime_tool",
    "Edit/Select Unsnapped": "allset.select_unsnapped",
    "Edit/Set Curve Colors...": "allset.curve_colors",
    "Curves/Buffer Curve/Snapshot": "allset.buffer_snapshot",
    "Curves/Swap Buffer Curve": "allset.buffer_swap",
    "Keys/Add Key Tool": "allset.add_key_tool",
}


def _cube_keys(times=(1, 5.5, 10, 12.25)):
    bpy.ops.object.select_all(action='DESELECT')
    bpy.ops.mesh.primitive_cube_add()
    ob = bpy.context.object
    for i, t in enumerate(times):
        ob.location.x = i
        ob.keyframe_insert("location", index=0, frame=t)
    return ob


def test_menu_items_wired_and_not_noticed():
    for tail, op in WIRED.items():
        act = menu_map.MAP[f"{GE}/{tail}"]
        assert act == op or act[0] == op, (tail, act)
        assert f"{GE}/{tail}" not in notices.NOTICES, tail
    for tail in ("Curves/Weighted Tangents", "Curves/Non-weighted Tangents", "Tangents/Lock Tangent Length",
                 "Tangents/Free Tangent Length", "View/Show Buffer Curves",
                 "Curves/Default Tangent Weight/Weighted Tangents",
                 "Curves/Default Tangent Weight/Non-weighted Tangents"):
        assert f"{GE}/{tail}" in menu_map.MAP, tail
    for op in ("retime_tool", "select_unsnapped", "curve_colors", "buffer_snapshot", "buffer_swap", "add_key_tool",
               "curve_weights", "tangent_weight_lock"):
        bpy.ops.allset.__getattr__(op).get_rna_type()


def test_toolbar_buttons_wired():
    icons = {spec[0]: spec[2] for spec in chrome.GRAPH_ICONS if isinstance(spec, tuple)}
    assert icons["key_retime_tool"] == "allset.retime_tool"
    assert icons["buffer_snapshot"] == "allset.buffer_snapshot" and icons["buffer_swap"] == "allset.buffer_swap"
    assert icons["tan_lock_length"] == ("allset.tangent_weight_lock", {"lock": True})
    for k in ("key_retime_tool", "buffer_swap", "tan_free_length", "tan_lock_length"):
        assert k not in chrome.NOTICES, k


def test_unsnapped_rule():
    assert gm.unsnapped([1.0, 5.5, 10.0, 12.25, 3.00001]) == [1, 3]
    assert gm.unsnapped([2.0, 3.0]) == []


def test_select_unsnapped_replaces_selection():
    ob = _cube_keys()
    fc = kit.fcurves(ob)[0]
    for kp in fc.keyframe_points:
        kp.select_control_point = True

    assert gm.select_unsnapped([fc]) == 2
    assert [kp.select_control_point for kp in fc.keyframe_points] == [False, True, False, True]


def test_default_tangent_weight_on_kit_created_curve():
    prefs = preferences.get(bpy.context)
    prefs.default_tangent_weight = 'NON_WEIGHTED'
    bpy.ops.object.select_all(action='DESELECT')
    bpy.ops.mesh.primitive_cube_add()
    ob = bpy.context.object
    ob.keyframe_insert("location", index=2, frame=1)
    gkm.after_insert(ob, "location", 2, 1)
    fc = next(f for f in kit.fcurves(ob) if f.array_index == 2)
    assert gw.is_weighted(fc) is False
    prefs.default_tangent_weight = 'WEIGHTED'
    ob.keyframe_insert("location", index=1, frame=1)
    gkm.after_insert(ob, "location", 1, 1)
    fc1 = next(f for f in kit.fcurves(ob) if f.array_index == 1)
    assert gw.is_weighted(fc1) is True
    # a second key on an existing curve doesn't re-mark it
    prefs.default_tangent_weight = 'NON_WEIGHTED'
    ob.keyframe_insert("location", index=1, frame=10)
    gkm.after_insert(ob, "location", 1, 10)
    assert gw.is_weighted(fc1) is True
    prefs.default_tangent_weight = 'NON_WEIGHTED'


def test_curve_color_rules_apply_and_remove():
    ob = _cube_keys()
    fc = kit.fcurves(ob)[0]
    assert gm.curve_attr(fc) == "translateX"
    prefs = preferences.get(bpy.context)
    gm.write_rules(prefs, [("translateX", (0.2, 0.4, 0.6))])
    gm.apply_rules(gm.read_rules(prefs))
    assert fc.color_mode == 'CUSTOM' and all(abs(a - b) < 1e-4 for a, b in zip(fc.color, (0.2, 0.4, 0.6)))
    # a user colour wins over the rule
    ob2 = _cube_keys()
    fc2 = kit.fcurves(ob2)[0]
    fc2.color_mode, fc2.color = 'CUSTOM', (1.0, 1.0, 0.0)
    gm.apply_rules(gm.read_rules(prefs))
    assert tuple(round(c, 3) for c in fc2.color) == (1.0, 1.0, 0.0)
    # removing the rule gives the rule-coloured curve its automatic colour back, the user's stays
    gm.write_rules(prefs, [])
    gm.apply_rules([])
    assert fc.color_mode == 'AUTO_RGB'
    assert fc2.color_mode == 'CUSTOM'
    prefs.curve_color_rules = ""


def test_add_key_rule():
    ob = _cube_keys((1, 10))
    fc = kit.fcurves(ob)[0]
    gm.add_key(fc, 5.0, 7.5)
    assert [(round(k.co.x, 4), round(k.co.y, 4)) for k in fc.keyframe_points] == [(1, 0), (5, 7.5), (10, 1)]
