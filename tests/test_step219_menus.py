"""Issue #130: the kit's main menus follow Maya 2026: every kit menu, item order, dividers and submenus
equal Maya's except the submenus
the kit fills at run time from the scene."""

from importlib import import_module
from pathlib import Path

import kit

ROOT = Path(__file__).resolve().parent.parent
menu_data = import_module(kit.MODULE + ".ui.menu_data")
menu_map = import_module(kit.MODULE + ".ui.menu_map")


def _paths(items, prefix):
    seen = {}
    for it in items:
        if it[0] == "-":
            continue
        n = seen[it[0]] = seen.get(it[0], 0) + 1
        path = f"{prefix}/{it[0]}" + (f"#{n}" if n > 1 else "")
        yield path
        if len(it) > 1:
            yield from _paths(it[1], path)


def test_header_says_maya_2026():
    assert "Maya 2026" in menu_data.__doc__


def test_maya_2026_items_present_and_2022_items_gone():
    allp = {p for m in menu_data.MENUS.values() for p in _paths(m[3], m[0])}
    for p in ("Deform/ML Deformer", "Deform/Paint Membership", "Deform/Pose Space Deformation/Pose Editor",
              "Visualize/Motion Trail Editor", "Visualize/Ghosting Editor", "Visualize/Blue Pencil",
              "Mesh/Booleans/Difference (A - B)", "Mesh/Booleans/Difference (B - A)", "Mesh/Booleans/Slice",
              "Mesh/Unsmooth", "Edit Mesh/Smart Extrude", "Modify/Zero Pivot", "Modify/Reorder Rotation...",
              "Create/Polygon Primitives/Polygon Disc", "Create/Polygon Type", "Windows/LookdevX Graph Editor"):
        assert p in allp, p
    for p in ("Deform/Paint Weights/Set Membership", "Visualize/Create Editable Motion Trail",
              "Visualize/Open Ghosting Editor", "Mesh/Booleans/Difference", "Create/Subdiv Primitives", "Create/Type",
              "Edit/Fur", "Display/Subdiv Surfaces"):
        assert p not in allp, p


def test_kit_mappings_follow_the_renames():
    m = menu_map.MAP
    assert m["Mesh/Booleans/Difference (A - B)"] == ("allset.boolean", {"operation": 'DIFFERENCE'})
    assert m["Mesh/Booleans/Difference (B - A)"] == ("allset.boolean", {"operation": 'DIFFERENCE_BA'})
    assert m["Edit Mesh/Smart Extrude"] == ("v3d", "allset.smart_extrude", {})
    assert m["Edit Mesh/Smart Extrude"] != m["Edit Mesh/Extrude"]
    assert m["Modify/Zero Pivot"] == "allset.reset_pivot"
    assert m["Visualize/Ghosting Editor"] == "allset.opt_ghosting_editor"
    assert m["Deform/Paint Membership"] == "paint.weight_paint_toggle"
    assert m["Create/Polygon Primitives/Polygon Disc"] == m["Create/Polygon Primitives/Cube"][:1] + (
        {"kind": 'DISC'},) or m["Create/Polygon Primitives/Polygon Disc"][1]["kind"] == 'DISC'
    assert m["Windows/LookdevX Graph Editor"] == "allset.hypershade"
    # no mapping left on a path Maya 2026 doesn't have
    allp = {p for mm in menu_data.MENUS.values() for p in _paths(mm[3], mm[0])}
    for key, kids in menu_map.CHILDREN.items():
        allp |= set(_paths(kids, key))
    tops = {mm[0] for mm in menu_data.MENUS.values()}
    extra = {f"{base}/{e[0]}" for k, v in menu_map.EXTRA.items() for e in v if e[0] != "-"
             for base in (k.rsplit('/', 1)[0], k.split('/')[0])}
    stale = [k for k in m if k.split("/")[0] in tops and k not in allp and k not in extra]
    assert not stale, stale


def test_boolean_difference_b_minus_a():
    import bpy
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    bpy.ops.mesh.primitive_cube_add(size=2)
    a = bpy.context.active_object
    a.name = "A"
    bpy.ops.mesh.primitive_cube_add(size=2, location=(1, 0, 0))
    b = bpy.context.active_object
    b.name = "B"
    a.select_set(True)
    b.select_set(True)
    bpy.context.view_layer.objects.active = b           # Maya: A first, B last (operand)
    assert bpy.ops.allset.boolean(operation='DIFFERENCE_BA') == {'FINISHED'}
    left = [o for o in bpy.data.objects]
    assert [o.name for o in left] == ["B"], [o.name for o in left]
    xs = [v.co.x + left[0].location.x for v in left[0].data.vertices]
    assert min(xs) > 0.99 and max(xs) < 2.01        # B (0..2) minus A (-1..1) = 1..2
