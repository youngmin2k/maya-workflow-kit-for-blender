"""Operators: allset.display_mode, allset.group."""

from importlib import import_module

import bpy
from mathutils import Matrix, Vector

import kit

display = import_module(kit.MODULE + ".operators.display")
group = import_module(kit.MODULE + ".operators.group")

SHADING_CASES = (
    ("WIREFRAME", {"type": "WIREFRAME"}),
    ("SHADED", {"type": "SOLID", "color_type": "MATERIAL"}),
    ("TEXTURED", {"type": "SOLID", "color_type": "TEXTURE"}),
    ("LIGHTS", {"type": "MATERIAL", "use_scene_lights": True, "use_scene_world": False}),
)


def _view3d_space():
    """(screen, area, space) of a 3D view in the startup file (present even in -b)."""
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type == 'VIEW_3D':
                return screen, area, area.spaces.active
    raise AssertionError("no 3D view in startup file")


def test_display_mode_sets_shading():
    _screen, _area, space = _view3d_space()
    for mode, want in SHADING_CASES:
        display.apply_display_mode(space.shading, mode)
        got = {k: getattr(space.shading, k) for k in want}
        assert got == want, (mode, got)


def test_display_mode_operator():
    screen, area, space = _view3d_space()
    assert not bpy.ops.allset.display_mode.poll(), "poll must reject non-3D context"
    region = next(r for r in area.regions if r.type == 'WINDOW')
    # No window in -b: override the screen too.
    with bpy.context.temp_override(screen=screen, area=area, region=region, space_data=space):
        for mode, want in SHADING_CASES:
            assert bpy.ops.allset.display_mode(mode=mode) == {'FINISHED'}, mode
            got = {k: getattr(space.shading, k) for k in want}
            assert got == want, (mode, got)


def _new_obj(name, loc):
    ob = bpy.data.objects.new(name, bpy.data.meshes.new(name))
    bpy.context.scene.collection.objects.link(ob)
    ob.location = loc
    return ob


def _select(objs):
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0] if objs else None


def _close(a, b, tol=1e-5):
    return all(abs(x - y) < tol for ra, rb in zip(a, b) for x, y in zip(ra, rb))


def _clear_groups():
    for ob in [o for o in bpy.data.objects if o.name.startswith("group")]:
        bpy.data.objects.remove(ob)


def test_group_at_world_origin():
    _clear_groups()
    a = _new_obj("A", (1, 2, 3))
    b = _new_obj("B", (-4, 0, 5))
    b.rotation_euler = (0.3, 0.2, 0.1)
    bpy.context.view_layer.update()
    worlds = {o.name: o.matrix_world.copy() for o in (a, b)}
    _select([a, b])
    assert bpy.ops.allset.group() == {'FINISHED'}
    grp = bpy.context.view_layer.objects.active
    assert grp.type == 'EMPTY' and grp.name == "group1", (grp.type, grp.name)
    assert grp.parent is None
    assert _close(grp.matrix_world, Matrix.Identity(4))
    assert [o.name for o in bpy.context.selected_objects] == ["group1"]
    bpy.context.view_layer.update()
    for o in (a, b):
        assert o.parent == grp
        assert _close(o.matrix_parent_inverse, Matrix.Identity(4)), o.name
        assert _close(o.matrix_world, worlds[o.name]), o.name
    # Identity group: local values equal world values (Maya Channel Box numbers).
    assert (a.location - Vector((1, 2, 3))).length < 1e-6


def test_group_under_common_parent():
    _clear_groups()
    p = _new_obj("P", (10, 0, 0))
    p.rotation_euler = (0, 0, 0.5)
    kids = [_new_obj("C1", (0, 0, 0)), _new_obj("C2", (0, 0, 0))]
    for c, off in zip(kids, ((1, 0, 0), (0, 1, 0))):
        c.parent = p
        c.location = off
    bpy.context.view_layer.update()
    worlds = {o.name: o.matrix_world.copy() for o in kids}
    _select(kids)
    bpy.ops.allset.group()
    grp = bpy.context.view_layer.objects.active
    bpy.context.view_layer.update()
    assert grp.parent == p, grp.parent
    assert _close(grp.matrix_basis, Matrix.Identity(4))  # pivot at the parent's origin
    assert _close(grp.matrix_world, p.matrix_world)
    for c in kids:
        assert c.parent == grp
        assert _close(c.matrix_world, worlds[c.name]), c.name


def test_group_naming_and_empty_selection():
    _clear_groups()
    assert group.next_group_name(["group1", "group3", "pCube1", "group", "group02x"]) == "group4"
    assert group.next_group_name([]) == "group1"
    _select([])
    bpy.ops.allset.group()
    first = bpy.context.view_layer.objects.active
    _select([])
    bpy.ops.allset.group()
    second = bpy.context.view_layer.objects.active
    assert (first.name, second.name) == ("group1", "group2"), (first.name, second.name)
    assert first.type == 'EMPTY' and not first.children
    bpy.data.objects.remove(first)
    _select([])
    bpy.ops.allset.group()
    assert bpy.context.view_layer.objects.active.name == "group3"  # Maya: one past the highest


def test_group_is_undoable_operator():
    assert 'UNDO' in group.ALLSET_OT_group.bl_options


def test_group_regroups_selected_group():
    """Maya: Ctrl+G twice nests the first group in a new one."""
    _clear_groups()
    a = _new_obj("G_A", (0, 0, 1))
    _select([a])
    bpy.ops.allset.group()
    bpy.ops.allset.group()  # selection is now group1
    g1, g2 = bpy.data.objects["group1"], bpy.data.objects["group2"]
    assert a.parent == g1 and g1.parent == g2 and g2.parent is None
