"""Maya selection modifiers in the Dope Sheet, NLA and Node Editor (Shift toggle, Ctrl deselect,
Ctrl+Shift add). GUI: tests/gui/gui_step86_select_modifiers.py."""

from importlib import import_module


import kit

patches = import_module(kit.MODULE + ".keymap.maya_patches")


def _items(km, idname, value):
    kc = kit.maya_kc()
    return [k for k in kc.keymaps[km].keymap_items
            if k.active and k.idname == idname and k.type == 'LEFTMOUSE' and k.value == value and not k.alt]


def _by_mods(items):
    return {(k.shift, k.ctrl): k for k in items}


def test_dopesheet_and_nla_clicks():
    for km, idname in (("Dopesheet", "action.clickselect"), ("NLA Editor", "nla.click_select")):
        m = _by_mods(_items(km, idname, 'PRESS'))
        assert set(m) == {(False, False), (True, False), (False, True), (True, True)}, (km, list(m))
        plain = m[(False, False)].properties
        assert plain.deselect_all and not plain.extend
        for mods in ((True, False), (False, True), (True, True)):      # no deselect option: toggle
            assert m[mods].properties.extend, (km, mods)
    m = _by_mods(_items("Dopesheet", "action.clickselect", 'PRESS'))
    assert not m[(False, False)].properties.column and not m[(False, False)].properties.channel
    kc = kit.maya_kc()
    alts = [k for k in kc.keymaps["Dopesheet"].keymap_items if k.idname == "action.clickselect" and k.alt]
    assert len(alts) == 4, "the Alt column / channel variants stay"


def test_node_clicks():
    m = _by_mods(_items("Node Editor", "node.select", 'PRESS'))
    assert set(m) == {(False, False), (True, False), (False, True), (True, True)}
    p = m[(False, False)].properties
    assert p.deselect_all and p.select_passthrough
    assert m[(True, False)].properties.toggle
    assert m[(False, True)].properties.deselect
    assert m[(True, True)].properties.extend and not m[(True, True)].properties.toggle


def test_boxes():
    # the Dope Sheet Shift box runs as SET, allset.select_2d_box (first) makes it Maya's toggle
    for km, idname, want in (("Dopesheet", "action.select_box", {(False, False): 'SET', (True, False): 'SET',
                                                                  (False, True): 'SUB', (True, True): 'ADD'}),
                             ("NLA Editor", "nla.select_box", {(False, False): 'SET', (True, False): 'ADD',
                                                               (False, True): 'SUB', (True, True): 'ADD'}),
                             ("Node Editor", "node.select_box", {(False, False): 'SET', (True, False): 'ADD',
                                                                 (True, True): 'ADD'})):
        m = _by_mods(_items(km, idname, 'CLICK_DRAG'))
        assert {mods: k.properties.mode for mods, k in m.items()} == want, (km, {k: v.properties.mode for k, v in m.items()})
        assert all(k.properties.tweak for k in m.values())
    # Node Editor Ctrl+drag stays Blender's link detach
    kc = kit.maya_kc()
    assert [k for k in kc.keymaps["Node Editor"].keymap_items
            if k.idname == "node.link" and k.type == 'LEFTMOUSE' and k.value == 'CLICK_DRAG' and k.ctrl and not k.shift]


def test_ctrl_shift_items_removed():
    kc = kit.maya_kc()
    for km, idname in patches.SELECT_CTRL_SHIFT_REMOVED:
        left = [k for k in kc.keymaps[km].keymap_items if k.idname == idname and k.type == 'LEFTMOUSE'
                and k.shift and k.ctrl and not k.alt]
        assert not left, km
    # the bracket keys keep select_leftright
    assert [k for k in kc.keymaps["Dopesheet"].keymap_items
            if k.idname == "action.select_leftright" and k.type == 'LEFT_BRACKET']
