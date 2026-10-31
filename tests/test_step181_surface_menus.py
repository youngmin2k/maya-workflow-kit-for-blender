"""The Surfaces menu leaves mapped to the kit's NURBS surface commands, their Maya option windows
(titles / fields / defaults), shelf routing and notices.
Geometry: tests of operators/surfaces_maya.py."""

import types
from importlib import import_module

import bpy

import kit

compat = import_module(kit.MODULE + ".compat")
menu_map = import_module(kit.MODULE + ".ui.menu_map")
menu_sets = import_module(kit.MODULE + ".ui.menu_sets")
menu_data = import_module(kit.MODULE + ".ui.menu_data")
notices = import_module(kit.MODULE + ".ui.notices")
shelf_map = import_module(kit.MODULE + ".ui.shelf_map")
ow = import_module(kit.MODULE + ".operators.option_windows")
ows = import_module(kit.MODULE + ".operators.option_windows_surfaces")

# Surfaces leaf -> (operator, props)
MAPPED = {
    "Surfaces/Loft": ("allset.loft", {}),
    "Surfaces/Planar": ("allset.surface_planar", {}),
    "Surfaces/Revolve": ("allset.revolve", {}),
    "Surfaces/Extrude": ("allset.surface_extrude", {}),
    "Surfaces/Birail/Birail 1 Tool": ("allset.birail1", {}),
    "Surfaces/Boundary": ("allset.surface_boundary", {"kind": 'BOUNDARY'}),
    "Surfaces/Square": ("allset.surface_boundary", {"kind": 'SQUARE'}),
    "Surfaces/Attach": ("allset.surface_attach", {}),
    "Surfaces/Detach": ("allset.surface_detach", {}),
    "Surfaces/Insert Isoparms": ("allset.surface_insert_isoparm", {}),
    "Surfaces/Duplicate NURBS Patch": ("allset.duplicate_nurbs_patch", {}),
    "Surfaces/Reverse Direction": ("allset.surface_reverse", {}),
    "Surfaces/Rebuild": ("allset.surface_rebuild", {}),
    "Surfaces/Bevel Plus": ("allset.bevel_plus", {}),
    "Surfaces/Open/Close": ("curve.cyclic_toggle", {}),
}

# Surfaces leaf -> (window key, Maya title, command button, the operator call the default values make)
WINDOWS = {
    "Surfaces/Loft": ("loft", "Loft Options", "Loft", "loft", dict(
        uniform=True, auto_reverse=True, close=False, degree='3', section_spans=1)),
    "Surfaces/Revolve": ("revolve", "Revolve Options", "Revolve", "revolve", dict(
        axis='Y', pivot='OBJECT', pivot_point=(0.0, 0.0, 0.0), start_sweep=0.0, end_sweep=360.0, degree='3',
        segments=8)),
    "Surfaces/Extrude": ("surface_extrude", "Extrude Options", "Extrude", "surface_extrude", dict(
        style='TUBE', length=1.0, direction='NORMAL', result_position='PROFILE', pivot='CLOSEST')),
    "Surfaces/Birail/Birail 1 Tool": ("birail1", "Birail 1 Options", "Birail 1 Tool", "birail1",
                                      dict(proportional=True)),
    "Surfaces/Boundary": ("surface_boundary", "Boundary Options", "Boundary", "surface_boundary",
                          dict(kind='BOUNDARY')),
    "Surfaces/Square": ("surface_square", "Square Surface Options", "Square Surface", "surface_boundary",
                        dict(kind='SQUARE')),
    "Surfaces/Attach": ("surface_attach", "Attach Surfaces Options", "Attach", "surface_attach", dict(
        method='BLEND', bias=0.5, keep_originals=True)),
    "Surfaces/Detach": ("surface_detach", "Detach Surfaces Options", "Detach", "surface_detach",
                        dict(keep_original=False)),
    "Surfaces/Reverse Direction": ("surface_reverse", "Reverse Surface Direction Options", "Reverse",
                                   "surface_reverse", dict(direction='U')),
    "Surfaces/Rebuild": ("surface_rebuild", "Rebuild Surface Options", "Rebuild", "surface_rebuild", dict(
        spans_u=4, spans_v=4, degree_u='3', degree_v='3')),
}


def _surface_leaves():
    """(path, mapped) per drawn Surfaces leaf (ui/menu_sets rules, = tools/menu_count.py)."""
    out = {}
    for path, it in menu_sets.iter_items():
        if path.startswith("Surfaces/") and (not menu_sets.sub_items(path, it) or path in menu_map.MAP):
            out[path] = path in menu_map.MAP
    return out


class _Recorder:
    """Stands in for ``bpy`` in option_windows_surfaces: records the operator call a window's run makes."""

    def __init__(self):
        self.calls = []
        rec = self

        class _Ops:
            def __getattr__(self, name):
                def call(mode, **kw):
                    rec.calls.append((name, mode, kw))
                    return {'FINISHED'}
                return call
        self.ops = types.SimpleNamespace(allset=_Ops())


def _call(window, values=None):
    real, rec = ows.bpy, _Recorder()
    ows.bpy = rec
    try:
        res = ow.run(window, bpy.context, values)
    finally:
        ows.bpy = real
    assert res == {'FINISHED'}, (window.key, res)
    assert len(rec.calls) == 1, rec.calls
    return rec.calls[0]


def test_surfaces_menu_mapped():
    for path, (op, props) in MAPPED.items():
        assert path in menu_map.MAP, path
        kind, target, got = menu_map.spec(path)
        assert (target, got) == (op, props), (path, target, got)
    # no stand-ins left: the Screw modifier / curve ops were Revolve / Reverse / Insert Isoparms once
    for path in ("Surfaces/Revolve", "Surfaces/Reverse Direction", "Surfaces/Insert Isoparms"):
        assert menu_map.spec(path)[1].startswith("allset."), path
    # the Curves menu keeps its own Reverse Direction / Insert Knot
    assert menu_map.spec("Curves/Reverse Direction")[1] == "curve.switch_direction"
    leaves = _surface_leaves()
    working = sum(leaves.values())
    print(f"Surfaces menu: {working} / {len(leaves)} working")
    assert len(leaves) == 41 and working >= 15, (working, len(leaves))


def test_operators_exist_once_built():
    # the operators come from operators/surfaces_maya.py checked when they are registered
    missing = []
    for path, (op, _props) in MAPPED.items():
        mod, name = op.split(".")
        if not compat.has_op(getattr(bpy.ops, mod), name):
            missing.append(op)
    print("surface operators not registered yet:", sorted(set(missing)))
    if compat.has_op(bpy.ops.allset, "loft") and compat.has_op(bpy.ops.allset, "revolve"):
        assert not missing, missing


def test_windows_bound_with_maya_titles_and_factory_values():
    for path, (key, title, button, op, factory) in WINDOWS.items():
        w = ow.find_path(path)
        assert w is not None and w.key == key, (path, w and w.key)
        assert path in w.paths and path in menu_data.OPTION_BOXES, path
        assert (w.title, w.action) == (title, button), (path, w.title, w.action)
        assert menu_sets.option_kind(path) == "window", path
        rna = getattr(bpy.ops.allset, "opt_" + key).get_rna_type()
        for f in w.fields:
            assert f.name in rna.properties, (key, f.name)
        # the default values make the expected operator call (= the command Maya runs by default)
        name, mode, kw = _call(w)
        assert (name, mode) == (op, 'EXEC_DEFAULT'), (key, name, mode)
        assert kw == factory, (key, kw)
        # allset.loft also exists as curve_tools' mesh loft: check the props once surfaces_maya registered
        if compat.has_op(bpy.ops.allset, "revolve") and compat.has_op(bpy.ops.allset, op):
            props = getattr(bpy.ops.allset, op).get_rna_type().properties
            for k, v in kw.items():
                assert k in props, (op, k)
                if k == "kind":         # Boundary / Square share allset.surface_boundary: the window picks the kind
                    continue
                d = props[k]
                default = tuple(d.default_array) if getattr(d, "is_array", False) else d.default
                assert default == v or (isinstance(v, float) and abs(default - v) < 1e-6), (op, k, default, v)


def test_window_fields_follow_maya():
    d = ow._BY_KEY
    # non-factory choices reach the operator
    assert _call(d["loft"], {"parameterization": "Chord length", "degree": "Linear", "close": True,
                             "section_spans": 3})[2] == dict(uniform=False, auto_reverse=True, close=True, degree='1',
                                                             section_spans=3)
    kw = _call(d["revolve"], {"axis": "X", "pivot": "Preset", "pivot_point": (1.0, 2.0, 3.0), "end_sweep": 180.0,
                              "segments": 4, "degree": "Linear"})[2]
    assert kw == dict(axis='X', pivot='PRESET', pivot_point=(1.0, 2.0, 3.0), start_sweep=0.0, end_sweep=180.0,
                      degree='1', segments=4), kw
    kw = _call(d["surface_extrude"], {"style": "Distance", "direction": "Specify", "direction_vector": "Z axis",
                                      "length": 2.5})[2]
    assert kw["style"] == 'DISTANCE' and kw["direction"] == 'Z' and kw["length"] == 2.5, kw
    kw = _call(d["surface_extrude"], {"result_position": "At path", "pivot": "Component"})[2]
    assert (kw["result_position"], kw["pivot"]) == ('PATH', 'COMPONENT'), kw
    assert _call(d["birail1"], {"transform_control": "Non proportional"})[2] == dict(proportional=False)
    assert _call(d["surface_attach"], {"method": "Connect", "keep_originals": False})[2]["method"] == 'CONNECT'
    for label, want in (("V", 'V'), ("Swap", 'SWAP'), ("Both", 'BOTH')):
        assert _call(d["surface_reverse"], {"direction": label})[2] == dict(direction=want)
    assert _call(d["surface_rebuild"], {"degree_u": "1 Linear", "degree_v": "5", "spans_v": 7})[2] == dict(
        spans_u=4, spans_v=7, degree_u='1', degree_v='5')
    # Maya field order of the radio groups (Reverse Surface Direction / Extrude option windows)
    reverse = {f.name: f for f in d["surface_reverse"].fields}
    assert reverse["direction"].items == ("U", "V", "Swap", "Both")
    extrude = {f.name: f for f in d["surface_extrude"].fields}
    assert extrude["style"].items == ("Distance", "Flat", "Tube")
    # what the kit can't follow is listed, not hidden
    assert any("Bezier" in m for m in d["loft"].missing)        # Polygons is made now
    assert _call(d["loft"], {"output": "Polygons"})[2]["output"] == 'POLYGONS'
    assert any("tolerance" in m.lower() for m in d["revolve"].missing)
    assert any("Rotation" in m for m in d["surface_extrude"].missing)


def test_notices_and_shelf():
    leaves = _surface_leaves()
    for path, mapped in leaves.items():
        if not mapped:
            n = notices.greyed_notice(path)
            assert n is not None and "Blender" in n[1], path
    # notices that described the old stand-ins are gone; Planar is still a filled 2D curve (no trims in Blender)
    assert "Surfaces/Loft" not in notices.NOTICES and "Surfaces/Extrude" not in notices.NOTICES
    assert "Surfaces/Planar" in notices.NOTICES
    assert "Screw" not in notices.CATEGORIES["Surfaces"][1]
    # shelf buttons run the menu items (Revolve was the Screw modifier)
    for label, path in (("Revolve", "Surfaces/Revolve"), ("Loft", "Surfaces/Loft"), ("Extrude", "Surfaces/Extrude"),
                        ("Birail 1 Tool", "Surfaces/Birail/Birail 1 Tool"), ("Attach Surfaces", "Surfaces/Attach"),
                        ("Detach Surfaces", "Surfaces/Detach"), ("Insert Isoparms", "Surfaces/Insert Isoparms"),
                        ("Rebuild Surfaces", "Surfaces/Rebuild")):
        command = next(c for shelf, _t, buttons in shelf_map_data() if shelf == "Surfaces"
                       for lab, c in buttons if lab == label)
        hit = shelf_map.lookup("Surfaces", label, command)
        assert hit is not None and hit[0] == menu_map.MAP[path], (label, hit)


def shelf_map_data():
    return import_module(kit.MODULE + ".ui.shelf_data").SHELVES
