"""Menu honesty — every greyed Maya menu item has a notice, cheap Blender equivalents mapped, mapped
items stay enabled in object mode the Maya way."""


import math
import types
from importlib import import_module

import bmesh
import bpy

import kit

menu_data = import_module(kit.MODULE + ".ui.menu_data")
menu_map = import_module(kit.MODULE + ".ui.menu_map")
menu_sets = import_module(kit.MODULE + ".ui.menu_sets")
notices = import_module(kit.MODULE + ".ui.notices")
items_ops = import_module(kit.MODULE + ".operators.menu_items")


def _clear():
    if bpy.context.active_object is not None and bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    for me in list(bpy.data.meshes):
        bpy.data.meshes.remove(me)


def _select(*obs):
    for o in bpy.context.scene.objects:
        o.select_set(False)
    for o in obs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = obs[-1]


def _cube(name="pCube1"):
    bpy.ops.mesh.primitive_cube_add(size=2.0)
    ob = bpy.context.active_object
    ob.name = name
    return ob


def _leaves():
    """(path, mapped) per drawn leaf (ui/menu_sets rules; tools/menu_count.py counts the same)."""
    out = {}
    for path, it in menu_sets.iter_items():
        if not menu_sets.sub_items(path, it) or path in menu_map.MAP:
            out[path] = path in menu_map.MAP
    return out


# --- (a) notices ------------------------------------------------------------------------------

def test_every_greyed_item_has_a_notice():
    greyed = [p for p, mapped in _leaves().items() if not mapped]
    missing = [p for p in greyed if notices.greyed_notice(p) is None]
    assert not missing, missing[:20]
    for p in greyed:
        substitute, line = notices.greyed_notice(p)
        assert substitute and "Blender" in line, (p, line)
    print(f"greyed items: {len(greyed)}, all with a notice")


def test_category_rules_all_used():
    greyed = [p for p, mapped in _leaves().items() if not mapped and p not in notices.NOTICES]
    used = set()
    for p in greyed:
        best = max((c for c in notices.CATEGORIES if p == c or p.startswith(c + "/")), key=len, default=None)
        used.add(best)
    dead = sorted(set(notices.CATEGORIES) - used)
    assert not dead, dead


def test_greyed_tooltip_carries_the_category():
    tip = menu_sets.ALLSET_OT_menu_unavailable.description(
        bpy.context, types.SimpleNamespace(item="Surfaces/Loft"))
    assert "Surfaces/Loft" in tip and "NURBS" in tip, tip
    tip = menu_sets.ALLSET_OT_menu_unavailable.description(
        bpy.context, types.SimpleNamespace(item="Generate/XGen Editor"))
    assert "XGen" in tip and "Curves" in tip, tip


def test_working_share_at_least_40_percent():
    leaves = _leaves()
    share = sum(leaves.values()) / len(leaves)
    print(f"menu leaves {len(leaves)}, working {sum(leaves.values())} ({share:.1%})")
    assert share >= 0.40, share


# --- (b) menu data + mappings -----------------------------------------------------------------

def test_runtime_menu_data():
    paths = {p for p, _it in menu_sets.iter_items()}
    for p in ("Modify/Prefix Hierarchy Names...", "Modify/Search and Replace Names...", "Modify/Center Pivot",
              "Modify/Add Attribute...", "Help/Maya Help", "Help/About Maya", "Audio/Import Audio...",
              "Audio/Waveform Display/Centered", "Create/Cameras/Stereo Camera", "Stereo/Make Links",
              "Cache/Alembic Cache/Import Alembic...", "Cache/Geometry Cache/Create New Cache",
              "Cache/GPU Cache/Refresh All...", "File/Game Exporter", "Create/Sweep Mesh",
              "Create/Universal Scene Description (USD)", "Select/USD Selection Mode", "Playback/Cached Playback",
              "Visualize/Ghost Selected", "Visualize/Time Slider Bookmarks", "Deform/Muscle",
              "Generate/XGen Editor"):
        assert p in paths, p
    modify = [it[0] for it in menu_data.MENUS["mainModifyMenu"][3]]
    i = modify.index("Prefix Hierarchy Names...")
    assert modify[i - 1] == "-" and modify[i + 2] == "-", modify     # own Naming section like Maya
    assert [it[0] for it in menu_data.MENUS["mainPipelineCacheMenu"][3]] == \
        ["Alembic Cache", "Geometry Cache", "GPU Cache"]
    assert "Cache/Alembic Cache/Import Alembic..." in menu_data.OPTION_BOXES
    # nothing listed twice: the Pivot / Attributes EXTRA moved into the data
    assert "Modify/Match Transformations" not in menu_map.EXTRA


def test_prefix_and_search_replace_names():
    _clear()
    a = _cube("pCube1")
    b = _cube("pCube2")
    b.parent = a
    a.data.name = "pCubeShape1"
    _select(a)
    bpy.ops.allset.prefix_hierarchy(prefix="L_")
    assert a.name == "L_pCube1" and b.name == "L_pCube2" and a.data.name == "L_pCubeShape1"
    _select(a)
    bpy.ops.allset.search_replace_names(search="L_", replace="R_", scope='SELECTED')
    assert a.name == "R_pCube1" and b.name == "L_pCube2"
    bpy.ops.allset.search_replace_names(search="L_", replace="R_", scope='ALL')
    assert b.name == "R_pCube2"


def test_soften_harden_object_and_edges():
    _clear()
    ob = _cube()
    _select(ob)
    bpy.ops.allset.soften_harden(angle=30.0)          # angle 30: cube edges (90 deg) hard
    assert not any(_smooth(ob, e) for e in range(12))
    assert all(p.use_smooth for p in ob.data.polygons)
    bpy.ops.allset.soften_harden(angle=180.0)
    assert all(_smooth(ob, e) for e in range(12))
    bpy.ops.allset.soften_harden(angle=0.0)
    assert not any(_smooth(ob, e) for e in range(12))


def _smooth(ob, i):
    sharp = ob.data.attributes.get("sharp_edge")
    return sharp is None or not sharp.data[i].value


def test_detach_vertex_and_object_mode_warning():
    _clear()
    ob = _cube()
    _select(ob)
    assert bpy.ops.allset.menu_item(item="Edit Mesh/Detach") == {'CANCELLED'}    # Maya warns on an object
    assert len(ob.data.vertices) == 8
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_mode(type='VERT')
    bpy.ops.mesh.select_all(action='DESELECT')
    bm = bmesh.from_edit_mesh(ob.data)
    bm.verts.ensure_lookup_table()
    bm.verts[0].select = True
    bmesh.update_edit_mesh(ob.data)
    bpy.ops.allset.detach()
    bpy.ops.object.mode_set(mode='OBJECT')
    assert len(ob.data.vertices) == 10, len(ob.data.vertices)     # a corner of 3 faces -> 3 vertices


def test_edge_flow_follows_curvature():
    _clear()
    # a cylinder side: a middle ring pushed inwards comes back onto the circle
    bpy.ops.mesh.primitive_cylinder_add(vertices=16, radius=1.0, depth=2.0)
    ob = bpy.context.active_object
    bpy.ops.object.mode_set(mode='EDIT')
    bm = bmesh.from_edit_mesh(ob.data)
    bmesh.ops.subdivide_edges(bm, edges=[e for e in bm.edges if abs(e.verts[0].co.z - e.verts[1].co.z) > 1],
                              cuts=3, use_grid_fill=False)
    ring = [v for v in bm.verts if abs(v.co.z) < 1e-4]
    for v in bm.edges:
        v.select = False
    for v in bm.verts:
        v.select = False
    for v in ring:
        v.co.z = 0.0
    edges = [e for e in bm.edges if all(abs(v.co.z) < 1e-4 for v in e.verts)]
    # bend the side: the rings above / below bulge out, the middle ring is flat at radius 1
    for v in bm.verts:
        if 1e-4 < abs(v.co.z) < 0.9:
            v.co.x *= 1.2
            v.co.y *= 1.2
    moved = items_ops.edge_flow(bm, edges, 1.0)
    bmesh.update_edit_mesh(ob.data)
    assert moved == len(ring), (moved, len(ring))
    assert all(math.hypot(v.co.x, v.co.y) > 1.2 for v in ring), [math.hypot(v.co.x, v.co.y) for v in ring][:3]
    bpy.ops.object.mode_set(mode='OBJECT')


def test_wedge_sweeps_faces_round_an_edge():
    _clear()
    bpy.ops.mesh.primitive_plane_add(size=2.0)
    ob = bpy.context.active_object
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bm = bmesh.from_edit_mesh(ob.data)
    bm.edges.ensure_lookup_table()
    edge = bm.edges[0]
    bm.select_history.add(edge)
    bmesh.update_edit_mesh(ob.data)
    assert bpy.ops.allset.wedge(angle=90.0, divisions=4) == {'FINISHED'}
    bpy.ops.object.mode_set(mode='OBJECT')
    assert len(ob.data.polygons) > 4, len(ob.data.polygons)


def test_nonlinear_object_display_checker_stereo():
    _clear()
    ob = _cube()
    _select(ob)
    bpy.ops.allset.nonlinear(method='BEND')
    md = ob.modifiers[-1]
    assert md.type == 'SIMPLE_DEFORM' and md.deform_method == 'BEND' and md.name == "bend1" and md.angle == 0.0
    bpy.ops.allset.object_display(kind='TEMPLATE')
    assert ob.hide_select and ob.display_type == 'WIRE' and not ob.select_get()
    bpy.ops.allset.object_display(kind='UNTEMPLATE')     # nothing selectable: every templated object
    assert not ob.hide_select and ob.display_type == 'TEXTURED'
    _select(ob)
    bpy.ops.allset.checker_shader()
    mat = ob.active_material
    img = next(n.image for n in mat.node_tree.nodes if n.type == 'TEX_IMAGE')
    assert img.generated_type == 'UV_GRID'
    bpy.ops.allset.stereo_camera()
    assert bpy.context.scene.render.use_multiview and bpy.context.active_object.type == 'CAMERA'
    bpy.context.scene.render.use_multiview = False
    assert bpy.ops.allset.delete_sounds() == {'FINISHED'}
    assert bpy.ops.allset.menu_note(item="Playback/Playback Looping/Continuous") == {'FINISHED'}


def test_sculpt_tool_brush():
    _clear()
    ob = _cube()
    _select(ob)
    assert bpy.ops.allset.sculpt_tool(brush="Grab") == {'FINISHED'}
    assert bpy.context.mode == 'SCULPT'
    brush = bpy.context.tool_settings.sculpt.brush
    assert brush is not None and brush.name == "Grab", brush
    bpy.ops.object.mode_set(mode='OBJECT')


# --- (c) mapped items enabled in object mode --------------------------------------------------

class _Rec:
    def __init__(self):
        self.log = []

    def operator(self, idname, text="", **kw):
        props = types.SimpleNamespace()
        self.log.append(("op", idname, text, props))
        return props

    def operator_menu_hold(self, idname, text="", **kw):
        props = types.SimpleNamespace()
        self.log.append(("hold", idname, text, props))
        return props

    def menu(self, idname, text="", **kw):
        self.log.append(("menu", idname, text))

    def __getattr__(self, name):
        return lambda *a, **k: None


def test_edit_mesh_menu_enabled_in_object_mode():
    _clear()
    ob = _cube()
    _select(ob)
    assert bpy.context.mode == 'OBJECT'
    rec = _Rec()
    getattr(bpy.types, menu_sets.menu_idname("mainEditMeshMenu")).draw(types.SimpleNamespace(layout=rec),
                                                                        bpy.context)
    greyed_mapped = []
    for entry in rec.log:
        if entry[0] not in ("op", "hold"):
            continue
        path = getattr(entry[3], "item", None)
        if entry[1] == "allset.menu_unavailable" and path in menu_map.MAP:
            greyed_mapped.append(path)
        if entry[1] not in ("allset.menu_unavailable", "allset.menu_item", "allset.menu_run",
                            "allset.menu_tool"):
            mod, name = entry[1].split(".")
            if not getattr(getattr(bpy.ops, mod), name).poll():
                greyed_mapped.append(entry[1])
    assert not greyed_mapped, greyed_mapped
    labels = {e[2]: e for e in rec.log if e[0] in ("op", "hold")}
    assert labels["Collapse"][1] == "allset.menu_item", labels["Collapse"]


def test_object_mode_runs_on_the_whole_mesh():
    _clear()
    ob = _cube()
    _select(ob)
    assert bpy.ops.allset.menu_item(item="Edit Mesh/Poke") == {'FINISHED'}
    assert bpy.context.mode == 'OBJECT' and len(ob.data.polygons) == 24, len(ob.data.polygons)   # 6 -> 24
    bpy.ops.ed.undo_push(message="poked")
    _clear()
    ob = _cube()
    _select(ob)
    bpy.ops.allset.menu_item(item="Edit Mesh/Bevel")
    assert len(ob.data.vertices) > 8 and bpy.context.mode == 'OBJECT'
    # Maya warns (no change) for Bridge on an object
    n = len(ob.data.vertices)
    assert bpy.ops.allset.menu_item(item="Edit Mesh/Bridge") == {'CANCELLED'}
    assert len(ob.data.vertices) == n
