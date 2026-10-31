"""#201: in a real UI: Maya Workflow Kit layout, Create > Lights shows Dome Light last; running it with an
image gives the World an environment texture and a selected domeLight1 locator with Intensity in the Channel Box;
the viewport (Material Preview) shows the image; one Ctrl+Z takes it all back.
Screenshots: gui_step276_menu.png (Create > Lights), gui_step276_dome.png (dome on)."""

import os
import sys
import tempfile
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, run, step, setup, screenshot, view3d, win, load_maya_layout  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


def shot(name):
    if SHOTS:
        screenshot(os.path.join(SHOTS, name))


class _Rec:
    """Stands in for the Create menu's layout: remembers the submenus it draws."""

    def __init__(self, found):
        object.__setattr__(self, "found", found)

    def menu(self, idname, text="", **_k):
        self.found.append((text, idname))

    def operator(self, *_a, **_k):
        return _Props()

    def __getattr__(self, _name):
        return lambda *a, **k: self

    def __setattr__(self, _name, _value):
        pass


class _Props:
    def __setattr__(self, _name, _value):
        pass


def lights_menu():
    """The Create menu's Lights submenu."""
    found = []
    cls = getattr(bpy.types, import_module(MODULE + ".ui.menu_sets").menu_idname("mainCreateMenu"))
    from types import SimpleNamespace
    cls.draw(SimpleNamespace(layout=_Rec(found)), bpy.context)
    return next(idn for text, idn in found if text.startswith("Lights"))


@step
def s_setup():
    setup()
    load_maya_layout()


@step
def s_image():
    path = os.path.join(tempfile.gettempdir(), "gui_dome_test.png")
    img = bpy.data.images.new("dome_src", 64, 32)
    px = []
    for y in range(32):
        for x in range(64):
            px += [x / 63, 0.3, y / 31, 1.0]
    img.pixels = px
    img.filepath_raw = path
    img.file_format = 'PNG'
    img.save()
    bpy.data.images.remove(img)
    C["path"] = path
    area, region = view3d()
    ev('MOUSEMOVE', 'NOTHING', x=region.x + region.width // 2, y=region.y + region.height // 2)
    with bpy.context.temp_override(window=win(), area=area, region=region):
        bpy.ops.wm.call_menu(name=lights_menu())


@step
def s_menu_shot():
    shot("gui_step276_menu.png")
    check(f"Lights menu opened ({lights_menu()})", bool(lights_menu()))
    ev('ESC', 'PRESS')
    ev('ESC', 'RELEASE')


@step
def s_run():
    bpy.ops.ed.undo_push(message="before dome")
    area, region = view3d()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        res = bpy.ops.allset.dome_light('EXEC_DEFAULT', True, filepath=C["path"])
        area.spaces.active.shading.type = 'MATERIAL'
        area.spaces.active.shading.use_scene_world = True
    dome = import_module(MODULE + ".operators.dome_light")
    ob = bpy.data.objects.get("domeLight1")
    tex = bpy.context.scene.world.node_tree.nodes.get(dome.N_TEX)
    check(f"Dome Light ran ({res}), domeLight1 selected, image on the World",
          res == {'FINISHED'} and ob is not None and bpy.context.active_object == ob
          and tex is not None and tex.image is not None)


@step
def s_wait():
    for a in win().screen.areas:
        a.tag_redraw()


@step
def s_dome_shot():
    shot("gui_step276_dome.png")
    cb = import_module(MODULE + ".ui.channel_box")
    ob = bpy.data.objects["domeLight1"]
    check("Intensity is a Channel Box channel", "intensity" in cb.custom_keys(ob))
    area, region = view3d()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        area.spaces.active.shading.type = 'SOLID'
        bpy.ops.ed.undo()


@step
def s_undo_check():
    check("one Ctrl+Z removes the dome", bpy.data.objects.get("domeLight1") is None)


run()
