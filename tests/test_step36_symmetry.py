"""Maya symmetric modelling (Status Line Symmetry, W/E/R marking menu Symmetry ▸).

One global Maya state (Scene.allset_symmetry) drives Blender's per-mesh mirror flags.
"""

import math
from importlib import import_module

import bmesh
import bpy

import kit

sym_mod = import_module(kit.MODULE + ".operators.symmetry")
mm = import_module(kit.MODULE + ".marking.menus")
draw = import_module(kit.MODULE + ".marking.draw")
status_line = import_module(kit.MODULE + ".ui.status_line")


def _scene(n=1):
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    obs = []
    for i in range(n):
        bpy.ops.mesh.primitive_cube_add(location=(0, 0, 0))
        obs.append(bpy.context.active_object)
    sym_mod.set_mode(bpy.context.scene.allset_symmetry, "OFF")
    bpy.context.scene.allset_symmetry.about = 'OBJECT'
    bpy.context.scene.allset_symmetry.axis = 'X'
    return obs


def _flags(ob):
    me = ob.data
    return (me.use_mirror_x, me.use_mirror_y, me.use_mirror_z, me.use_mirror_topology)


def _sym():
    return bpy.context.scene.allset_symmetry


def test_factory_default_is_maya():
    # defaults like Maya: off, axis x, about object.
    scene = bpy.data.scenes.new("SymDefaults")
    try:
        s = scene.allset_symmetry
        assert (s.on, s.about, s.axis) == (False, 'OBJECT', 'X'), (s.on, s.about, s.axis)
        assert sym_mod.label(s) == "Symmetry: Off"
    finally:
        bpy.data.scenes.remove(scene)


def test_modes_set_mesh_flags():
    ob, = _scene()
    bpy.ops.object.mode_set(mode='EDIT')
    expect = {
        "OBJECT_X": (True, False, False, False), "OBJECT_Y": (False, True, False, False),
        "OBJECT_Z": (False, False, True, False), "WORLD_Z": (False, False, True, False),
        "TOPOLOGY": (False, False, True, True),  # topology keeps the last axis (Z)
        "OFF": (False, False, False, False),
    }
    for mode, flags in expect.items():
        bpy.ops.allset.symmetry(mode=mode)
        assert _flags(ob) == flags, (mode, _flags(ob))
    bpy.ops.allset.symmetry(mode="OBJECT_Y")
    assert sym_mod.label(_sym()) == "Object Y"
    assert sym_mod.mode_of(_sym()) == "OBJECT_Y"


def test_world_uses_closest_local_axis():
    ob, = _scene()
    ob.rotation_euler = (0, 0, math.radians(90))  # local Y now points along world -X
    bpy.context.view_layer.update()
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.allset.symmetry(mode="WORLD_X")
    assert _flags(ob) == (False, True, False, False), _flags(ob)
    assert sym_mod.world_fit(ob, _sym())
    bpy.ops.allset.symmetry(mode="OBJECT_X")
    assert _flags(ob) == (True, False, False, False), _flags(ob)
    # Off the world plane: Blender still mirrors through the origin -> reported as not fitting.
    bpy.ops.object.mode_set(mode='OBJECT')
    ob.location.x = 3
    bpy.context.view_layer.update()
    sym_mod.set_mode(_sym(), "WORLD_X")
    assert not sym_mod.world_fit(ob, _sym())


def test_entering_edit_mode_applies_global_state():
    a, b = _scene(2)
    b.location.x = 5
    bpy.ops.object.select_all(action='DESELECT')
    a.select_set(True)
    bpy.context.view_layer.objects.active = a
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.allset.symmetry(mode="OBJECT_X")
    assert _flags(a)[0]
    bpy.ops.object.mode_set(mode='OBJECT')
    assert not _flags(b)[0]
    bpy.ops.object.select_all(action='DESELECT')
    b.select_set(True)
    bpy.context.view_layer.objects.active = b
    bpy.ops.object.mode_set(mode='EDIT')
    assert _flags(b) == (True, False, False, False), _flags(b)  # Maya: symmetry is global
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.allset.symmetry(mode="OFF")
    b.data.use_mirror_x = True  # a Blender user's per-mesh flag outside edit mode
    bpy.ops.object.mode_set(mode='EDIT')
    assert _flags(b) == (False, False, False, False), _flags(b)


def test_blender_header_buttons_update_global_state():
    ob, = _scene()
    bpy.ops.object.mode_set(mode='EDIT')
    ob.data.use_mirror_z = True  # Blender's own X/Y/Z mirror button in the tool header
    bpy.context.view_layer.update()
    s = _sym()
    assert (s.on, s.about, s.axis) == (True, 'OBJECT', 'Z'), (s.on, s.about, s.axis)
    ob.data.use_mirror_z = False
    bpy.context.view_layer.update()
    assert not _sym().on


def test_toggle_returns_to_last_mode():
    ob, = _scene()
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.allset.symmetry(mode="WORLD_Y")
    bpy.ops.allset.symmetry(mode="TOGGLE")
    assert not _sym().on and _flags(ob) == (False,) * 4
    bpy.ops.allset.symmetry(mode="TOGGLE")
    assert sym_mod.mode_of(_sym()) == "WORLD_Y", sym_mod.mode_of(_sym())


def test_marking_menu_parts():
    ob, = _scene()
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.allset.symmetry(mode="AXIS_Z")       # axis only: still off
    assert not _sym().on and _sym().axis == 'Z'
    bpy.ops.allset.symmetry(mode="ABOUT_WORLD")
    assert not _sym().on and _sym().about == 'WORLD'
    bpy.ops.allset.symmetry(mode="ON")           # check box on: keeps about / axis
    assert sym_mod.mode_of(_sym()) == "WORLD_Z" and _flags(ob)[2]
    for part, want in (("ON", True), ("ABOUT_WORLD", True), ("ABOUT_OBJECT", False),
                       ("AXIS_Z", True), ("AXIS_X", False), ("TOPOLOGY", False)):
        assert sym_mod.item_state(part) is want, part
        assert draw.checked(("allset.symmetry", {"mode": part})) is want, part
    bpy.ops.allset.symmetry(mode="ON")
    assert not _sym().on and not any(_flags(ob))


def test_switching_on_symmetrizes_selection():
    # turning symmetry on symmetrizes the selection: the mirrored side is selected too.
    ob, = _scene()
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_mode(type='VERT')
    bm = bmesh.from_edit_mesh(ob.data)
    for v in bm.verts:
        v.select = v.co.x > 0 and v.co.z > 0
    bm.select_flush(True)
    bmesh.update_edit_mesh(ob.data)
    bpy.ops.allset.symmetry(mode="OBJECT_X")
    bm = bmesh.from_edit_mesh(ob.data)
    picked = sorted((round(v.co.x), round(v.co.z)) for v in bm.verts if v.select)
    assert picked == [(-1, 1), (-1, 1), (1, 1), (1, 1)], picked


def test_transform_moves_mirrored_side():
    ob, = _scene()
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.allset.symmetry(mode="OBJECT_X")
    bpy.ops.mesh.select_mode(type='VERT')
    bm = bmesh.from_edit_mesh(ob.data)
    for v in bm.verts:
        v.select = v.co.x > 0
    bm.select_flush(True)
    bmesh.update_edit_mesh(ob.data)
    # Exec needs mirror=True to read the mesh flags; interactive G / gizmo read them itself (GUI test).
    bpy.ops.transform.translate(value=(0.5, 0, 0), mirror=True)
    bpy.ops.object.mode_set(mode='OBJECT')
    xs = sorted(round(v.co.x, 3) for v in ob.data.vertices)
    assert xs == [-1.5] * 4 + [1.5] * 4, xs


def test_marking_menus_have_symmetry():
    for menu in (mm.OPT_MOVE, mm.OPT_ROTATE, mm.OPT_SCALE):
        label, sub = menu.radial["N"]
        assert label == "Symmetry" and isinstance(sub, mm.Sub), menu.name
        assert set(sub.radial) == {"N", "W", "E", "NE", "SW", "S", "SE"}


class _Layout:
    def __init__(self, log):
        self.log = log

    def _sub(self, *_a, **_k):
        return _Layout(self.log)

    row = column = _sub

    def operator(self, idname, text="", **kw):
        self.log.append(("op", idname, text, kw.get("depress")))
        return type("P", (), {})()

    def menu(self, idname, text="", **kw):
        self.log.append(("menu", idname, text))

    def separator(self, **_k):
        pass

    def label(self, text="", **_k):
        self.log.append(("label", text))


def test_status_line_draws_symmetry():
    ob, = _scene()
    log = []
    status_line.draw_symmetry(_Layout(log), bpy.context)
    assert ("menu", "ALLSET_MT_symmetry", "Symmetry: Off") in log, log
    assert ("op", "allset.symmetry", "", False) in log, log
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.allset.symmetry(mode="OBJECT_X")
    log.clear()
    status_line.draw_symmetry(_Layout(log), bpy.context)
    assert ("menu", "ALLSET_MT_symmetry", "Object X") in log, log
    assert ("op", "allset.symmetry", "", True) in log, log
    assert any(f is status_line.draw_tool_symmetry
               for f in bpy.types.VIEW3D_PT_active_tool.draw._draw_funcs)


def test_disable_removes_state():
    _scene()
    kit.disable()
    try:
        assert not hasattr(bpy.types.Scene, "allset_symmetry")
        assert not any(getattr(f, "__module__", "").endswith("symmetry")
                       for f in bpy.app.handlers.depsgraph_update_post)
    finally:
        kit.enable()
