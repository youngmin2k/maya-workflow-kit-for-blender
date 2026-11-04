"""#298: the UV Editor's Shift+RMB marking menu is Maya's UV editing menu (Snap / Straighten / Optimize / Align /
Rotate / Layout / Unfold / ... per component), and a cut edge shows as a border at once, also a single edge cut
inside a shell. GUI: tests/gui/gui_issue298_uv_shift_menu.py."""

import math
import types
from importlib import import_module

import bmesh
import bpy

import kit

marking = import_module(kit.MODULE + ".marking")
mm = import_module(kit.MODULE + ".marking.menus")
compat = import_module(kit.MODULE + ".compat")
menu_map = import_module(kit.MODULE + ".ui.menu_map")
uvd = import_module(kit.MODULE + ".ui.uv_display")
uvt = import_module(kit.MODULE + ".operators.uv_tools")
uv_arrays = import_module(kit.MODULE + ".operators.uv_arrays")
cut_sew = import_module(kit.MODULE + ".operators.cut_sew")


def _ring(menu):
    return {p: label for p, (label, _a) in menu.radial.items()}


def _list(sub):
    return [e[0] for e in sub.items if e != mm.DIVIDER]


def _ctx(sync=True, select_mode=(True, False, False), uv_mode='VERTEX', island=False, shell_mask=False):
    ts = bpy.context.scene.tool_settings
    ts.use_uv_select_sync = sync
    ts.mesh_select_mode = select_mode
    compat.set_uv_island_mode(ts, island)
    if not island:
        ts.uv_select_mode = uv_mode
    wm = types.SimpleNamespace(allset_uv_shell_mask=shell_mask)
    return types.SimpleNamespace(mode='EDIT_MESH', scene=bpy.context.scene, active_object=None, window_manager=wm,
                                 space_data=types.SimpleNamespace(type='IMAGE_EDITOR', mode='UV'))


def test_menu_follows_the_component():
    def pick(**kw):
        return marking.resolve("SHIFT_RMB", _ctx(**kw))
    assert pick(sync=False, uv_mode='VERTEX') == ("pie", marking.idname("SHIFT_UV"))
    assert pick(sync=False, uv_mode='EDGE') == ("pie", marking.idname("SHIFT_UV"))
    assert pick(sync=True, select_mode=(True, False, False)) == ("pie", marking.idname("SHIFT_UV"))
    assert pick(sync=True, select_mode=(False, True, False)) == ("pie", marking.idname("SHIFT_UV"))
    assert pick(sync=True, select_mode=(False, False, True)) == ("pie", marking.idname("SHIFT_UV_FACE"))
    assert pick(sync=False, uv_mode='FACE') == ("pie", marking.idname("SHIFT_UV_FACE"))
    assert pick(sync=False, island=True) == ("pie", marking.idname("SHIFT_UV_SHELL"))
    assert pick(sync=True, select_mode=(False, False, True), shell_mask=True) == \
        ("pie", marking.idname("SHIFT_UV_SHELL"))
    for name in ("SHIFT_UV", "SHIFT_UV_SHELL", "SHIFT_UV_FACE"):
        assert name in mm.MENUS and marking.idname(name)


def test_uv_menu_ring_and_list():
    m = mm.SHIFT_UV
    assert _ring(m) == {"N": "Snap", "NE": "Straighten", "E": "Optimize", "SE": "Align UVs", "S": "Rotate UVs",
                        "SW": "Layout", "W": "Unfold", "NW": "Normalize"}
    assert _list(m) == ["Distribute", "Flip", "Map Border", "Symmetrize", "Unitize", "Auto Seams", "Create UV Shell",
                        "Cut UVs", "Delete UVs", "Merge UVs", "Sew UVs", "Measure Pixel Distance", "Tools", "Pinning"]
    assert _ring(m.radial["N"][1]) == {"NE": "Snap Together", "SE": "Match UVs", "SW": "Match Grid",
                                       "NW": "Snap and Stack"}
    assert _ring(m.radial["NE"][1]) == {"N": "Straighten UVs", "NE": "Straighten Border", "NW": "Straighten Shell"}
    assert _ring(m.radial["SE"][1]) == {"NE": "Max V", "E": "Center V", "SE": "Min V", "S": "Linear Align",
                                        "SW": "Min U", "W": "Center U", "NW": "Max U"}
    assert _ring(m.radial["S"][1]) == {"E": "Rotate Clockwise", "W": "Rotate Counterclockwise"}
    assert _ring(m.radial["SW"][1]) == {"SW": "Layout UV", "W": "Layout Along U", "NW": "Layout Along V"}
    assert _ring(m.radial["W"][1]) == {"W": "Unfold", "NW": "Unfold Along U", "SW": "Unfold Along V"}
    # the kit's UV commands run, as in the UV Editor menus and the UV Toolkit
    entries = {p: a for p, _l, a in mm.label_walk(m, "SHIFT_UV")}
    assert entries["SHIFT_UV/Cut UVs"] == ("item", "UV Editor/Cut/Sew/Cut")
    assert entries["SHIFT_UV/Unfold/Unfold"] == ("item", "UV Editor/Modify/Unfold")
    assert entries["SHIFT_UV/Unfold/Unfold Along V"] == ("allset.uv_unfold_along", {"axis": 'V'})
    assert entries["SHIFT_UV/Layout/Layout UV"] == ("item", "UV Editor/Modify/Layout")
    assert entries["SHIFT_UV/Align UVs/Max U"] == ("allset.uv_align_to", {"axis": 'U', "where": 'MAX'})
    assert menu_map.MAP["UV Editor/Modify/Unfold"] == "allset.uv_unfold"
    assert menu_map.MAP["UV Editor/Modify/Layout"] == "allset.uv_layout"


def test_shell_and_face_menus():
    s = mm.SHIFT_UV_SHELL
    assert _ring(s) == {"N": "Mapping", "NE": "Flip Along V", "E": "Optimize", "SE": "Align Shells",
                        "S": "Rotate Shell", "SW": "Layout", "W": "Unfold", "NW": "Flip Along U"}
    assert _list(s) == ["Auto Seams", "Match Grid", "Match UVs", "Normalize", "Straighten Border", "Straighten UVs",
                        "Unitize", "Distribute Shells", "Gather Shells", "Orient Shells", "Randomize Shells",
                        "Snap and Stack Shells", "Stack Shells", "Stack and Orient Shells", "Stack Similar Shells",
                        "Unstack Shells", "Tools", "Pinning"]
    assert _ring(s.radial["N"][1]) == {"N": "Planar Mapping", "NE": "Normal-Based Mapping", "NW": "Automatic Mapping"}
    f = mm.SHIFT_UV_FACE
    assert _ring(f) == {"N": "Mapping", "NE": "Straighten UVs", "E": "Optimize", "SE": "Create UV Shell",
                        "S": "Rotate Faces", "SW": "Layout", "W": "Unfold", "NW": "Normalize"}
    assert _list(f) == ["Cycle", "Flip", "Match Grid", "Match UVs", "Symmetrize", "Tools", "Pinning"]
    rows = dict(e for e in mm.SHIFT_UV.items if e != mm.DIVIDER)
    tools = rows["Tools"]
    assert _list(tools) == ["Cut Tool", "Sew Tool", "Optimize Tool", "Unfold Tool", "Grab Tool", "Lattice Tool",
                            "Pin Tool", "Pinch Tool", "Smear Tool", "Symmetrize Tool"]
    pinning = rows["Pinning"]
    assert _list(pinning)[:4] == ["Pin Selection", "Inverse Pinning", "Unpin Selection", "Unpin All"]


def _clear():
    if bpy.context.active_object is not None and bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)


def _grid():
    """A 4 x 4 quad grid in edit mode, one UV shell (UVs = x, y / 4), nothing selected."""
    _clear()
    n = 4
    verts = [(x, y, 0.0) for y in range(n + 1) for x in range(n + 1)]
    faces = [(y * (n + 1) + x, y * (n + 1) + x + 1, (y + 1) * (n + 1) + x + 1, (y + 1) * (n + 1) + x)
             for y in range(n) for x in range(n)]
    me = bpy.data.meshes.new("grid")
    me.from_pydata(verts, [], faces)
    me.uv_layers.new(name="UVMap")
    ob = bpy.data.objects.new("grid", me)
    bpy.context.collection.objects.link(ob)
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.mode_set(mode='EDIT')
    bm = bmesh.from_edit_mesh(me)
    uv = bm.loops.layers.uv.active
    for f in bm.faces:
        for loop in f.loops:
            loop[uv].uv = (loop.vert.co.x / n, loop.vert.co.y / n)
    bmesh.update_edit_mesh(me)
    return ob


def _middle_edge(bm):
    """The edge from (2, 1) to (2, 2): inside the grid, both ends inside too."""
    for e in bm.edges:
        cos = sorted((round(v.co.x), round(v.co.y)) for v in e.verts)
        if cos == [(2, 1), (2, 2)]:
            return e
    raise AssertionError("no middle edge")


def _has(points, a, b):
    segs = {tuple(sorted(((round(p[0], 4), round(p[1], 4)), (round(q[0], 4), round(q[1], 4)))))
            for p, q in zip(points[0::2], points[1::2])}
    return tuple(sorted((a, b))) in segs


def test_single_interior_cut_shows_as_border():
    ob = _grid()
    bm = bmesh.from_edit_mesh(ob.data)
    uv = bm.loops.layers.uv.active
    before = uvd.border_segments(bm, uv, uvd.shown_faces(bm, True))
    assert len(before) == 16, f"the grid's outline only: {len(before)}"
    edge = _middle_edge(bm)
    uvt.cut(bm, uv, [edge])
    bmesh.update_edit_mesh(ob.data)
    assert edge.seam and len(uvt.islands(bm, uv)) == 1, "one cut edge doesn't split the shell"
    after = uvd.border_segments(bm, uv, uvd.shown_faces(bm, True))
    assert len(after) == 18, f"the cut edge's two sides are borders now: {len(after)}"
    a = uv_arrays.read(ob, bm, uv, bpy.context.evaluated_depsgraph_get())
    pts = uv_arrays.border_points(a, uv_arrays.shown_faces(a, True)).tolist()
    assert len(pts) == 2 * 18, len(pts)
    assert _has(pts, (0.5, 0.25), (0.5, 0.5)), "the cut edge is in the drawn borders"
    assert edge in cut_sew.border_edges(bm, uv), "the 3D Cut and Sew tool shows it too"
    # sewing it back takes the border away
    uvt.sew(bm, uv, [edge])
    bmesh.update_edit_mesh(ob.data)
    assert len(uvd.border_segments(bm, uv, uvd.shown_faces(bm, True))) == 16


def test_cut_operator_then_drawn_borders():
    """allset.uv_cut (Cut UVs in the menu) on one selected interior edge: the UV Editor's cached border lines
    have it right away."""
    ob = _grid()
    bm = bmesh.from_edit_mesh(ob.data)
    ts = bpy.context.scene.tool_settings
    ts.use_uv_select_sync = True
    ts.mesh_select_mode = (False, True, False)
    for e in bm.edges:
        e.select_set(False)
    for f in bm.faces:
        f.select_set(False)
    _middle_edge(bm).select_set(True)
    bmesh.update_edit_mesh(ob.data)
    n0 = len(uvd.segments_of(ob, True))
    assert bpy.ops.allset.uv_cut() == {'FINISHED'}
    uvd._invalidate()       # what the depsgraph handler does after the cut
    assert len(uvd.segments_of(ob, True)) == n0 + 4, "two more border sides (4 line points)"


def _uv_area():
    scr = bpy.context.window.screen
    a = next(a for a in scr.areas if a.type in ('VIEW_3D', 'IMAGE_EDITOR'))
    a.ui_type = 'UV'
    return a, next(r for r in a.regions if r.type == 'WINDOW')


def test_rotate_clockwise_turns_clockwise():
    ob = _grid()
    ts = bpy.context.scene.tool_settings
    ts.use_uv_select_sync = True
    bpy.ops.mesh.select_all(action='SELECT')
    a, r = _uv_area()
    _label, action = mm.SHIFT_UV.radial["S"][1].radial["E"]
    op, props = action
    assert op == "transform.rotate"
    bm = bmesh.from_edit_mesh(ob.data)
    uv = bm.loops.layers.uv.active
    corner = next(l for f in bm.faces for l in f.loops if round(l.vert.co.x) == 4 and round(l.vert.co.y) == 4)
    vi = corner.vert.index
    with bpy.context.temp_override(area=a, region=r):
        bpy.ops.transform.rotate(**props)
    bm = bmesh.from_edit_mesh(ob.data)
    uv = bm.loops.layers.uv.active
    corner = next(l for f in bm.faces for l in f.loops if l.vert.index == vi)
    x, y = corner[uv].uv
    # (1, 1) about the centre (0.5, 0.5), a quarter turn clockwise -> (1, 0)
    assert math.isclose(x, 1.0, abs_tol=1e-4) and math.isclose(y, 0.0, abs_tol=1e-4), (x, y)
