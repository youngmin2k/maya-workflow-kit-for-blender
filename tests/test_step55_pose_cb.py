"""Joints = pose bones in the Channel Box, Outliner and Attribute Editor; constraint
weight rows (``locator1W0`` = influence) and constrained channels. GUI: tests/gui/gui_step55_pose.py."""

import math
from importlib import import_module

import bpy

import kit

compat = import_module(kit.MODULE + ".compat")
cb = import_module(kit.MODULE + ".ui.channel_box")
outliner = import_module(kit.MODULE + ".ui.outliner")
ae = import_module(kit.MODULE + ".ui.attribute_editor")
patches = import_module(kit.MODULE + ".keymap.maya_patches")


class Recorder:
    """A stand-in UILayout that records labels / operator texts (tests/test_step50_chrome.py)."""

    def __init__(self, log=None):
        self.log = [] if log is None else log

    def __getattr__(self, name):
        if name in ("row", "column", "split", "box", "column_flow", "grid_flow"):
            return lambda *a, **k: Recorder(self.log)
        if name == "panel":
            return lambda *a, **k: (Recorder(self.log), Recorder(self.log))
        if name in ("menu", "operator", "prop", "label", "popover", "menu_contents"):
            def add(*args, **kw):
                self.log.append((name, kw.get("text", args[0] if args else ""), kw))
                return type("Props", (), {})()
            return add
        return lambda *a, **k: None

    def __setattr__(self, name, value):
        if name == "log":
            object.__setattr__(self, name, value)

    def texts(self, kind):
        return [t for k, t, _kw in self.log if k == kind]


def _mode(mode):
    if bpy.context.active_object is not None and bpy.context.mode != mode:
        bpy.ops.object.mode_set(mode=mode)


def _skeleton(quaternion_last=False):
    """skeleton1: joint1 > joint2 > joint3 (kit Create Joints + two more bones, XYZ like the kit)."""
    if bpy.context.active_object is not None and bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    us = bpy.context.scene.unit_settings
    us.system, us.scale_length, us.length_unit, us.system_rotation = 'METRIC', 1.0, 'CENTIMETERS', 'DEGREES'
    assert bpy.ops.allset.create(kind='JOINT') == {'FINISHED'}
    arm = bpy.context.active_object
    bpy.ops.object.mode_set(mode='EDIT')
    prev = arm.data.edit_bones["joint1"]
    for name in ("joint2", "joint3"):
        eb = arm.data.edit_bones.new(name)
        eb.head = prev.tail
        eb.tail = prev.tail + (prev.tail - prev.head)
        eb.parent, eb.use_connect = prev, True
        prev = eb
    bpy.ops.object.mode_set(mode='POSE')
    for pb in arm.pose.bones:
        pb.rotation_mode = 'XYZ'
        cb.set_bone_selected(pb, False)
    if quaternion_last:
        arm.pose.bones["joint3"].rotation_mode = 'QUATERNION'
    bpy.context.window_manager.allset_cb_selected = ""
    return arm


def _pick(arm, *names):
    for pb in arm.pose.bones:
        cb.set_bone_selected(pb, pb.name in names)
    if names:
        arm.data.bones.active = arm.data.bones[names[0]]
    cb.rebuild_rows()


def _draw_cb():
    rec = Recorder()
    cb.ALLSET_PT_channel_box.draw(type("P", (), {"layout": rec})(), bpy.context)
    return rec


def test_lead_and_targets_follow_pose_bones():
    arm = _skeleton()
    _mode('OBJECT')
    assert cb.lead() == arm and cb.targets() == [arm]
    _mode('POSE')
    _pick(arm)
    assert cb.lead() is None and cb.targets() == [], "no joint selected = empty Channel Box"
    _pick(arm, "joint2", "joint3")
    pb2, pb3 = arm.pose.bones["joint2"], arm.pose.bones["joint3"]
    assert cb.lead() == pb2 and cb.targets() == [pb2, pb3]
    cb.set_bone_selected(pb2, False)          # active but not selected: Maya has no such lead
    assert cb.lead() == pb3
    _mode('EDIT')
    assert cb.placing_joints() and "Editing joints: W / E / R move them," in _draw_cb().texts("label")
    _mode('POSE')


def test_bone_channels_paths_and_entry():
    arm = _skeleton()
    _pick(arm, "joint2", "joint3")
    pb2, pb3 = arm.pose.bones["joint2"], arm.pose.bones["joint3"]
    assert cb.full_path(pb2, "rotation_euler") == 'pose.bones["joint2"].rotation_euler'
    assert all(cb.has_channel(pb2, k) for k in ("tx", "rx", "rz", "sz", "v"))
    pb3.rotation_euler[2] = math.radians(5)
    assert cb.apply_entry("rz", "+=10") == 2           # relative per joint (Channel Box entry rule)
    assert abs(math.degrees(pb2.rotation_euler[2]) - 10) < 1e-4
    assert abs(math.degrees(pb3.rotation_euler[2]) - 15) < 1e-4
    assert bpy.context.scene.allset_cb.rz_text == "10", bpy.context.scene.allset_cb.rz_text
    assert cb.apply_entry("tx", "2") == 2 and abs(pb2.location[0] - 0.02) < 1e-6   # 2 cm
    cb.set_value(pb2, "v", False)
    assert compat.bone_hidden(pb2) and not cb.get_value(pb2, "v")
    assert not cb.is_keyable(pb2, "v"), "Bone.hide is armature data: not in the object's action"
    cb.set_value(pb2, "v", True)
    _pick(arm, "joint2", "joint3")                        # hiding a bone deselects it
    rec = _draw_cb()
    assert "joint2" not in rec.texts("label")             # the name is a prop row
    assert "+1" in rec.texts("label")


def test_channel_menu_ops_on_joints():
    arm = _skeleton()
    _pick(arm, "joint2", "joint3")
    pb2, pb3 = arm.pose.bones["joint2"], arm.pose.bones["joint3"]
    cb.set_selected_channels(["rz"])
    assert bpy.ops.allset.cb_key_selected() == {'FINISHED'}
    fc = cb.fcurve(pb2, "rz")
    assert fc is not None and fc.data_path == 'pose.bones["joint2"].rotation_euler' and fc.array_index == 2
    assert fc.group is not None and fc.group.name == "joint2"
    assert cb.fcurve(pb3, "rz") is not None and cb.channel_state(pb2, "rz") == 'KEYED'
    bpy.context.scene.frame_set(5)
    assert bpy.ops.allset.cb_breakdown_selected() == {'FINISHED'}
    assert any(k.type == 'BREAKDOWN' for k in fc.keyframe_points)
    bpy.ops.allset.cb_mute(mute=True)
    assert fc.mute
    bpy.ops.allset.cb_delete_keys()
    assert cb.fcurve(pb2, "rz") is None and cb.fcurve(pb3, "rz") is None
    drv = pb2.driver_add("rotation_euler", 2)
    assert cb.channel_state(pb2, "rz") == 'DRIVEN', drv
    bpy.ops.allset.cb_break_connections()
    assert cb.driver(pb2, "rz") is None
    bpy.ops.allset.cb_lock(lock=True)
    assert pb2.lock_rotation[2] and pb3.lock_rotation[2] and not pb2.lock_rotation[0]
    assert cb.apply_entry("rz", "45") == 0, "locked channels take no entry"
    bpy.ops.allset.cb_lock(lock=False)
    cb.set_selected_channels(["sx", "sy", "sz"])
    bpy.ops.allset.cb_hide(lock=True)
    assert cb.is_hidden(pb2, "sx") and pb2.lock_scale[0] and "allset_cb_hidden" in pb2.keys()
    assert "Scale X" not in _draw_cb().texts("operator")
    bpy.ops.allset.cb_show_all()
    assert not cb.is_hidden(pb2, "sx")
    cb.set_selected_channels(["tx"])
    bpy.ops.allset.cb_keyable(keyable=False)
    assert not cb.is_keyable(pb3, "tx")
    bpy.ops.allset.cb_key_selected()
    assert cb.fcurve(pb3, "tx") is None
    pb2.location[0] = 0.3
    bpy.ops.allset.cb_duplicate_values()
    assert abs(pb3.location[0] - 0.3) < 1e-6
    cb.set_selected_channels([])
    bpy.ops.allset.cb_key_all()                      # every keyable visible channel
    assert cb.fcurve(pb2, "sz") is not None and cb.fcurve(pb3, "tx") is None


def test_custom_attribute_on_joint():
    arm = _skeleton()
    _pick(arm, "joint2")
    pb2 = arm.pose.bones["joint2"]
    pb2["curl"] = 1.0
    cb.rebuild_rows()
    assert cb.full_path(pb2, '["curl"]') == 'pose.bones["joint2"]["curl"]'
    row = next(r for r in bpy.context.scene.allset_cb.rows if r.kind == "CUSTOM")
    row.text = "+=2"
    assert pb2["curl"] == 3.0
    cb.set_selected_channels(["cp:curl"])
    bpy.ops.allset.cb_key_selected()
    assert cb.fcurve(pb2, "cp:curl") is not None


def test_quaternion_joint_rotate_order_button():
    arm = _skeleton(quaternion_last=True)
    _pick(arm, "joint3")
    pb3 = arm.pose.bones["joint3"]
    pb3.rotation_quaternion = (0.9, 0.3, 0.2, 0.1)
    pb3.rotation_quaternion.normalize()
    bpy.context.view_layer.update()
    before = pb3.matrix_basis.copy()
    # a quaternion joint shows Maya's Rotate X / Y / Z (written back as a quaternion)
    assert cb.has_channel(pb3, "rx")
    rec = _draw_cb()
    assert "Rotation mode QUATERNION" not in rec.texts("label")
    assert bpy.ops.allset.cb_rotate_order(order='XYZ') == {'FINISHED'}     # converting still keeps the pose
    bpy.context.view_layer.update()
    assert pb3.rotation_mode == 'XYZ' and cb.has_channel(pb3, "rx")
    err = max(abs(a - b) for ra, rb in zip(before, pb3.matrix_basis) for a, b in zip(ra, rb))
    assert err < 1e-5, ("pose kept", err)


def test_constraint_weight_rows():
    arm = _skeleton()
    _mode('OBJECT')
    loc = bpy.data.objects.new("locator1", None)
    bpy.context.scene.collection.objects.link(loc)
    bpy.context.view_layer.objects.active = arm
    _mode('POSE')
    pb2, pb3 = arm.pose.bones["joint2"], arm.pose.bones["joint3"]
    for pb in (pb2, pb3):
        con = pb.constraints.new('COPY_LOCATION')
        con.target = loc
    pb2.constraints.new('LIMIT_ROTATION')             # a Maya transform limit, not an INPUTS node
    _pick(arm, "joint2", "joint3")
    con2 = pb2.constraints[0]
    assert [c.type for c in cb.constraints(pb2)] == ['COPY_LOCATION']
    assert cb.constraint_node_name(pb2, con2) == "joint2_pointConstraint1"
    assert cb.weight_name(con2) == "locator1W0"
    assert cb.constrained_keys(pb2) == {"tx", "ty", "tz"}
    con2.use_y = False
    assert cb.constrained_keys(pb2) == {"tx", "tz"}
    assert not [r for r in bpy.context.scene.allset_cb.rows if r.kind == "CONSTRAINT"], "collapsed node"
    cb.set_open(pb2, cb.con_node(pb2, con2))          # Maya: click the node name to show its weight
    cb.rebuild_rows()
    rows = [r for r in bpy.context.scene.allset_cb.rows if r.kind == "CONSTRAINT"]
    assert len(rows) == 1 and rows[0].name == "influence", [(r.kind, r.name) for r in rows]
    rows[0].text = "0.5"
    assert abs(con2.influence - 0.5) < 1e-6 and abs(pb3.constraints[0].influence - 0.5) < 1e-6
    rec = _draw_cb()
    labels = rec.texts("label")
    assert "INPUTS" in labels and "locator1W0" in labels, labels
    assert "joint2_pointConstraint1" in rec.texts("operator"), "the node name is the expand button"
    blue = [kw for k, _t, kw in rec.log if k == "operator" and kw.get("depress") and _t not in
            ("Translate X", "Translate Z")]
    assert len(blue) == 2, ("Translate X / Z drawn as blue (pressed) value buttons", blue)
    con2.enabled = False
    assert cb.constrained_keys(pb2) == set()
    # An armature target names the joint (Maya: the joint's weight attribute)
    con2.target, con2.subtarget = arm, "joint1"
    assert cb.weight_name(con2) == "joint1W0"
    # Objects: Child Of = Maya parent constraint, all transform channels
    _mode('OBJECT')
    ch = loc.constraints.new('CHILD_OF')
    ch.target = arm
    assert cb.constraint_node_name(loc, ch) == "locator1_parentConstraint1"
    assert cb.constrained_keys(loc) == {"tx", "ty", "tz", "rx", "ry", "rz", "sx", "sy", "sz"}


def test_object_mode_armature_hint_and_object_menu():
    arm = _skeleton()
    _mode('OBJECT')
    arm.select_set(True)
    assert cb.POSE_HINT in _draw_cb().texts("label")
    _mode('POSE')
    _pick(arm, "joint1", "joint3")
    rec = Recorder()
    cb.ALLSET_MT_cb_object.draw(type("M", (), {"layout": rec})(), bpy.context)
    assert rec.texts("operator") == ["joint1", "joint3"]
    assert bpy.ops.allset.cb_make_lead(name="joint3", only=True) == {'FINISHED'}
    assert cb.lead() == arm.pose.bones["joint3"] and cb.targets() == [arm.pose.bones["joint3"]]


def test_virtual_slider_targets_joints():
    arm = _skeleton()
    _pick(arm, "joint1", "joint2")
    cb.set_selected_channels(["rx"])
    pairs = cb.slider_targets(bpy.context)
    assert [(n.name, k) for n, k in pairs] == [("joint1", "rx"), ("joint2", "rx")]
    events = {(km, idname, ev.get("type"), ev.get("ctrl", False)) for km, idname, ev, _p, _s in patches.ADDED}
    assert ("Pose", "allset.cb_virtual_slider", "MIDDLEMOUSE", False) in events
    assert ("Object Non-modal", "object.posemode_toggle", "TAB", True) in events


def test_outliner_joint_rows_and_click():
    arm = _skeleton()
    _mode('OBJECT')
    wm = bpy.context.window_manager
    outliner.rebuild(force=True)
    rows = [(r.kind, r.label, r.depth, r.has_children) for r in wm.allset_outliner_rows]
    assert rows == [('OBJECT', "skeleton1", 0, True)], rows
    arm.allset_expanded = True
    arm.data.bones["joint1"].allset_expanded = True
    outliner.rebuild(force=True)
    rows = [(r.kind, r.label, r.depth) for r in wm.allset_outliner_rows]
    assert rows == [('OBJECT', "skeleton1", 0), ('JOINT', "joint1", 1), ('JOINT', "joint2", 2)], rows
    bpy.ops.allset.outliner_expand(name="skeleton1", bone="joint1", recursive=True)
    bpy.ops.allset.outliner_expand(name="skeleton1", bone="joint1", recursive=True)
    rows = [r.label for r in wm.allset_outliner_rows]
    assert rows == ["skeleton1", "joint1", "joint2", "joint3"], rows
    assert outliner.icon_for(wm.allset_outliner_rows[2], arm) == 'BONE_DATA'
    # click joint2: pose mode + that joint
    assert bpy.ops.allset.outliner_select(index=2, mode='REPLACE') == {'FINISHED'}
    assert arm.mode == 'POSE' and cb.lead() == arm.pose.bones["joint2"]
    assert wm.allset_outliner_index == 2
    bpy.ops.allset.outliner_select(index=3, mode='TOGGLE')
    assert [pb.name for pb in cb.targets()] == ["joint3", "joint2"]
    bpy.ops.allset.outliner_select(index=1, mode='RANGE')
    assert {pb.name for pb in cb.targets()} == {"joint1", "joint2", "joint3"}
    wm.allset_outliner_rows[3].label = "wrist"            # rename = bone name
    assert "wrist" in arm.data.bones
    # an object row leaves pose mode
    bpy.ops.allset.outliner_select(index=0, mode='REPLACE')
    assert arm.mode == 'OBJECT' and cb.lead() == arm


def test_attribute_editor_joint_tabs():
    arm = _skeleton()
    _mode('OBJECT')
    loc = bpy.data.objects.new("locator1", None)
    bpy.context.scene.collection.objects.link(loc)
    bpy.context.view_layer.objects.active = arm
    _mode('POSE')
    pb2 = arm.pose.bones["joint2"]
    con = pb2.constraints.new('COPY_ROTATION')
    con.target = loc
    _pick(arm, "joint2")
    assert ae.tabs(pb2) == [("J", "joint2", "joint"),
                            (f"C:{con.name}", "joint2_orientConstraint1", "orientConstraint")]
    wm = bpy.context.window_manager
    wm.allset_ae_tab, wm.allset_ae_kind = "", "S"
    assert ae.current_tab(bpy.context, pb2) == "J"
    rec = Recorder()
    notices = import_module(kit.MODULE + ".ui.notices")
    tips, tip = [], notices.tip
    notices.tip = lambda layout, text, **kw: tips.append(text)
    try:
        ae.draw(rec, bpy.context, pb2)
    finally:
        notices.tip = tip
    labels = rec.texts("label")
    assert "joint:" in labels and "Transform Attributes" in labels and "Joint" in labels, labels
    # the joint axis note is a tooltip (no Blender sentences in the AE)
    assert "Joint Orient" in labels and ae.JOINT_AXIS_NOTE not in labels and ae.JOINT_AXIS_NOTE in tips
    assert "Display as Control Shape" in rec.texts("prop") and "Draw Style" in rec.texts("prop")
    ae.set_tab(bpy.context, f"C:{con.name}")
    rec = Recorder()
    ae.draw(rec, bpy.context, pb2)
    assert "locator1W0" in rec.texts("prop"), rec.texts("prop")
    # Joint Orient = rest rotation relative to the parent's rest
    eul = ae.joint_orient(pb2)
    assert all(abs(v) < 1e-5 for v in eul), tuple(eul)     # a straight chain: no orient
    assert bpy.ops.allset.ae_add_limit(type='LIMIT_ROTATION') == {'FINISHED'}
    assert any(c.type == 'LIMIT_ROTATION' for c in pb2.constraints), "Limit Information adds to the joint"
    _mode('EDIT')
    rec = Recorder()
    ae.draw_panel(rec, bpy.context)
    assert "Editing joints: W / E / R move them," in rec.texts("label")
    _mode('POSE')
