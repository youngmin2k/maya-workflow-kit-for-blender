"""In a real UI: Maya layout template in the user's theme (the kit ships no theme), area placement,
screenshots."""

import os
import sys

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, run, step, setup, screenshot, win, load_maya_layout  # noqa: E402
from importlib import import_module  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")


def areas(t):
    return [a for a in win().screen.areas if a.type == t]


@step
def s_setup():
    setup()
    load_maya_layout()


@step
def s_wait():
    pass


@step
def s_layout():
    # Maya General: Tool Box | Outliner | view (+ sidebar dock), full-width strip and timeline
    check("workspace General", win().workspace.name == "General")
    views = sorted(areas('VIEW_3D'), key=lambda a: -a.width * a.height)
    v3d, column = views[0], views[-1]
    outl = areas('OUTLINER')[0]
    time = areas('DOPESHEET_EDITOR')[0]
    check("Tool Box column, then Outliner, left of the viewport",
          len(views) == 2 and column.x < outl.x and outl.x + outl.width <= v3d.x + 2)
    # CB/LE | AE | MTK = Maya's tab stack, its own area right of the viewport (no other Properties column)
    md = import_module(MODULE + ".ui.maya_dock")
    props = areas('PROPERTIES')
    check("one Properties area: the Maya tab stack, right of the viewport",
          len(props) == 1 and md.role(props[0]) == 'STACK' and props[0].x >= v3d.x + v3d.width)
    check("timeline across the bottom", time.y < v3d.y and time.width >= win().width - 4)   # 5.x: 2 px edge
    check("Outliner about 16% of the width", 0.10 < outl.width / win().width < 0.22)
    check("no viewport sidebar (the Maya panels are their own areas)", not v3d.spaces.active.show_region_ui)
    if SHOTS:
        screenshot(os.path.join(SHOTS, "gui_step5_layout.png"))
    bpy.ops.mesh.primitive_cube_add()


@step
def s_object():
    md = import_module(MODULE + ".ui.maya_dock")
    check("the tab stack shows the Channel Box with an object", md.current_tab() == 'CHANNEL_BOX')
    if SHOTS:
        screenshot(os.path.join(SHOTS, "gui_step5_object.png"))


run()
