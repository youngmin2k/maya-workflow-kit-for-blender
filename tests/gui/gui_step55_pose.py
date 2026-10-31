"""In a real UI, in a Maya user's hand order: a skeleton (kit Create Joints + two joints) ->
Ctrl+Tab pose mode -> click joint2 in the view -> the Channel Box shows joint2 with Translate / Rotate /
Scale (XYZ) -> type "+=10" in Rotate Z -> S keys it -> Lock Selected on Rotate -> rotating in the view
does nothing; a Copy Location constraint to locator1 -> CB INPUTS weight row locator1W0 -> 0.5 ->
influence 0.5, Translate fields blue."""

import math
import os
import sys
from importlib import import_module

import bpy
from bpy_extras import view3d_utils

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, dock_area, dock_region, ev, find_button, open_inputs, px, run, scroll_channel_box, screenshot, setup, step, tap, view3d, win  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {"tries": 0}
# Channel Box rows: Translate X value field 136 px left of the UI region's right edge and 114 px
# below its top at scale 1.25 (gui_step38); rows are 16 px at 1.0 (ROW_SCALE 0.8) = 20 at 1.25.
ROW = 20


def cb():
    return import_module(MODULE + ".ui.channel_box")


def shot(name):
    if SHOTS:
        screenshot(os.path.join(SHOTS, name))


def ui_region():
    return dock_region()       # the Maya tab stack (was the 3D View sidebar)


def dock():
    return dock_area(), dock_region()


def main_region():
    return next(r for r in view3d()[0].regions if r.type == 'WINDOW')


def redraw():
    for a in win().screen.areas:
        a.tag_redraw()


def field(row, from_right=136):
    """Window position of Channel Box value row ``row`` (0 = Translate X): the value / name column x found by
    ``find_button`` (the dock's width is not the old sidebar's), rows ROW px apart below Translate X."""
    x = C["value_x"] if from_right == 136 else C["name_x"]
    return x, C["tx_y"] - px(ROW * row)


def goto_tab(category, then):
    """Ctrl+wheel over the sidebar tab strip until ``category`` shows (gui_step11)."""
    def s_tab():
        r = ui_region()
        if r.active_panel_category != category and C["tries"] < 12:
            C["tries"] += 1
            ev('MOUSEMOVE', 'NOTHING', x=r.x + r.width - 8, y=r.y + r.height - 60)
            ev('WHEELDOWNMOUSE', 'PRESS', ctrl=True)
            sys.modules["sim"]._steps.insert(0, s_tab)
            return
        C["tries"] = 0
        check(f"sidebar shows the {category} tab", r.active_panel_category == category)
        then()
    return s_tab


def arm():
    return bpy.data.objects["skeleton1"]


def hover_view():
    r = main_region()
    ev('MOUSEMOVE', 'NOTHING', x=r.x + 40, y=r.y + 40)


def type_text(text):
    ev('A', 'PRESS', ctrl=True)     # select the whole text, then type over it
    ev('A', 'RELEASE', ctrl=True)
    for ch in text:
        ev('TEXTINPUT', 'PRESS', unicode=ch)


@step
def s_setup():
    C["x"], C["y"] = setup()
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    us = bpy.context.scene.unit_settings
    us.system, us.length_unit, us.system_rotation = 'METRIC', 'CENTIMETERS', 'DEGREES'
    dock_area('CHANNEL_BOX')    # Maya's tab stack right of the viewport, before framing the view
    area, region = view3d()
    with bpy.context.temp_override(window=win(), area=area, region=main_region()):
        bpy.ops.allset.create(kind='JOINT')
        a = bpy.context.active_object
        bpy.ops.object.mode_set(mode='EDIT')
        prev = a.data.edit_bones["joint1"]
        for name in ("joint2", "joint3"):     # what the Joint Tool will place
            eb = a.data.edit_bones.new(name)
            eb.head, eb.tail = prev.tail, prev.tail + (prev.tail - prev.head)
            eb.parent, eb.use_connect = prev, True
            prev = eb
        bpy.ops.object.mode_set(mode='OBJECT')
        for pb in a.pose.bones:
            pb.rotation_mode = 'XYZ'
        a.select_set(True)
        bpy.context.view_layer.objects.active = a
        bpy.ops.view3d.view_axis(type='FRONT')
        bpy.ops.view3d.view_selected()
    redraw()


@step
def s_dock_wait():
    redraw()


@step
def s_object_mode_shot():
    shot("gui_step55_object_mode.png")
    check("object mode: the lead is the armature object", cb().lead() == arm())
    r = main_region()
    ev('MOUSEMOVE', 'NOTHING', x=r.x + r.width // 2, y=r.y + 30)
    ev('TAB', 'PRESS', ctrl=True)
    ev('TAB', 'RELEASE', ctrl=True)


@step
def s_pose_mode():
    check(f"Ctrl+Tab = pose mode ({arm().mode})", arm().mode == 'POSE')
    a = arm()
    for pb in a.pose.bones:
        cb().set_bone_selected(pb, False)
    # click the middle of joint2 in the view (Maya: click the joint)
    r, rv3d = main_region(), view3d()[0].spaces.active.region_3d
    b = a.data.bones["joint2"]
    mid = a.matrix_world @ ((b.head_local + b.tail_local) / 2)
    p = view3d_utils.location_3d_to_region_2d(r, rv3d, mid)
    C["bone_xy"] = (r.x + int(p.x), r.y + int(p.y))
    ev('MOUSEMOVE', 'NOTHING', x=C["bone_xy"][0], y=C["bone_xy"][1])


@step
def s_click_bone():
    x, y = C["bone_xy"]
    ev('LEFTMOUSE', 'PRESS', x=x, y=y)
    ev('LEFTMOUSE', 'RELEASE', x=x, y=y)
    redraw()


@step
def s_bone_picked():
    ld = cb().lead()
    check(f"clicking joint2 makes it the Channel Box lead ({getattr(ld, 'name', None)})",
          ld is not None and ld.name == "joint2")
    check("joint2 has Euler channels (Rotate X/Y/Z rows)", ld is not None and cb().has_channel(ld, "rz"))
    redraw()


# the joint's rows (pose mode: no object-mode note row above them), looked up by data path
step(find_button(dock, lambda path, _cmd: path.endswith("tx_text"), C, "tx", x_frac=0.7, step_px=6))   # inside the value column of the step-142 narrow dock
step(find_button(dock, lambda path, cmd: "cb_select_channel" in cmd or path.endswith("tx_sel"), C, "name", y_from="tx"))


@step
def s_columns():
    check(f"Channel Box columns found in the dock (value {C['tx']}, name {C['name']})", C["tx"] and C["name"])
    C["value_x"] = C["tx"][0] if C["tx"] else 0
    C["name_x"] = C["name"][0] if C["name"] else 0
    C["tx_y"] = C["tx"][1] if C["tx"] else 0


@step
def s_cb_shot():
    shot("gui_step55_cb_joint.png")
    C["rz"] = field(5)
    ev('MOUSEMOVE', 'NOTHING', x=C["rz"][0], y=C["rz"][1])


@step
def s_click_rz():
    x, y = C["rz"]
    ev('LEFTMOUSE', 'PRESS', x=x, y=y)
    ev('LEFTMOUSE', 'RELEASE', x=x, y=y)


@step
def s_type_rz():
    type_text("+=10")
    redraw()


@step
def s_typed():
    shot("gui_step55_cb_typing.png")
    tap('RET')


@step
def s_rz_applied():
    pb = arm().pose.bones["joint2"]
    deg = math.degrees(pb.rotation_euler[2])
    check(f"'+=10' in Rotate Z rotated joint2 to {deg:.3f} deg", abs(deg - 10) < 1e-3)
    hover_view()


@step
def s_key():
    tap('S')


@step
def s_keyed():
    pb = arm().pose.bones["joint2"]
    fc = cb().fcurve(pb, "rz")
    check("S keyed joint2: F-curve pose.bones[\"joint2\"].rotation_euler[2]",
          fc is not None and fc.data_path == 'pose.bones["joint2"].rotation_euler')
    # select the Rotate X..Z channel names (Shift = add), then Channels > Lock Selected
    C["names"] = [field(i, from_right=290) for i in (3, 4, 5)]
    x, y = C["names"][0]
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
    redraw()


@step
def s_select_rx():
    x, y = C["names"][0]
    ev('LEFTMOUSE', 'PRESS', x=x, y=y)
    ev('LEFTMOUSE', 'RELEASE', x=x, y=y)


@step
def s_hover_rz():
    C["sel_rx"] = cb().selected_channels()
    x, y = C["names"][2]
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)     # hover first: buttons activate on mouse move
    redraw()


@step
def s_select_rz():
    x, y = C["names"][2]
    ev('LEFTMOUSE', 'PRESS', x=x, y=y)
    ev('LEFTMOUSE', 'RELEASE', x=x, y=y)


@step
def s_lock():
    sel = cb().selected_channels()
    check(f"clicking channel names of a joint selects them ({C['sel_rx']}, then {sel})",
          C["sel_rx"] == ["rx"] and sel == ["rz"])
    # Shift+click adds; simulated Shift doesn't reach UI buttons, so set Rotate X..Z here
    cb().set_selected_channels(["rx", "ry", "rz"])
    bpy.ops.allset.cb_lock(lock=True)      # Channels > Lock Selected (menu clicks: gui_step6)
    redraw()


@step
def s_locked_shot():
    shot("gui_step55_cb_locked.png")
    pb = arm().pose.bones["joint2"]
    check("Lock Selected locked joint2's rotation", all(pb.lock_rotation))
    C["before"] = tuple(pb.rotation_euler)
    area = view3d()[0]
    with bpy.context.temp_override(window=win(), area=area, region=main_region()):
        bpy.ops.transform.rotate(value=0.7, orient_axis='Y', orient_type='VIEW')
        bpy.ops.transform.rotate(value=0.5, orient_axis='Z', orient_type='GLOBAL')


@step
def s_not_rotated():
    pb = arm().pose.bones["joint2"]
    check(f"rotating in the view leaves a locked joint as it was ({tuple(pb.rotation_euler)})",
          max(abs(a - b) for a, b in zip(C["before"], pb.rotation_euler)) < 1e-6)
    # Constrain: locator1 drives joint2's translate (Copy Location = Maya point constraint)
    loc = bpy.data.objects.new("locator1", None)
    bpy.context.scene.collection.objects.link(loc)
    con = pb.constraints.new('COPY_LOCATION')
    con.target = loc
    cb().rebuild_rows()
    open_inputs()    # the constraint node starts collapsed (Maya)
    scroll_channel_box()    # ... and a long Channel Box scrolls inside its part
    redraw()


@step
def s_wait():
    redraw()


@step
def s_constraint_shot():
    shot("gui_step55_cb_constraint.png")
    rows = [r for r in bpy.context.scene.allset_cb.rows if r.kind == "CONSTRAINT"]
    check("CB INPUTS has the constraint weight row (locator1W0)", len(rows) == 1)
    redraw()


def _is_w0(path, _cmd):
    """The weight row's text field (looked up by data path, the Channel Box part scrolls)."""
    rows = bpy.context.scene.allset_cb.rows
    return any(r.kind == "CONSTRAINT" and path.endswith(f"rows[{i}].text") for i, r in enumerate(rows))


step(find_button(dock, _is_w0, C, "w0", x_frac=0.7, step_px=6))


@step
def s_hover_w0():
    check(f"locator1W0 weight field found ({C.get('w0')})", C.get("w0") is not None)
    ev('MOUSEMOVE', 'NOTHING', x=C["w0"][0], y=C["w0"][1])


@step
def s_click_w0():
    x, y = C["w0"]
    ev('LEFTMOUSE', 'PRESS', x=x, y=y)
    ev('LEFTMOUSE', 'RELEASE', x=x, y=y)


@step
def s_type_w0():
    type_text("0.5")
    redraw()


@step
def s_w0_typed():
    shot("gui_step55_cb_weight_typing.png")
    tap('RET')


@step
def s_w0_applied():
    con = arm().pose.bones["joint2"].constraints[0]
    check(f"locator1W0 = 0.5 -> influence {con.influence:.3f}", abs(con.influence - 0.5) < 1e-6)
    check("Translate channels are constrained (drawn blue)",
          cb().constrained_keys(arm().pose.bones["joint2"]) == {"tx", "ty", "tz"})
    redraw()


@step
def s_final_shot():
    shot("gui_step55_cb_weight.png")
    bpy.context.window_manager.allset_dock = 'ATTRIBUTE_EDITOR'
    bpy.ops.allset.ae_tab(key="J")
    redraw()


@step
def s_ae_wait():
    redraw()


@step
def s_ae_shot():
    shot("gui_step55_ae_joint.png")
    ae = import_module(MODULE + ".ui.attribute_editor")
    pb = arm().pose.bones["joint2"]
    check(f"AE shows the joint tab and its constraint node ({[t[1] for t in ae.tabs(pb)]})",
          [t[2] for t in ae.tabs(pb)] == ["joint", "pointConstraint"])
    bpy.context.window_manager.allset_dock = 'CHANNEL_BOX'


run()
