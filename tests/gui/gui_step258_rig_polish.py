"""Lane B (Issue #155) in a real UI: the Maya layout after Skeleton > Create Joints (three joints, root away
from the origin): the Outliner row reads joint1 (Maya 2026), the Channel Box
Translate of the root = its position, and with the skeleton in Object Mode the Channel Box joint hint fits the dock.
Run at both scales: default (effective 1.25 on this PC) and ``ALLSET_GUI_UI_SCALE=0.8`` (effective 1.0)."""

import json
import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, run, screenshot, setup, step, view3d, win, load_maya_layout, dock_region  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
ROOT = (3.0, -1.0, 2.0)


def shot(name):
    if SHOTS:
        screenshot(os.path.join(SHOTS, f"{name}_{bpy.context.preferences.system.ui_scale:.2f}.png"))


def outliner():
    for area in win().screen.areas:
        if area.type == 'OUTLINER':
            return area, next(r for r in area.regions if r.type == 'WINDOW')
    return None, None


def redraw_all():
    for area in win().screen.areas:
        area.tag_redraw()


@step
def s_setup():
    setup()
    load_maya_layout()


@step
def s_joints():
    bpy.ops.allset.keymap_activate()
    units = import_module(MODULE + ".operators.units")
    k = units.maya_unit(bpy.context.scene)
    pts = [[c * k for c in p] for p in (ROOT, (3.0, -1.0, 6.0), (5.0, -1.0, 9.0))]
    area, region = view3d()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        for ob in list(bpy.context.selected_objects):
            ob.select_set(False)
        bpy.ops.allset.joint_tool(points=json.dumps(pts))
    redraw_all()


@step
def s_wait():
    a, r = outliner()
    if a is not None:
        ev('MOUSEMOVE', 'NOTHING', x=r.x + r.width // 2, y=r.y + 10)
    redraw_all()


@step
def s_check_pose():
    shot("258_pose")
    ob = bpy.data.objects.get("skeleton1")
    check(f"skeleton in pose mode ({ob.mode if ob else None})", ob is not None and ob.mode == 'POSE')
    ol = import_module(MODULE + ".ui.outliner_joints")
    _a, r = outliner()
    seen = ol.SEEN.get(r.as_pointer()) if r is not None else None
    check(f"Outliner row of skeleton1 reads joint1 ({seen})", seen == [("skeleton1", "joint1")])
    c = bpy.context.scene.allset_cb
    shown = (c.tx_text, c.ty_text, c.tz_text)
    check(f"Channel Box Translate of joint1 = its position {shown}",
          all(abs(float(v) - w) < 1e-3 for v, w in zip(shown, ROOT)))


@step
def s_object_mode():
    area, region = view3d()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        bpy.ops.object.mode_set(mode='OBJECT')
    redraw_all()


@step
def s_wait2():
    redraw_all()


@step
def s_check_hint():
    shot("258_hint")
    import blf
    cb = import_module(MODULE + ".ui.channel_box")
    md = import_module(MODULE + ".ui.maya_dock")
    scale = bpy.context.preferences.system.ui_scale
    r = dock_region()
    blf.size(0, 11.0 * scale)
    w = blf.dimensions(0, cb.POSE_HINT)[0]
    # panel side margins (~1 unit each side) and the tab strip on the right
    room = r.width - md.strip_px(scale) - 20 * scale * 2
    check(f"hint '{cb.POSE_HINT}' {w:.0f} px fits the dock {room:.0f} px (scale {scale})", w <= room)
    ol = import_module(MODULE + ".ui.outliner_joints")
    _a, orr = outliner()
    seen = ol.SEEN.get(orr.as_pointer()) if orr is not None else None
    check(f"Object Mode: the Outliner row still reads joint1 ({seen})", seen == [("skeleton1", "joint1")])


@step
def s_second():
    units = import_module(MODULE + ".operators.units")
    k = units.maya_unit(bpy.context.scene)
    pts = [[c * k for c in p] for p in ((-4.0, 0.0, 1.0), (-4.0, 0.0, 5.0))]
    area, region = view3d()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        if bpy.context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.allset.joint_tool(points=json.dumps(pts))
    redraw_all()


@step
def s_wait3():
    redraw_all()


@step
def s_check_two():
    shot("258_two")
    ol = import_module(MODULE + ".ui.outliner_joints")
    _a, orr = outliner()
    seen = sorted(ol.SEEN.get(orr.as_pointer()) or [])
    check(f"two skeletons: rows read joint1 and joint4 ({seen})",
          seen == [("skeleton1", "joint1"), ("skeleton2", "joint4")])


run()
