"""In a real UI: the Maya Graph Editor outliner with pCube1 (translateX / translateY), a keyed
10-joint skeleton and pSphere1's blendShape1 -> joint and blendShape node rows, only the selected nodes highlighted,
the list scrolls (``allset.graph_channel_scroll``), a click on a joint row shows only that joint's curves
(screenshots with ALLSET_GUI_SHOTS)."""

import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, run, setup, step, win, load_maya_layout  # noqa: E402

GUI_TIMEOUT = 240
SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}
JOINTS = 10


def mod(name):
    return import_module(MODULE + name)


def shot(name, window=None):
    if SHOTS:
        with bpy.context.temp_override(window=window or win()):
            bpy.ops.screen.screenshot(filepath=os.path.join(SHOTS, name))


def v3d():
    area = max((a for a in win().screen.areas if a.type == 'VIEW_3D'), key=lambda a: a.width * a.height)
    return area, next(r for r in area.regions if r.type == 'WINDOW')


def graph():
    for w in bpy.context.window_manager.windows:
        for a in w.screen.areas:
            if a.ui_type == 'FCURVES':
                return w, a, next(r for r in a.regions if r.type == 'CHANNELS')
    return None, None, None


def redraw():
    for w in bpy.context.window_manager.windows:
        for a in w.screen.areas:
            a.tag_redraw()


def wev(window, type, value, x, y, **kw):
    window.event_simulate(type=type, value=value, x=x, y=y, **kw)


@step
def s_setup():
    setup()
    bpy.ops.allset.make_maya(open_layout=False)
    load_maya_layout()


@step
def s_scene():
    bpy.ops.allset.keymap_activate()
    area, region = v3d()
    k = mod(".operators.units").maya_unit()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        bpy.ops.allset.create(kind='CUBE')
        cube = bpy.context.active_object
        for frame, x in ((1, 0.0), (24, 5.0)):
            cube.location.x = x * k
            cube.keyframe_insert("location", index=0, frame=frame)
        cube.keyframe_insert("location", index=1, frame=12)
        arm = bpy.data.objects.new("skeleton1", bpy.data.armatures.new("skeleton1"))
        bpy.context.scene.collection.objects.link(arm)
        bpy.context.view_layer.objects.active = arm
        bpy.ops.object.mode_set(mode='EDIT')
        for i in range(JOINTS):
            eb = arm.data.edit_bones.new(f"joint{i + 1}")
            eb.head, eb.tail = (0, 0, i * k), (0, 0, (i + 1) * k)
        bpy.ops.object.mode_set(mode='OBJECT')
        for pb in arm.pose.bones:
            mod(".ui.channel_box").set_bone_selected(pb, True)   # Only Show Selected: curves of selected bones (5.x: no Bone.select)
            pb.rotation_mode = 'XYZ'
            for frame, z in ((1, 0.0), (24, 0.5)):
                pb.rotation_euler.z = z
                pb.keyframe_insert("rotation_euler", index=2, frame=frame)
            pb.keyframe_insert("location", index=1, frame=1)
            pb.keyframe_insert("scale", index=0, frame=1)
        bpy.ops.allset.create(kind='SPHERE')
        sphere = bpy.context.active_object
        sphere.shape_key_add(name="Basis")
        smile = sphere.shape_key_add(name="smile")
        sphere.data.shape_keys.name = "blendShape1"
        for frame, v in ((1, 0.0), (24, 1.0)):
            smile.value = v
            smile.keyframe_insert("value", frame=frame)
        for ob in (cube, arm, sphere):
            ob.select_set(True)
        bpy.context.view_layer.objects.active = cube
        C["graph"] = bpy.ops.allset.menu_item(item="Windows/Animation Editors/Graph Editor")
    C["arm"] = arm.name


@step
def s_graph():
    w, a, ch = graph()
    check(f"Graph Editor window opened ({C['graph']})", a is not None)
    redraw()


@step
def s_graph_wait():
    redraw()


@step
def s_graph_shot():
    w, a, ch = graph()
    chrome = mod(".ui.editor_chrome")
    with bpy.context.temp_override(window=w, area=a, region=ch):
        rows = chrome.rows(bpy.context, a.spaces.active)
        kinds = [k for k, _n, _f in rows]
        names = [n.name for k, n, _f in rows if k != "ATTR"]
        n_vis = chrome.visible_rows(ch)
    check(f"outliner rows: pCube1, blendShape1, {JOINTS} joints, no skeleton1 row ({names[:4]}...)",
          names[:3] == ["pCube1", "blendShape1", "joint1"] and kinds.count("JOINT") == JOINTS
          and "skeleton1" not in names)
    check(f"list longer than the region ({len(rows)} rows, {n_vis} visible)", len(rows) > n_vis)
    C["n"], C["vis"] = len(rows), n_vis
    shot("gui_step150_outliner_top.png", w)


@step
def s_scroll():
    w, a, ch = graph()
    with bpy.context.temp_override(window=w, area=a, region=ch):
        C["scroll"] = bpy.ops.allset.graph_channel_scroll(delta=5)
    redraw()


@step
def s_scroll_check():
    w, a, ch = graph()
    chrome = mod(".ui.editor_chrome")
    with bpy.context.temp_override(window=w, area=a, region=ch):
        off = chrome.scroll_offset(bpy.context, ch, C["n"])
    check(f"scroll by 5 rows ({C['scroll']}, offset {off})", C["scroll"] == {'FINISHED'} and off == 5)
    shot("gui_step150_outliner_scrolled.png", w)
    with bpy.context.temp_override(window=w, area=a, region=ch):
        bpy.ops.allset.graph_channel_scroll(delta=999)
        off = chrome.scroll_offset(bpy.context, ch, C["n"])
        rows = chrome.rows(bpy.context, a.spaces.active)
    check(f"scroll clamps at the last page (offset {off} = {C['n']} - {C['vis']})", off == C["n"] - C["vis"])
    # the last joint's row, on screen after the scroll: click it
    k = next(i for i, r in enumerate(rows) if r[0] == "JOINT" and r[1].name == f"joint{JOINTS}")
    top, h = chrome.metrics(ch)
    C["click"] = (w, ch.x + int(60 * bpy.context.preferences.system.ui_scale), ch.y + top - int((k - off + 0.5) * h))
    redraw()
    wev(w, 'MOUSEMOVE', 'NOTHING', *C["click"][1:])


@step
def s_press():
    w, x, y = C["click"]
    wev(w, 'LEFTMOUSE', 'PRESS', x, y)


@step
def s_release():
    w, x, y = C["click"]
    wev(w, 'LEFTMOUSE', 'RELEASE', x, y)


@step
def s_click_check():
    chrome = mod(".ui.editor_chrome")
    arm = bpy.data.objects[C["arm"]]
    mine = f'pose.bones["joint{JOINTS}"]'
    fcs = chrome.object_curves(arm)
    shown = [fc.data_path for fc in fcs if not fc.hide]
    check(f"click joint{JOINTS} -> only its 3 curves shown and selected ({shown})",
          len(shown) == 3 and all(p.startswith(mine) for p in shown)
          and all(fc.select == fc.data_path.startswith(mine) for fc in fcs))
    with bpy.context.temp_override(window=graph()[0], area=graph()[1], region=graph()[2]):
        labels = [chrome.attr_label(fc) for k, n, fc in chrome.rows(bpy.context, graph()[1].spaces.active)
                  if k == "ATTR" and n.name == "joint1"]
    check(f"joint attributes in the Maya order, not keying order ({labels})",
          labels == ["Translate Y", "Rotate Z", "Scale X"])
    redraw()


@step
def s_click_wait():
    redraw()


@step
def s_click_shot():
    w, _a, _ch = graph()
    shot("gui_step150_outliner_joint_click.png", w)


run()
