"""#171: on a Rigify rig in Maya mode, clicking a control dropped the rig out of Pose mode — the click watcher
(ui/toolbox pose_empty_click) tested only bone head-tail lines, so a click on a custom-shape widget away from its bone
counted as empty space; a near miss went select_object_at -> Object mode; with the Move tool an unkeyed rig went to
Edit mode. Maya has no selection mode: picking a control never changes the mode, a click on nothing clears the
selection (Maya UV shell selection rules), a click on another object selects it.

The session: Maya layout, Rigify human rig generated, Pose mode, Select Box tool: wire clicks on torso / hips / head /
root, a Shift click, a near miss and an empty click, W + a control click, a click on a mesh, Ctrl+Z, save / open."""

import os
import sys
import tempfile
from importlib import import_module

import bpy
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, run, setup, step, screenshot, load_maya_layout, view3d, win  # noqa: E402

GUI_TIMEOUT = 300
SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {"t": {}}


def rig():
    return next((o for o in bpy.context.scene.objects if o.type == 'ARMATURE' and o.name.startswith("rig")), None)


def ctx():
    area, r = view3d()
    return bpy.context.temp_override(window=win(), area=area, region=r)


def picked():
    rg = rig()
    cb = import_module(MODULE + ".ui.channel_box")
    return sorted(pb.name for pb in rg.pose.bones if cb.bone_selected(pb))


def add(fn, name):
    fn.__name__ = name
    step(fn)


@step
def s_setup():
    setup()
    load_maya_layout()


@step
def s_rig():
    import addon_utils
    addon_utils.enable("rigify", default_set=True)
    with ctx():
        bpy.ops.object.armature_human_metarig_add()
        meta = bpy.context.view_layer.objects.active
        bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.pose.rigify_generate()
        meta.hide_set(True)
        bpy.ops.allset.create(kind='CUBE')                    # a mesh away from the rig
        cube = bpy.context.view_layer.objects.active
        cube.location = (1.5, 0.0, 1.0)      # metres, beside the 2 m human rig
        C["cube"] = cube.name
    rg = rig()
    check(f"Rigify rig generated ({rg and len(rg.pose.bones)} bones)", rg is not None)


@step
def s_pose():
    rg = rig()
    with ctx():
        for o in bpy.context.selected_objects:
            o.select_set(False)
        rg.select_set(True)
        bpy.context.view_layer.objects.active = rg
        bpy.ops.object.mode_set(mode='POSE')
        bpy.ops.pose.select_all(action='SELECT')
        bpy.ops.view3d.view_selected()
        bpy.ops.pose.select_all(action='DESELECT')
    check("rig in Pose mode", rg.mode == 'POSE')


@step
def s_wait_view():
    pass


@step
def s_targets():
    """Per control, a point on its drawn widget far from every bone line (where the old watcher saw empty space)."""
    from bpy_extras.view3d_utils import location_3d_to_region_2d
    cs = import_module(MODULE + ".operators.control_shapes")
    area, r = view3d()
    rv3d = area.spaces.active.region_3d
    rg = rig()
    dg = bpy.context.evaluated_depsgraph_get()
    mw = rg.matrix_world
    seg = []
    for pb in rg.pose.bones:
        p = location_3d_to_region_2d(r, rv3d, mw @ pb.head)
        q = location_3d_to_region_2d(r, rv3d, mw @ pb.tail)
        if p is not None and q is not None:
            seg.append((p, q))
    P = np.array([s[0] for s in seg])
    Q = np.array([s[1] for s in seg])

    def line_dist(pt):
        d = Q - P
        t = np.clip(((pt - P) * d).sum(1) / np.maximum((d * d).sum(1), 1e-9), 0, 1)
        return float(np.linalg.norm(pt - (P + t[:, None] * d), axis=1).min())
    for name in ("torso", "hips", "head", "root", "hand_ik.L"):
        pb = rg.pose.bones[name]
        sa, sb = cs.shape_segments(rg, pb, dg)
        best = None
        for A, B in zip(sa, sb):
            s = location_3d_to_region_2d(r, rv3d, (A + B) / 2)
            a2, b2 = location_3d_to_region_2d(r, rv3d, A), location_3d_to_region_2d(r, rv3d, B)
            if s is None or a2 is None or b2 is None or not (30 < s[0] < r.width - 30 and 30 < s[1] < r.height - 30):
                continue
            tang = np.array(b2) - np.array(a2)
            if np.linalg.norm(tang) < 1:
                continue
            tang /= np.linalg.norm(tang)
            dl = line_dist(np.array(s))
            if best is None or dl > best[0]:
                best = (dl, np.array(s), np.array((-tang[1], tang[0])))
        if best is not None:
            C["t"][name] = best
        else:
            print("no target", name, len(sa), r.width, r.height, flush=True)
    print("targets", {k: round(v[0], 1) for k, v in C["t"].items()}, flush=True)
    check("widget points found for torso / hips / head / root", all(n in C["t"] for n in ("torso", "hips", "head", "root")))


def at(name, offset=0.0):
    _area, r = view3d()
    _d, s, n = C["t"][name]
    p = s + n * offset
    return r.x + int(round(p[0])), r.y + int(round(p[1]))


def click(tag, where, shift=False, then=None):
    def hover():
        x, y = where()
        ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
    add(hover, f"{tag}_hover")
    add(lambda: ev('LEFTMOUSE', 'PRESS', shift=shift), f"{tag}_press")
    add(lambda: ev('LEFTMOUSE', 'RELEASE', shift=shift), f"{tag}_release")
    add(lambda: None, f"{tag}_w1")       # the old watcher acted 0.06 s after the click
    add(lambda: None, f"{tag}_w2")
    if then:
        add(then, f"{tag}_check")


for name in ("torso", "hips", "head", "root"):
    click(f"wire_{name}", lambda name=name: at(name),
          then=lambda name=name: check(f"click on the {name} widget: Pose mode kept, {name} picked ({picked()})",
                                       rig().mode == 'POSE' and picked() == [name]))

click("shift_torso", lambda: at("torso"), shift=True,
      then=lambda: check(f"Shift click adds torso, still Pose ({picked()})",
                         rig().mode == 'POSE' and picked() == ["root", "torso"]))

click("near_miss_root", lambda: at("root", 14.0),
      then=lambda: check(f"a click 14 px off the root widget (outside Maya's click box): Pose kept, selection "
                         f"cleared ({picked()})", rig().mode == 'POSE' and picked() == []))

click("wire_root2", lambda: at("root"),
      then=lambda: check("the next control click selects again", rig().mode == 'POSE' and picked() == ["root"]))


def to_move():
    with ctx():
        bpy.ops.wm.tool_set_by_id(name="builtin.move")


add(to_move, "w_tool")
add(lambda: None, "w_settle")
if True:
    click("w_hand", lambda: at("hand_ik.L") if "hand_ik.L" in C["t"] else at("head"),
          then=lambda: check(f"Move tool + control click: still Pose, not Edit ({rig().mode}, {picked()})",
                             rig().mode == 'POSE' and len(picked()) == 1))
add(lambda: None, "w_watch1")       # joint_selection.sync_tool_mode runs every 0.25 s
add(lambda: None, "w_watch2")
add(lambda: check(f"the 0.25 s tool watch kept Pose ({rig().mode})", rig().mode == 'POSE'), "w_watch_check")


def empty_point():
    area, r = view3d()
    return r.x + 40, r.y + r.height - 60


click("empty", empty_point,
      then=lambda: check(f"click on empty space: Pose kept, nothing picked ({picked()})",
                         rig().mode == 'POSE' and picked() == []))


def cube_point():
    from bpy_extras.view3d_utils import location_3d_to_region_2d
    area, r = view3d()
    ob = bpy.data.objects[C["cube"]]
    p = location_3d_to_region_2d(r, area.spaces.active.region_3d, ob.matrix_world.translation)
    C["cube_seen"] = p is not None and 0 < p[0] < r.width and 0 < p[1] < r.height
    return (r.x + int(p[0]), r.y + int(p[1])) if p is not None else empty_point()


def frame_all():
    with ctx():
        bpy.ops.view3d.view_all()


add(frame_all, "frame_all")
add(lambda: None, "frame_wait")
click("cube", cube_point,
      then=lambda: check(f"click on a mesh: Pose left, the mesh selected ({bpy.context.mode}, "
                         f"{bpy.context.view_layer.objects.active and bpy.context.view_layer.objects.active.name})",
                         not C.get("cube_seen") or (rig().mode == 'OBJECT'
                                                    and bpy.context.view_layer.objects.active.name == C["cube"])))


@step
def s_shot():
    if SHOTS:
        screenshot(os.path.join(SHOTS, "gui_step255_rigify.png"))


@step
def s_undo():
    with ctx():
        bpy.ops.ed.undo()
    check("Ctrl+Z after the mesh click: no error", True)


@step
def s_save_open():
    C["file"] = os.path.join(tempfile.mkdtemp(), "rig255.blend")
    with ctx():
        if bpy.context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.wm.save_as_mainfile(filepath=C["file"])
    bpy.ops.wm.open_mainfile(filepath=C["file"])


@step
def s_close_security_popup():
    from sim import tap
    tap('ESC')      # Blender asks about the Rigify rig_ui.py text's auto-run after an open


@step
def s_reopened_pose():
    rg = rig()
    with ctx():
        for o in bpy.context.selected_objects:
            o.select_set(False)
        rg.select_set(True)
        bpy.context.view_layer.objects.active = rg
        bpy.ops.object.mode_set(mode='POSE')
        bpy.ops.wm.tool_set_by_id(name="builtin.select_box")
        bpy.ops.pose.select_all(action='SELECT')
        bpy.ops.view3d.view_selected()
        bpy.ops.pose.select_all(action='DESELECT')
    check("saved / reopened rig back in Pose", rig().mode == 'POSE')


@step
def s_wait2():
    pass


@step
def s_wait3():
    pass


@step
def s_targets2():
    s_targets()


def s_diag():
    sp = import_module(MODULE + ".operators.select_priority")
    area, r = view3d()
    x, y = at("torso")
    with bpy.context.temp_override(window=win(), area=area, region=r):
        got = sp.pick_joint(bpy.context, rig(), (x - r.x, y - r.y), sp.RADIUS_PX * bpy.context.preferences.system.ui_scale)
    print("diag pick_joint", got, "at", (x - r.x, y - r.y), "region", r.width, r.height, "mode", bpy.context.mode,
          "tool", bpy.context.workspace.tools.from_space_view3d_mode('POSE').idname, flush=True)
    if SHOTS:
        screenshot(os.path.join(SHOTS, "gui_step255_reopen.png"))


click("re_torso", lambda: at("torso"),
      then=lambda: check(f"after reopening: torso widget click keeps Pose ({picked()})",
                         rig().mode == 'POSE' and picked() == ["torso"]))

run()
