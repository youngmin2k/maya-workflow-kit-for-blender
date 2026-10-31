"""Maya click / marquee modifiers outside the 3D View (Maya 2022).
Per editor, the four variants (plain / Shift / Ctrl / Ctrl+Shift) of a click
and a marquee: the Blender selection the kit's keymap item makes, then the kit's rule (operators/select_2d.py) —
the result must be Maya's. Plus the keymap items (first place, PASS_THROUGH ops) and the selection
state read / write on real keys and UVs."""

from importlib import import_module

import bmesh
import bpy

import kit

sel = import_module(kit.MODULE + ".operators.select_2d")
maya_patches = import_module(kit.MODULE + ".keymap.maya_patches")

F = frozenset

# Maya: (editor, variant, before, clicked, Maya result)
CLICKS = [
    # Graph Editor: plain on a selected key keeps the selection, Ctrl acts like plain, Shift toggles, Ctrl+Shift adds
    ("GRAPH", "none", {1, 10}, 10, {1, 10}), ("GRAPH", "shift", {1, 10}, 10, {1}),
    ("GRAPH", "ctrl", {1, 10}, 10, {1, 10}), ("GRAPH", "ctrl+shift", {1, 10}, 10, {1, 10}),
    ("GRAPH", "none", {1}, 10, {10}), ("GRAPH", "shift", {1}, 10, {1, 10}),
    ("GRAPH", "ctrl", {1}, 10, {10}), ("GRAPH", "ctrl+shift", {1}, 10, {1, 10}),
    # Dope Sheet: replace / toggle / deselect / add
    ("DOPE", "none", {1, 10}, 10, {10}), ("DOPE", "shift", {1, 10}, 10, {1}),
    ("DOPE", "ctrl", {1, 10}, 10, {1}), ("DOPE", "ctrl+shift", {1, 10}, 10, {1, 10}),
    ("DOPE", "none", {1}, 10, {10}), ("DOPE", "shift", {1}, 10, {1, 10}),
    ("DOPE", "ctrl", {1}, 10, {1}), ("DOPE", "ctrl+shift", {1}, 10, {1, 10}),
    # UV Editor: Blender's uv.select has deselect / toggle / extend (no kit rule needed)
    ("UV", "none", {0}, 1, {1}), ("UV", "shift", {0}, 1, {0, 1}), ("UV", "ctrl", {0}, 1, {0}),
    ("UV", "ctrl+shift", {0}, 1, {0, 1}),
]
RULE = {("GRAPH", "none"): 'KEEP', ("GRAPH", "ctrl"): 'CTRL', ("GRAPH", "ctrl+shift"): 'ADD',
        ("DOPE", "ctrl"): 'DESELECT', ("DOPE", "ctrl+shift"): 'ADD'}

# marquee catching keys 10 + 20 with keys 1 + 10 selected; Maya (Graph Editor, Dope Sheet, UV Editor alike)
BOXES = [("none", {10, 20}), ("shift", {1, 20}), ("ctrl", {1}), ("ctrl+shift", {1, 10, 20})]


def _blender_click(rule, variant, before, clicked):
    """What Blender's selection does inside the kit operator: KEEP runs a plain replace, ADD / DESELECT a toggle."""
    if rule in ('KEEP', 'CTRL') or variant == "none":
        return F({clicked})
    return before ^ F({clicked})


def test_click_tables_match_maya():
    for editor, variant, before, clicked, maya in CLICKS:
        before = F(before)
        rule = RULE.get((editor, variant))
        if editor == 'UV':
            got = {"none": F({clicked}), "shift": before ^ F({clicked}), "ctrl": before - F({clicked}),
                   "ctrl+shift": before | F({clicked})}[variant]
        else:
            after = _blender_click(rule, variant, before, clicked)
            got = sel.RULES[rule](before, after) if rule else after
        print(editor, variant, sorted(before), clicked, "->", sorted(got))
        assert got == F(maya), (editor, variant, sorted(before), sorted(got), sorted(maya))


def test_rules_leave_an_unchanged_selection_alone():
    for before in (F(), F({1}), F({1, 10})):
        for name, rule in sel.RULES.items():
            if name != 'XOR':
                assert rule(before, before) == before, (name, before)
    # Graph Editor Ctrl+click on empty space (Maya: the selection stays); plain click there clears
    assert sel.rule_ctrl(F({1, 10}), F()) == F({1, 10}) and sel.rule_keep(F({1, 10}), F()) == F()


def test_marquee_tables_match_maya():
    for editor in ('GRAPH', 'DOPE', 'UV'):
        for variant, maya in BOXES:
            before, inside = F({1, 10}), F({10, 20})
            mode = {"none": "SET", "shift": "SET", "ctrl": "SUB", "ctrl+shift": "ADD"}[variant]
            after = {"SET": inside, "SUB": before - inside, "ADD": before | inside}[mode]
            got = sel.rule_xor(before, after) if variant == "shift" else after
            print(editor, variant, "->", sorted(got))
            assert got == F(maya), (editor, variant, sorted(got))


def _items(km_name, idname):
    km = kit.maya_kc().keymaps.get(km_name)
    assert km is not None, km_name
    return [k for k in km.keymap_items if k.idname == idname and k.active]


def test_keymap_items_first_and_props():
    for km_name, editor, click, wanted in (
            ("Graph Editor", 'GRAPH', "graph.clickselect",
             {(False, False): 'KEEP', (False, True): 'CTRL', (True, True): 'ADD'}),
            ("Dopesheet", 'DOPE', "action.clickselect", {(False, True): 'DESELECT', (True, True): 'ADD'})):
        items = _items(km_name, "allset.select_2d_click")
        got = {(bool(k.shift), bool(k.ctrl)): k.properties.rule for k in items
               if k.type == 'LEFTMOUSE' and k.value == 'PRESS' and k.properties.editor == editor}
        assert got == wanted, (km_name, got)
        names = [k.idname for k in kit.maya_kc().keymaps[km_name].keymap_items]
        assert names.index("allset.select_2d_click") < names.index(click), km_name
    uv_kms = sorted(km for km in maya_patches.SELECT_2D_KEYMAPS if "Uv" in km or km == maya_patches.UV_KM)
    assert uv_kms, sorted(maya_patches.SELECT_2D_KEYMAPS)
    for km_name, editor in (("Graph Editor", 'GRAPH'), ("Dopesheet", 'DOPE'), *((km, 'UV') for km in uv_kms)):
        boxes = [k for k in _items(km_name, "allset.select_2d_box") if k.value == 'CLICK_DRAG' and k.shift]
        assert boxes and boxes[0].properties.editor == editor, km_name
        shift_box = [k for k in kit.maya_kc().keymaps[km_name].keymap_items
                     if k.idname.endswith("select_box") and k.shift and not k.ctrl and k.value == 'CLICK_DRAG']
        assert shift_box and all(k.properties.mode == 'SET' for k in shift_box), km_name
    assert {"allset.select_2d_click", "allset.select_2d_box"} <= set(maya_patches.PASS_THROUGH_FIRST)


def test_outliner_click_is_maya_qt_rule():
    km = kit.maya_kc().keymaps["Outliner"]
    got = {}
    for k in km.keymap_items:
        if k.idname == "outliner.item_activate" and k.type == 'LEFTMOUSE' and k.value == 'CLICK' and not k.alt:
            got[(bool(k.shift), bool(k.ctrl))] = (k.properties.extend, k.properties.extend_range)
    # plain replace, Shift range, Ctrl toggle, Ctrl+Shift add the range (Maya Outliner)
    assert got == {(False, False): (False, False), (True, False): (False, True), (False, True): (True, False),
                   (True, True): (True, True)}, got
    toggles = [k for k in km.keymap_items if k.idname == "allset.select_2d_click" and k.ctrl and not k.shift]
    assert toggles and toggles[0].properties.rule == 'TOGGLE' and toggles[0].value == 'CLICK'
    names = [k.idname for k in km.keymap_items]
    assert names.index("allset.select_2d_click") < names.index("outliner.item_activate")
    # Blender's extend click on a selected, not active row only makes it active: the kit deselects it (Maya toggle)
    assert sel.rule_outliner_toggle(F({"a", "b"}), F({"a", "b"}), "a") == F({"b"})
    assert sel.rule_outliner_toggle(F({"a"}), F({"a", "b"}), "b") == F({"a", "b"})
    assert sel.rule_outliner_toggle(F({"a", "b"}), F({"b"}), "a") == F({"b"})


def test_key_state_round_trip():
    ob = bpy.data.objects.new("pCube1", None)
    bpy.context.scene.collection.objects.link(ob)
    for f, v in ((1, 0.0), (10, 5.0), (20, 0.0)):
        ob.location.x = v
        ob.keyframe_insert("location", index=0, frame=f)
    items = sel.key_items()
    keys = sorted(items, key=lambda k: items[k].co.x)
    sel.set_key_state(F(keys[:2]))
    assert sel.key_state() == F(keys[:2])
    sel.set_key_state(sel.rule_xor(F(keys[:2]), F(keys[1:])))
    assert sel.key_state() == F({keys[0], keys[2]})
    fc = kit.fcurves(ob)[0]
    assert [kp.select_control_point for kp in fc.keyframe_points] == [True, False, True]


def test_uv_state_round_trip():
    me = bpy.data.meshes.new("uvPlaneShape")
    bm = bmesh.new()
    bm.loops.layers.uv.new("map1")
    bmesh.ops.create_grid(bm, x_segments=2, y_segments=2, size=1.0, calc_uvs=True)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new("uvPlane", me)
    bpy.context.scene.collection.objects.link(ob)
    bpy.context.view_layer.objects.active = ob
    ob.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.context.scene.tool_settings.use_uv_select_sync = False
    want = F({("uvPlane", 0), ("uvPlane", 1), ("uvPlane", 5)})
    sel.set_uv_state(want)
    assert sel.uv_state() == want, sorted(sel.uv_state())
    bpy.context.scene.tool_settings.use_uv_select_sync = True
    sel.set_uv_state(F({("uvPlane", 0)}))
    assert sel.uv_state() == F({("uvPlane", 0)})
    bpy.ops.object.mode_set(mode='OBJECT')
