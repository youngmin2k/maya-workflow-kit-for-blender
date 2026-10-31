"""Maya option windows for the key commands, Parent / Unparent / Ungroup, Duplicate Special,
Connect, Circularize, Make Hole and Insert Edge Loop (issues #33, #35). Fields / labels / defaults
follow Maya's option windows."""

import math
from importlib import import_module

import bmesh
import bpy
from mathutils import Vector

import kit

ow = import_module(kit.MODULE + ".operators.option_windows")
owe = import_module(kit.MODULE + ".operators.option_windows_edit")
tk = import_module(kit.MODULE + ".operators.time_keys")
menu_map = import_module(kit.MODULE + ".ui.menu_map")
menu_sets = import_module(kit.MODULE + ".ui.menu_sets")
notices = import_module(kit.MODULE + ".ui.notices")

U = 0.01          # Blender metres per Maya cm (the Maya Workflow Kit template units)

# window key -> Maya menu paths whose option box opens it
PATHS = {
    "delete_keys": ("Key/Delete Keys", "Edit/Keys/Delete Keys"),
    "cut_keys": ("Key/Cut Keys", "Edit/Keys/Cut Keys"),
    "copy_keys": ("Key/Copy Keys", "Edit/Keys/Copy Keys"),
    "paste_keys": ("Key/Paste Keys", "Edit/Keys/Paste Keys"),
    "scale_keys": ("Key/Scale Keys", "Edit/Keys/Scale Keys"),
    "snap_keys": ("Key/Snap Keys", "Edit/Keys/Snap Keys"),
    "parent": ("Edit/Parent",),
    "unparent": ("Edit/Unparent",),
    "ungroup": ("Edit/Ungroup",),
    "duplicate_special_maya": ("Edit/Duplicate Special",),
    "connect": ("Edit Mesh/Connect",),
    "connect_tool": ("Mesh Tools/Connect",),
    "circularize": ("Edit Mesh/Circularize",),
    "make_hole": ("Mesh Tools/Make Hole",),
    "insert_edge_loop": ("Mesh Tools/Insert Edge Loop",),
}

_SCOPE = [("objects", "Objects:", "Selected"), ("hierarchy", "Hierarchy:", "Selected"),
          ("channels", "Channels:", "All keyable"), ("driven", "Driven channels:", False), ("shapes", "Shapes:", True),
          ("time_range", "Time range:", "All"), ("start", "Start time:", 0.0), ("end", "End time:", 10.0)]
_DEL = [("method", "Method:", "Keys"), ("adjustment", "Adjustment:", "None"), ("connect", "Connect:", False)]

# (field name, label, default) in the window's screen order
FIELDS = {
    # (Control points: missing)
    "delete_keys": ("Delete Keys Options", "Delete Keys", _SCOPE + _DEL),
    # :92-95 (no Objects row)
    "cut_keys": ("Cut Keys Options", "Cut Keys", _SCOPE[1:] + _DEL),
    # :97-99
    "copy_keys": ("Copy Keys Options", "Copy Keys", _SCOPE[1:] + [("method", "Method:", "Keys")]),
    # :101-113
    "paste_keys": ("Paste Keys Options", "Paste Keys", [
        ("time_range", "Time range:", "Current"), ("start", "Start time:", 0.0), ("end", "End time:", 10.0),
        ("time_offset", "Time offset:", 0.0), ("value_offset", "Value offset:", 0.0), ("copies", "Copies:", 1),
        ("method", "Paste method:", "Merge"), ("replace_region", "Replace region:", "Time range")]),
    # :115-118
    "scale_keys": ("Scale Keys Options", "Scale Keys", _SCOPE + [
        ("method", "Method:", "Scale/Pivot"), ("only_specified", "", True), ("time_scale", "Time scale:", 1.0),
        ("time_pivot", "Time pivot:", 0.0), ("value_scale", "Value scale:", 1.0), ("value_pivot", "Value pivot:", 0.0),
        ("new_start", "New start time:", 1.0), ("new_end", "New end time:", 10.0)]),
    # :120-123
    "snap_keys": ("Snap Keys Options", "Snap Keys", _SCOPE + [
        ("snap", "Snap:", "Times"), ("time_multiple", "Snap times to multiple of:", 1.0),
        ("value_multiple", "Snap values to multiple of:", 1.0)]),
    # :62-75
    "parent": ("Parent Options", "Parent", [("preserve", "", True)]),
    "unparent": ("Unparent Options", "Unparent", [("preserve", "", True)]),
    "ungroup": ("Ungroup Options", "Ungroup", [("under", "Ungroup under:", "Parent"), ("preserve", "", True)]),
    # :154-167
    "duplicate_special_maya": ("Duplicate Special Options", "Duplicate Special", [
        ("geometry_type", "Geometry type:", "Copy"), ("group_under", "Group under:", "Parent"), ("smart", "", False),
        ("translate", "Translate:", (0.0, 0.0, 0.0)), ("rotate", "Rotate:", (0.0, 0.0, 0.0)),
        ("scale", "Scale:", (1.0, 1.0, 1.0)), ("copies", "Number of copies:", 1)]),
    # :136-139
    "connect": ("Connect Components Options", "Connect", [("edge_flow", "", False),
                                                          ("adjust_edge_flow", "Adjust Edge Flow:", 1.0)]),
    # :252-256
    "connect_tool": ("Connect Tool", "Connect", [("slide", "Slide:", 0.5), ("segments", "Segments:", 1)]),
    # :141-152 (Relax Interior / Alignment / Smoothing Angle / Supporting Edges: missing)
    "circularize": ("Polygon Circularize Options", "Circularize", [
        ("normal_offset", "Normal Offset:", 0.0), ("radial_offset", "Radial Offset:", 0.0), ("twist", "Twist:", 0.0),
        ("evenly", "Evenly Distribute:", True), ("divisions", "Add Divisions:", 0)]),
    # :247-250
    "make_hole": ("Make Hole Tool", "Make Hole", [("merge_mode", "Merge mode:", "None")]),
    # :239-245
    "insert_edge_loop": ("Insert Edge Loop Tool", "Insert Edge Loop", [
        ("maintain", "Maintain position:", "Relative distance from edge"), ("loops", "Number of edge loops:", 2),
        ("edge_flow", "", False), ("adjust_edge_flow", "Adjust Edge Flow:", 1.0),
        ("smoothing", "Smoothing angle:", 30.0)]),     # the kit Offset Edge Loop tool honours it
}


def _clear():
    if bpy.context.active_object is not None and bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    for coll in (bpy.data.meshes, bpy.data.actions):
        for idb in list(coll):
            coll.remove(idb)
    us = bpy.context.scene.unit_settings
    us.system, us.length_unit, us.scale_length = 'METRIC', 'CENTIMETERS', 1.0
    bpy.context.window_manager.allset_cb_selected = ""
    for key in FIELDS:
        ow.store(key, None)


def _select(*obs):
    for o in bpy.context.scene.objects:
        o.select_set(False)
    for o in obs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = obs[-1] if obs else None


def _run(key, **values):
    res = ow.run(ow._BY_KEY[key], bpy.context, values)
    assert not isinstance(res, str), (key, res)
    return res


# --- windows ----------------------------------------------------------------------------------------

def test_every_path_opens_its_window():
    for key, paths in PATHS.items():
        for path in paths:
            assert path in menu_map.MAP, path
            assert menu_sets.option_kind(path) == "window", (path, menu_sets.option_kind(path))
            assert ow.find_path(path).key == key, (path, ow.find_path(path).key)
            if path.endswith("Scale Keys"):        # mapped now (Mesh Tools/Make Hole keeps its "differs" note)
                assert path not in notices.NOTICES, f"{path} is mapped now: its notice must go"
        assert hasattr(bpy.ops.allset, "opt_" + key)


def test_fields_labels_defaults_are_maya():
    for key, (title, button, fields) in FIELDS.items():
        w = ow._BY_KEY[key]
        assert (w.title, w.action) == (title, button), (key, w.title, w.action)
        got = [(f.name, f.label, f.default) for f in w.fields]
        assert got == fields, (key, got)
        rna = getattr(bpy.ops.allset, "opt_" + key).get_rna_type()
        for f in w.fields:
            d = rna.properties[f.name].default_array if f.kind.startswith("vec") else rna.properties[f.name].default
            want = f.default
            if f.kind == "enum":
                assert d == want and want in f.items, (key, f.name, d)
            elif f.kind.startswith("vec"):
                assert tuple(d) == tuple(want), (key, f.name)
            else:
                assert abs(float(d) - float(want)) < 1e-6, (key, f.name, d)


def test_key_menu_items_run_with_maya_factory_options():
    m = menu_map.MAP
    for menu in ("Key", "Edit/Keys"):
        for name, act in (("Cut", "CUT"), ("Copy", "COPY"), ("Snap", "SNAP")):
            assert m[f"{menu}/{name} Keys"] == ("allset.time_keys", {"action": act, "time_range": 'ALL'})
        assert m[f"{menu}/Paste Keys"] == ("allset.time_keys", {"action": "PASTE"})     # Current + Merge
        assert m[f"{menu}/Scale Keys"] == "allset.opt_scale_keys"


# --- key commands -----------------------------------------------------------------------------------

BASE = [(0, 0), (5, 10), (10, 0), (15, 10), (20, 0)]           # BASE (frame, Maya value)
TARGET = [(0, 1), (3, 2), (6, 3), (9, 4), (12, 5), (20, 6)]


def _keyed(name, keys, parent=None):
    me = bpy.data.meshes.new(name)
    ob = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(ob)
    if parent is not None:
        ob.parent = parent
    for t, v in keys:
        ob.location.x = v * U
        ob.keyframe_insert("location", index=0, frame=t)
    for kp in kit.fcurves(ob).find("location", index=0).keyframe_points:
        kp.interpolation = 'LINEAR'
    return ob


def _keys(ob):
    fcs = kit.fcurves(ob)
    fc = fcs.find("location", index=0) if fcs is not None else None
    if fc is None:
        return None
    return sorted([round(kp.co.x, 3), round(kp.co.y / U, 3)] for kp in fc.keyframe_points)


def _close(a, b):
    assert a is not None and len(a) == len(b) and all(abs(x[0] - y[0]) < 1e-3 and abs(x[1] - y[1]) < 1e-3
                                                      for x, y in zip(a, b)), (a, b)


def test_delete_keys_ranges_hierarchy_methods():
    _clear()
    a = _keyed("a", BASE)
    _select(a)
    _run("delete_keys", time_range="Start/End", start=4, end=12)
    _close(_keys(a), [[0, 0], [15, 10], [20, 0]])                       # Maya clear_keys
    _run("delete_keys")                                                  # Time range All (factory)
    assert _keys(a) is None, "every key goes, the curve too"

    _clear()
    a = _keyed("a", BASE)
    _select(a)
    _run("delete_keys", time_range="Start/End", start=4, end=12, method="Segments")
    _close(_keys(a), [[0, 0], [4, 8], [12, 4], [15, 10], [20, 0]])      # clear_curve
    _clear()
    a = _keyed("a", BASE)
    _select(a)
    _run("delete_keys", time_range="Start/End", start=4, end=12, adjustment="Collapse")
    _close(_keys(a), [[0, 0], [7, 10], [12, 0]])                          # clear_areaCollapse
    _clear()
    a = _keyed("a", BASE)
    _select(a)
    _run("delete_keys", time_range="Start/End", start=4, end=12, method="Segments", connect=True)
    _close(_keys(a), [[0, 0], [4, 8], [7, 14], [12, 4]])                 # clear_curveConnect

    _clear()
    par = _keyed("par", BASE)
    kid = _keyed("kid", BASE, parent=par)
    _select(par)
    _run("delete_keys")
    assert _keys(par) is None and _keys(kid) is not None, "Hierarchy Selected leaves the child"
    par = _keyed("par2", BASE)
    kid.parent = par
    _select(par)
    _run("delete_keys", hierarchy="Below")
    assert _keys(par) is None and _keys(kid) is None, "Hierarchy Below reaches the child"


def test_cut_copy_paste_options():
    _clear()
    src = _keyed("src", BASE)
    dst = _keyed("dst", TARGET)
    _select(src)
    _run("copy_keys", time_range="Start/End", start=4, end=16)           # keys 5 (10), 10 (0), 15 (10)
    _select(dst)
    _run("paste_keys", time_range="Start", start=3)                     # Merge (factory)
    _close(_keys(dst), [[0, 1], [3, 2], [4, 10], [6, 3], [9, 0], [12, 5], [14, 10], [20, 6]])   # paste_merge_at3
    for method, region, kw, want in (
            ("Insert", "Time range", dict(time_range="Start", start=3),
             [[0, 1], [4, 10], [9, 0], [14, 10], [18, 3], [21, 4], [24, 5], [32, 6]]),            # paste_insert_at3
            ("Replace", "Time range", dict(time_range="Start/End", start=3, end=15),
             [[0, 1], [4, 10], [9, 0], [14, 10], [20, 6]]),                                        # paste_replace_3_15
            ("Replace", "Entire curve", dict(time_range="Start", start=3), [[4, 10], [9, 0], [14, 10]]),
            ("Merge", "Time range", dict(time_range="Start", start=0, time_offset=10, copies=2),     # offset10_copies2
             [[0, 1], [3, 2], [6, 3], [9, 4], [11, 10], [12, 5], [16, 0], [20, 6], [21, 10], [33, 10], [38, 0],
              [43, 10]]),
            ("Merge", "Time range", dict(time_range="Start", start=3, value_offset=5),             # valueoffset5
             [[0, 1], [3, 2], [4, 15], [6, 3], [9, 5], [12, 5], [14, 15], [20, 6]]),
            ("Merge", "Time range", dict(time_range="Clipboard"),                                    # merge_clipboard
             [[0, 1], [3, 2], [5, 10], [6, 3], [9, 4], [10, 0], [12, 5], [15, 10], [20, 6]])):
        bpy.data.objects.remove(dst)
        dst = _keyed("dst", TARGET)
        _select(dst)
        _run("paste_keys", method=method, replace_region=region, **kw)
        _close(_keys(dst), want)
    # copies of a Time range All copy follow each other (paste_allcopy_copies2_at30)
    _clear()
    src = _keyed("src", BASE)
    _select(src)
    _run("copy_keys")
    dst = _keyed("dst", [(0, 100)])
    _select(dst)
    bpy.context.scene.frame_set(30)
    _run("paste_keys", copies=2)
    _close(_keys(dst), [[0, 100], [30, 0], [35, 10], [40, 0], [45, 10], [50, 0], [55, 10], [60, 0], [65, 10],
                        [70, 0]])
    # Cut = copy + delete; Segments copies the range ends (cutpaste_curve)
    _clear()
    src = _keyed("src", BASE)
    _select(src)
    _run("cut_keys", time_range="Start/End", start=4, end=12, method="Segments")
    _close(_keys(src), [[0, 0], [4, 8], [12, 4], [15, 10], [20, 0]])
    dst = _keyed("dst", [(0, 100), (40, 100)])
    _select(dst)
    _run("paste_keys", time_range="Start", start=30)
    _close(_keys(dst), [[0, 100], [30, 8], [31, 10], [36, 0], [38, 4], [40, 100]])


def test_scale_keys():
    _clear()
    a = _keyed("a", BASE)
    _select(a)
    _run("scale_keys", time_scale=2, time_pivot=0)
    _close(_keys(a), [[0, 0], [10, 10], [20, 0], [30, 10], [40, 0]])        # scale_t2_p0_all: 5 -> 10
    _clear()
    a = _keyed("a", BASE)
    _select(a)
    _run("scale_keys", value_scale=2, value_pivot=5)
    _close(_keys(a), [[0, -5], [5, 15], [10, -5], [15, 15], [20, -5]])        # scale_v2_p5_all
    _clear()
    a = _keyed("a", BASE)
    _select(a)
    _run("scale_keys", time_range="Start/End", start=4, end=12, time_scale=2, time_pivot=5, only_specified=False)
    _close(_keys(a), [[0, 0], [5, 10], [15, 0], [20, 10], [25, 0]])          # scale_t2_p5_range_notspecified
    _clear()
    a = _keyed("a", BASE)
    _select(a)
    _run("scale_keys", method="Start/End", time_range="Start/End", start=0, end=20, new_start=10, new_end=50)
    _close(_keys(a), [[10, 0], [20, 10], [30, 0], [40, 10], [50, 0]])        # scale_startend_0_20_to_10_50


def test_snap_keys():
    _clear()
    a = _keyed("a", [(0.4, 1.3), (5.6, 2.74), (10.2, -1.26)])
    _select(a)
    _run("snap_keys")
    _close(_keys(a), [[0, 1.3], [6, 2.74], [10, -1.26]])                     # snap_time1
    _clear()
    a = _keyed("a", [(0.4, 1.3), (5.6, 2.74), (10.2, -1.26)])
    _select(a)
    _run("snap_keys", snap="Both", time_multiple=2, value_multiple=0.5)
    _close(_keys(a), [[0, 1.5], [6, 2.5], [10, -1.5]])                       # snap_both


def test_time_slider_copy_paste_still_half_frame():
    _clear()
    a = _keyed("a", [(1, 0), (24.3, 3)])
    _select(a)
    bpy.context.window_manager.allset_time_range_on = False
    bpy.context.scene.frame_set(24)
    assert tk.copy_keys(bpy.context, 24, 24) == 1, "a key within half a frame of the Time Slider frame"
    tk.paste_keys(bpy.context, 40)
    assert [round(x, 3) for x, _y in _keys(a)] == [1.0, 24.3, 40.3]


# --- Edit menu ----------------------------------------------------------------------------------------

def _empty(name, loc=(0, 0, 0)):
    ob = bpy.data.objects.new(name, None)
    bpy.context.collection.objects.link(ob)
    ob.location = loc
    return ob


def test_parent_unparent_preserve_off():
    _clear()
    child = _empty("child", (1, 2, 3))
    par = _empty("par", (10, 0, 0))
    par.rotation_euler.z = math.radians(90)
    par.scale = (2, 2, 2)
    bpy.context.view_layer.update()
    _select(child, par)
    _run("parent", preserve=False)
    bpy.context.view_layer.update()
    assert child.parent is par and (child.location - Vector((1, 2, 3))).length < 1e-6, "local values kept"
    want = par.matrix_world @ Vector((1, 2, 3))
    assert (child.matrix_world.translation - want).length < 1e-5, "it moves with the parent (Maya parent -r)"
    _select(child)
    _run("unparent", preserve=False)
    bpy.context.view_layer.update()
    assert child.parent is None and (child.matrix_world.translation - Vector((1, 2, 3))).length < 1e-6
    # factory Preserve position: the world position stays
    _select(child, par)
    _run("parent")
    bpy.context.view_layer.update()
    assert (child.matrix_world.translation - Vector((1, 2, 3))).length < 1e-5


def test_ungroup_options():
    _clear()
    par = _empty("par", (10, 0, 0))
    grp = _empty("grp", (0, 0, 5))
    grp.parent = par
    child = _empty("child", (1, 2, 3))
    child.parent = grp
    bpy.context.view_layer.update()
    world = child.matrix_world.translation.copy()
    _select(grp)
    _run("ungroup", preserve=False)
    bpy.context.view_layer.update()
    assert child.parent is par and (child.location - Vector((1, 2, 8))).length < 1e-6, child.location   # Maya 1 7 3
    grp = _empty("grp2", (0, 0, 5))
    grp.parent = par
    child.parent = grp
    child.location = (1, 2, 3)
    bpy.context.view_layer.update()
    world = child.matrix_world.translation.copy()
    _select(grp)
    _run("ungroup", under="World")
    bpy.context.view_layer.update()
    assert child.parent is None and (child.matrix_world.translation - world).length < 1e-5   # ungroup -world


def test_duplicate_special_smart_transform():
    _clear()
    me = bpy.data.meshes.new("m")
    ob = bpy.data.objects.new("pCube1", me)
    bpy.context.collection.objects.link(ob)
    _select(ob)
    _run("duplicate_special_maya", translate=(2.0, 0.0, 0.0), copies=2)
    assert len(bpy.context.selected_objects) == 2
    xs = sorted(round(o.location.x / U, 3) for o in bpy.context.selected_objects)
    assert xs == [2.0, 4.0], xs
    _clear()
    ob = bpy.data.objects.new("pCube1", bpy.data.meshes.new("m"))
    bpy.context.collection.objects.link(ob)
    _select(ob)
    bpy.ops.allset.duplicate_special()
    copy = bpy.context.active_object
    copy.location.x += 3 * U
    bpy.context.view_layer.update()
    _run("duplicate_special_maya", smart=True, copies=2)
    xs = sorted(round(o.location.x / U, 3) for o in bpy.context.scene.objects)
    assert xs == [0.0, 3.0, 6.0, 9.0], xs


# --- Edit Mesh / Mesh Tools -----------------------------------------------------------------------------

def _grid():
    """Maya polyPlane sx 4 sy 4 w 4 h 4 in Blender axes (Maya (x, y, z) -> Blender (x, -z, y)), the 4 middle faces
    selected (Maya circularize case)."""
    _clear()
    bpy.ops.mesh.primitive_grid_add(x_subdivisions=4, y_subdivisions=4, size=4)
    ob = bpy.context.active_object
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_mode(type='FACE')
    bm = bmesh.from_edit_mesh(ob.data)
    for f in bm.faces:
        c = f.calc_center_median()
        f.select = abs(c.x) < 1.01 and abs(c.y) < 1.01
    bm.select_flush_mode()
    bmesh.update_edit_mesh(ob.data)
    return ob


def _vert_at(ob, x, y, tol=0.02):
    bm = bmesh.from_edit_mesh(ob.data)
    return next((v.co.copy() for v in bm.verts if abs(v.co.x - x) < tol and abs(v.co.y - y) < tol), None)


def _loop_radius(ob):
    bm = bmesh.from_edit_mesh(ob.data)
    rs = [math.hypot(v.co.x, v.co.y) for v in bm.verts if 0.3 < math.hypot(v.co.x, v.co.y) < 1.9]
    return sum(rs) / len(rs), len(rs)


def test_circularize_options():
    ob = _grid()
    _run("circularize")
    r, n = _loop_radius(ob)
    assert n == 8 and abs(r - 1.2071) < 1e-3, (r, n)                   # circ_default
    ob = _grid()
    _run("circularize", radial_offset=0.5 / U)
    assert abs(_loop_radius(ob)[0] - 1.7071) < 1e-3                       # circ_radial05
    ob = _grid()
    bm = bmesh.from_edit_mesh(ob.data)
    i = next(v.index for v in bm.verts if (v.co - Vector((-1.0, -1.0, 0.0))).length < 1e-4)   # Maya vtx 6
    _run("circularize", twist=45)
    bm = bmesh.from_edit_mesh(ob.data)
    bm.verts.ensure_lookup_table()
    # circ_twist45: Maya vtx 6 (-1, 0, 1) -> (0, 0, 1.2071) (untwisted: -0.8536, 0, 0.8536); Blender (x, -z, y)
    assert (bm.verts[i].co - Vector((0.0, -1.2071, 0.0))).length < 1e-3, bm.verts[i].co
    ob = _grid()
    _run("circularize", normal_offset=0.3 / U)
    centre = _vert_at(ob, 0.0, 0.0)
    assert centre is not None and abs(centre.z - 0.3) < 1e-4, centre      # circ_normal03: the inner vertex too
    ob = _grid()
    _run("circularize", divisions=2)
    r, n = _loop_radius(ob)
    assert n == 24 and abs(r - 1.1544) < 1e-3, (r, n)                     # circ_divisions2
    assert _vert_at(ob, 0.8162, -0.8162) is not None
    bpy.ops.object.mode_set(mode='OBJECT')


def _sphere_edges(ob):
    """The two latitude edges between longitudes 90 and 135 degrees on the equator and the ring below
    (Maya connect case: e[20], e[28] of an 8 x 8 sphere)."""
    bm = bmesh.from_edit_mesh(ob.data)
    out = []
    for e in bm.edges:
        a, b = e.verts
        if abs(a.co.z - b.co.z) > 1e-4 or abs(a.co.z) > 0.4:
            continue
        angs = sorted(round(math.degrees(math.atan2(v.co.y, v.co.x))) % 360 for v in e.verts)
        if angs == [90, 135] and (abs(a.co.z) < 1e-4 or abs(a.co.z + 0.38268) < 1e-3):
            out.append(e)
    return bm, out


def _connect(flow, **values):
    _clear()
    bpy.ops.mesh.primitive_uv_sphere_add(segments=8, ring_count=8, radius=1.0)
    ob = bpy.context.active_object
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_mode(type='EDGE')
    bpy.ops.mesh.select_all(action='DESELECT')
    bm, edges = _sphere_edges(ob)
    assert len(edges) == 2, len(edges)
    for e in edges:
        e.select = True
    n0 = len(bm.verts)
    bmesh.update_edit_mesh(ob.data)
    _run("connect", edge_flow=flow, **values)
    bm = bmesh.from_edit_mesh(ob.data)
    bm.verts.ensure_lookup_table()
    new = [bm.verts[i].co.copy() for i in range(n0, len(bm.verts))]
    bpy.ops.object.mode_set(mode='OBJECT')
    return sorted(new, key=lambda c: c.z)


def test_connect_edge_flow():
    flat = _connect(False)
    assert len(flat) == 2
    assert abs(math.hypot(flat[1].x, flat[1].y) - 0.92388) < 1e-4, flat   # connect_flat: the equator midpoint
    flow = _connect(True)
    # connect_flow1: radius 0.94106 below, 1.01859 on the equator; connect_flow05: halfway
    assert abs(math.hypot(flow[0].x, flow[0].y) - 0.94106) < 1e-3, flow
    assert abs(math.hypot(flow[1].x, flow[1].y) - 1.01859) < 1e-3, flow
    half = _connect(True, adjust_edge_flow=0.5)
    assert abs(math.hypot(half[1].x, half[1].y) - 0.97124) < 1e-3, half


def test_connect_tool_segments_slide():
    _clear()
    bpy.ops.mesh.primitive_plane_add(size=2)
    ob = bpy.context.active_object
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_mode(type='EDGE')
    bm = bmesh.from_edit_mesh(ob.data)
    for e in bm.edges:
        e.select = abs(e.verts[0].co.x - e.verts[1].co.x) < 1e-6       # the two edges along Y
    bm.select_flush_mode()
    bmesh.update_edit_mesh(ob.data)
    _run("connect_tool", segments=2)
    bm = bmesh.from_edit_mesh(ob.data)
    ys = sorted({round(v.co.y, 4) for v in bm.verts})
    assert ys == [-1.0, -0.3333, 0.3333, 1.0], ys
    bpy.ops.object.mode_set(mode='OBJECT')
    # Slide 0.25, one segment: both new points on the same side, the new edge parallel to the others
    _clear()
    bpy.ops.mesh.primitive_plane_add(size=2)
    ob = bpy.context.active_object
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_mode(type='EDGE')
    bm = bmesh.from_edit_mesh(ob.data)
    for e in bm.edges:
        e.select = abs(e.verts[0].co.x - e.verts[1].co.x) < 1e-6
    bm.select_flush_mode()
    bmesh.update_edit_mesh(ob.data)
    _run("connect_tool", slide=0.25)
    bm = bmesh.from_edit_mesh(ob.data)
    new = [v for v in bm.verts if abs(abs(v.co.y) - 1.0) > 1e-4]
    assert len(new) == 2 and abs(new[0].co.y - new[1].co.y) < 1e-6 and abs(abs(new[0].co.y) - 0.5) < 1e-6, \
        [tuple(v.co) for v in new]
    bpy.ops.object.mode_set(mode='OBJECT')


def _hole_scene():
    """Maya hole case: a 4 x 4 face and a 1 x 1 stamp centred at Maya (0.5, 0.5, 0.25) = Blender (0.5, -0.25, 0.5)."""
    _clear()
    me = bpy.data.meshes.new("m")
    bm = bmesh.new()
    big = [bm.verts.new(c) for c in ((-2, -2, 0), (2, -2, 0), (2, 2, 0), (-2, 2, 0))]
    small = [bm.verts.new(Vector(c) + Vector((0.5, -0.25, 0.5))) for c in
             ((-0.5, -0.5, 0), (0.5, -0.5, 0), (0.5, 0.5, 0), (-0.5, 0.5, 0))]
    bm.faces.new(big)
    bm.faces.new(small)
    bm.to_mesh(me)
    ob = bpy.data.objects.new("m", me)
    bpy.context.collection.objects.link(ob)
    _select(ob)
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_mode(type='FACE')
    bm = bmesh.from_edit_mesh(ob.data)
    bm.faces.ensure_lookup_table()
    for f in bm.faces:
        f.select = True
    bm.faces.active = bm.faces[1]
    bmesh.update_edit_mesh(ob.data)
    return ob


def test_make_hole_merge_modes():
    ob = _hole_scene()
    _run("make_hole")                                       # None (factory): nothing moves
    bm = bmesh.from_edit_mesh(ob.data)
    assert any((v.co - Vector((1.0, 0.25, 0.5))).length < 1e-5 for v in bm.verts)
    bpy.ops.object.mode_set(mode='OBJECT')
    ob = _hole_scene()
    _run("make_hole", merge_mode="First")                   # hole_0: the stamp moves onto the face's centre
    bm = bmesh.from_edit_mesh(ob.data)
    assert any((v.co - Vector((0.5, 0.5, 0.0))).length < 1e-5 for v in bm.verts)
    bpy.ops.object.mode_set(mode='OBJECT')
    ob = _hole_scene()
    _run("make_hole", merge_mode="Project Second")          # hole_5: the face goes up to the stamp's plane
    bm = bmesh.from_edit_mesh(ob.data)
    assert any((v.co - Vector((2.0, 2.0, 0.5))).length < 1e-5 for v in bm.verts)
    bpy.ops.object.mode_set(mode='OBJECT')


def test_insert_edge_loop_values_reach_the_kit_tool():
    """LOOP: the window's values go to the kit Insert Edge Loop tool (Scene.allset_loop_tools), not to
    Blender's Loop Cut."""
    w = ow._BY_KEY["insert_edge_loop"]
    v = {**w.defaults(), "maintain": "Multiple edge loops", "loops": 3, "edge_flow": True, "adjust_edge_flow": 0.5,
         "smoothing": 45.0}
    s = owe.insert_edge_loop_options(bpy.context, v)
    assert (s.iel_position, s.iel_loops, s.iel_edge_flow, s.iel_adjust_flow, s.iel_smoothing) == (
        'MULTIPLE', 3, True, 0.5, 45.0)
    v.update(maintain="Equal distance from edge", edge_flow=False)
    owe.insert_edge_loop_options(bpy.context, v)
    assert (s.iel_position, s.iel_edge_flow) == ('EQUAL', False)
    s.property_unset("iel_position")
    for name in ("iel_loops", "iel_edge_flow", "iel_adjust_flow", "iel_smoothing"):
        s.property_unset(name)

