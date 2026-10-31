"""Selected edges and manipulator look.

Edges: Blender's sharp-edge overlay is switched off with the face overlay in Maya layout views, the hilite wire is
1.5 px (just covers Blender's own 2 px edit edge), selected edges 2 px with a larger depth bias. Manipulator: plane
handles at 0.52-0.68 arrow units with a rim + lightened translucent fill, the active handle / centre #fdff88,
the centre light blue #64dcff while an axis is active."""

from importlib import import_module

import kit


def _mod(name):
    return import_module(kit.MODULE + name)


def test_edge_constants():
    cc = _mod(".ui.component_colors")
    assert cc.OVERLAY_OFF == ("show_faces", "show_edge_sharp")
    assert cc.LINE_PX == 1.5 and cc.EDGE_SEL_PX == 2.0
    assert cc.EDGE_SEL_BIAS > cc.DEPTH_BIAS > cc.FACE_BIAS
    # a switch the kit made is the only one it undoes (same rule for both overlays)
    act = cc.face_overlay_action
    assert act(True, True, False) == (False, True)
    assert act(False, False, True) == (True, False)
    assert act(False, False, False) == (None, False)


def test_plane_handle_shape_and_colours():
    m = _mod(".ui.manipulator")
    draw, pick = m.shapes('PLANE')
    assert [t for t, _v in draw] == ['TRIS', 'LINES'], "fill first, then the rim"
    xs = [v[0] for v in draw[1][1]]
    assert abs(min(xs) - 0.52) < 1e-6 and abs(max(xs) - 0.68) < 1e-6, "Maya 02: 0.52-0.68 arrow units"
    fill = m.plane_fill((0.9, 0.0, 0.0))
    assert fill[0] > 0.9 and abs(fill[1] - m.PLANE_LIGHTEN) < 1e-6
    assert m.ACTIVE == (0xfd / 255, 1.0, 0x88 / 255) and m.CENTER_IDLE == (0x64 / 255, 0xdc / 255, 1.0)


def test_centre_active_by_default():
    m = _mod(".ui.manipulator")
    manip = _mod(".operators.manip")
    manip.HANDLES.pop('TRANSLATE', None)
    assert m._is_active('TRANSLATE', None), "no remembered handle = the centre is Maya's active handle"
    manip.HANDLES['TRANSLATE'] = {"constraint_axis": (True, False, False)}
    try:
        assert not m._is_active('TRANSLATE', None) and m._is_active('TRANSLATE', (True, False, False))
    finally:
        manip.HANDLES.pop('TRANSLATE', None)
