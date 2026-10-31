"""Maya view furniture maths (ViewCube projection / hit test / face -> view axis, labels, sizes,
layout) and the Maya Workflow Kit template flags (Blender navigation gizmo and text info off)."""

import math
from importlib import import_module

import bpy
from mathutils import Vector

import kit

vf = import_module(kit.MODULE + ".ui.view_furniture")
app_template = import_module(kit.MODULE + ".app_template")


def _q(direction):
    return Vector(direction).normalized().to_track_quat('-Z', 'Y')


def test_maya_persp_shows_front_right_top_and_box_is_65px():
    q = _q(vf.MAYA_PERSP_DIR)
    faces = vf.faces_2d(q, (0.0, 0.0), 65.0)
    assert sorted(f[0] for f in faces) == ["FRONT", "RIGHT", "TOP"], [f[0] for f in faces]
    xs = [p[0] for f in faces for p in f[1]]
    ys = [p[1] for f in faces for p in f[1]]
    assert abs(max(max(xs) - min(xs), max(ys) - min(ys)) - 65.0) < 0.5
    # FRONT is on the left, RIGHT on the right
    cx = {f[0]: sum(p[0] for p in f[1]) / 4 for f in faces}
    assert cx["FRONT"] < 0 < cx["RIGHT"]


def test_hit_face_and_top_view_shows_top_only():
    q = _q(vf.MAYA_PERSP_DIR)
    faces = vf.faces_2d(q, (100.0, 100.0), 65.0)
    for name, poly, *_r in faces:
        cx, cy = sum(p[0] for p in poly) / 4, sum(p[1] for p in poly) / 4
        assert vf.hit_face(faces, cx, cy) == name
    assert vf.hit_face(faces, 0.0, 0.0) is None
    top = vf.faces_2d(_q((0, 0, -1)), (0.0, 0.0), 65.0)
    assert [f[0] for f in top] == ["TOP"]
    # each face is a valid view3d.view_axis type
    types = {i.identifier for i in bpy.ops.view3d.view_axis.get_rna_type().properties["type"].enum_items}
    assert set(vf.FACE_NAMES) <= types


def test_labels():
    assert vf.label_for('PERSP', False, (0.5, 0.5, -0.7)) == "persp"
    assert vf.label_for('ORTHO', False, (0.5, 0.5, -0.7)) == "persp"
    assert vf.label_for('ORTHO', True, (0.0, 0.0, -1.0)) == "top -Y"
    assert vf.label_for('ORTHO', True, (0.0, 1.0, 0.0)) == "front -Z"
    assert vf.label_for('ORTHO', True, (-1.0, 0.0, 0.0)) == "side -X"
    assert vf.label_for('CAMERA', False, (0, 0, -1), "camera1") == "camera1"


def test_sizes_and_layout_match_maya():
    assert abs(vf.cube_size(1001, 612) - 65.0) < 1e-6
    assert abs(vf.cube_size(497, 300) - 48.0) < 1.5          # four-view panel: 48 px
    assert abs(vf.cube_size(1001 * 1.25, 612 * 1.25, 1.25) - 65.0 * 1.25) < 1e-6
    # a view at (315, 172, 1001, 612) in image coords -> region-local bounds (0, 0, 1001, 612)
    cube, label, triad = vf.layout((0, 0, 1001, 612), 1.0, 65.0)
    assert cube == (1001 - 26 - 32.5, 612 - 27 - 32.5)       # box 26 px from the right, 27 from the top
    assert label == (500.5 - 9, 9) and triad == (26, 26)


def test_triad_axes_follow_view():
    ends = {i: e for i, e, _d in vf.triad(_q((0, 0, -1)), (0.0, 0.0), 13.0)}
    assert abs(ends[0][0] - 13) < 1e-6 and abs(ends[1][1] - 13) < 1e-6   # top view: x right, y up
    assert math.hypot(*ends[2]) < 1e-6                                   # z towards the viewer


def test_template_views_are_maya_views():
    import os
    bpy.ops.wm.open_mainfile(filepath=os.path.join(app_template.SOURCE_DIR, "startup.blend"))
    try:
        views = [sp for sc in bpy.data.screens for a in sc.areas for sp in a.spaces if sp.type == 'VIEW_3D']
        bad = [(sp.show_gizmo_navigate, sp.overlay.show_text) for sp in views
               if sp.show_gizmo_navigate or sp.overlay.show_text]
        assert views and not bad, bad
        # (one of Blender's own workspace views has overlays off: it shows no furniture at all)
        assert all(vf.maya_view(sp) for sp in views if sp.overlay.show_overlays)
    finally:
        bpy.ops.wm.read_homefile()


def test_registration_and_hud_menu():
    prefs = bpy.context.preferences.addons[kit.MODULE].preferences
    assert prefs.maya_viewcube and prefs.maya_camera_names and prefs.maya_view_axis
    menu_map = import_module(kit.MODULE + ".ui.menu_map")
    for item in ("Camera Names", "View Axis", "ViewCube"):   # Maya 2026 label
        entry = menu_map.MAP["Display/Heads Up Display/" + item]
        assert entry[0] == "wm.context_toggle" and kit.MODULE in entry[1]["data_path"], entry
    assert vf._handle
    kit.disable()
    try:
        assert not vf._handle
    finally:
        kit.enable()
