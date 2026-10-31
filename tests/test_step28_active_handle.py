"""MMB drag = the last picked manipulator handle (Maya active handle).
The drag itself: tests/gui/gui_step28_active_handle.py."""

from importlib import import_module
from types import SimpleNamespace

import bpy

import kit

manip = import_module(kit.MODULE + ".operators.manip")
patches = import_module(kit.MODULE + ".keymap.maya_patches")


def _props(axes, orient='GLOBAL', axis='Z'):
    return SimpleNamespace(constraint_axis=axes, orient_type=orient, orient_axis=axis)


def test_handle_from_registered_transform():
    kind, h = manip.handle_from_op("TRANSFORM_OT_translate", _props((True, False, False)))
    assert kind == 'TRANSLATE' and h == {"constraint_axis": (True, False, False), "orient_type": 'GLOBAL'}
    kind, h = manip.handle_from_op("TRANSFORM_OT_translate", _props((True, True, False), 'LOCAL'))
    assert h["constraint_axis"] == (True, True, False) and h["orient_type"] == 'LOCAL', "plane handle"
    assert manip.handle_from_op("TRANSFORM_OT_translate", _props((False, False, False))) == \
        ('TRANSLATE', None), "centre = free"
    kind, h = manip.handle_from_op("TRANSFORM_OT_rotate", _props((False, False, True), axis='Z'))
    assert kind == 'ROTATE' and h["orient_axis"] == 'Z'
    assert manip.handle_from_op("TRANSFORM_OT_rotate", _props((False, False, False), axis='VIEW')) == \
        ('ROTATE', None), "view ring = free"
    kind, h = manip.handle_from_op("TRANSFORM_OT_resize", _props((False, True, False)))
    assert kind == 'RESIZE' and h["constraint_axis"] == (False, True, False)
    assert manip.handle_from_op("TRANSFORM_OT_trackball", _props((False,) * 3)) == (None, None)


def test_reset():
    manip.HANDLES['TRANSLATE'] = {"constraint_axis": (True, False, False), "orient_type": 'GLOBAL'}
    manip.reset_handle('TRANSLATE')
    assert 'TRANSLATE' not in manip.HANDLES


def test_keymaps():
    kc = kit.maya_kc()
    for name in patches.GIZMO_KEYMAPS:
        # the kit puts its Ctrl+LMB item in front; the first plain item is still the handle press
        items = [k for k in kc.keymaps[name].keymap_items if k.active and not k.ctrl]
        first = items[0]
        assert (first.idname, first.type, first.value, first.shift) == \
            ("allset.manip_press", 'LEFTMOUSE', 'PRESS', False), name
    for km, _idname, mode in patches.MMB_TOOLS:
        # the emulated Alt+LMB tumble (#242) leads every MMB list and passes through otherwise
        mmb = [k for k in kc.keymaps[km].keymap_items if k.active and k.type == 'MIDDLEMOUSE' and not k.shift
               and k.idname != "allset.emulated_tumble"]
        assert [k.idname for k in mmb] == ["allset.cb_virtual_slider", "allset.manip_mmb"], (km, mmb)
        assert mmb[1].properties.mode == mode
    assert "allset.manip_press" in patches.PASS_THROUGH_FIRST


def test_mmb_without_selection_passes():
    for ob in list(bpy.data.objects):
        ob.select_set(False)
    # no 3D view in background mode: poll fails, nothing happens
    assert not bpy.ops.allset.manip_mmb.poll()
