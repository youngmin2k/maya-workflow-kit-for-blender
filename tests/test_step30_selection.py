"""Selection feel — marquee select-through keymap items, the X-ray watch, the
pre-selection gizmo group, Blender's undo steps left alone.

Box/lasso through hidden vertices and the highlight are checked in tests/gui/gui_step30_selection.py.
"""

import types
from importlib import import_module

import bpy

import kit

patches = import_module(kit.MODULE + ".keymap.maya_patches")
marquee = import_module(kit.MODULE + ".operators.marquee")
preselect = import_module(kit.MODULE + ".operators.preselect")
preferences = import_module(kit.MODULE + ".preferences")


def test_select_through_items_lead_box_and_lasso():
    kc = kit.maya_kc()
    assert "allset.select_through" in patches.PASS_THROUGH_FIRST
    for km_name in patches.SELECT_DRAG_KEYMAPS:
        items = [k for k in kc.keymaps[km_name].keymap_items if k.active]
        target = "view3d.select_lasso" if "Lasso" in km_name else "view3d.select_box"
        for shift in (False, True):
            for ctrl in (False, True):
                same = [k.idname for k in items if k.type == 'LEFTMOUSE' and k.value == 'CLICK_DRAG'
                        and k.shift == shift and k.ctrl == ctrl and not k.alt]
                # other kit PASS_THROUGH items may sit between (allset.uv_shell_box)
                rest = [i for i in same[1:] if i not in patches.PASS_THROUGH_FIRST]
                assert same[0] == "allset.select_through" and rest[:1] == [target], (km_name, shift, ctrl, same)


def _fake_entry(running):
    shading = types.SimpleNamespace(show_xray=True, xray_alpha=1.0)
    space = types.SimpleNamespace(shading=shading)
    window = types.SimpleNamespace(modal_operators=[types.SimpleNamespace(bl_idname="VIEW3D_OT_select_box")]
                                   if running else [])
    # entries hold pointers (#36): resolve the fake ones through the lookup hooks
    _FAKES[id(space)], _FAKES[id(window)] = space, window
    return shading, window, [id(space), id(window), "show_xray", "xray_alpha", 0.5, False, 0.0]


_FAKES = {}


def test_watch_restores_after_the_select_modal():
    saved = marquee._lookup_space, marquee._lookup_window
    marquee._lookup_space = lambda sp, _wp: _FAKES.get(sp)
    marquee._lookup_window = _FAKES.get
    try:
        _watch_restores()
    finally:
        marquee._lookup_space, marquee._lookup_window = saved
        _FAKES.clear()


def _watch_restores():
    shading, window, entry = _fake_entry(running=True)
    marquee._active.clear()
    marquee._active[1] = entry
    assert marquee._watch() is not None and shading.show_xray, "still dragging"
    window.modal_operators.clear()
    assert marquee._watch() is None, "nothing left to watch"
    assert shading.show_xray is False and shading.xray_alpha == 0.5
    # Never saw the modal (e.g. the drag was taken by something else): restore after a second.
    shading, window, entry = _fake_entry(running=False)
    marquee._active[2] = entry
    for _ in range(int(marquee._GIVE_UP / marquee._TICK) + 1):
        if marquee._watch() is None:
            break
    assert shading.show_xray is False and not marquee._active


def test_select_through_needs_edit_mesh_and_option():
    # Headless: no 3D View space; begin() must refuse quietly.
    assert marquee.begin(bpy.context) is False
    assert bpy.ops.allset.select_through.poll()


def test_preselect_group_registered_and_polls_off():
    assert "bl_rna" in preselect.ALLSET_GGT_preselect.__dict__, "registered"
    assert preferences.get().preselect_highlight is True
    assert preselect._enabled(bpy.context) is False, "object mode"


def test_undo_steps_left_alone():
    """The kit sets no undo preset: Blender's value stays."""
    prefs = bpy.context.preferences
    default = type(prefs.edit).bl_rna.properties["undo_steps"].default
    assert prefs.edit.undo_steps == default, prefs.edit.undo_steps
    assert not hasattr(preferences.get(), "use_maya_undo")
