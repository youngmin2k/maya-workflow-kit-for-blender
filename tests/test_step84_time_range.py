"""Maya Time Slider range — drag the middle to move its keys, an end arrow to scale them.
GUI: tests/gui/gui_step84_time_range.py."""

from importlib import import_module

import bpy

import kit

tr = import_module(kit.MODULE + ".operators.time_range")
patches = import_module(kit.MODULE + ".keymap.maya_patches")
cb = import_module(kit.MODULE + ".ui.channel_box")


def test_zone():
    assert tr.zone(5, 10, 100, 8) is None and tr.zone(101, 10, 100, 8) is None
    assert tr.zone(12, 10, 100, 8) == 'LEFT' and tr.zone(95, 10, 100, 8) == 'RIGHT'
    assert tr.zone(50, 10, 100, 8) == 'MOVE'
    assert tr.zone(12, 10, 30, 8) == 'MOVE'                 # narrow range: only move


def test_new_range_and_map_frame():
    assert tr.new_range(10, 20, 'MOVE', 15, 20) == (15, 25)
    assert tr.new_range(10, 20, 'RIGHT', 20, 30) == (10, 30)
    assert tr.new_range(10, 20, 'RIGHT', 20, 2) == (10, 11)     # never crosses the other end
    assert tr.new_range(10, 20, 'LEFT', 10, 0) == (0, 20)
    assert tr.new_range(10, 20, 'LEFT', 10, 25) == (19, 20)
    assert tr.new_range(12, 12, 'RIGHT', 12, 20) == (20, 20)     # one frame: moves
    assert tr.map_frame(14, 10, 20, 'MOVE', 15, 18) == (17, 1.0)
    assert tr.map_frame(15, 10, 20, 'RIGHT', 20, 30) == (20.0, 2.0)      # pivot = left end
    assert tr.map_frame(15, 10, 20, 'LEFT', 10, 0) == (10.0, 2.0)        # pivot = right end
    assert tr.map_frame(13, 10, 20, 'RIGHT', 20, 25)[0] == 14.0           # 14.5 -> whole frame


def test_clashes():
    # keys 1 10 20 30, moved index 1 (10 -> 20) lands on index 2
    assert tr.clashes([1, 20, 20, 30], {1}) == [2]
    # two moved keys on the same frame: the later one stays
    assert tr.clashes([1, 15, 15, 30], {1, 2}) == [1]
    assert tr.clashes([1, 12, 14, 30], {1, 2}) == []


def _animated(keys=((1, 0.0), (12, 5.0), (15, -2.0), (20, 8.0), (30, 1.0))):
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    ob = bpy.data.objects.new("cube", None)
    bpy.context.scene.collection.objects.link(ob)
    for f, v in keys:
        ob.location[0] = v
        ob.keyframe_insert("location", index=0, frame=f)
    bpy.context.view_layer.objects.active = ob
    ob.select_set(True)
    return ob, cb._fcurves(ob).find("location", index=0)


def _drag(fc, a, b):
    idx = [i for i, kp in enumerate(fc.keyframe_points) if a - 0.5 <= kp.co.x < b + 0.5]
    return tr.Drag([(fc, idx)], a, b)


def _keys(fc):
    return [(round(kp.co.x, 3), round(kp.co.y, 3)) for kp in fc.keyframe_points]


def test_drag_move_from_snapshot_and_overwrite():
    _ob, fc = _animated()
    d = _drag(fc, 10, 16)                          # keys 12, 15
    d.apply('MOVE', 12, 30)                        # passes the keys at 20 and 30 (+18)
    d.apply('MOVE', 12, 20)                        # back to +8: 20 and 23
    assert _keys(fc) == [(1, 0), (20, 8), (20, 5), (23, -2), (30, 1)] or \
        _keys(fc) == [(1, 0), (20, 5), (20, 8), (23, -2), (30, 1)]
    assert d.finish('MOVE', 12, 20) == 2
    assert _keys(fc) == [(1, 0), (20, 5), (23, -2), (30, 1)]       # the old key at 20 overwritten


def test_drag_scale_handles_and_cancel():
    _ob, fc = _animated()
    before = _keys(fc)
    hr = fc.keyframe_points[1].handle_right.x - fc.keyframe_points[1].co.x
    d = _drag(fc, 12, 20)                           # 12 15 20
    d.apply('RIGHT', 20, 28)                        # 12..28: scale 2
    d.finish('RIGHT', 20, 28)
    assert [k[0] for k in _keys(fc)] == [1, 12, 18, 28, 30]
    kp = fc.keyframe_points[1]
    assert abs((kp.handle_right.x - kp.co.x) - hr * 2) < 1e-4 or kp.handle_right_type in {'AUTO', 'AUTO_CLAMPED'}
    _ob, fc = _animated()
    d = _drag(fc, 12, 20)
    d.apply('LEFT', 12, 2)
    d.cancel()
    assert _keys(fc) == before


def test_keymap_item_leads_time_scrub():
    kc = kit.maya_kc()
    items = [k.idname for k in kc.keymaps["Dopesheet"].keymap_items
             if k.active and k.type == 'LEFTMOUSE' and k.value == 'PRESS' and not (k.shift or k.ctrl or k.alt)]
    assert items.index("allset.time_range_drag") < items.index("allset.time_scrub"), items
    assert "allset.time_range_drag" in patches.PASS_THROUGH_FIRST
