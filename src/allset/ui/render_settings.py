# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya Render Settings window (step 105).

Maya 2022 (menus and factory values): a window with the menu bar Edit / Presets / Help, the rows
Render Layer and Render Using, then the tabs Common | <renderer>. Common holds the output: Path / File name / Image
size lines, Color Management, File Output (file name prefix, image format, Frame/Animation ext, frame padding),
Frame Range, Renderable Cameras, Image Size (presets, HD 540 = 960 x 540 by default).

Blender: ``allset.render_settings`` opens a Properties window on the Render tab only, marked as the kit's (window
pointer, like the Light Editor). Its header draws the Maya menus, ``ALLSET_PT_rs_head`` the two rows and the tabs.
Common = ``ALLSET_PT_rs_common`` drawn over ``scene.render`` through Scene properties with get / set (a UI edit
pushes an undo step, step 38); the renderer tab = Blender's own Render panels. Those are hidden in the Common tab by
wrapping their poll (the ``ui/dock_tabs.py`` technique), only in the marked window.
"""

import os

import bpy
from bpy.props import EnumProperty, IntProperty, StringProperty

_WINDOWS = set()        # window pointers of kit Render Settings windows
_wrapped = []           # (panel class, its own poll or None, child panels)

# Image size presets (the Render Settings Presets labels; HD 540 = 960 x 540 is the
# default): key -> (label, width, height, pixel aspect)
SIZES = (
    ("320x240", "320x240", 320, 240, 1.0), ("640x480", "640x480", 640, 480, 1.0),
    ("1K_SQUARE", "1k Square", 1024, 1024, 1.0), ("2K_SQUARE", "2k Square", 2048, 2048, 1.0),
    ("3K_SQUARE", "3k Square", 3072, 3072, 1.0), ("4K_SQUARE", "4k Square", 4096, 4096, 1.0),
    ("CCIR_PAL", "CCIR PAL/Quantel PAL", 720, 576, 1.067), ("CCIR_601", "CCIR 601/Quantel NTSC", 720, 486, 0.9),
    ("FULL_1024", "Full 1024", 1024, 768, 1.0), ("FULL_1280", "Full 1280/Screen", 1280, 1024, 1.0),
    ("HD_540", "HD 540", 960, 540, 1.0), ("HD_720", "HD 720", 1280, 720, 1.0), ("HD_1080", "HD 1080", 1920, 1080, 1.0),
    ("NTSC_4D", "NTSC 4d", 646, 485, 1.0), ("PAL_768", "PAL 768", 768, 576, 1.0), ("PAL_780", "PAL 780", 780, 576, 1.0),
    ("TARGA_486", "Targa 486 (tga)", 512, 486, 1.0), ("TARGA_NTSC", "Targa NTSC (tga)", 512, 482, 1.0),
    ("TARGA_PAL", "Targa PAL (tga)", 512, 576, 1.0),
)
SIZE_ITEMS = [("CUSTOM", "Custom", "Width and height of your own")] + [
    (k, label, f"{w} x {h}") for k, label, w, h, _a in SIZES]
# Maya Frame/Animation ext choices Blender can write (render.filepath patterns); the Maya label first
EXTS = (("SINGLE", "name.ext (Single Frame)", ""), ("DOT", "name.#.ext", "."), ("PLAIN", "name#.ext", ""),
        ("UNDERSCORE", "name_#.ext", "_"))
# Default values like Maya (defaultResolution 960 x 540, imageFormat 32 = PNG, extensionPadding 4, animation off)
DEFAULTS = {"size": "HD_540", "file_format": 'PNG', "padding": 4, "ext": "SINGLE"}


def mark(window):
    _WINDOWS.add(window.as_pointer())


def is_render_settings(context):
    window, space = context.window, context.space_data
    return (window is not None and space is not None and space.type == 'PROPERTIES'
            and window.as_pointer() in _WINDOWS)


# --- render.filepath <-> Maya Path / File name prefix / ext / padding ----------------------------------------------

def split_path(filepath):
    """(directory, prefix, ext key, padding) of a Blender output path ("//../images/shot.####")."""
    head, tail = os.path.split(filepath)
    if filepath.endswith(("/", "\\")):
        head, tail = filepath, ""
    n = len(tail) - len(tail.rstrip("#"))
    stem = tail[:len(tail) - n] if n else tail
    ext = "SINGLE"
    if n:
        if stem.endswith("."):
            ext, stem = "DOT", stem[:-1]
        elif stem.endswith("_"):
            ext, stem = "UNDERSCORE", stem[:-1]
        else:
            ext = "PLAIN"
    return head, stem, ext, n


def join_path(directory, prefix, ext, padding):
    sep = dict((k, s) for k, _l, s in EXTS)[ext]
    tail = prefix + ("" if ext == "SINGLE" else sep + "#" * max(1, padding))
    if not directory:
        return tail
    return directory + ("" if directory.endswith(("/", "\\")) else os.sep) + tail


def _rw(field):
    def get(scene):
        d, p, e, n = split_path(scene.render.filepath)
        # a single-frame name has no frame number: Maya still shows its padding (4, greyed)
        return {"dir": d, "prefix": p, "ext": e, "padding": n or DEFAULTS["padding"]}[field]

    def set_(scene, value):
        d, p, e, n = split_path(scene.render.filepath)
        parts = {"dir": d, "prefix": p, "ext": e, "padding": n or DEFAULTS["padding"]}
        if field == "ext":
            value = [k for k, _l, _s in EXTS][value]
        parts[field] = value
        scene.render.filepath = join_path(parts["dir"], parts["prefix"], parts["ext"], parts["padding"])
    return get, set_


def _ext_get(scene):
    return [k for k, _l, _s in EXTS].index(split_path(scene.render.filepath)[2])


def size_key(render):
    for k, _label, w, h, a in SIZES:
        if (render.resolution_x, render.resolution_y) == (w, h) and abs(render.pixel_aspect_x / render.pixel_aspect_y
                                                                      - a) < 1e-3:
            return k
    return "CUSTOM"


def _size_get(scene):
    return [k for k, _l, _d in SIZE_ITEMS].index(size_key(scene.render))


def apply_size(render, key):
    for k, _label, w, h, a in SIZES:
        if k == key:
            render.resolution_x, render.resolution_y = w, h
            render.resolution_percentage = 100
            # Blender's pixel aspect fields start at 1: an aspect below 1 is written as 1 : 1/a
            render.pixel_aspect_x, render.pixel_aspect_y = (a, 1.0) if a >= 1.0 else (1.0, 1.0 / a)
            return True
    return False


def _size_set(scene, index):
    apply_size(scene.render, SIZE_ITEMS[index][0])


def apply_defaults(scene):
    """Maya Presets > Import Render Settings > Default Settings: HD 540, PNG, single frame, padding 4 (the frame range
    stays: Blender has one range for the Time Slider and the render)."""
    r = scene.render
    apply_size(r, DEFAULTS["size"])
    from .. import compat
    compat.set_file_format(r.image_settings, DEFAULTS["file_format"])
    d, p, _e, _n = split_path(r.filepath)
    r.filepath = join_path(d, p, DEFAULTS["ext"], DEFAULTS["padding"])


def info_lines(scene):
    """Maya's three lines over the Common tab: Path, File name, Image size."""
    r = scene.render
    d, p, _e, _n = split_path(r.filepath)
    name = os.path.basename(r.frame_path(frame=scene.frame_start)) if p or _e != "SINGLE" else \
        f"{bpy.path.display_name_from_filepath(bpy.data.filepath) or 'untitled'}{r.file_extension}"
    w = r.resolution_x * r.resolution_percentage // 100
    h = r.resolution_y * r.resolution_percentage // 100
    return (f"Path: {bpy.path.abspath(d) if d else '(scene folder)'}", f"File name: {name}",
            f"Image size: {w} x {h} ({w / 72:.1f} x {h / 72:.1f} inches 72 pixels/inch)")


# --- panels ------------------------------------------------------------------------------------------------------

def _tab_items(self, context):
    scene = context.scene if context else bpy.context.scene
    engine = scene.render.engine
    try:
        label = scene.render.bl_rna.properties["engine"].enum_items[engine].name
    except (KeyError, AttributeError):
        label = engine.title()
    return [("COMMON", "Common", "Maya Common tab: output path, frame range, cameras, image size"),
            ("RENDERER", label, "The renderer's settings (Blender's Render properties)")]


class _Panel:
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "render"

    @classmethod
    def poll(cls, context):
        return is_render_settings(context)


class ALLSET_PT_rs_head(_Panel, bpy.types.Panel):
    bl_label = "Render Settings"
    bl_options = {'HIDE_HEADER'}

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        window, scene = context.window, context.scene
        layout.template_search(window, "view_layer", scene, "view_layers", text="Render Layer")
        layout.prop(scene.render, "engine", text="Render Using")
        layout.use_property_split = False
        layout.row(align=True).prop(context.window_manager, "allset_rs_tab", expand=True)


class ALLSET_PT_rs_common(_Panel, bpy.types.Panel):
    bl_label = "Common"
    bl_options = {'HIDE_HEADER'}

    @classmethod
    def poll(cls, context):
        return is_render_settings(context) and context.window_manager.allset_rs_tab == 'COMMON'

    def draw(self, context):
        draw_common(self.layout, context)


def draw_common(layout, context):
    scene = context.scene
    r = scene.render
    col = layout.column(align=True)
    for line in info_lines(scene):
        col.label(text=line)
    header, body = layout.panel("ALLSET_rs_color", default_closed=True)
    header.label(text="Color Management")
    if body:
        body.use_property_split = True
        body.prop(scene.view_settings, "view_transform", text="View Transform")
        body.prop(scene.display_settings, "display_device", text="Display")
    header, body = layout.panel("ALLSET_rs_file_output", default_closed=False)
    header.label(text="File Output")
    if body:
        body.use_property_split = True
        body.prop(scene, "allset_rs_dir", text="Path")
        body.prop(scene, "allset_rs_prefix", text="File name prefix")
        if not scene.allset_rs_prefix:
            body.label(text="(not set; using scene name)")
        body.prop(r.image_settings, "file_format", text="Image format")
        body.prop(scene, "allset_rs_ext", text="Frame/Animation ext")
        sub = body.row()
        sub.enabled = scene.allset_rs_ext != 'SINGLE'
        sub.prop(scene, "allset_rs_padding", text="Frame padding")
    header, body = layout.panel("ALLSET_rs_frames", default_closed=False)
    header.label(text="Frame Range")
    if body:
        body.use_property_split = True
        body.prop(scene, "frame_start", text="Start frame")
        body.prop(scene, "frame_end", text="End frame")
        body.prop(scene, "frame_step", text="By frame")
    header, body = layout.panel("ALLSET_rs_cameras", default_closed=False)
    header.label(text="Renderable Cameras")
    if body:
        body.use_property_split = True
        body.prop(scene, "camera", text="Renderable Camera")
    header, body = layout.panel("ALLSET_rs_size", default_closed=False)
    header.label(text="Image Size")
    if body:
        body.use_property_split = True
        body.prop(scene, "allset_rs_size", text="Presets")
        body.prop(r, "resolution_x", text="Width")
        body.prop(r, "resolution_y", text="Height")
        body.prop(r, "resolution_percentage", text="Scale (Blender)")
        aspect = r.resolution_x * r.pixel_aspect_x / max(1.0, r.resolution_y * r.pixel_aspect_y)
        body.label(text=f"Device aspect ratio: {aspect:.3f}")
        body.label(text=f"Pixel aspect ratio: {r.pixel_aspect_x / r.pixel_aspect_y:.3f}")
        row = body.row(align=True)
        row.prop(r, "pixel_aspect_x", text="Pixel aspect X")
        row.prop(r, "pixel_aspect_y", text="Y")
    # Maya Common > Render Options > Skip existing frames = Blender's Overwrite off + Placeholders on
    header, body = layout.panel("ALLSET_rs_options", default_closed=False)
    header.label(text="Render Options")
    if body:
        body.use_property_split = True
        body.prop(r, "use_overwrite")
        body.prop(r, "use_placeholder")


class ALLSET_OT_rs_defaults(bpy.types.Operator):
    """Maya Presets > Import Render Settings > Default Settings: HD 540 (960 x 540), PNG, single frame, padding 4"""
    bl_idname = "allset.rs_defaults"
    bl_label = "Default Render Settings"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        apply_defaults(context.scene)
        return {'FINISHED'}


# --- window -----------------------------------------------------------------------------------------------------

def open_window(context):
    """A new Properties window on the Render tab only, marked as the kit's Render Settings."""
    from ..operators import menu_extras
    area = max(context.window.screen.areas, key=lambda a: a.width * a.height, default=None)
    if area is None:
        return None
    window = menu_extras.open_window(context, area, "render_settings")
    if window is None:
        return None
    target = window.screen.areas[0]
    target.ui_type = 'PROPERTIES'
    space = target.spaces.active
    for prop in space.bl_rna.properties:
        if prop.identifier.startswith("show_properties_"):
            setattr(space, prop.identifier, prop.identifier == "show_properties_render")
    try:
        space.context = 'RENDER'
    except TypeError:
        pass
    mark(window)
    context.window_manager.allset_rs_tab = 'COMMON'
    return window


def _header_draw(self, context):
    if not is_render_settings(context):
        return _orig["header"](self, context)
    from . import editor_chrome
    layout = self.layout
    layout.template_header()
    editor_chrome.draw_menus(layout, context, "Render Settings")


_orig = {}


# --- hiding Blender's Render panels in the Common tab (ui/dock_tabs.py technique) ------------------------------

def _hidden(context):
    if not is_render_settings(context):
        return False
    return context.window_manager.allset_rs_tab == 'COMMON'


def _make_poll(original, always=False):
    def poll(cls, context):
        if (always and is_render_settings(context)) or _hidden(context):
            return False
        return original(context) if original is not None else True
    return classmethod(poll)


def _subclasses(cls):
    for sub in cls.__subclasses__():
        yield sub
        yield from _subclasses(sub)


def _module_names(cls):
    """Global names of the module that defined ``cls``, read from one of its own functions (draw / poll ...) — no
    lookup in the module table (step 130); {} when the class defines no function itself."""
    for attr in vars(cls).values():
        func = getattr(attr, "__func__", attr)          # classmethod / staticmethod
        names = getattr(func, "__globals__", None)
        if isinstance(names, dict) and names.get("__name__") == cls.__module__:
            return names
    return {}


def _class_order(cls):
    """The defining module's ``classes`` sequence, or [] when it isn't a tuple / list. Third-party render panels
    can come from modules whose global ``classes`` is something else — a submodule (``from . import classes``),
    a dict, a generator — which made Maya mode fail to switch on (#79, 'module' object is not iterable)."""
    seq = _module_names(cls).get("classes", ())
    if not isinstance(seq, (tuple, list)):
        return []
    return list(seq)


def registration_key(cls):
    """Blender lists panels in registration order, and re-registering moves a panel to the end: re-register them in
    the order they were registered — bl_ui modules in ``bl_ui._modules`` order, each module's ``classes`` tuple
    order, add-ons (Cycles) after them (subclass order put EEVEE's Motion Blur above Sampling)."""
    seq = _class_order(cls)
    index = seq.index(cls) if cls in seq else len(seq)
    if cls.__module__.startswith("bl_ui."):
        import bl_ui
        names = list(getattr(bl_ui, "_modules", ()))
        name = cls.__module__.split(".", 1)[1]
        return (0, names.index(name) if name in names else len(names), "", index)
    return (1, 0, cls.__module__, index)


def render_panels():
    """Top-level Properties > Render panels that aren't the kit's, registered now, in registration order."""
    seen, out = set(), []
    for cls in _subclasses(bpy.types.Panel):
        if cls in seen or cls.__name__.startswith("ALLSET_"):
            continue
        seen.add(cls)
        if (getattr(cls, "bl_space_type", None) == 'PROPERTIES' and getattr(cls, "bl_context", "") == "render"
                and not getattr(cls, "bl_parent_id", "") and cls.is_registered):
            out.append(cls)
    return sorted(out, key=registration_key)


def _children(parent, panels):
    pid = getattr(parent, "bl_idname", "") or parent.__name__
    for cls in sorted(panels, key=registration_key):
        if getattr(cls, "bl_parent_id", "") == pid and cls.is_registered:
            yield cls
            yield from _children(cls, panels)


def _reregister(cls, kids, poll, raw=None):
    """Re-register ``cls`` + ``kids`` with ``poll``; False (``cls`` left with ``raw``) when Blender refuses (step 279)."""
    from .. import safe_reg
    return safe_reg.reregister_panel(cls, kids, poll, raw)


def wrap_panels():
    everything = [c for c in _subclasses(bpy.types.Panel) if getattr(c, "bl_space_type", None) == 'PROPERTIES']
    for cls in render_panels():
        raw = cls.__dict__.get("poll")
        kids = list(_children(cls, everything))
        # RENDER_PT_context = Blender's engine row: the kit's Render Using row replaces it in the window
        if _reregister(cls, kids, _make_poll(getattr(cls, "poll", None), always=cls.__name__ == "RENDER_PT_context"),
                       raw):
            _wrapped.append((cls, raw, kids))


def unwrap_panels():
    """Original polls back. A class its owner already unregistered (an add-on going away first, e.g. Cycles while a
    template load re-enables add-ons) only gets its poll back: registering it again would make the owner's own
    register fail ("already registered")."""
    for cls, raw, kids in _wrapped:     # forward: the registration order again
        if cls.is_registered:
            _reregister(cls, [k for k in kids if k.is_registered], raw, raw)
        elif raw is not None:
            cls.poll = raw
        elif "poll" in cls.__dict__:
            del cls.poll
    _wrapped.clear()


classes = (ALLSET_PT_rs_head, ALLSET_PT_rs_common, ALLSET_OT_rs_defaults)


def register():
    sc = bpy.types.Scene
    get, set_ = _rw("dir")
    sc.allset_rs_dir = StringProperty(name="Path", subtype='DIR_PATH', get=get, set=set_,
                                        description="Maya Render Settings Path: the folder of the render output")
    get, set_ = _rw("prefix")
    sc.allset_rs_prefix = StringProperty(name="File name prefix", get=get, set=set_,
                                           description="Maya File name prefix (empty = the scene name)")
    _g, set_ = _rw("ext")
    sc.allset_rs_ext = EnumProperty(name="Frame/Animation ext", items=[(k, l, "") for k, l, _s in EXTS],
                                      get=_ext_get, set=set_,
                                      description="Maya Frame/Animation ext: how the frame number joins the name")
    get, set_ = _rw("padding")
    sc.allset_rs_padding = IntProperty(name="Frame padding", min=1, max=10, get=get, set=set_,
                                         description="Digits of the frame number (Maya extensionPadding)")
    sc.allset_rs_size = EnumProperty(name="Image Size Presets", items=SIZE_ITEMS, get=_size_get, set=_size_set,
                                       description="Maya image size presets (HD 540 = 960 x 540 is the default)")
    bpy.types.WindowManager.allset_rs_tab = EnumProperty(name="Render Settings Tab", items=_tab_items,
                                                           options={'SKIP_SAVE'})
    for cls in classes:
        bpy.utils.register_class(cls)
    wrap_panels()      # after the kit panels: Blender's re-registered ones come after them
    funcs = bpy.types.PROPERTIES_HT_header._dyn_ui_initialize()
    _orig["header"] = funcs[0]
    funcs[0] = _header_draw


def unregister():
    if "header" in _orig:
        bpy.types.PROPERTIES_HT_header._dyn_ui_initialize()[0] = _orig.pop("header")
    unwrap_panels()
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    for name in ("allset_rs_dir", "allset_rs_prefix", "allset_rs_ext", "allset_rs_padding",
                 "allset_rs_size"):
        delattr(bpy.types.Scene, name)
    del bpy.types.WindowManager.allset_rs_tab
    _WINDOWS.clear()
