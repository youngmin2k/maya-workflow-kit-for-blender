"""Display > Toggle Show/Hide ❒ and Edit > Delete by Type > Non-Deformer History ❒ open Maya's option
windows again (they fell to the generic "Blender has no settings" window before); results follow the
Maya results."""

from importlib import import_module

import bpy

import kit

menu_sets = import_module(kit.MODULE + ".ui.menu_sets")
ow = import_module(kit.MODULE + ".operators.option_windows")
visibility = import_module(kit.MODULE + ".operators.visibility")

TOGGLE = "Display/Toggle Show/Hide"
NONDEF = "Edit/Delete by Type/Non-Deformer History"


def _fresh():
    if bpy.context.object is not None and bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    ow.store(visibility.TOGGLE_KEY, {"first_selection": "Independent"})


def _cube(name):
    me = bpy.data.meshes.new(name)
    me.from_pydata([(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)], [], [(0, 1, 2, 3)])
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def _abc(hidden):
    """a, b, c all selected (c = lead); the ``hidden`` ones hidden but kept selected (Maya: hidden while selected)."""
    _fresh()
    obs = [_cube(n) for n in "abc"]
    for ob in obs:
        ob.select_set(True)
    bpy.context.view_layer.objects.active = obs[2]          # c = lead; Maya's first = a
    for ob in obs:
        if ob.name in hidden:
            ob.select_set(False)
            ob.hide_viewport = True
            ob[visibility.KEPT] = True
    return obs


def _shown(obs):
    return [not ob.hide_viewport for ob in obs]


def test_both_boxes_are_maya_windows():
    for path, key, title in ((TOGGLE, "toggle_show_hide", "Toggle Visibility Options"),
                             (NONDEF, "non_deformer_history", "Delete Non Deformer History Options")):
        assert menu_sets.option_kind(path) == "window", (path, menu_sets.option_kind(path))
        w = ow.find_path(path)
        assert w is not None and w.key == key and w.title == title, (path, w and w.key)
    toggle = ow.find_path(TOGGLE)
    assert toggle.action == "Apply and Close" and toggle.defaults() == {"first_selection": "Independent"}
    nondef = ow.find_path(NONDEF)
    assert nondef.action == "Delete" and nondef.defaults() == {"delete": "All non-deformer history"}


def test_toggle_independent_flips_each():
    # Maya: (hidden, shown, shown) -> (shown, hidden, hidden)
    obs = _abc({"a"})
    bpy.ops.allset.visibility(action='TOGGLE', behaviour='INDEPENDENT')
    assert _shown(obs) == [True, False, False], _shown(obs)
    assert all(ob.select_get() or visibility.KEPT in ob for ob in obs), "selection kept"


def test_toggle_dependent_follows_the_first():
    # Maya: (hidden, shown, shown) -> all shown (the opposite of the first selected a)
    obs = _abc({"a"})
    bpy.ops.allset.visibility(action='TOGGLE', behaviour='DEPENDENT')
    assert _shown(obs) == [True, True, True], _shown(obs)
    obs = _abc({"b"})
    bpy.ops.allset.visibility(action='TOGGLE', behaviour='DEPENDENT')
    assert _shown(obs) == [False, False, False], _shown(obs)


def test_saved_window_value_drives_h_and_the_menu():
    obs = _abc({"a"})
    ow.store(visibility.TOGGLE_KEY, {"first_selection": "Dependent"})
    bpy.ops.allset.visibility(action='TOGGLE')                 # h: the saved First Selection
    assert _shown(obs) == [True, True, True], _shown(obs)
    obs = _abc({"a"})
    ow.run(ow.find_path(TOGGLE), bpy.context, {"first_selection": "Independent"})
    assert _shown(obs) == [True, False, False], _shown(obs)
    ow.store(visibility.TOGGLE_KEY, {"first_selection": "Independent"})


def _history_cube():
    _fresh()
    ob = _cube("pCube1")
    ob.modifiers.new("polyExtrudeFace1", 'SOLIDIFY')
    ob.modifiers.new("bend1", 'SIMPLE_DEFORM')
    ob.modifiers.new("polyBevel1", 'BEVEL')
    for o in bpy.context.scene.objects:
        o.select_set(o == ob)
    bpy.context.view_layer.objects.active = ob
    return ob


def test_non_deformer_history_all_and_before_only():
    # Maya: polyCube -> extrude -> bend -> bevel: All keeps only bend; before only keeps bend + bevel
    ob = _history_cube()
    w = ow.find_path(NONDEF)
    ow.run(w, bpy.context, {"delete": "History before deformers only"})
    assert [m.name for m in ob.modifiers] == ["bend1", "polyBevel1"], [m.name for m in ob.modifiers]
    ob = _history_cube()
    n0 = len(ob.data.vertices)
    ow.run(w, bpy.context, {"delete": "All non-deformer history"})
    assert [m.name for m in ob.modifiers] == ["bend1"], [m.name for m in ob.modifiers]
    assert len(ob.data.vertices) > n0, "solidify + bevel baked into the mesh"
