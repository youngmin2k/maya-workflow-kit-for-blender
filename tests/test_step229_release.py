"""Release prep 0.5.0: Modify > Reorder Rotation keeps the orientation (Maya xform -roo -p), and the
Modify items mapped here are in the menu map."""

import bpy
from mathutils import Euler

import kit

from importlib import import_module


def test_reorder_rotation_keeps_orientation():
    mm = import_module(kit.MODULE + ".operators.modify_maya")
    bpy.ops.object.empty_add()
    ob = bpy.context.active_object
    ob.rotation_mode = 'XYZ'
    ob.rotation_euler = Euler((0.3, -0.7, 1.1), 'XYZ')
    before = ob.matrix_basis.to_3x3().copy()
    assert mm.reorder_rotation([ob], 'ZXY') == 1
    assert ob.rotation_mode == 'ZXY'
    after = ob.rotation_euler.to_matrix()
    err = max(abs(before[i][j] - after[i][j]) for i in range(3) for j in range(3))
    assert err < 1e-6, (err, tuple(ob.rotation_euler), [tuple(r) for r in before], [tuple(r) for r in after])
    assert mm.reorder_rotation([ob], 'ZXY') == 0
    assert bpy.ops.allset.reorder_rotation('EXEC_DEFAULT', order='YZX') == {'FINISHED'}
    assert ob.rotation_mode == 'YZX'


def test_modify_items_mapped():
    menu_map = import_module(kit.MODULE + ".ui.menu_map")
    assert menu_map.MAP["Modify/Reorder Rotation..."] == "allset.reorder_rotation"
    assert menu_map.MAP["Modify/Paint Attributes Tool"] == "paint.weight_paint_toggle"
