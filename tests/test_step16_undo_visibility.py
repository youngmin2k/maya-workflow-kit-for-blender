"""Maya z / Shift+Z / Ctrl+Y undo-redo, h / Ctrl+H / Alt+H / Shift+H /
Ctrl+Shift+H visibility, Ctrl+1 isolate, Ctrl+Shift+I invert."""

from importlib import import_module

import bpy

import kit

visibility = import_module(kit.MODULE + ".operators.visibility")

KC = "Maya-style"


def _items(km, type, shift=False, ctrl=False, alt=False):
    km = kit.maya_kc().keymaps[km]
    return [(k.idname, dict(k.properties.items()) if k.properties else {}) for k in km.keymap_items
            if k.active and k.type == type and k.value == 'PRESS' and k.shift == shift
            and k.ctrl == ctrl and k.alt == alt and not k.oskey]


def test_undo_redo_keys_in_screen():
    assert ("ed.undo", {}) in _items("Screen", "Z")
    assert ("ed.redo", {}) in _items("Screen", "Z", shift=True)
    assert ("ed.redo", {}) in _items("Screen", "Y", ctrl=True)
    assert ("ed.undo", {}) in _items("Screen", "Z", ctrl=True), "Blender's Ctrl+Z kept"
    # Editor keymaps run first: nothing there may take plain z.
    for km in ("3D View", "View2D", "Image", "Node Editor", "Object Mode", "Mesh", "Outliner",
               "Graph Editor", "Dopesheet"):
        assert _items(km, "Z") == [], (km, _items(km, "Z"))


def _kmis(km, type, shift=False, ctrl=False, alt=False):
    km = kit.maya_kc().keymaps[km]
    return [k for k in km.keymap_items if k.active and k.type == type and k.value == 'PRESS'
            and k.shift == shift and k.ctrl == ctrl and k.alt == alt and not k.oskey]


def test_visibility_keys():
    want = {(False, False, False): "TOGGLE", (False, True, False): "HIDE",
            (False, False, True): "HIDE_UNSELECTED", (True, False, False): "SHOW_SELECTED",
            (True, True, False): "SHOW_LAST"}
    for km in ("Object Mode", "Outliner"):         # Outliner: Maya hides there with the same keys
        for (shift, ctrl, alt), action in want.items():
            got = _kmis(km, "H", shift=shift, ctrl=ctrl, alt=alt)
            assert [(k.idname, k.properties.action) for k in got] == [("allset.visibility", action)],                 (km, shift, ctrl, alt, [k.idname for k in got])
    alt_h = _kmis("Mesh", "H", alt=True)
    assert [k.idname for k in alt_h] == ["mesh.hide"] and alt_h[0].properties.unselected
    for mods in ({"shift": True}, {"ctrl": True, "shift": True}, {"ctrl": True, "alt": True}):
        assert [k.idname for k in _kmis("Mesh", "H", **mods)] == ["mesh.reveal"], mods


def test_isolate_and_invert_keys():
    got = _items("3D View", "ONE", ctrl=True)
    # allset.isolate = local view without framing (keeps the camera) with the selection's descendants
    assert [g[0] for g in got] == ["allset.isolate"], got
    assert _items("Mesh", "ONE", ctrl=True) == [], "Mesh Ctrl+1 vertex mode removed"
    assert [g[0] for g in _items("Object Mode", "I", ctrl=True, shift=True)] == ["object.select_all"]
    assert [g[0] for g in _items("Mesh", "I", ctrl=True, shift=True)] == ["mesh.select_all"]


# --- allset.visibility -------------------------------------------------------------

def _scene(names=("a", "b", "c")):
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o)
    obs = []
    for n in names:
        ob = bpy.data.objects.new(n, None)
        bpy.context.scene.collection.objects.link(ob)
        obs.append(ob)
    bpy.context.view_layer.update()
    return obs


def _select(*obs):
    for o in bpy.context.view_layer.objects:
        o.select_set(o in obs)
    if obs:
        bpy.context.view_layer.objects.active = obs[0]


def _vis(action):
    assert bpy.ops.allset.visibility(action=action) == {'FINISHED'}


def test_h_toggles_and_keeps_selection():
    a, b, c = _scene()
    _select(a, b)
    _vis('TOGGLE')
    assert a.hide_viewport and b.hide_viewport and not c.hide_viewport
    _vis('TOGGLE')   # nothing visible selected: the kept selection comes back, selected
    assert not a.hide_viewport and not b.hide_viewport
    assert a.select_get() and b.select_get() and not c.select_get()
    assert visibility.KEPT not in a and visibility.KEPT not in b


def test_h_new_selection_replaces_kept():
    a, b, c = _scene()
    _select(a)
    _vis('TOGGLE')
    _select(b)
    _vis('TOGGLE')          # hides b; a is no longer the kept selection
    _vis('TOGGLE')          # shows b only
    assert not b.hide_viewport and a.hide_viewport


def test_hide_show_last_and_selected():
    a, b, c = _scene()
    _select(a)
    _vis('HIDE')
    assert a.hide_viewport and not a.select_get()
    _select(b)
    _vis('HIDE_UNSELECTED')                 # hides c (a is already hidden)
    assert c.hide_viewport and not b.hide_viewport
    _vis('SHOW_LAST')                       # last hide = c only
    assert not c.hide_viewport and a.hide_viewport and c.select_get()
    bpy.context.view_layer.objects.active = a   # e.g. picked in the Outliner
    _vis('SHOW_SELECTED')
    assert not a.hide_viewport and a.select_get()


def test_show_selected_uses_kept():
    a, b, c = _scene()
    _select(a, b)
    _vis('TOGGLE')
    _select(c)
    _vis('SHOW_SELECTED')
    assert not a.hide_viewport and not b.hide_viewport


def test_outliner_visibility_keys():
    # #223: the Maya visibility keys work with the mouse over the Outliner
    want = {(False, False, False): "TOGGLE", (False, True, False): "HIDE",
            (False, False, True): "HIDE_UNSELECTED", (True, False, False): "SHOW_SELECTED",
            (True, True, False): "SHOW_LAST"}
    for (shift, ctrl, alt), action in want.items():
        got = _kmis("Outliner", "H", shift=shift, ctrl=ctrl, alt=alt)
        assert [(k.idname, k.properties.action) for k in got] == [("allset.visibility", action)], \
            (shift, ctrl, alt, [k.idname for k in got])


def test_group_hide_show_with_children():
    # #223: Ctrl+H on a group in the Outliner hides its children too (dag.sync);
    # Shift+H with the hidden row active shows the group and its children again
    grp, child, other = _scene(("group1", "pCube1", "pCube2"))
    child.parent = grp
    bpy.context.view_layer.update()
    _select(grp)
    _vis('HIDE')
    assert grp.hide_viewport and child.hide_get() and not other.hide_get()
    bpy.context.view_layer.objects.active = grp      # the hidden row clicked in the Outliner
    _vis('SHOW_SELECTED')
    assert not grp.hide_viewport and not child.hide_get()
