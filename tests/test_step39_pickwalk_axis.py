"""Edit-mode component pick-walk (arrow keys) and Alt+Shift axis-locked tumble/track.
"""

import math
from importlib import import_module

import bmesh
import bpy
from mathutils import Quaternion, Vector

import kit

pw = import_module(kit.MODULE + ".operators.pickwalk")
view = import_module(kit.MODULE + ".operators.view")
km = import_module(kit.MODULE + ".keymap")


def front(p):
    return p.x, p.z


def _grid():
    """5 x 5 vertex grid in the XZ plane (front view), spacing 0.5, centred on the origin."""
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    bpy.ops.mesh.primitive_grid_add(x_subdivisions=4, y_subdivisions=4, size=2)
    ob = bpy.context.active_object
    for v in ob.data.vertices:
        v.co = (v.co.x, 0.0, v.co.y)
    bpy.ops.object.mode_set(mode='EDIT')
    return ob


def _bm(ob):
    return bmesh.from_edit_mesh(ob.data)


def _at(seq, x, z):
    return next(e for e in seq if abs(pw.centre(e).x - x) < 1e-4 and abs(pw.centre(e).z - z) < 1e-4)


def _xz(e):
    c = pw.centre(e)
    return round(c.x, 3), round(c.z, 3)


def test_vertex_walk_follows_screen_direction():
    bm = _bm(_grid())
    v = _at(bm.verts, 0, 0)
    assert _xz(pw.step_component(v, "RIGHT", front)) == (0.5, 0)
    assert _xz(pw.step_component(v, "LEFT", front)) == (-0.5, 0)
    assert _xz(pw.step_component(v, "UP", front)) == (0, 0.5)
    assert _xz(pw.step_component(v, "DOWN", front)) == (0, -0.5)
    corner = _at(bm.verts, 1, 1)
    assert pw.step_component(corner, "RIGHT", front) is corner, "no neighbour that way: stay"


def test_face_walk_follows_screen_direction():
    bm = _bm(_grid())
    f = _at(bm.faces, 0.25, 0.25)
    assert _xz(pw.step_component(f, "RIGHT", front)) == (0.75, 0.25)
    assert _xz(pw.step_component(f, "UP", front)) == (0.25, 0.75)
    assert _xz(pw.step_component(f, "LEFT", front)) == (-0.25, 0.25)
    assert _xz(pw.step_component(f, "DOWN", front)) == (0.25, -0.25)


def test_edge_walk_loop_and_ring():
    bm = _bm(_grid())
    e = _at(bm.edges, 0.25, 0)                   # horizontal edge right of the centre
    assert _xz(pw.step_component(e, "RIGHT", front)) == (0.75, 0)    # loop
    assert _xz(pw.step_component(e, "LEFT", front)) == (-0.25, 0)
    assert _xz(pw.step_component(e, "UP", front)) == (0.25, 0.5)     # ring
    assert _xz(pw.step_component(e, "DOWN", front)) == (0.25, -0.5)
    vert = _at(bm.edges, 0, 0.25)                # vertical edge: Up/Down still = ring (sideways)
    ring = {_xz(pw.step_component(vert, d, front)) for d in ("UP", "DOWN")}
    assert ring <= {(0.5, 0.25), (-0.5, 0.25)}, ring
    assert _xz(pw.step_component(vert, "UP", front)) != _xz(vert)
    border = _at(bm.edges, 0.25, -1)             # bottom border: nothing below
    assert pw.step_component(border, "DOWN", front) is border
    assert _xz(pw.step_component(border, "UP", front)) == (0.25, -0.5)


def test_operator_walks_selection_and_active():
    ob = _grid()
    bpy.ops.mesh.select_mode(type='VERT')
    bpy.ops.mesh.select_all(action='DESELECT')
    bm = _bm(ob)
    a, b = _at(bm.verts, 0, 0), _at(bm.verts, -0.5, -0.5)
    a.select_set(True)
    b.select_set(True)
    bm.select_history.add(a)
    bmesh.update_edit_mesh(ob.data)
    bpy.ops.allset.pick_walk_component(direction='RIGHT')   # headless: front projection
    bm = _bm(ob)
    sel = sorted(_xz(v) for v in bm.verts if v.select)
    assert sel == [(0, -0.5), (0.5, 0)], sel
    assert _xz(bm.select_history.active) == (0.5, 0)
    bpy.ops.mesh.select_mode(type='FACE')
    bpy.ops.mesh.select_all(action='DESELECT')
    bm = _bm(ob)
    _at(bm.faces, 0.25, 0.25).select_set(True)
    bmesh.update_edit_mesh(ob.data)
    bpy.ops.allset.pick_walk_component(direction='UP')
    bm = _bm(ob)
    assert [_xz(f) for f in bm.faces if f.select] == [(0.25, 0.75)]


def test_axis_choice_and_locked_offsets():
    assert view.choose_axis(2, 1) is None
    assert view.choose_axis(10, 6) == 'H' and view.choose_axis(3, -9) == 'V'
    assert view.locked_offset('H', 10, 6) == (10, 0) and view.locked_offset('V', 10, 6) == (0, 6)
    rot0 = Quaternion((1, 0, 0), math.radians(60))       # looking down at an angle
    h = view.tumble_rotation('H', 50, 0, rot0, 0.01)
    # horizontal: turntable about world Z, the view's tilt (angle to Z) is kept
    z = Vector((0, 0, 1))
    assert abs((h @ Vector((0, 0, 1))).angle(z) - (rot0 @ Vector((0, 0, 1))).angle(z)) < 1e-6
    v = view.tumble_rotation('V', 0, 50, rot0, 0.01)
    # vertical: about the view's right axis, which stays put
    right0 = rot0 @ Vector((1, 0, 0))
    assert ((v @ Vector((1, 0, 0))) - right0).length < 1e-6
    assert abs(v.rotation_difference(rot0).angle - 0.5) < 1e-6


def test_keymap_items():
    data = km.generate_data()
    items = {k[0]: k[2]["items"] for k in data}
    mesh = [(i[0], i[1]["type"], dict(i[2]["properties"]) if i[2] else {}) for i in items["Mesh"]]
    for key, d in (("UP_ARROW", "UP"), ("DOWN_ARROW", "DOWN"), ("LEFT_ARROW", "LEFT"), ("RIGHT_ARROW", "RIGHT")):
        assert ("allset.pick_walk_component", key, {"direction": d}) in mesh, key
    assert not any(i[0] in ("mesh.select_more", "mesh.select_less") and i[1] in ("UP_ARROW", "DOWN_ARROW")
                   for i in mesh)
    v3d = [(i[0], i[1]["type"], i[1].get("shift"), i[1].get("alt"), i[1].get("ctrl"),
            dict(i[2]["properties"]) if i[2] else {}) for i in items["3D View"]]
    assert ("allset.view_axis_lock", "LEFTMOUSE", True, True, None, {"mode": "TUMBLE"}) in v3d
    assert ("allset.view_axis_lock", "MIDDLEMOUSE", True, True, None, {"mode": "TRACK"}) in v3d
