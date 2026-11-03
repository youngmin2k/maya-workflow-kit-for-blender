"""Maya UV Toolkit: every button runs a working command, Align Min / Avg / Max U / V (UVs and whole shells, over several
meshes), Straighten UVs with its angle tolerance, Unfold Along U / V, Randomize Shells and their option windows."""
from importlib import import_module

import bmesh
import bpy

import kit

tk = import_module(kit.MODULE + ".operators.uv_toolkit_ops")
uv_toolkit = import_module(kit.MODULE + ".ui.uv_toolkit")
menu_map = import_module(kit.MODULE + ".ui.menu_map")
option_windows = import_module(kit.MODULE + ".operators.option_windows")


def _clear():
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)


def _quads(name, cells, x0=0.0):
    """One mesh of separate unit quads; ``cells`` = list of 4 UV corners per quad (one shell each)."""
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    uv = bm.loops.layers.uv.new("map1")
    for i, corners in enumerate(cells):
        x = x0 + 2.0 * i
        vs = [bm.verts.new((x + a, b, 0.0)) for a, b in ((0, 0), (1, 0), (1, 1), (0, 1))]
        f = bm.faces.new(vs)
        for lp, c in zip(f.loops, corners):
            lp[uv].uv = c
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(ob)
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    return ob


def _square(u, v, size=0.1):
    return [(u, v), (u + size, v), (u + size, v + size), (u, v + size)]


def _edit(*obs, mode='UV'):
    for ob in obs:
        ob.select_set(True)
    bpy.context.view_layer.objects.active = obs[0]
    bpy.ops.object.mode_set(mode='EDIT')
    assert bpy.ops.allset.uv_component(mode=mode) == {'FINISHED'}
    for ob in obs:
        bm = bmesh.from_edit_mesh(ob.data)
        for seq in (bm.verts, bm.edges, bm.faces):
            for el in seq:
                el.select = True
        bmesh.update_edit_mesh(ob.data)
    bpy.ops.uv.select_all(action='SELECT')


def _uvs(ob):
    """UV coordinates per face (rounded), read in edit mode."""
    bm = bmesh.from_edit_mesh(ob.data)
    uv = bm.loops.layers.uv.active
    return [[tuple(round(c, 5) for c in lp[uv].uv) for lp in f.loops] for f in bm.faces]


def test_every_toolkit_button_runs_a_mapped_command():
    paths = [p for _t, p in uv_toolkit.CREATE]
    for rows in (uv_toolkit.CUT_SEW, uv_toolkit.SNAP, uv_toolkit.ARRANGE):
        paths += [f"{uv_toolkit.UVE}/{p}" for _t, p in rows]
    paths += [f"{uv_toolkit.UVE}/Select/{it if isinstance(it, str) else it[1]}" for it in uv_toolkit.SELECT_BY_TYPE]
    missing = [p for p in paths if p not in menu_map.MAP]
    assert not missing, missing
    assert len(paths) == len(set(paths))
    # what used to be greyed in the toolkit now runs the kit's commands
    for key in ("UV Toolkit/Select By Type/Back-Facing", "UV Toolkit/Select By Type/Texture Borders",
                "UV Toolkit/Unfold/Straighten"):
        assert key not in uv_toolkit.GREY
    # Match Islands = Stack Similar Shells
    assert menu_map.MAP[f"{uv_toolkit.UVE}/Modify/Stack Similar Shells"] == "allset.uv_stack_similar"


def test_align_uvs_min_avg_max():
    _clear()
    a = _quads("alignA", [_square(0.1, 0.1), _square(0.5, 0.3)])
    b = _quads("alignB", [_square(0.3, 0.6)], x0=10.0)
    _edit(a, b)
    assert bpy.ops.allset.uv_align_to(axis='U', where='MIN') == {'FINISHED'}
    assert {c[0] for f in _uvs(a) + _uvs(b) for c in f} == {0.1}
    assert {c[1] for f in _uvs(a) for c in f} == {0.1, 0.2, 0.3, 0.4}      # V untouched
    assert bpy.ops.allset.uv_align_to(axis='V', where='MAX') == {'FINISHED'}
    assert {c[1] for f in _uvs(a) + _uvs(b) for c in f} == {0.7}
    bpy.ops.object.mode_set(mode='OBJECT')
    _clear()
    a = _quads("alignC", [_square(0.1, 0.1), _square(0.5, 0.5)])
    _edit(a)
    assert bpy.ops.allset.uv_align_to(axis='U', where='AVG') == {'FINISHED'}
    assert {c[0] for f in _uvs(a) for c in f} == {0.35}          # bounding-box centre of 0.1 .. 0.6
    bpy.ops.object.mode_set(mode='OBJECT')


def test_align_shells_moves_whole_shells():
    _clear()
    a = _quads("shellsA", [_square(0.1, 0.1, 0.1), _square(0.5, 0.3, 0.2)])
    b = _quads("shellsB", [_square(0.3, 0.6, 0.1)], x0=10.0)
    _edit(a, b, mode='SHELL')
    assert bpy.ops.allset.uv_align_to(axis='U', where='MAX') == {'FINISHED'}
    for f in _uvs(a) + _uvs(b):
        assert max(c[0] for c in f) == 0.7, f       # every shell's right edge on the right of all of them
    sizes = sorted(round(max(c[0] for c in f) - min(c[0] for c in f), 5) for f in _uvs(a) + _uvs(b))
    assert sizes == [0.1, 0.1, 0.2], (sizes, _uvs(a), _uvs(b))       # shells keep their shape
    assert bpy.ops.allset.uv_align_to(axis='V', where='AVG') == {'FINISHED'}
    for f in _uvs(a) + _uvs(b):
        assert round(0.5 * (max(c[1] for c in f) + min(c[1] for c in f)), 5) == 0.4, f
    bpy.ops.object.mode_set(mode='OBJECT')


def test_straighten_uvs_uses_the_angle_tolerance():
    _clear()
    # a slanted quad: bottom edge 10 degrees off U, right edge 5 degrees off V, top edge 40 degrees off U
    import math
    t10, t5 = math.tan(math.radians(10)), math.tan(math.radians(5))
    corners = [(0.0, 0.0), (0.4, 0.4 * t10), (0.4 + 0.4 * t5, 0.4), (0.0, 0.4 + 0.5 * math.tan(math.radians(40)))]
    a = _quads("straight", [corners])
    _edit(a)
    assert bpy.ops.allset.uv_straighten_uvs(axis='UV', tolerance=30.0) == {'FINISHED'}
    (f,) = _uvs(a)
    assert f[0][1] == f[1][1], f                 # bottom edge now along U
    assert f[1][0] == f[2][0], f                 # right edge now along V
    assert f[2][1] != f[3][1], f                 # 40 degrees: left alone
    bpy.ops.object.mode_set(mode='OBJECT')
    _clear()
    a = _quads("straightU", [corners])
    _edit(a)
    assert bpy.ops.allset.uv_straighten_uvs(axis='V', tolerance=30.0) == {'FINISHED'}
    (f,) = _uvs(a)
    assert f[0][1] != f[1][1] and f[1][0] == f[2][0], f      # V only
    bpy.ops.object.mode_set(mode='OBJECT')


def test_unfold_along_keeps_the_other_axis():
    _clear()
    # a 1 x 1 quad whose UVs are squashed to half width: Unfold Along U widens it, V stays
    a = _quads("along", [[(0.0, 0.0), (0.25, 0.0), (0.25, 0.5), (0.0, 0.5)]])
    _edit(a)
    before = _uvs(a)[0]
    assert bpy.ops.allset.uv_unfold_along(axis='U') == {'FINISHED'}
    after = _uvs(a)[0]
    assert [c[1] for c in after] == [c[1] for c in before]
    width = max(c[0] for c in after) - min(c[0] for c in after)
    assert width > 0.3, after                   # closer to the 3D proportion (square)
    mean = sum(c[0] for c in after) / 4
    assert abs(mean - 0.125) < 1e-4, mean       # stays where it was
    bpy.ops.object.mode_set(mode='OBJECT')


def test_randomize_shells():
    _clear()
    a = _quads("rand", [_square(0.1 * i, 0.1) for i in range(6)])
    _edit(a)
    before = _uvs(a)
    # by default: move up to 0.1 along U and V, no turn, no scale
    assert bpy.ops.allset.uv_randomize(seed=7) == {'FINISHED'}
    after = _uvs(a)
    assert after != before
    for f0, f1 in zip(before, after):
        du, dv = f1[0][0] - f0[0][0], f1[0][1] - f0[0][1]
        assert abs(du) <= 0.1 + 1e-6 and abs(dv) <= 0.1 + 1e-6
        assert all(abs((c1[0] - c0[0]) - du) < 1e-5 and abs((c1[1] - c0[1]) - dv) < 1e-5
                   for c0, c1 in zip(f0, f1))     # moved whole: no turn, no scale
    # clockwise only: every shell turns by a negative angle
    import math
    assert bpy.ops.allset.uv_randomize(seed=3, translate_u=False, translate_v=False, rotate_cw=True) == {'FINISHED'}
    for f0, f1 in zip(after, _uvs(a)):
        e0 = (f0[1][0] - f0[0][0], f0[1][1] - f0[0][1])
        e1 = (f1[1][0] - f1[0][0], f1[1][1] - f1[0][1])
        ang = math.degrees(math.atan2(e0[0] * e1[1] - e0[1] * e1[0], e0[0] * e1[0] + e0[1] * e1[1]))
        assert -22.5 - 1e-3 <= ang <= 0.0, ang
    bpy.ops.object.mode_set(mode='OBJECT')


def test_option_windows():
    by = {w.key: w for w in option_windows.WINDOWS}
    st, rnd = by["straighten_uvs"], by["randomize_shells"]
    assert st.paths == ("UV Editor/Modify/Straighten UVs",) and st.defaults() == {"direction": "UV", "angle": 30.0}
    assert rnd.paths == ("UV Editor/Modify/Randomize Shells",)
    assert rnd.defaults() == {"translate_u": True, "translate_v": True, "translate": 0.1, "rotate_cw": False,
                              "rotate_ccw": False, "rotate": 22.5, "scale_up": False, "scale_down": False,
                              "scale": 10.0}
    assert menu_map.MAP["UV Editor/Modify/Straighten UVs"] == "allset.uv_straighten_uvs"
    assert menu_map.MAP["UV Editor/Modify/Randomize Shells"] == "allset.uv_randomize"
    assert option_windows.find_path("UV Editor/Modify/Randomize Shells") is rnd
    assert hasattr(bpy.ops.allset, "opt_randomize_shells") and hasattr(bpy.ops.allset, "opt_straighten_uvs")
