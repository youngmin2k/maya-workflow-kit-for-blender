"""#98 #100: no Blender tooltip on the Maya Move / Scale manipulator, no Blender report texts in the status
row (keying set, effector note, Pivot edit, status info warnings, Anim Player job)."""

import inspect
import types
from importlib import import_module

import bpy
from mathutils import Vector

import kit

time_keys = import_module(kit.MODULE + ".operators.time_keys")
skin = import_module(kit.MODULE + ".operators.skin")
joints = import_module(kit.MODULE + ".operators.joints")
hold = import_module(kit.MODULE + ".operators.hold")
manipulator = import_module(kit.MODULE + ".ui.manipulator")
command_line = import_module(kit.MODULE + ".command_line")
cb = import_module(kit.MODULE + ".ui.channel_box")


def _clear():
    if bpy.context.active_object is not None and bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)


def _paths(ob):
    return sorted((fc.data_path, fc.array_index) for fc in kit.fcurves(ob))


def test_98_manipulator_handles_have_no_tooltip():
    # every handle and dial the kit Move / Scale manipulator creates turns Blender's gizmo tooltip off
    for fn in (manipulator.ALLSET_GGT_xform._new, manipulator.ALLSET_GGT_xform._dial):
        assert "use_tooltip = False" in inspect.getsource(fn), fn.__name__
    assert "use_tooltip" in bpy.types.Gizmo.bl_rna.properties


def test_100_shift_w_e_r_key_only_their_channels():
    _clear()
    bpy.ops.mesh.primitive_cube_add()
    ob = bpy.context.active_object
    for channels, path in (("TRANSLATE", "location"), ("ROTATE", "rotation_euler"), ("SCALE", "scale")):
        assert bpy.ops.allset.set_key(channels=channels) == {'FINISHED'}
        assert {p for p, _i in _paths(ob)} >= {path}
    assert _paths(ob) == sorted([(p, i) for p in ("location", "rotation_euler", "scale") for i in range(3)])
    # the keymap: Shift+W / E / R = allset.set_key(channels), IC's keyframe_insert_by_name gone
    kc = kit.maya_kc()
    items = {(i.type, i.properties.channels) for i in kc.keymaps["Screen"].keymap_items
             if i.idname == "allset.set_key" and i.shift and i.active}
    assert items == {("W", "TRANSLATE"), ("E", "ROTATE"), ("R", "SCALE")}, items
    for km in ("Object Mode", "Pose"):
        assert not [i for i in kc.keymaps[km].keymap_items if i.active and i.shift and i.type in {'W', 'E', 'R'}
                    and not i.ctrl and not i.alt and i.idname == "anim.keyframe_insert_by_name"], km


def test_100_ik_handle_result_in_command_line_not_a_blender_note():
    _clear()
    arm = joints.new_skeleton(bpy.context)
    parent = None
    for p in ((0, 0, 0), (0, 0.3, 1), (0, 0, 2)):
        parent = joints.add_joint(arm, Vector(p), parent, length=0.5)
    joints.finish(bpy.context, arm, ["joint1", "joint2", "joint3"])
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode='POSE')
    for pb in arm.pose.bones:
        cb.set_bone_selected(pb, pb.name in ("joint1", "joint3"))
    arm.data.bones.active = arm.data.bones["joint3"]
    assert bpy.ops.allset.ik_handle() == {'FINISHED'}
    assert command_line._result["text"] == "Result: ikHandle1", command_line._result
    assert "Blender has" not in inspect.getsource(skin)


def test_100_no_pivot_edit_report():
    assert "Pivot edit " not in inspect.getsource(hold.ALLSET_OT_pivot_toggle)


class _Layout:
    """Records the template calls a status-bar draw makes."""

    def __init__(self, calls):
        self.calls = calls
        self.ui_units_x = 0

    def row(self, **_kw):
        return self

    def __getattr__(self, name):
        def call(*_a, **_kw):
            self.calls.append(name)
            return self
        return call


def test_100_status_row_has_no_status_info_and_no_player_job():
    calls = []
    context = types.SimpleNamespace(screen=types.SimpleNamespace(is_animation_playing=True),
                                    area=None, window=None, workspace=None, mode='OBJECT',
                                    window_manager=bpy.context.window_manager,
                                    preferences=bpy.context.preferences)
    command_line.draw_help_line(_Layout(calls), context)
    assert "template_reports_banner" in calls and "template_running_jobs" not in calls, calls
    calls.clear()
    context.screen.is_animation_playing = False
    command_line.draw_help_line(_Layout(calls), context)
    assert "template_running_jobs" in calls, calls
    code = [ln for ln in inspect.getsource(command_line.draw_status_bar).splitlines()
            if not ln.strip().startswith("#")]
    assert not any("template_status_info" in ln for ln in code)
