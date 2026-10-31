"""In a real UI: Outliner drags parent the Maya way — LMB drop (Blender's drag, redone), MMB drag onto /
between / empty space, selection kept, reorder, undo; screenshot of the MMB drop highlight."""

import math
import os
import sys

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import check, ev, run, step, setup, screenshot, win, load_maya_layout  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
WORLD = {"A": (1, 0, 0), "B": (0, 2, 0), "C": (0, 0, 3), "D": (0, -2, 0)}


def outl():
    a = next(a for a in win().screen.areas if a.type == 'OUTLINER')
    return a, next(r for r in a.regions if r.type == 'WINDOW')


def row_xy(i, frac=0.5):
    """Window position of row i (frac 0 = top edge, 1 = bottom edge)."""
    _a, r = outl()
    h = 20 * bpy.context.preferences.system.ui_scale
    _x, y = r.view2d.view_to_region(0, -(i + frac) * h, clip=False)
    # on the row's (one-letter) name: from ~2.25 units without the mode column (it was ~3.25 with it)
    return r.x + int(2.5 * h), r.y + int(y)


def empty_xy():
    _a, r = outl()
    return r.x + 90, r.y + 15


def ob(n):
    return bpy.data.objects[n]


def identity(o):
    return all(abs(o.matrix_parent_inverse[i][j] - (i == j)) < 1e-6 for i in range(4) for j in range(4))


def world_kept(n):
    return (ob(n).matrix_world.translation - __import__("mathutils").Vector(WORLD[n])).length < 1e-4


def rows_check(expected, label):
    """Steps: hover each of rows 0-4 (one tick), then hit-test it like the kit does (selection put back)."""
    got = []

    def mover(i):
        def s():
            x, y = row_xy(i)
            ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
        return s

    def hitter():
        def s():
            from importlib import import_module
            from sim import MODULE
            od = import_module(MODULE + ".operators.outliner_drag")
            a, r = outl()
            with bpy.context.temp_override(window=win(), area=a, region=r):
                o = od._first_object(od.hit_ids(bpy.context))
            got.append(o.name if o else None)
        return s

    for i in range(5):
        step(mover(i))
        step(hitter())

    @step
    def s_check():
        check(f"{label} ({got})", got[:len(expected)] == expected)


def redraw():
    for a in win().screen.areas:
        a.tag_redraw()


def undo(kind="undo"):
    with bpy.context.temp_override(window=win()):
        getattr(bpy.ops.ed, kind)()


@step
def s_setup():
    setup()
    load_maya_layout()


@step
def s_scene():
    bpy.ops.allset.keymap_activate()
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o)
    col = bpy.context.scene.collection.children[0]
    for n, loc in WORLD.items():
        o = bpy.data.objects.new(n, bpy.data.meshes.new(n))
        col.objects.link(o)
        o.location = loc
    ob("A").rotation_euler = (0, 0, math.radians(30))
    ob("A").scale = (2, 2, 2)
    bpy.ops.ed.undo_push(message="scene")
    redraw()


rows_check(["A", "B", "C", "D", None], "rows (creation order) A B C D")


def drag(button, src, dst, shift=False):
    """Steps: hover, press, small move, move to dst (twice), release, wait."""
    def s1():
        ev('MOUSEMOVE', 'NOTHING', x=src()[0], y=src()[1])

    def s2():
        ev(button, 'PRESS')

    def s3():
        x, y = src()
        ev('MOUSEMOVE', 'NOTHING', x=x + 4, y=y - 12)

    def s4():
        ev('MOUSEMOVE', 'NOTHING', x=dst()[0], y=dst()[1])

    def s5():
        ev(button, 'RELEASE')
    return [s1, s2, s3, s4, s4, s5]


def add(steps):
    for s in steps:
        step(s)


# 1. LMB drop B onto A (Blender's drag) -> Maya parenting, one undo step
add(drag('LEFTMOUSE', lambda: row_xy(1), lambda: row_xy(0)))


@step
def s_wait1():
    redraw()


@step
def s_lmb_check():
    b = ob("B")
    last = bpy.context.window_manager.operators[-1].bl_idname
    check(f"LMB drop: B under A, parent inverse identity, world kept (last op {last})",
          b.parent == ob("A") and identity(b) and world_kept("B") and last == "ALLSET_OT_outliner_reparent")
    check(f"LMB drop: B channels are local to A (Maya), not its world values ({tuple(round(v, 3) for v in b.location)})",
          (b.location - __import__("mathutils").Vector(WORLD["B"])).length > 0.1)
    undo()


@step
def s_lmb_undo():
    check("LMB drop: one undo = before the drop", ob("B").parent is None and world_kept("B"))
    undo("redo")


@step
def s_lmb_redo():
    check("LMB drop: redo = the Maya result", ob("B").parent == ob("A") and identity(ob("B")))
    for o in bpy.data.objects:
        o.select_set(False)
    ob("D").select_set(True)
    bpy.context.view_layer.objects.active = ob("D")
    redraw()


# rows now: A (collapsed), C, D
rows_check(["A", "C", "D"], "rows after parenting: A C D")


# 2. MMB drag C (not selected) onto A: only C moves, selection stays D
_mmb = drag('MIDDLEMOUSE', lambda: row_xy(1), lambda: row_xy(0))
add(_mmb[:-1])


@step
def s_mmb_shot():
    redraw()


@step
def s_mmb_shot2():
    if SHOTS:
        screenshot(os.path.join(SHOTS, "gui_step82_outliner_drag.png"))
    check("MMB drag in progress: nothing parented yet", ob("C").parent is None)


add(_mmb[-1:])


@step
def s_mmb_check():
    c = ob("C")
    check("MMB onto A: C under A, parent inverse identity, world kept",
          c.parent == ob("A") and identity(c) and world_kept("C"))
    check(f"MMB drag kept the selection (D only: {[o.name for o in bpy.context.selected_objects]})",
          [o.name for o in bpy.context.selected_objects] == ["D"] and bpy.context.view_layer.objects.active == ob("D"))
    a, r = outl()
    with bpy.context.temp_override(window=win(), area=a, region=r):
        ids = [i.name for i in bpy.context.selected_ids]
    check(f"Outliner highlight follows the kept selection ({ids})", ids == ["D"])
    # expand A to show its children
    bpy.context.view_layer.objects.active = ob("B")
    with bpy.context.temp_override(window=win(), area=a, region=r):
        bpy.ops.outliner.show_active()
    bpy.context.view_layer.objects.active = ob("D")
    redraw()


rows_check(["A", "B", "C", "D"], "rows with A open: A B C D")


# 3. MMB drag B onto empty space -> world
add(drag('MIDDLEMOUSE', lambda: row_xy(1), empty_xy))


@step
def s_empty_check():
    b = ob("B")
    check("MMB onto empty space: B to the world, world kept", b.parent is None and world_kept("B"))
    redraw()


# rows: A, C (child), D, B — the Maya Outliner is unsorted (creation order) and Maya lists an unparented node last
# among the world's nodes (ui/outliner_order.py)
rows_check(["A", "C", "D", "B"], "rows: A C D B (unparented B last)")


# 4. MMB drag D between the top edge and A (top quarter of row 0) -> D drawn first
add(drag('MIDDLEMOUSE', lambda: row_xy(2), lambda: row_xy(0, 0.1)))


@step
def s_order_check():
    check("reorder kept A in the world and in place, C its child, selection D",
          ob("A").parent is None and world_kept("A") and ob("C").parent == ob("A") and world_kept("C")
          and ob("D").parent is None and [o.name for o in bpy.context.selected_objects] == ["D"])
    redraw()


rows_check(["D", "A", "C", "B"], "rows after the drag: D A C B")

# 5. LMB drop C (Maya child of the rotated, scaled A) onto empty space -> parent_clear redone: world kept
add(drag('LEFTMOUSE', lambda: row_xy(2), empty_xy))


@step
def s_wait5():
    redraw()


@step
def s_clear_check():
    c = ob("C")
    check(f"LMB onto empty space: C to the world, world kept ({tuple(round(v, 3) for v in c.matrix_world.translation)})",
          c.parent is None and world_kept("C") and identity(c))


# 6. MMB drag A onto its own child C: skipped (cycle), nothing changes
@step
def s_cycle_setup():
    ob("C").parent = None
    from importlib import import_module
    from sim import MODULE
    import_module(MODULE + ".operators.parenting").set_parent_maya(ob("C"), ob("A"))
    redraw()


rows_check(["D", "A", "C", "B"], "rows before the cycle drag: D A C B")
add(drag('MIDDLEMOUSE', lambda: row_xy(1), lambda: row_xy(2)))


@step
def s_cycle_check():
    check("MMB onto its own child: skipped", ob("A").parent is None and ob("C").parent == ob("A") and world_kept("A"))


@step
def s_end():
    redraw()


run()
