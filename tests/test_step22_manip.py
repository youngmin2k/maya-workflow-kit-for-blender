"""Shift+drag a manipulator = Maya Smart Duplicate.

The Maya keyconfig puts ``allset.manip_duplicate`` (Shift+LMB press, PASS_THROUGH)
in front of the gizmo's own tweak; the operator duplicates only in object mode with a
selection, the option on and the transform gizmo shown. The drag itself is checked in
tests/gui/gui_step22_manip_duplicate.py.
"""

from importlib import import_module

import bpy

import kit

manip = import_module(kit.MODULE + ".operators.manip")
patches = import_module(kit.MODULE + ".keymap.maya_patches")
preferences = import_module(kit.MODULE + ".preferences")
mm = import_module(kit.MODULE + ".marking.menus")


def _fresh():
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    bpy.ops.mesh.primitive_cube_add()
    ob = bpy.context.view_layer.objects.active
    ob.name, ob.data.name = "pCube1", "pCubeShape1"
    return ob


def test_gizmo_keymaps_run_smart_duplicate_first():
    kc = kit.maya_kc()
    for name in patches.GIZMO_KEYMAPS:
        items = [k for k in kc.keymaps[name].keymap_items if k.active]
        ids = [k.idname for k in items]
        dup = items[ids.index("allset.manip_duplicate")]
        assert (dup.type, dup.value, dup.shift, dup.ctrl, dup.alt) == \
            ('LEFTMOUSE', 'PRESS', True, False, False), name
        # manip_press (plain LMB) is in front too; both before the gizmo's tweak
        assert ids.index("allset.manip_duplicate") < ids.index("gizmogroup.gizmo_tweak"), (name, ids)
    assert "allset.manip_duplicate" in patches.PASS_THROUGH_FIRST


def test_gizmo_tweak_takes_shift_drag():
    # #175: a CLICK_DRAG carries the press's modifiers, so the gizmo's tweak must accept
    # Shift or the Shift+drag that manip_duplicate passes on starts no transform. Ctrl too (a drag started with
    # Ctrl held moves the handle with snapping); Alt as IC.
    kc = kit.maya_kc()
    for name in patches.GIZMO_KEYMAPS:
        tweaks = [k for k in kc.keymaps[name].keymap_items if k.active
                  and k.idname == "gizmogroup.gizmo_tweak" and k.type == 'LEFTMOUSE' and k.value == 'CLICK_DRAG']
        assert tweaks, name
        for k in tweaks:
            assert (k.shift, k.ctrl, k.alt) == (-1, -1, 0), (name, k.shift, k.ctrl, k.alt)


def test_shift_precision_kept():
    # Shift held when the drag starts doesn't turn precision on, so Blender's
    # Shift precision during a drag stays.
    km = kit.maya_kc().keymaps["Transform Modal Map"]
    assert {k.type for k in km.keymap_items if k.propvalue == 'PRECISION'} == {'LEFT_SHIFT', 'RIGHT_SHIFT'}


def _run():
    n = len(bpy.data.objects)
    res = bpy.ops.allset.manip_duplicate()
    assert res == {'PASS_THROUGH'}, res
    return len(bpy.data.objects) - n


def test_duplicates_only_when_it_applies():
    shown = manip.from_xform_gizmo
    manip.from_xform_gizmo = lambda _context: True
    prefs = preferences.get()
    try:
        ob = _fresh()
        assert _run() == 1
        copy = bpy.context.view_layer.objects.active
        assert copy.name == "pCube2" and copy.data.name == "pCubeShape2" and not ob.select_get()
        assert (copy.matrix_world.translation - ob.matrix_world.translation).length < 1e-6

        prefs.smart_duplicate = False
        assert _run() == 0, "option off"
        prefs.smart_duplicate = True

        for o in bpy.context.view_layer.objects:
            o.select_set(False)
        assert _run() == 0, "nothing selected"

        copy.select_set(True)
        bpy.ops.object.mode_set(mode='EDIT')
        assert _run() == 0, "edit mode: Smart Extrude, no new object"
        bpy.ops.object.mode_set(mode='OBJECT')

        manip.from_xform_gizmo = lambda _context: False
        assert _run() == 0, "not the transform manipulator (light gizmo, ...)"
    finally:
        manip.from_xform_gizmo = shown
        prefs.smart_duplicate = True


def test_hold_menus_toggle_smart_duplicate():
    for menu in (mm.OPT_MOVE, mm.OPT_ROTATE, mm.OPT_SCALE):
        items = dict(i for i in menu.items if i != mm.DIVIDER)
        assert items["Shift Duplicate"] == ("allset.manip_option", {"option": 'SMART_DUPLICATE'}), menu
        assert items["Shift Extrude"] == ("allset.manip_option", {"option": 'SMART_EXTRUDE'}), menu
    prefs = preferences.get()
    assert prefs.smart_duplicate is True, "on by default"
    bpy.ops.allset.manip_option(option='SMART_DUPLICATE')
    assert prefs.smart_duplicate is False
    bpy.ops.allset.manip_option(option='SMART_DUPLICATE')
    assert prefs.smart_duplicate is True
