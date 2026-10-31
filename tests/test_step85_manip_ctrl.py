"""Manipulator Ctrl+LMB (Move: snapped drag of that handle, Scale axis: the other two), Ctrl+click centre =
free, Shift+MMB = closest axis.
GUI: tests/gui/gui_step85_manip_ctrl.py."""

from importlib import import_module

import bpy

import kit

manip = import_module(kit.MODULE + ".operators.manip")
patches = import_module(kit.MODULE + ".keymap.maya_patches")
manipulator = import_module(kit.MODULE + ".ui.manipulator")


def test_plane_of():
    assert manip.plane_of('X') == (False, True, True)
    assert manip.plane_of('Y') == (True, False, True)
    assert manip.plane_of('Z') == (True, True, False)
    planes = {v[0] for v in manipulator.PLANES.values()}       # each is a manipulator plane handle
    assert {manip.plane_of(a) for a in 'XYZ'} == planes


def test_pick_axis():
    dirs = [(50, -20), (30, 25), (0, 60)]        # a perspective view: X right-down, Y right-up, Z up
    assert manip.pick_axis((10, -4), dirs) == 0
    assert manip.pick_axis((-10, 4), dirs) == 0  # opposite direction: same axis
    assert manip.pick_axis((2, 30), dirs) == 2
    assert manip.pick_axis((12, 10), dirs) == 1
    assert manip.pick_axis((10, 0), [None, (0.0, 0.0), (0, 60)]) == 2   # axes pointing at the viewer skipped
    assert manip.pick_axis((0, 0), dirs) is None
    assert manip.pick_axis((5, 5), [None, None, None]) is None


def test_keymap_items():
    kc = kit.maya_kc()
    for km in patches.GIZMO_KEYMAPS:
        items = [k for k in kc.keymaps[km].keymap_items if k.active and k.type == 'LEFTMOUSE' and k.value == 'PRESS'
                 and k.ctrl and not k.shift and not k.alt]
        assert items and items[0].idname == "allset.manip_ctrl", (km, [k.idname for k in items])
    assert "allset.manip_ctrl" in patches.PASS_THROUGH_FIRST
    for km, _idname, mode in patches.MMB_TOOLS:
        found = [k for k in kc.keymaps[km].keymap_items if k.idname == "allset.manip_mmb_auto"
                 and k.type == 'MIDDLEMOUSE' and k.value == 'PRESS' and k.shift and not k.ctrl]
        assert (len(found) == 1 and found[0].properties.mode == mode) if mode != 'ROTATE' else not found, km


def test_ctrl_passes_through_without_a_gizmo():
    # background: no gizmo group in the context -> the event goes on to Blender's gizmo tweak
    assert manip._highlighted(bpy.context) is None


def test_handle_slots():
    assert {"handle_role", "handle_axis"} <= set(manipulator.ALLSET_GT_maya_handle.__slots__)
