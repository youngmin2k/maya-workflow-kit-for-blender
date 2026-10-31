"""Lane ITEMS (#74 #62): marking-menu entries run their main-menu items, greyed entries have notices,
component-mode RMB Select All / Deselect All / Invert follow the main menu's component rules."""

from importlib import import_module

import bmesh
import bpy

import kit

mm = import_module(kit.MODULE + ".marking.menus")
modal = import_module(kit.MODULE + ".marking.modal")
rmb_items = import_module(kit.MODULE + ".marking.rmb_items")
engine = import_module(kit.MODULE + ".marking.engine")
menu_map = import_module(kit.MODULE + ".ui.menu_map")
notices = import_module(kit.MODULE + ".ui.notices")

# Baseline (af51cd0): menus.walk over MENUS = 464 entries, 128 greyed (None or an empty Sub).
BASELINE = (464, 128)

# Greyed marking entries whose Maya command already worked from the main menus.
QUANT_25 = [
    "SHIFT_OBJECT/Fill Holes", "SHIFT_OBJECT/Extrude", "SHIFT_OBJECT/Quadrangulate",
    "SHIFT_OBJECT/Booleans/Union", "SHIFT_OBJECT/Booleans/Difference (A - B)",
    "SHIFT_OBJECT/Booleans/Intersection",
    "SHIFT_VERTEX/Vertex Normals/Vertex Normal Edit Tool", "SHIFT_VERTEX/Detach Components",
    "SHIFT_VERTEX/Circularize Vertices", "SHIFT_EDGE/Circularize Components",
    "SHIFT_FACE/Circularize Components", "SHIFT_EDGE/Soften/Harden Edges/Soften/Harden",
    "SHIFT_EDGE/Edit Edge Flow", "SHIFT_FACE/Wedge Face",
    "SHIFT_FACE/Face Normals/Reverse Normals", "SHIFT_DEFAULT/Quad Draw Tool",
    "CTRL_CONVERT/To UV Shell",
    "SHIFT_UV/Mapping/Best Plane", "SHIFT_UV_SHELL/Mapping/Best Plane",
    "SHIFT_UV/Mapping/Contour Stretch", "SHIFT_UV_SHELL/Mapping/Contour Stretch",
    "SHIFT_UV/UV Set Editor", "SHIFT_UV_SHELL/UV Set Editor",
    "RMB_MESH/Make Live", "RMB_CURVE/Make Live",
]


def _entries():
    return {p: a for name, menu in mm.MENUS.items() for p, _l, a in mm.label_walk(menu, name)}


def _item_path(action):
    """The main-menu path an entry runs, or None."""
    if isinstance(action, tuple) and len(action) == 2 and action[0] == "item":
        return action[1]
    if isinstance(action, tuple) and len(action) == 2 and action[0] == "allset.mm_object_item":
        return action[1]["item"]
    return None


def test_greyed_counts_and_notices():
    entries = list(_entries().items())
    greyed = [p for p, a in entries if mm.is_greyed(a)]
    print(f"marking entries {BASELINE[0]} -> {len(entries)}, greyed {BASELINE[1]} -> {len(greyed)}")
    assert greyed == [p for p, _l in mm.greyed_entries()]
    missing = [p for p in greyed if p not in notices.MARKING]
    assert not missing, missing
    stale = [k for k in notices.MARKING if k not in greyed]
    assert not stale, stale
    for key, (substitute, line) in notices.MARKING.items():
        assert substitute and line.endswith("."), key
    # Maya 2026 adds the shared Select / constraint submenus of the tool option menus and Polygon Display lists
    assert len(greyed) <= 115, len(greyed)


def test_item_paths_are_mapped():
    bad = [(p, _item_path(a)) for p, a in _entries().items()
           if _item_path(a) is not None and _item_path(a) not in menu_map.MAP]
    assert not bad, bad
    # ("item", path) normalizes to the main menu's operator
    assert menu_map.normalize(("item", "Mesh/Fill Hole")) == ("op", "allset.menu_item", {"item": "Mesh/Fill Hole"})


def test_quant_25_mapped():
    entries = _entries()
    for path in QUANT_25:
        assert path in entries, path
        action = entries[path]
        assert not mm.is_greyed(action), path
        assert modal.poll_action(action), path
    via_menu = [p for p in QUANT_25 if _item_path(entries[p]) is not None]
    assert len(via_menu) >= 22, via_menu   # Reverse Normals etc. may stay direct operators


def _cube_edit():
    kit_clear()
    bpy.ops.mesh.primitive_cube_add(size=2.0)
    ob = bpy.context.active_object
    bpy.ops.object.mode_set(mode='EDIT')
    return ob


def kit_clear():
    if bpy.context.active_object is not None and bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)


def _rmb(label):
    return dict(e for e in mm.RMB_MESH.items if e != mm.DIVIDER)[label]


def _selected_verts(ob):
    bm = bmesh.from_edit_mesh(ob.data)
    return sum(v.select for v in bm.verts)


def test_component_mode_select_items_follow_edit_mode():
    for label, path in (("Select All", "Select/All"), ("Deselect All", "Select/Deselect All"),
                        ("Invert Selection", "Select/Inverse")):
        assert _rmb(label) == ("item", path), label
        assert path in menu_map.EDIT_MODE, path
        assert modal.poll_action(_rmb(label)), label
    ob = _cube_edit()
    bpy.ops.mesh.select_all(action='DESELECT')
    modal.run_action(bpy.context, _rmb("Select All"))
    assert bpy.context.mode == 'EDIT_MESH' and _selected_verts(ob) == 8
    bm = bmesh.from_edit_mesh(ob.data)
    bm.verts.ensure_lookup_table()
    for v in bm.verts:
        v.select_set(False)
    bm.verts[0].select_set(True)
    bm.select_flush_mode()
    bmesh.update_edit_mesh(ob.data)
    modal.run_action(bpy.context, _rmb("Invert Selection"))
    assert bpy.context.mode == 'EDIT_MESH' and _selected_verts(ob) == 7, _selected_verts(ob)
    # SelectNone in component mode = clear + object mode (menu_map.EDIT_MODE)
    modal.run_action(bpy.context, _rmb("Deselect All"))
    assert bpy.context.mode == 'OBJECT' and not ob.select_get()


def test_select_hierarchy():
    kit_clear()
    bpy.ops.mesh.primitive_cube_add()
    root = bpy.context.active_object
    bpy.ops.mesh.primitive_cube_add(location=(3, 0, 0))
    child = bpy.context.active_object
    child.parent = root
    bpy.ops.mesh.primitive_cube_add(location=(6, 0, 0))
    other = bpy.context.active_object
    bpy.context.window_manager.allset_mm_target = root.name
    bpy.context.view_layer.objects.active = root
    bpy.ops.object.mode_set(mode='EDIT')      # from component mode: object mode first
    assert modal.poll_action(_rmb("Select Hierarchy"))
    modal.run_action(bpy.context, _rmb("Select Hierarchy"))
    assert bpy.context.mode == 'OBJECT'
    assert root.select_get() and child.select_get() and not other.select_get()
    assert bpy.context.view_layer.objects.active == root
    bpy.context.window_manager.allset_mm_target = ""


def test_actions_and_sets_submenus():
    kit_clear()
    bpy.ops.mesh.primitive_cube_add()
    a = bpy.context.active_object
    bpy.ops.mesh.primitive_cube_add(location=(3, 0, 0))
    b = bpy.context.active_object
    actions = dict(e for e in _rmb("Actions").items)
    assert set(actions) == {"Template", "Untemplate", "Unparent", "Bounding Box"}
    # Bounding Box toggles the menu's object only
    bpy.context.window_manager.allset_mm_target = a.name
    modal.run_action(bpy.context, actions["Bounding Box"])
    assert a.display_type == 'BOUNDS' and b.display_type != 'BOUNDS'
    modal.run_action(bpy.context, actions["Bounding Box"])
    assert a.display_type == 'TEXTURED'
    # Template acts on the menu's object, the rest of the selection comes back
    b.select_set(True)
    bpy.context.view_layer.objects.active = b
    modal.run_action(bpy.context, actions["Template"])
    assert a.display_type == 'WIRE' and a.hide_select and b.select_get() and b.display_type != 'WIRE'
    modal.run_action(bpy.context, actions["Untemplate"])
    assert not a.hide_select
    # UV Sets / Color Sets: Blender menus listing the mesh's sets; picking one makes it current
    for label, idname in (("UV Sets", "ALLSET_MT_uv_sets_rmb"), ("Color Sets", "ALLSET_MT_color_sets_rmb")):
        assert _rmb(label) == ("menu", idname) and hasattr(bpy.types, idname)
    a.data.uv_layers.new(name="map2")
    bpy.ops.allset.mm_uv_set(name="map2")
    assert a.data.uv_layers.active.name == "map2"
    a.data.color_attributes.new("colorSet1", 'FLOAT_COLOR', 'POINT')
    a.data.color_attributes.new("colorSet2", 'FLOAT_COLOR', 'POINT')
    bpy.ops.allset.mm_color_set(name="colorSet2")
    assert a.data.color_attributes.active_color.name == "colorSet2"
    bpy.context.window_manager.allset_mm_target = ""


def test_poly_items():
    # Reverse Propagate: the picked face flips and its shell follows
    ob = _cube_edit()
    bm = bmesh.from_edit_mesh(ob.data)
    bm.faces.ensure_lookup_table()
    before = [f.normal.copy() for f in bm.faces]
    for f in bm.faces:
        f.select_set(False)
    bm.faces[0].select_set(True)
    bmesh.update_edit_mesh(ob.data)
    bpy.ops.allset.mm_poly(kind='REVERSE_PROPAGATE')
    bm = bmesh.from_edit_mesh(ob.data)
    bm.normal_update()
    bm.faces.ensure_lookup_table()
    assert all(f.normal.dot(n) < -0.99 for f, n in zip(bm.faces, before))
    # To Vertex Perimeter of two neighbouring faces: their 6 border vertices
    bpy.ops.mesh.select_all(action='DESELECT')
    bpy.ops.mesh.select_mode(type='FACE')
    bm = bmesh.from_edit_mesh(ob.data)
    bm.faces.ensure_lookup_table()
    f0 = bm.faces[0]
    f1 = next(e.link_faces[1] if e.link_faces[0] == f0 else e.link_faces[0] for e in f0.edges)
    f0.select_set(True)
    f1.select_set(True)
    bmesh.update_edit_mesh(ob.data)
    bpy.ops.allset.mm_poly(kind='VERTEX_PERIMETER')
    assert _selected_verts(ob) == 6, _selected_verts(ob)
    # To Edge Ring and Collapse on a cube edge ring: 4 edges collapse
    bpy.ops.mesh.select_all(action='DESELECT')
    bpy.ops.mesh.select_mode(type='EDGE')
    bm = bmesh.from_edit_mesh(ob.data)
    bm.edges.ensure_lookup_table()
    bm.edges[0].select_set(True)
    bmesh.update_edit_mesh(ob.data)
    bpy.ops.allset.mm_poly(kind='RING_COLLAPSE')
    bm = bmesh.from_edit_mesh(ob.data)
    assert len(bm.verts) < 8, len(bm.verts)
    # To Shell Border of a closed cube: nothing (no open edges); of a plane: its 4 border edges
    kit_clear()
    bpy.ops.mesh.primitive_plane_add()
    ob = bpy.context.active_object
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.subdivide(number_cuts=1)
    bpy.ops.mesh.select_all(action='DESELECT')
    bm = bmesh.from_edit_mesh(ob.data)
    bm.verts.ensure_lookup_table()
    bm.verts[0].select_set(True)
    bmesh.update_edit_mesh(ob.data)
    bpy.ops.allset.mm_poly(kind='SHELL_BORDER')
    bm = bmesh.from_edit_mesh(ob.data)
    assert sum(e.select for e in bm.edges) == 8
    assert all(e.is_boundary for e in bm.edges if e.select)
    bpy.ops.object.mode_set(mode='OBJECT')


def _session(menu):
    return engine.Session(menu, (400, 400), 0.0, lambda text: 8.0 * len(text), engine.Params(), modal.poll_action)


def test_hover_notice():
    s = _session(mm.RMB_MESH)
    item = next(it for it in s.stack[-1][0].items if it.label == "Time Editor")
    s.hover = (item, False)
    key, text = modal.hover_notice(s)
    assert key == "RMB_MESH/Time Editor" and "NLA" in text, (key, text)
    item = next(it for it in s.stack[-1][0].items if it.label == "Select All")
    s.hover = (item, False)
    assert modal.hover_notice(s) is None
