"""The finest perspective grid step (and so X-hold grid snap) is one Maya unit.

Blender skips grid steps below 1 m in user perspective views and divides by scale_length,
so ``units.grid_scale`` = metres per display unit. The Maya Workflow Kit template has it on every 3D
view; Maya Units sets and restores it. The snap itself is
checked in tests/gui/gui_step25_grid_snap.py.
"""

from importlib import import_module
from pathlib import Path

import bpy

import kit

units = import_module(kit.MODULE + ".operators.units")


def _set(system, unit, scale):
    us = bpy.context.scene.unit_settings
    us.system, us.length_unit, us.scale_length = system, unit, scale


def test_grid_scale_per_unit_setting():
    for setting, want in ((('METRIC', 'CENTIMETERS', 1.0), 0.01),     # Maya Workflow Kit template
                          (('METRIC', 'CENTIMETERS', 0.01), 0.01),    # Maya Units
                          (('METRIC', 'METERS', 1.0), 1.0),           # factory
                          (('METRIC', 'MILLIMETERS', 1.0), 0.001),
                          (('NONE', 'ADAPTIVE', 1.0), 1.0)):
        _set(*setting)
        assert abs(units.grid_scale() - want) < 1e-9, (setting, units.grid_scale())
        if setting[0] != 'NONE':
            # finest perspective step in BU = grid_scale / scale_length = one Maya unit
            assert abs(units.grid_scale() / setting[2] - units.maya_unit()) < 1e-6, setting
    _set('METRIC', 'METERS', 1.0)


def test_template_views_have_cm_grid():
    path = Path(import_module(kit.MODULE).__file__).parent / "app_template" / "Maya_Workflow_Kit" / "startup.blend"
    bpy.ops.wm.open_mainfile(filepath=str(path))
    views = list(units._views())
    grids = [v.overlay.grid_scale for v in views]
    assert views and all(abs(g - 0.01) < 1e-6 for g in grids), grids
    units.apply_file(rescale_views=True)
    try:
        assert all(abs(v.overlay.grid_scale - 0.01) < 1e-6 for v in views)
    finally:
        units.restore_file()
    assert all(abs(v.overlay.grid_scale - 0.01) < 1e-6 for v in views)
    bpy.ops.wm.read_homefile()


def test_maya_units_sets_and_restores_grid_scale():
    views = list(units._views())
    before = [v.overlay.grid_scale for v in views]
    assert all(abs(b - 1.0) < 1e-6 for b in before), before
    units.apply_file()
    try:
        assert all(abs(v.overlay.grid_scale - 0.01) < 1e-6 for v in views)
    finally:
        units.restore_file()
    assert [v.overlay.grid_scale for v in views] == before
