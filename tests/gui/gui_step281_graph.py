"""#192: in a real UI, an animator's first minutes: Maya Workflow Kit layout, a fresh pCube1 selected,
a ~750 px Graph Editor. Maya: the unkeyed cube is listed at once (bare node row); the toolbar is its own row under the
menus with every tangent button in reach; S over the editor keys 10 channels; handles show on selected keys only;
F frames the selected key; Ctrl+Z; Save As + Open keeps the layout."""

import os
import sys
import tempfile
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, load_maya_layout, run, setup, step, win  # noqa: E402

GUI_TIMEOUT = 240
SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "") or bpy.app.tempdir
PATH = os.path.join(tempfile.mkdtemp(), "graph281.blend")
C = {}


def mod(name):
    return import_module(MODULE + name)


def chrome():
    return mod(".ui.editor_chrome")


def shot(name):
    with bpy.context.temp_override(window=win()):
        bpy.ops.screen.screenshot(filepath=os.path.join(SHOTS, name))


def redraw():
    for a in win().screen.areas:
        a.tag_redraw()


def graph():
    a = next((a for a in win().screen.areas if a.ui_type == 'FCURVES'), None)
    return a, (next(r for r in a.regions if r.type == 'WINDOW') if a else None)


def rows():
    a, _r = graph()
    return [(k, n.name, len(c)) for k, n, c in chrome().listed_nodes(bpy.context, a.spaces.active)]


def hover_graph():
    _a, r = graph()
    ev('MOUSEMOVE', 'NOTHING', x=r.x + r.width // 2, y=r.y + r.height // 2)


@step
def s_setup():
    setup()
    bpy.ops.allset.make_maya(open_layout=False)
    load_maya_layout()


@step
def s_scene():
    area = max((a for a in win().screen.areas if a.type == 'VIEW_3D'), key=lambda a: a.width * a.height)
    region = next(r for r in area.regions if r.type == 'WINDOW')
    with bpy.context.temp_override(window=win(), area=area, region=region):
        bpy.ops.allset.create(kind='CUBE')
    C["cube"] = bpy.context.active_object.name
    C["area"] = area.as_pointer()


@step
def s_graph():
    area = next(a for a in win().screen.areas if a.as_pointer() == C["area"])
    check(f"the main view becomes the Graph Editor ({area.width} px wide)", area.width > 600)
    area.ui_type = 'FCURVES'


@step
def s_wait():
    redraw()


@step
def s_wait2():
    redraw()


@step
def s_unkeyed():
    a, _r = graph()
    sp = a.spaces.active
    foot = next(r for r in a.regions if r.type == 'FOOTER')
    check(f"toolbar on its own row under the menus (footer {foot.alignment}, shown {sp.show_region_footer})",
          chrome().toolbar_row(a))
    check("tangent handles on selected keys only (Maya On Active Keys)", sp.use_only_selected_keyframe_handles)
    check(f"unkeyed selected pCube1 = a bare node row (got {rows()})", rows() == [("OBJECT", C["cube"], 0)])
    C["width"] = a.width
    redraw()


@step
def s_shot_unkeyed():
    shot("gui_step281_unkeyed.png")
    hover_graph()


@step
def s_key_s():
    ev('S', 'PRESS')
    ev('S', 'RELEASE')


@step
def s_keyed():
    check(f"S over the Graph Editor keys 10 channels (got {rows()})", rows() == [("OBJECT", C["cube"], 10)])
    ob = bpy.data.objects[C["cube"]]
    bpy.context.scene.frame_set(20)
    ob.location.x = 4.0 * mod(".operators.units").maya_unit()
    ob.keyframe_insert("location", index=0, frame=20)
    bpy.ops.ed.undo_push(message="keys")
    for fc in kit_fcurves(ob):
        for kp in fc.keyframe_points:
            kp.select_control_point = kp.select_left_handle = kp.select_right_handle = False
        fc.select = fc.data_path == "location" and fc.array_index == 0
    fc = next(f for f in kit_fcurves(ob) if f.data_path == "location" and f.array_index == 0)
    fc.keyframe_points[1].select_control_point = True
    redraw()


def kit_fcurves(ob):
    return mod(".compat").id_fcurves(ob)


@step
def s_frame_f():
    hover_graph()
    ev('F', 'PRESS')
    ev('F', 'RELEASE')


@step
def s_framed():
    _a, r = graph()
    t0 = r.view2d.region_to_view(0, 0)[0]
    t1 = r.view2d.region_to_view(r.width - 1, 0)[0]
    check(f"F frames the selected key and its segment (time {t0:.1f} .. {t1:.1f})", t0 < 2 and 18 < t1 < 25)
    redraw()


@step
def s_shot_keyed():
    shot("gui_step281_keyed.png")
    hover_graph()
    ev('Z', 'PRESS', ctrl=True)
    ev('Z', 'RELEASE', ctrl=True)


@step
def s_undone():
    ob = bpy.data.objects[C["cube"]]
    fc = next((f for f in kit_fcurves(ob) if f.data_path == "location" and f.array_index == 0), None)
    n = len(fc.keyframe_points) if fc else 0
    check(f"Ctrl+Z removes the frame 20 key (keys on Translate X: {n})", n == 1)
    bpy.ops.wm.save_as_mainfile(filepath=PATH)


@step
def s_open():
    bpy.ops.wm.open_mainfile(filepath=PATH)


@step
def s_wait3():
    redraw()


@step
def s_reopened():
    a, _r = graph()
    check("reopened: a Graph Editor with the toolbar row", a is not None and chrome().toolbar_row(a))
    if a is not None:
        check(f"reopened: pCube1 listed with its 10 channels (got {rows()})", rows() == [("OBJECT", C["cube"], 10)])
    redraw()


@step
def s_shot_reopened():
    shot("gui_step281_reopened.png")


run()
