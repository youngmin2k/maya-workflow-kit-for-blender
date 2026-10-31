"""Maya grid — finite 12 units, a line every unit, thicker every 5, axes (Maya
grid metrics), drawn by the kit in the views that use it; projection maths checked against Blender's."""

import math
import os
from importlib import import_module

import bpy
from mathutils import Matrix, Vector

import kit

grid = import_module(kit.MODULE + ".ui.maya_grid")
app_template = import_module(kit.MODULE + ".app_template")


def test_segments_are_maya_grid():
    segs = grid.segments()
    # per direction: axis 1, majors at +-5 / +-10 = 4, minors 25 - 5 = 20
    assert len(segs["axis"]) == 2 and len(segs["major"]) == 8 and len(segs["minor"]) == 40, \
        {k: len(v) for k, v in segs.items()}
    ends = [c for lines in segs.values() for line in lines for p in line for c in p]
    assert min(ends) == -12 and max(ends) == 12
    majors = sorted({line[0][0] for line in segs["major"] if line[0][1] == -12})
    assert majors == [-10, -5, 5, 10], majors
    minors = sorted({line[0][0] for line in segs["minor"] if line[0][1] == -12})
    assert -12 in minors and 12 in minors and 1 in minors and 5 not in minors


def test_plane_points_and_view_planes():
    segs = grid.segments()["axis"]
    unit = 0.01
    pts = grid.plane_points(segs, "FLOOR", unit)
    assert all(abs(p[2]) < 1e-12 for p in pts) and max(abs(p[0]) for p in pts) == 12 * unit
    assert all(p[1] == 0.0 for p in grid.plane_points(segs, "XZ", unit))
    assert all(p[0] == 0.0 for p in grid.plane_points(segs, "YZ", unit))
    assert grid.plane_for_view('PERSP', False, (0.3, 0.5, -0.8)) == "FLOOR"
    assert grid.plane_for_view('ORTHO', True, (0.0, 0.0, -1.0)) == "FLOOR"   # top
    # Maya's front / side cameras grid their own plane
    assert grid.plane_for_view('ORTHO', True, (0.0, 1.0, 0.0)) == "XZ"       # front (looks +Y)
    assert grid.plane_for_view('ORTHO', True, (-1.0, 0.0, 0.0)) == "YZ"      # right
    assert grid.plane_for_view('ORTHO', False, (0.0, 1.0, 0.0)) == "FLOOR"   # user ortho


class _Region:
    def __init__(self, w, h):
        self.width, self.height = w, h


class _RV3D:
    def __init__(self, m):
        self.perspective_matrix = m


def _persp(w, h, eye, lens=35.0):
    eye = Vector(eye)
    rot = eye.normalized().to_track_quat('Z', 'Y').to_matrix().to_4x4()
    viewm = (Matrix.Translation(eye) @ rot).inverted()
    f = lens / 18.0                          # 36 mm sensor width
    near, far = 0.001, 100.0
    proj = Matrix(((f, 0, 0, 0), (0, f * w / h, 0, 0),
                   (0, 0, (far + near) / (near - far), 2 * far * near / (near - far)), (0, 0, -1, 0)))
    return proj @ viewm


def test_corner_projection_matches_blender_within_1px():
    from bpy_extras.view3d_utils import location_3d_to_region_2d
    w, h = 1003, 653                          # Maya MainPane
    unit = 0.01
    for m in (_persp(w, h, (0.28, -0.28, 0.21)),
              Matrix.Scale(1 / 0.2, 4) @ Matrix.Rotation(math.radians(-90), 4, 'X')):
        for c in grid.corners("FLOOR", unit) + grid.corners("XZ", unit):
            ours = grid.project(m, c, w, h)
            ref = location_3d_to_region_2d(_Region(w, h), _RV3D(m), Vector(c))
            if ref is None:
                assert ours is None
                continue
            assert abs(ours[0] - ref.x) <= 1 and abs(ours[1] - ref.y) <= 1, (c, ours, tuple(ref))
    # the grid edge is 12 units out: corner (12, 12) at unit 0.01 = (0.12, 0.12, 0)
    assert grid.corners("FLOOR", unit)[2] == (0.12, 0.12, 0.0)


def _space():
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type == 'VIEW_3D':
                return area.spaces.active
    raise AssertionError("no 3D view")


def test_state_toggle():
    space = _space()
    ov = space.overlay
    ov.show_floor, ov.grid_lines = True, 16
    assert grid.visible(space) and not grid.is_on(space)
    assert grid.toggle(space) is False                    # Blender floor shown -> grid off
    assert not grid.visible(space) and ov.grid_lines == grid.OFF_LINES
    assert grid.toggle(space) is True                     # nothing shown -> Maya grid
    assert grid.is_on(space) and not ov.show_floor and not ov.show_ortho_grid
    assert not ov.show_axis_x and not ov.show_axis_y
    grid.set_grid(space, False)
    ov.show_floor = True


def test_template_views_use_maya_grid():
    path = os.path.join(app_template.SOURCE_DIR, "startup.blend")
    bpy.ops.wm.open_mainfile(filepath=path)
    try:
        views = [sp for sc in bpy.data.screens for a in sc.areas for sp in a.spaces if sp.type == 'VIEW_3D']
        assert views
        bad = [(sp.overlay.show_floor, sp.overlay.show_ortho_grid, sp.overlay.grid_lines)
               for sp in views if not grid.is_on(sp)]
        assert not bad, bad
        # X-hold snap step (Blender's finest perspective grid step) stays one Maya unit
        assert all(abs(sp.overlay.grid_scale - 0.01) < 1e-9 for sp in views)
    finally:
        bpy.ops.wm.read_homefile()


def test_draw_handler_removed_on_disable():
    assert grid._handle
    mod = grid
    kit.disable()
    try:
        assert not mod._handle
        assert "toggle_grid" not in dir(bpy.ops.allset)
    finally:
        kit.enable()


def test_ortho_grid_fills_the_view():
    # Maya's ortho cameras grid the whole panel (16_four_view.png: ~31 units across, lines edge to edge)
    assert grid.fills_view('ORTHO', True) and not grid.fills_view('ORTHO', False)
    assert not grid.fills_view('PERSP', False)
    segs = grid.span_segments((-20.0, 20.0), (-3.0, 7.0), 5, 5)
    us = sorted({a[0] for a, b in segs["minor"] + segs["major"] + segs["axis"] if a[0] == b[0]})
    assert us[0] == -20.0 and us[-1] == 20.0 and len(us) == 41          # beyond the ±12 of the ground grid
    assert all(a[1] == -3.0 and b[1] == 7.0 for a, b in segs["axis"] if a[0] == b[0])
    assert ((0.0, -3.0), (0.0, 7.0)) in segs["axis"] and ((5.0, -3.0), (5.0, 7.0)) in segs["major"]
    lo, hi = grid.view_span(1.3, 15.0, 8.0)
    assert lo <= 1.3 - 15.0 and hi >= 1.3 + 15.0 and lo % 8 == 0 and hi % 8 == 0
