"""In the Maya layout the kit's click listeners (Channel Box wheel, joint / pose clicks) stay up as modal operators
for the whole session. Timers that wait for "no modal tool running" must not count them: the project autosave and
the Maya tangent watch still run."""

import os
import sys
import tempfile
import time
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import check, load_maya_layout, run, setup, step, view3d, win  # noqa: E402

MODULE = "bl_ext.user_default.allset"
_S = {}


def _mod(name):
    return import_module(f"{MODULE}.{name}")


def _modals():
    return [op.bl_idname for w in bpy.context.window_manager.windows for op in w.modal_operators]


@step
def s_setup():
    setup()
    load_maya_layout()


@step
def s_wait():
    pass                # the listeners start from timers after the layout loads


@step
def s_wait2():
    pass


@step
def s_listeners_up():
    mods = _modals()
    _S["mods"] = mods
    check(f"kit listener modals run in the Maya layout ({mods})", "ALLSET_OT_cb_wheel" in mods)


@step
def s_autosave_edit():
    autosave, project, preferences = _mod("operators.autosave"), _mod("operators.project"), _mod("preferences")
    root = os.path.join(tempfile.mkdtemp(prefix="aslis_"), "proj")
    project.create_project(root)
    _S["root"] = root
    p = preferences.get()
    p.project_root = root
    p.autosave_enable = True
    p.autosave_interval = 1.0
    area, region = view3d()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        bpy.ops.allset.create(kind='CUBE')
        bpy.ops.ed.undo_push(message="cube")


@step
def s_autosave_tick():
    autosave = _mod("operators.autosave")
    autosave._state["last"] = time.monotonic() - 120.0      # the interval has passed
    check(f"the listeners don't hold up the autosave ({_modals()})", not autosave.busy())
    autosave._timer()


@step
def s_autosave_check():
    preferences = _mod("preferences")
    folder = os.path.join(_S["root"], "autosave")
    names = sorted(os.listdir(folder)) if os.path.isdir(folder) else []
    check(f"the autosave wrote a copy ({names})", names == ["untitled.0001.blend"])
    p = preferences.get()
    for attr in ("autosave_enable", "autosave_interval", "project_root"):
        p.property_unset(attr)


@step
def s_tangent_watch():
    mt, cb, compat = _mod("operators.maya_tangents"), _mod("ui.channel_box"), _mod("compat")
    ob = bpy.data.objects["pCube1"]
    sc = bpy.context.scene
    for f, v in ((1, 0.0), (4, 1.0), (10, 3.0), (18, 3.5), (25, 6.0)):
        sc.frame_set(f)
        ob.location.z = v
        cb.keyframe(ob, "tz")
    fc = next(c for c in compat.id_fcurves(ob) if c.data_path == "location" and c.array_index == 2)
    maya = tuple(fc.keyframe_points[2].handle_right)
    mid = fc.keyframe_points[2]
    mid.handle_right = (maya[0], maya[1] + 0.5)          # an edit moved the arm off the Maya shape
    check(f"the tangent watch is not held up by the listeners ({_modals()})", not mt._busy())
    n = mt.watch(bpy.context)
    now = tuple(fc.keyframe_points[2].handle_right)
    check(f"the watch writes the Maya shape back ({n} curve(s), {now} vs {maya})",
          n >= 1 and abs(now[1] - maya[1]) < 1e-5)


run()
