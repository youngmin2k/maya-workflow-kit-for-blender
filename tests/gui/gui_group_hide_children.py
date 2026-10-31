"""Maya: hiding a group hides everything below it, and a node parented under a hidden group is hidden too (Maya
DAG rule). In a real UI: Ctrl+H on group1 in the Outliner and in the viewport, then pCube2 parented into the hidden
group (no explicit ``dag.sync``: the depsgraph handler has to catch it), and Shift+H in the Outliner shows the group
again. Before the fix the Outliner's Ctrl+H was Blender's ``outliner.hide`` (``hide_set``): pCube1 stayed visible and
Shift+H there did nothing."""

import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, run, step, setup, view3d, win  # noqa: E402


def outliner():
    area = next(a for a in win().screen.areas if a.type == 'OUTLINER')
    return area, next(r for r in area.regions if r.type == 'WINDOW')


def hover(area_region):
    _a, r = area_region
    ev('MOUSEMOVE', 'NOTHING', x=r.x + r.width // 2, y=r.y + r.height // 2)


def ctrl_h():
    ev('LEFT_CTRL', 'PRESS', ctrl=True)
    ev('H', 'PRESS', ctrl=True)
    ev('H', 'RELEASE', ctrl=True)
    ev('LEFT_CTRL', 'RELEASE')


def obs():
    return bpy.data.objects["group1"], bpy.data.objects["pCube1"], bpy.data.objects["pCube2"]


def select_only(ob):
    for o in bpy.context.view_layer.objects:
        o.select_set(o == ob)
    bpy.context.view_layer.objects.active = ob


def show_all():
    for o in bpy.context.view_layer.objects:
        o.hide_viewport = False
        o.hide_set(False)
    import_module(MODULE + ".operators.dag").sync()


def state(ob):
    return f"{ob.name}: visible={ob.visible_get()} hide_viewport={ob.hide_viewport} hide_get={ob.hide_get()}"


@step
def s_setup():
    setup()
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    area, region = view3d()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        bpy.ops.allset.create(kind='CUBE')
        c1 = bpy.context.active_object
        bpy.ops.allset.create(kind='CUBE')
        select_only(c1)
        bpy.ops.allset.group()
    g, c1, c2 = obs()
    check(f"setup: group1 > pCube1, pCube2 beside ({c1.parent and c1.parent.name}, {c2.parent})",
          c1.parent == g and c2.parent is None)
    select_only(g)
    hover(outliner())


@step
def s_outliner_ctrl_h():
    ctrl_h()


@step
def s_outliner_check():
    g, c1, _c2 = obs()
    print(state(g), "|", state(c1), flush=True)
    check(f"Outliner Ctrl+H hides group1 ({state(g)})", not g.visible_get())
    check(f"Outliner Ctrl+H is Maya's Hide: group1's Visibility goes off ({state(g)})", g.hide_viewport)
    check(f"Outliner Ctrl+H: pCube1 under group1 is hidden too ({state(c1)})", not c1.visible_get())
    bpy.context.view_layer.objects.active = g      # group1 clicked in the Outliner (a hidden row can't select)


@step
def s_outliner_shift_h():
    ev('LEFT_SHIFT', 'PRESS', shift=True)
    ev('H', 'PRESS', shift=True)
    ev('H', 'RELEASE', shift=True)
    ev('LEFT_SHIFT', 'RELEASE')


@step
def s_outliner_shown():
    g, c1, _c2 = obs()
    print(state(g), "|", state(c1), flush=True)
    check(f"Outliner Shift+H shows group1 again ({state(g)})", g.visible_get())
    check(f"Outliner Shift+H: pCube1 comes back with it ({state(c1)})", c1.visible_get())
    show_all()
    select_only(g)
    hover(view3d())


@step
def s_view_ctrl_h():
    ctrl_h()


@step
def s_view_check():
    g, c1, _c2 = obs()
    print(state(g), "|", state(c1), flush=True)
    check(f"viewport Ctrl+H hides group1 ({state(g)})", not g.visible_get())
    check(f"viewport Ctrl+H: pCube1 under group1 is hidden too ({state(c1)})", not c1.visible_get())
    # pCube2 dropped onto the hidden group1 in the Outliner (the drop writes the parent; no explicit sync here)
    c2 = obs()[2]
    mw = c2.matrix_world.copy()
    c2.parent = g
    c2.matrix_world = mw


@step
def s_settle():
    pass


@step
def s_parent_check():
    g, _c1, c2 = obs()
    print(state(c2), flush=True)
    check(f"pCube2 is now under group1 ({c2.parent and c2.parent.name})", c2.parent == g)
    check(f"pCube2 parented into the hidden group is hidden ({state(c2)})", not c2.visible_get())


run()
