"""Generate the Maya Workflow Kit app template splash images.

    python tools/make_splash.py [--media]   # re-runs itself in `blender -b --factory-startup`

Writes src/allset/app_template/Maya_Workflow_Kit/splash.png (1000x500) and splash_2x.png (2000x1000):
Blender shows them as the splash screen while the Maya Workflow Kit template is active; and
src/allset/welcome.png (256x256, the cubes only) for the welcome dialog (icons are square), and the same
square as docs/distribution/media/icon.png plus media/featured.png (1920x1080) for the extensions.blender.org listing. The artwork is the kit's own (no Maya image or logo): a Maya-like
panel grey and highlight blue, three wire cubes in Maya-style
dormant blue / lead green / selected white, Blender's bundled font.
Rendered with Workbench (flat lighting, object colours, Standard view transform).
"""

import math
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "src" / "allset" / "app_template" / "Maya_Workflow_Kit"
MEDIA = ROOT / "docs" / "distribution" / "media"   # extensions.blender.org icon + featured image


def srgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


def lin(c):
    return tuple(v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in c)


PANEL = "#444444"
HIGHLIGHT = "#5285a6"
TEXT = "#eeeeee"
TEXT_DIM = "#bbbbbb"
TEXT_SMALL = "#808080"
GRID = "#404040"
WIRES = (("#000460", -2.3), ("#43ffa3", 0.0), ("#ffffff", 2.3))   # dormant, lead, selected


def run_outside_blender():
    import subprocess
    sys.path.insert(0, str(ROOT / "tools"))
    import build
    r = subprocess.run([os.environ.get("BLENDER", build.DEFAULT_BLENDER), "-b", "--factory-startup",
                        "--python-exit-code", "1", "--python", __file__, "--", *sys.argv[1:]],
                       env=build.sandbox_env(), stdin=subprocess.DEVNULL,
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    for line in r.stdout.splitlines():
        if line.startswith("make_splash"):
            print(line)
    if r.returncode:
        sys.stderr.write(r.stdout[-3000:] + r.stderr[-3000:])
    return r.returncode


def main():
    import bpy

    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.engine = 'BLENDER_WORKBENCH'
    scene.display.shading.light = 'FLAT'
    scene.display.shading.color_type = 'OBJECT'
    world = bpy.data.worlds.new("bg")        # Workbench renders the world colour as background
    world.color = lin(srgb(PANEL))
    scene.world = world
    scene.display.render_aa = '32'
    scene.view_settings.view_transform = 'Standard'
    scene.render.film_transparent = False
    scene.render.image_settings.file_format = 'PNG'
    scene.render.image_settings.color_mode = 'RGB'

    cam_data = bpy.data.cameras.new("cam")
    cam_data.type = 'ORTHO'
    cam_data.ortho_scale = 20.0
    cam = bpy.data.objects.new("cam", cam_data)
    cam.location = (0, -30, 0)
    cam.rotation_euler = (math.radians(90), 0, 0)
    scene.collection.objects.link(cam)
    scene.camera = cam

    def colour(ob, hex_colour):
        ob.color = (*lin(srgb(hex_colour)), 1.0)

    def box(name, x, z, w, h, hex_colour, y=0.0):
        bpy.ops.mesh.primitive_plane_add(size=1, location=(x, y, z), rotation=(math.radians(90), 0, 0))
        ob = bpy.context.active_object
        ob.name = name
        ob.scale = (w, h, 1)
        colour(ob, hex_colour)

    def text(body, x, z, size, hex_colour, align='LEFT'):
        curve = bpy.data.curves.new(body[:12], 'FONT')
        curve.body = body
        curve.size = size
        curve.align_x = align
        ob = bpy.data.objects.new(body[:12], curve)
        ob.location = (x, -1.0, z)
        ob.rotation_euler = (math.radians(90), 0, 0)
        scene.collection.objects.link(ob)
        colour(ob, hex_colour)

    # Accent bar (Maya highlight blue) and a dark footer band
    box("bar", 0, 4.75, 20, 0.5, HIGHLIGHT)
    box("footer", 0, -4.55, 20, 0.9, "#2b2b2b", y=0.5)
    # Grid lines behind the cubes
    for i in range(-6, 7):
        box(f"gv{i}", -5.0 + i * 0.6, -0.4, 0.03, 6.0, GRID, y=2.0)
        if -4 <= i <= 4:
            box(f"gh{i}", -5.0, -0.4 + i * 0.6, 7.2, 0.03, GRID, y=2.0)
    # Three wire cubes like Maya's selection colours (dormant blue, lead green, selected white)
    for hex_colour, dx in WIRES:
        bpy.ops.mesh.primitive_cube_add(size=1.8, location=(-5.0 + dx, 0, -0.3))
        ob = bpy.context.active_object
        ob.rotation_euler = (math.radians(-30), 0, math.radians(40))
        mod = ob.modifiers.new("wire", 'WIREFRAME')
        mod.thickness = 0.06
        colour(ob, hex_colour)
    # Text (Blender's bundled font)
    title = len(bpy.data.objects)
    # the product name + the lockup line "for Maya users, in Blender" (Maya only
    # as the audience)
    text("Maya Workflow Kit", 0.6, 1.0, 0.95, TEXT)
    text("for Maya users, in Blender", 0.65, -0.3, 0.55, TEXT_DIM)
    text("The whole Maya workflow in Blender, in one install", 0.65, -1.1, 0.3, TEXT_DIM)
    text("hotbox · marking menus · Channel Box · shelves", 0.65, -1.8, 0.3, TEXT_DIM)
    text("Not affiliated with or endorsed by Autodesk. Maya is a trademark of Autodesk, Inc.",
         0.0, -4.7, 0.3, TEXT_SMALL, align='CENTER')

    OUT.mkdir(parents=True, exist_ok=True)
    # --media: only the listing pictures (tools/make_listing_media.py); re-rendering the shipped PNGs changes their bytes
    media_only = "--media" in sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else False
    for name, pct in () if media_only else (("splash.png", 100), ("splash_2x.png", 200)):
        scene.render.resolution_x, scene.render.resolution_y = 1000, 500
        scene.render.resolution_percentage = pct
        scene.render.filepath = str(OUT / name)
        bpy.ops.render.render(write_still=True)
        print(f"make_splash: wrote {(OUT / name).relative_to(ROOT)}")

    # Square welcome icon: the grid + cubes, no text or bars
    for ob in list(bpy.data.objects)[title:]:
        ob.hide_render = True
    for name in ("bar", "footer"):
        bpy.data.objects[name].hide_render = True
    cam.location.x = -5.0
    cam.location.z = -0.4
    cam_data.ortho_scale = 8.4
    scene.render.resolution_x = scene.render.resolution_y = 256
    scene.render.resolution_percentage = 100
    welcome = OUT.parent.parent / "welcome.png"
    MEDIA.mkdir(parents=True, exist_ok=True)
    # the same square picture is the extensions.blender.org icon (256 x 256)
    for path in (MEDIA / "icon.png",) if media_only else (welcome, MEDIA / "icon.png"):
        scene.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        print(f"make_splash: wrote {path.relative_to(ROOT)}")

    # Featured image of the listing (16:9, 1920 x 1080): the splash picture with bars at the taller frame's edges
    for ob in list(bpy.data.objects)[title:]:
        ob.hide_render = False
    for name in ("bar", "footer"):
        bpy.data.objects[name].hide_render = False
    bpy.data.objects["bar"].location.z = 5.375
    bpy.data.objects["footer"].location.z = -5.175
    bpy.data.objects["Not affiliat"].location.z = -5.3
    # the listing leads with "not just a keymap"
    bpy.data.objects["hotbox · mar"].data.body = "not just a keymap: hotbox, Channel Box, menus, shelves, Maya concepts"
    cam.location.x = cam.location.z = 0.0
    cam_data.ortho_scale = 20.0
    scene.render.resolution_x, scene.render.resolution_y = 1920, 1080
    featured = MEDIA / "featured.png"
    scene.render.filepath = str(featured)
    bpy.ops.render.render(write_still=True)
    print(f"make_splash: wrote {featured.relative_to(ROOT)}")


if __name__ == "__main__":
    try:
        import bpy  # noqa: F401
    except ImportError:
        sys.exit(run_outside_blender())
    main()
