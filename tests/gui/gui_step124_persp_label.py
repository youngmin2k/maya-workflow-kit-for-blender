"""The Maya camera label "persp" drew twice in pose / paint modes. Those modes add a 29 px asset shelf
header strip under the view; with Region Overlap off (Maya mode) it never draws and kept the pixels of the
label drawn there before the mode change. ui/view_furniture.py hides that strip while the shelf is collapsed (the
view gets the height back) and shows it again when the kit unregisters. Checked on the regions and on a screenshot
(the camera label drawn once)."""

import os
import sys
import tempfile
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, run, step, setup, screenshot, win, load_maya_layout  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


def area3d():
    return max((a for a in win().screen.areas if a.type == 'VIEW_3D'), key=lambda a: a.width * a.height)


def region(kind):
    return next((r for r in area3d().regions if r.type == kind), None)


def redraw():
    for a in win().screen.areas:
        a.tag_redraw()


def label_rows():
    """Rows (window y) under the view's bottom 70 px with label-bright pixels near the label's x."""
    path = os.path.join(SHOTS or tempfile.gettempdir(), "gui_step124_pose.png")
    screenshot(path)
    img = bpy.data.images.load(path)
    w, h = img.size
    px = img.pixels[:]
    bpy.data.images.remove(img)
    area = area3d()
    cx = area.x + area.width // 2      # area.x / y are window coordinates, like the screenshot (not win().x / y)
    rows = []
    for y in range(area.y, area.y + 70):
        n = sum(1 for x in range(cx - 60, cx + 40) if px[(y * w + x) * 4] > 0.8)
        if 0 < n < 60:          # text, not the area's outline (a full-width line)
            rows.append(y)
    groups = []
    for y in rows:
        if groups and y - groups[-1][-1] <= 2:
            groups[-1].append(y)
        else:
            groups.append([y])
    return sum(1 for g in groups if len(g) >= 5)     # text lines; grid lines are 1-2 px


@step
def s_setup():
    setup()
    load_maya_layout()


@step
def s_arm():
    bpy.ops.allset.keymap_activate()
    bpy.ops.object.armature_add()
    C["h"] = region('WINDOW').height
    redraw()


@step
def s_pose():
    bpy.ops.object.mode_set(mode='POSE')
    redraw()


@step
def s_wait():
    redraw()


@step
def s_wait2():
    redraw()


@step
def s_check():
    header = region('ASSET_SHELF_HEADER')
    check(f"pose mode, Region Overlap off: the asset shelf header strip is hidden "
          f"({header and header.height} px), the view keeps its height ({region('WINDOW').height} / {C['h']})",
          header is not None and header.height <= 1 and region('WINDOW').height == C["h"])
    n = label_rows()
    check(f"the camera label is drawn once ({n} text line(s) at the bottom of the view)", n == 1)


@step
def s_unregister():
    vf = import_module(MODULE + ".ui.view_furniture")
    hid = bool(vf._HIDDEN)
    vf._show_strips()
    header = region('ASSET_SHELF_HEADER')
    if hid:
        check(f"unregister gives the strip back ({header and header.height} px)",
              header is not None and header.height > 1)
    else:   # 5.2.3: Blender keeps the collapsed shelf's header at 1 px itself, the kit hid nothing
        check(f"the kit hid no strip, so unregister has nothing to give back ({header and header.height} px)",
              header is not None and header.height <= 1)


run()
