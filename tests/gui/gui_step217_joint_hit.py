"""B3 / B4 in a real UI.
B3: a Joint Tool click inside an existing joint's drawn sphere branches from it, outside it starts a new skeleton
(Maya 2026: hit area = the drawn sphere) - at two zoom levels.
B4: picking the skeleton object with no bone selected enters Pose with the root joint selected (Channel Box = root)."""

import os
import sys
from importlib import import_module

import bpy
from bpy_extras import view3d_utils
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, run, setup, step, tap, win  # noqa: E402

C = {}


def mod(name):
    return import_module(MODULE + name)


def main_view():
    toolbox = mod(".ui.toolbox")
    areas = [a for a in win().screen.areas if a.type == 'VIEW_3D' and not toolbox.is_toolbox(a.spaces.active)]
    area = max(areas, key=lambda a: a.width * a.height)
    return area, next(r for r in area.regions if r.type == 'WINDOW')


def override():
    area, region = main_view()
    return bpy.context.temp_override(window=win(), area=area, region=region)


def running():
    return any(op.bl_idname == "ALLSET_OT_joint_tool" for op in win().modal_operators)


def armatures():
    return [o for o in bpy.data.objects if o.type == 'ARMATURE']


def click_at(x, y):
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
    ev('LEFTMOUSE', 'PRESS', x=x, y=y)
    ev('LEFTMOUSE', 'RELEASE', x=x, y=y)


def sphere_px():
    """(window x, y of joint2's head, its drawn sphere radius in px)."""
    joints = mod(".operators.joints")
    rig = bpy.data.objects[C["rig"]]
    area, region = main_view()
    rv3d = area.spaces.active.region_3d
    bone = rig.data.bones["joint2"]
    head = rig.matrix_world @ bone.head_local
    p = view3d_utils.location_3d_to_region_2d(region, rv3d, head)
    right = rv3d.view_rotation @ Vector((1, 0, 0))
    e = view3d_utils.location_3d_to_region_2d(region, rv3d, head + right * joints.joint_sphere_radius(rig, bone))
    return region.x + p.x, region.y + p.y, (e - p).length


def zoom(distance):
    area, _region = main_view()
    rv3d = area.spaces.active.region_3d
    rv3d.view_location = (0, 0, 4)
    rv3d.view_distance = distance
    area.tag_redraw()


@step
def s_setup():
    setup()
    bpy.ops.allset.make_maya(open_layout=False)
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    joints = mod(".operators.joints")
    with override():
        rig = joints.new_skeleton(bpy.context)
        a = joints.add_joint(rig, (0, 0, 0))
        b = joints.add_joint(rig, (0, 0, 4), a)          # joint1 4 long: joint2's sphere = 0.2
        joints.add_joint(rig, (0, 0, 6), b)
        joints.finish(bpy.context, rig, [a])
        bpy.ops.object.mode_set(mode='OBJECT')
    C["rig"] = rig.name
    zoom(12.0)


def _case(name, factor, expect_branch):
    @step
    def start():
        for o in bpy.context.selected_objects:
            o.select_set(False)
        C["count"] = len(armatures())
        C["bones"] = len(bpy.data.objects[C["rig"]].data.bones)
        x, y, r = sphere_px()
        C["r_" + name] = r
        C["at"] = (int(x + max(r * factor, 0)), int(y))
        with override():
            bpy.ops.allset.joint_tool('INVOKE_DEFAULT')
    start.__name__ = f"s_{name}_start"

    @step
    def first():
        click_at(*C["at"])
    first.__name__ = f"s_{name}_first"

    @step
    def second():
        x, y = C["at"]
        click_at(x + 150, y + 60)
    second.__name__ = f"s_{name}_second"

    @step
    def enter():
        _a, r = main_view()
        ev('MOUSEMOVE', 'NOTHING', x=r.x + r.width // 2, y=r.y + 40)
        tap('RET')
    enter.__name__ = f"s_{name}_enter"

    @step
    def result():
        rig = bpy.data.objects[C["rig"]]
        r = C["r_" + name]
        branched = len(armatures()) == C["count"] and len(rig.data.bones) == C["bones"] + 1
        new_root = len(armatures()) == C["count"] + 1
        check(f"{name}: click {factor:.2f} x sphere ({r:.1f} px) -> "
              f"{'branch' if expect_branch else 'new skeleton'}",
              branched if expect_branch else new_root)
        check(f"{name}: Enter ended the tool", not running())
        with override():
            if bpy.context.mode != 'OBJECT':
                bpy.ops.object.mode_set(mode='OBJECT')
        for o in armatures():
            if o.name != C["rig"]:
                bpy.data.objects.remove(o)
    result.__name__ = f"s_{name}_result"


# zoomed in: sphere ~ 20+ px -> inside at 0.7 r branches, outside at 1.4 r does not
_case("near_in", 0.7, True)
_case("near_out", 1.4, False)


@step
def s_zoom_out():
    zoom(40.0)
    with override():
        bpy.ops.object.mode_set(mode='OBJECT') if bpy.context.mode != 'OBJECT' else None


_case("far_in", 0.7, True)


@step
def s_far_sizes():
    check(f"the sphere is smaller zoomed out ({C['r_far_in']:.1f} < {C['r_near_in']:.1f} px)",
          C["r_far_in"] < C["r_near_in"])


@step
def s_b4_pick():
    rig = bpy.data.objects[C["rig"]]
    cbm = mod(".ui.channel_box")
    with override():
        if bpy.context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        for pb in rig.pose.bones:
            cbm.set_bone_selected(pb, False)
        rig.data.bones.active = None
        for o in bpy.context.selected_objects:
            o.select_set(False)
        bpy.context.view_layer.objects.active = None


@step
def s_b4_select():
    rig = bpy.data.objects[C["rig"]]
    # what an Outliner click on the skeleton does: selected + active (the automatic Pose tick follows)
    rig.select_set(True)
    bpy.context.view_layer.objects.active = rig


@step
def s_b4_wait():
    pass


@step
def s_b4_check():
    rig = bpy.data.objects[C["rig"]]
    cbm = mod(".ui.channel_box")
    check(f"picking the skeleton entered Pose ({rig.mode})", rig.mode == 'POSE')
    ld = cbm.lead()
    check(f"Channel Box lead = the root joint ({getattr(ld, 'name', None)})",
          ld is not None and ld.name == "joint1")


run()
