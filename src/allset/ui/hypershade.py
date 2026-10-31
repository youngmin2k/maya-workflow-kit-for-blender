# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya Hypershade = its own window, laid out the Maya way (issue #25; before:
a Shader Editor + sidebar tab).

Maya's standard Hypershade is a
floating window: the menu bar (File / Edit / View / Create / Tabs / Graph / Window / Options / Help) over the Browser
(top-left: toolbar, 10 swatch tabs, swatch grid), Material Viewer (top-right), Create (bottom-left: category tree +
node list), the Graph work area (centre: graph toolbar, "Untitled_1" tab, node editor) and the Property Editor
(bottom-right). ``allset.hypershade`` builds the same arrangement out of Blender areas in a new window
(``hypershade_layout`` = Maya's proportions as ``area_split`` steps, made one per timer tick):

- menu strip = a Shader Editor one header high whose header draws only the Maya menus (``NODE_HT_header``'s own draw
  swapped, ``own_draw``); items in ``editor_menu_map`` "Hypershade/...";
- Graph = a Shader Editor whose header is Maya's graph toolbar (``editor_chrome.ICONS["Hypershade"]``) + Blender's
  node menus folded into "Blender"; a drawn "Untitled_1" tab at its top-left;
- Browser / Create / Material Viewer / Property Editor = Properties editors on the Tool tab (the Maya dock
  mechanism), marked by hidden tab flags (``MARK`` + ``PANE_FLAGS``) and drawn by ``ALLSET_PT_hypershade_pane``.

The Hypershade's current material (Browser click, Create, Edit menu) shows in the Graph (the active object's slot
when it has it, else the Graph is pinned to it), the Material Viewer and the Property Editor.
Windows > Rendering Editors > Hypershade, the Status Line icon and the hotbox's Windows menu all run
``allset.hypershade``; other Shader Editors keep the Maya menu bar in their header (``draw_collapsible``).
"""

import bpy
from bpy.props import BoolProperty, EnumProperty, StringProperty

from .. import results
from .. import compat, live_refs
from ..operators import material as material_ops
from ..operators import menu_extras
from . import ae_layout, hypershade_layout

# Maya Hypershade Create > Maya > Surface, alphabetical like Maya: the ones Blender can build
CREATE = ('ANISOTROPIC', 'BLINN', 'LAMBERT', 'LAYERED', 'PHONG', 'PHONG_E', 'RAMP', 'STANDARD_SURFACE', 'SURFACE',
          'USE_BACKGROUND')
COLUMNS = 3

# Browser swatch tabs (Maya's tab bar)
TABS = (("MATERIALS", "Materials", "Materials of the scene"),
        ("TEXTURES", "Textures", "Image and texture nodes in the materials"),
        ("UTILITIES", "Utilities", "Other nodes in the materials (Maya utility nodes)"),
        ("RENDERING", "Rendering", "Worlds (Blender's environment / render node)"),
        ("LIGHTS", "Lights", "Light objects"),
        ("CAMERAS", "Cameras", "Camera objects"),
        ("SHADING_GROUPS", "Shading Groups", "Maya shading groups: one per material"))
# Maya's last three Browser tabs: no Blender counterpart (greyed, notices in PANE_NOTICES)
MAYA_ONLY_TABS = ("Bake Sets", "Projects", "Asset Nodes")
# View > As Icons / As List / As Small ... Extra Large Swatches (Maya's View menu; descriptions = the Browser
# toolbar's Maya tooltips); icon scale per size
SWATCHES = (("ICONS", "As Icons", "View as icons", 2.0), ("LIST", "As List", "View as list", 0.0),
            ("SMALL", "As Small Swatches", "View as small swatches", 2.0),
            ("MEDIUM", "As Medium Swatches", "View as medium swatches", 3.0),
            ("LARGE", "As Large Swatches", "View as large swatches", 4.5),
            ("XLARGE", "As Extra Large Swatches", "View as extra large swatches", 6.0))
SORTS = (("NAME", "By Name", "Sort by name"), ("TYPE", "By Type", "Sort by type"), ("TIME", "By Time", "Sort by time"))
# Browser toolbar icons (Blender icons standing in for Maya's)
SWATCH_ICONS = {"ICONS": 'IMGDISPLAY', "LIST": 'LONGDISPLAY', "SMALL": 'DOT', "MEDIUM": 'RADIOBUT_OFF',
                "LARGE": 'MATSPHERE', "XLARGE": 'MATERIAL'}
SORT_ICONS = {"NAME": 'SORTALPHA', "TYPE": 'SORTBYEXT', "TIME": 'SORTTIME'}

TEXTURE_NODES = {'TEX_IMAGE', 'TEX_CHECKER', 'TEX_NOISE', 'TEX_WAVE', 'TEX_VORONOI', 'TEX_BRICK', 'TEX_GRADIENT',
                 'TEX_MAGIC', 'TEX_ENVIRONMENT', 'TEX_SKY', 'TEX_WHITE_NOISE', 'TEX_GABOR'}
SHADER_NODES = {'OUTPUT_MATERIAL', 'BSDF_PRINCIPLED', 'MIX_SHADER', 'ADD_SHADER', 'HOLDOUT', 'EMISSION',
                'BSDF_DIFFUSE', 'BSDF_GLOSSY', 'BSDF_TRANSPARENT', 'BSDF_TRANSLUCENT', 'BSDF_REFRACTION', 'BSDF_GLASS',
                'SUBSURFACE_SCATTERING', 'BSDF_TOON', 'BSDF_SHEEN', 'BSDF_HAIR', 'BSDF_HAIR_PRINCIPLED',
                'VOLUME_ABSORPTION', 'VOLUME_SCATTER', 'PRINCIPLED_VOLUME', 'BSDF_METALLIC', 'FRAME', 'REROUTE',
                'GROUP_INPUT', 'GROUP_OUTPUT'}


def materials():
    return sorted((m for m in bpy.data.materials if not m.is_grease_pencil), key=lambda m: m.name.lower())


def current(context):
    """The Hypershade's current material: the picked one, else the active object's active material."""
    mat = bpy.data.materials.get(context.window_manager.allset_hs_material)
    if mat is None and context.active_object is not None:
        mat = context.active_object.active_material
    return mat


def assigned_materials():
    """Materials some object in a scene uses (Maya: connected to a shading group with members). Data left behind by
    a deleted object still counts as a user in Blender, so users alone don't tell."""
    out = set()
    for scene in bpy.data.scenes:
        for ob in scene.objects:
            out.update(s.material for s in ob.material_slots if s.material is not None)
    return out


def release_editors(mats):
    """Let every Shader Editor showing one of ``mats`` go of its tree before the materials are removed: a pinned
    editor keeps drawing the freed tree and Blender crashes."""
    trees = {m.node_tree.as_pointer() for m in mats if m.node_tree is not None}
    if not trees:
        return
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            for space in area.spaces:
                if space.type != 'NODE_EDITOR':
                    continue
                shown = {t.as_pointer() for t in (space.node_tree, space.edit_tree) if t is not None}
                if shown & trees:
                    space.node_tree = None
                    space.pin = False


def show(context, mat, space=None):
    """Make ``mat`` current and show it in the Shader Editor ``space`` (default: the Hypershade Graph of this
    window, since panes are Properties editors): the active object's slot when it has the material (the editor
    follows the object, unpinned), else pin the editor to it."""
    context.window_manager.allset_hs_material = mat.name
    ob = context.active_object
    index = next((i for i, s in enumerate(ob.material_slots) if s.material == mat), None) if ob else None
    if space is None or space.type != 'NODE_EDITOR':
        graph = graph_area(getattr(context, "screen", None))
        space = graph.spaces.active if graph is not None else None
    if space is None or space.type != 'NODE_EDITOR':
        if index is not None:
            ob.active_material_index = index
        return
    if index is not None:
        ob.active_material_index = index
        space.pin = False
    elif mat.node_tree is not None:
        space.pin = True
        space.node_tree = mat.node_tree


# --- the Hypershade window: panes, menu strip, Graph ---------------------------------------------------------
# A pane = a Properties editor on the Tool tab (header hidden) with both MARK flags and one PANE_FLAGS flag. Two of
# maya_dock's role flags make ``maya_dock.role`` None and ``tool_dock.is_dock`` False, so neither the Maya dock panel
# nor Tool Settings draw there; the flags are saved with the file and copied by ``area_dupli``.
MARK = ("show_properties_world", "show_properties_texture")
PANE_FLAGS = {"BROWSER": "show_properties_render", "CREATE": "show_properties_output",
              "VIEWER": "show_properties_view_layer", "PROPERTY": "show_properties_scene"}
PANE_LABELS = {"BROWSER": "Browser", "CREATE": "Create", "VIEWER": "Material Viewer", "PROPERTY": "Property Editor"}


def _flags(space):
    return [p.identifier for p in space.bl_rna.properties if p.identifier.startswith("show_properties_")]


def pane(area):
    """'BROWSER' / 'CREATE' / 'VIEWER' / 'PROPERTY' for a Hypershade pane, else None."""
    if area is None or area.type != 'PROPERTIES':
        return None
    space = area.spaces.active
    if space.show_region_header or not space.show_properties_tool or not all(getattr(space, f) for f in MARK):
        return None
    on = [name for name, flag in PANE_FLAGS.items() if getattr(space, flag, False)]
    if len(on) != 1:
        return None
    allowed = {"show_properties_tool", *MARK, PANE_FLAGS[on[0]], *compat.LATER_PROPERTIES_TABS}
    if any(getattr(space, f) for f in _flags(space) if f not in allowed):
        return None
    return on[0]


def context_pane(context):
    return pane(getattr(context, "area", None))


def set_pane(area, name, window=None):
    """Make the Properties editor ``area`` the Hypershade pane ``name``. False while its space can't take the Tool
    tab yet (a new Properties space has an empty tab list until it has drawn: retry next tick)."""
    space = area.spaces.active
    try:
        space.context = 'TOOL'
    except TypeError:
        return False
    for flag in _flags(space):
        setattr(space, flag, flag in ("show_properties_tool", *MARK, PANE_FLAGS[name]))
    space.show_region_header = False
    nav = next((r for r in area.regions if r.type == 'NAVIGATION_BAR'), None)
    if nav is not None and nav.width > 1 and window is not None and not bpy.app.background:
        try:
            with bpy.context.temp_override(window=window, area=area):
                bpy.ops.screen.region_toggle(region_type='NAVIGATION_BAR')
        except (RuntimeError, TypeError):
            pass
    area.tag_redraw()
    return True


def is_hypershade(screen):
    try:
        return screen is not None and any(pane(a) is not None for a in screen.areas)
    except ReferenceError:
        return False


def _node_areas(screen):
    return [a for a in screen.areas if a.type == 'NODE_EDITOR' and a.ui_type == 'ShaderNodeTree']


def graph_area(screen):
    """The Hypershade Graph of ``screen`` (its tallest Shader Editor), else None."""
    if not is_hypershade(screen):
        return None
    areas = _node_areas(screen)
    return max(areas, key=lambda a: a.height, default=None)


def menu_area(screen):
    """The Hypershade menu strip of ``screen`` (its lowest Shader Editor when there are two or more), else None."""
    if not is_hypershade(screen):
        return None
    areas = _node_areas(screen)
    if len(areas) < 2:
        return None
    return min(areas, key=lambda a: a.height)


def hypershade_windows(wm=None):
    wm = wm or bpy.context.window_manager
    return [w for w in wm.windows if is_hypershade(w.screen)]


def _largest_area(context):
    return max(context.window.screen.areas, key=lambda a: a.width * a.height, default=None)


def _header_px(area):
    """Height for the menu strip: a header (Blender's HEADERY = 26 px x UI scale) plus the area border; an area
    shorter than its header collapses the header to 1 px and shows the main region instead."""
    header = next((r for r in area.regions if r.type == 'HEADER'), None)
    scale = bpy.context.preferences.system.ui_scale or 1.0
    h = header.height if header is not None and header.height > 1 else round(26 * scale)
    return max(h, round(26 * scale)) + 3


def build_later(window, graph, tries=200):
    """Split ``window`` (its only area ``graph``, a Shader Editor) into Maya's Hypershade layout, one split per tick
    (area rects update one tick after a split), then turn the panes into Properties editors and mark them. Window and
    areas are kept as pointers (live_refs, #36)."""
    win_ptr = window.as_pointer()
    roles = {"GRAPH": graph.as_pointer()}
    state = {"steps": None, "i": 0, "n": tries, "typed": False}

    def area_of(role):
        return live_refs.area(roles.get(role), win_ptr)

    def tick():
        win = live_refs.window(win_ptr)
        state["n"] -= 1
        if win is None or state["n"] <= 0:
            return None
        try:
            return _tick(win)
        except ReferenceError:
            return None

    def _tick(win):
        screen = win.screen
        if state["steps"] is None:
            g = area_of("GRAPH")
            if g is None:
                return None
            if g.height <= 1 or g.width <= 1:
                return 0.02
            state["steps"] = hypershade_layout.plan(g.height, _header_px(g))
        steps = state["steps"]
        if state["i"] < len(steps):
            src, direction, factor, new = steps[state["i"]]
            area = area_of(src)
            if area is None:
                return None
            if area.width <= 1 or area.height <= 1:
                return 0.02
            region = next((r for r in area.regions if r.type == 'WINDOW'), None)
            before = {a.as_pointer() for a in screen.areas}
            with bpy.context.temp_override(window=win, screen=screen, area=area, region=region):
                bpy.ops.screen.area_split(direction=direction, factor=factor)
            made = next((a for a in screen.areas if a.as_pointer() not in before), None)
            if made is None:
                return 0.02
            roles[new] = made.as_pointer()
            state["i"] += 1
            return 0.02
        if not state["typed"]:
            for role in ("MENU", "GRAPH"):
                a = area_of(role)
                if a is not None:
                    sp = a.spaces.active
                    sp.show_region_toolbar = False
                    sp.show_region_ui = False
            for role in PANE_FLAGS:
                a = area_of(role)
                if a is not None:
                    a.ui_type = 'PROPERTIES'
            state["typed"] = True
            return 0.02
        done = True
        for role in PANE_FLAGS:
            a = area_of(role)
            if a is not None and pane(a) != role:
                with bpy.context.temp_override(window=win):
                    done = set_pane(a, role, win) and done
        if not done:
            return 0.05
        for a in screen.areas:
            a.tag_redraw()
        return None
    bpy.app.timers.register(tick, first_interval=0.0)


# --- Browser items --------------------------------------------------------------------------------------------

def _node_items(want_textures):
    out = []
    for mat in materials():
        if not compat.material_uses_nodes(mat):
            continue
        for node in mat.node_tree.nodes:
            if node.type in SHADER_NODES or node.name == "Maya Diffuse":
                continue        # the diffuse multiply is part of the Maya material (operators/material.py)
            if (node.type in TEXTURE_NODES) == want_textures:
                out.append((f"{mat.name}::{node.name}", node.label or node.name, mat, node))
    return out


def browser_items(context, tab):
    """[(key, label, icon or ID with a preview, type name)] of a Browser tab, sorted by the View menu's order."""
    scene = context.scene
    if tab == 'MATERIALS':
        items = [(m.name, m.name, m, m.get(material_ops.TYPE_PROP, "material")) for m in materials()]
    elif tab in {'TEXTURES', 'UTILITIES'}:
        items = []
        for key, label, mat, node in _node_items(tab == 'TEXTURES'):
            img = getattr(node, "image", None)
            items.append((key, label, img if img is not None else
                          ('TEXTURE' if tab == 'TEXTURES' else 'NODE'), node.bl_idname))
    elif tab == 'RENDERING':
        items = [(w.name, w.name, w, "world") for w in bpy.data.worlds]
    elif tab in {'LIGHTS', 'CAMERAS'}:
        kind = 'LIGHT' if tab == 'LIGHTS' else 'CAMERA'
        items = [(o.name, o.name, ('LIGHT_' + o.data.type if kind == 'LIGHT' else 'CAMERA_DATA'),
                  o.data.type if kind == 'LIGHT' else "camera")
                 for o in scene.objects if o.type == kind]
        items = [(k, lab, ic if ic in _ICONS else 'LIGHT', t) for k, lab, ic, t in items]
    else:   # SHADING_GROUPS
        items = [(m.name, material_ops.shading_group_name(m), 'NODETREE', "shadingEngine") for m in materials()]
    wm = context.window_manager
    order = wm.allset_hs_sort
    if order == 'TYPE':
        items.sort(key=lambda it: (str(it[3]).lower(), it[1].lower()))
    elif order == 'TIME':
        items.sort(key=lambda it: _uid(context, tab, it[0]))
    else:
        items.sort(key=lambda it: it[1].lower())
    if wm.allset_hs_reverse:
        items.reverse()
    return items


_ICONS = {'LIGHT_POINT', 'LIGHT_SUN', 'LIGHT_SPOT', 'LIGHT_AREA', 'CAMERA_DATA'}


def icon_value(name):
    """The icon id of a named Blender icon (template_icon takes ids only)."""
    return bpy.types.UILayout.bl_rna.functions["prop"].parameters["icon"].enum_items[name].value


def _uid(context, tab, key):
    """Creation order (session uid grows with every new data-block)."""
    if tab == 'MATERIALS' or tab == 'SHADING_GROUPS':
        data = bpy.data.materials.get(key)
    elif tab == 'RENDERING':
        data = bpy.data.worlds.get(key)
    elif tab in {'LIGHTS', 'CAMERAS'}:
        data = bpy.data.objects.get(key)
    else:
        data = bpy.data.materials.get(key.split("::", 1)[0])
    return getattr(data, "session_uid", 0)


class ALLSET_OT_hypershade(bpy.types.Operator):
    """Hypershade: Maya's window with the Browser, Material Viewer, Create, the graph (Shader Editor) and the
    Property Editor"""
    bl_idname = "allset.hypershade"
    bl_label = "Hypershade"

    def execute(self, context):
        if context.window is None:
            return {'CANCELLED'}
        if is_hypershade(context.screen):     # Hypershade > Window > Browser / Create / Property Editor: shown here
            return {'FINISHED'}
        # Maya brings its one Hypershade to the front; Blender can't raise a window: the old one closes and a fresh
        # one opens on top
        from . import maya_dock
        for w in hypershade_windows(context.window_manager):
            maya_dock.close_window_later(w)
        area = _largest_area(context)
        if area is None:
            return {'CANCELLED'}
        window = menu_extras.open_window(context, area, "hypershade")
        if window is None:
            from . import window_places
            if not window_places.deferred():     # opens on a later tick (#203)
                self.report({'ERROR'}, "Could not open a new window")
            return {'CANCELLED'}
        target = window.screen.areas[0]
        target.ui_type = 'ShaderNodeTree'
        mat = current(context)
        if mat is not None:
            show(context, mat, target.spaces.active)
        build_later(window, target)
        return {'FINISHED'}


class ALLSET_OT_hs_pick(bpy.types.Operator):
    """Show this material in the graph and the Property Editor (Maya Hypershade swatch click)"""
    bl_idname = "allset.hs_pick"
    bl_label = "Pick Material"

    material: StringProperty(name="Material", options={'SKIP_SAVE'})

    def execute(self, context):
        mat = bpy.data.materials.get(self.material)
        if mat is None:
            return {'CANCELLED'}
        show(context, mat, context.space_data)
        _redraw(context)
        return {'FINISHED'}


# Browser material swatch = a toggle on this Material property: on = the Hypershade's current material; a click
# picks it like ``allset.hs_pick`` (clicking the picked one keeps it picked). Nothing is stored (get / set).
PICK_PROP = "allset_hs_pick"


def _get_pick(mat):
    try:
        return current(bpy.context) == mat
    except (AttributeError, ReferenceError):
        return False


def _set_pick(mat, _value):
    context = bpy.context
    show(context, mat, getattr(context, "space_data", None))
    _redraw(context)


class ALLSET_OT_hs_item(bpy.types.Operator):
    """Maya Hypershade Browser swatch: a light / camera = select it; a texture / utility = show it in its graph;
    a world = the scene's environment"""
    bl_idname = "allset.hs_item"
    bl_label = "Browser Item"
    bl_options = {'REGISTER', 'UNDO'}

    tab: EnumProperty(items=[t for t in TABS], name="Tab", options={'SKIP_SAVE'})
    key: StringProperty(options={'SKIP_SAVE'})

    def execute(self, context):
        if self.tab in {'LIGHTS', 'CAMERAS'}:
            ob = context.scene.objects.get(self.key)
            if ob is None:
                return {'CANCELLED'}
            for o in context.selected_objects:
                o.select_set(False)
            ob.select_set(True)
            context.view_layer.objects.active = ob
        elif self.tab == 'RENDERING':
            world = bpy.data.worlds.get(self.key)
            if world is None:
                return {'CANCELLED'}
            context.scene.world = world
        elif self.tab in {'TEXTURES', 'UTILITIES'}:
            mname, _sep, nname = self.key.partition("::")
            mat = bpy.data.materials.get(mname)
            node = mat.node_tree.nodes.get(nname) if mat is not None and mat.node_tree else None
            if node is None:
                return {'CANCELLED'}
            show(context, mat, context.space_data)
            for n in mat.node_tree.nodes:
                n.select = n == node
            mat.node_tree.nodes.active = node
        else:
            return bpy.ops.allset.hs_pick(material=self.key)
        _redraw(context)
        return {'FINISHED'}


class ALLSET_OT_hs_create(bpy.types.Operator):
    """Create a material of this type without assigning it (Maya Hypershade Create)"""
    bl_idname = "allset.hs_create"
    bl_label = "Create Material"
    bl_options = {'REGISTER', 'UNDO'}

    kind: EnumProperty(items=material_ops.KIND_ITEMS, name="Material")

    def execute(self, context):
        mat = material_ops.new_material(self.kind)
        mat.use_fake_user = True    # no user yet: Blender would drop it on save, Maya keeps it
        show(context, mat, context.space_data)
        context.window_manager.allset_hs_tab = 'MATERIALS'
        return {'FINISHED'}


class ALLSET_OT_hs_node(bpy.types.Operator):
    """Add this Maya node type to the current material's graph (Maya Hypershade Create: a texture / utility node
    is made on its own; the Blender node is left unconnected)"""
    bl_idname = "allset.hs_node"
    bl_label = "Create Node"
    bl_options = {'REGISTER', 'UNDO'}

    node_type: StringProperty(name="Node", options={'SKIP_SAVE'})
    label: StringProperty(name="Maya Name", options={'SKIP_SAVE'})
    operation: StringProperty(name="Operation", options={'SKIP_SAVE'})    # Math / Vector Math nodes

    def execute(self, context):
        mat = current(context)
        if mat is None:
            mat = material_ops.new_material('LAMBERT')
            mat.use_fake_user = True
        compat.ensure_material_nodes(mat)
        tree = mat.node_tree
        try:
            node = tree.nodes.new(self.node_type)
        except RuntimeError:
            self.report({'ERROR'}, f"Blender has no node {self.node_type}")
            return {'CANCELLED'}
        if self.label:
            node.label = self.label
        if self.operation and hasattr(node, "operation"):
            node.operation = self.operation
        left = min((n.location.x for n in tree.nodes if n != node), default=0.0)
        node.location = (left - 300.0, 300.0)      # left of the network, like a new upstream node
        for n in tree.nodes:
            n.select = n == node
        tree.nodes.active = node
        show(context, mat, context.space_data)
        _redraw(context)
        return {'FINISHED'}


class ALLSET_OT_hs_edit(bpy.types.Operator):
    """Maya Hypershade Edit menu commands"""
    bl_idname = "allset.hs_edit"
    bl_label = "Hypershade Edit"
    bl_options = {'REGISTER', 'UNDO'}

    action: EnumProperty(items=(
        ("DELETE", "Delete", "Delete the current material (lambert1 stays, like Maya's)"),
        ("DELETE_UNUSED", "Delete Unused Nodes", "Delete the materials no object uses (lambert1 stays)"),
        ("DELETE_MATERIALS", "Delete All Materials", "Delete every material but lambert1"),
        ("SELECT_OBJECTS", "Select Objects with Materials", "Select the objects that use the current material"),
        ("FROM_OBJECT", "Select Materials from Objects", "The active object's material becomes current"),
        ("DUPLICATE", "Duplicate", "Copy the current material (and its network)"),
    ), name="Action", options={'SKIP_SAVE'})

    def execute(self, context):
        act = self.action
        cur = current(context)
        if act in {"DELETE", "SELECT_OBJECTS", "DUPLICATE"} and cur is None:
            self.report({'WARNING'}, "No material selected in the Hypershade")
            return {'CANCELLED'}
        if act == "DELETE":
            if material_ops.is_default(cur):
                self.report({'WARNING'}, f"{cur.name} can't be deleted (the default material, like Maya)")
                return {'CANCELLED'}
            release_editors([cur])
            bpy.data.materials.remove(cur)
            context.window_manager.allset_hs_material = ""
        elif act in {"DELETE_UNUSED", "DELETE_MATERIALS"}:
            assigned = assigned_materials() if act == "DELETE_UNUSED" else set()
            doomed = [m for m in materials() if not material_ops.is_default(m) and m not in assigned]
            release_editors(doomed)
            if context.window_manager.allset_hs_material in {m.name for m in doomed}:
                context.window_manager.allset_hs_material = ""
            for m in doomed:
                bpy.data.materials.remove(m)
            n = len(doomed)
            results.result(self, f"Deleted {n} material{'s' if n != 1 else ''}")
        elif act == "SELECT_OBJECTS":
            for o in context.selected_objects:
                o.select_set(False)
            hits = [o for o in context.scene.objects if any(s.material == cur for s in o.material_slots)]
            for o in hits:
                try:
                    o.select_set(True)
                except RuntimeError:
                    pass
            if hits:
                context.view_layer.objects.active = hits[0]
        elif act == "FROM_OBJECT":
            ob = context.active_object
            if ob is None or ob.active_material is None:
                self.report({'WARNING'}, "Select an object with a material")
                return {'CANCELLED'}
            show(context, ob.active_material, context.space_data)
        elif act == "DUPLICATE":
            new = cur.copy()
            new.use_fake_user = True
            show(context, new, context.space_data)
        _redraw(context)
        return {'FINISHED'}


# --- panes ----------------------------------------------------------------------------------------------------

# Create: Maya's category tree (Favorites > Maya > Surface, then Maya > ...) -> Hypershade Create menu
# submenus whose items the list shows (same paths as the Create menu, so menu and pane agree)
CREATE_CATEGORIES = (
    ("FAVORITES", "Favorites", None),
    ("MAYA", "Maya", None),
    ("SURFACE", "Surface", ("Materials",)),
    ("VOLUMETRIC", "Volumetric", ("Volumetric Materials",)),
    ("DISPLACEMENT", "Displacement", ()),
    ("TEX2D", "2D Textures", ("2D Textures",)),
    ("TEX3D", "3D Textures", ("3D Textures",)),
    ("ENV", "Env Textures", ("Environment Textures",)),
    ("OTHER", "Other Textures", ("Layered Texture",)),
    ("LIGHTS", "Lights", ("Lights",)),
    ("UTILITIES", "Utilities", ("General Utilities", "Scalar Utilities", "Switch Utilities", "Color Utilities",
                                "Particle Utilities")),
    ("IMAGE_PLANES", "Image Planes", ("Image Plane",)),
    ("GLOW", "Glow", ("Glow",)),
    ("RENDERING", "Rendering", ("Rendering",)),
)
# Maya's Displacement category has no Hypershade Create menu items: greyed (category notice)
DISPLACEMENT = ("C Muscle Shader", "Displacement", "Usd Preview Surface")
# Favorites > Maya > Surface (Maya's list order)
FAVORITES = ("Standard Surface", "Blinn", "Lambert", "Layered Shader", "Phong", "Phong E", "Ramp Shader",
             "Surface Shader", "Use Background")
HS = "Hypershade"

# Notices of pane controls that are not Maya menu items (notices.PANEL_NOTICES, filled on register)
PANE_NOTICES = {
    **{f"{HS}/Browser/{t}": ("Not in Blender", f"Blender has no {t.lower()} to list: the {t} tab stays empty.")
       for t in MAYA_ONLY_TABS},
    f"{HS}/Browser/Pause Swatches": ("Material previews", "Blender renders material previews in the background "
                                     "by itself: no pause."),
    f"{HS}/Browser/Show": ("Search field", "Blender's Browser filters by the name in the search field only."),
    f"{HS}/Bins": ("Not in Blender", "Blender has no node bins: the Browser tabs list everything."),
    f"{HS}/Property Editor/Presets": ("Not in Blender", "Blender has no attribute presets for materials."),
}


def _create_menu():
    from . import editor_menu_data
    return dict(editor_menu_data.EDITORS[HS])["Create"]


def _menu_entries(sub):
    """(label, Maya menu path) of the Hypershade Create menu's submenu (or single item) ``sub``."""
    for it in _create_menu():
        if it[0] != sub:
            continue
        if len(it) > 1 and isinstance(it[1], list):
            return [(c[0], f"{HS}/Create/{sub}/{c[0]}") for c in it[1] if c[0] != '-']
        return [(sub, f"{HS}/Create/{sub}")]
    return []


def create_items(category):
    """(label, Maya menu path) listed by the Create pane for a category (Maya: the category scrolls / filters the
    list; "Maya" = all of them)."""
    if category == 'FAVORITES':
        return [(label, f"{HS}/Create/Materials/{label}") for label in FAVORITES]
    if category == 'MAYA':
        out = []
        for key, _label, _subs in CREATE_CATEGORIES[2:]:
            out += create_items(key)
        return out
    key, _label, subs = next(c for c in CREATE_CATEGORIES if c[0] == category)
    if key == 'DISPLACEMENT':
        return [(label, f"{HS}/Create/Displacement/{label}") for label in DISPLACEMENT]
    out = []
    for sub in subs:
        out += _menu_entries(sub)
    if key == 'UTILITIES':
        out.sort(key=lambda e: e[0].lower())       # Maya lists the utilities alphabetically, one list
    return out


def draw_title(layout, name):
    """Maya's panel title bar: the panel name between dotted grips."""
    from .maya_dock import HANDLE
    row = layout.row()
    row.alignment = 'CENTER'
    row.label(text=f"{HANDLE}  {PANE_LABELS[name]}  {HANDLE}")


def _greyed(layout, key, text="", icon='NONE'):
    sub = layout.row(align=True)
    sub.enabled = False
    sub.operator("allset.menu_unavailable", text=text, icon=icon).item = key


def draw_browser(layout, context):
    wm = context.window_manager
    # Maya's Browser toolbar: pause | as icons / list | swatch sizes | sort | search (+ Show)
    bar = layout.row(align=False)
    sub = bar.row(align=True)
    _greyed(sub, f"{HS}/Browser/Pause Swatches", icon='PAUSE')
    sub = bar.row(align=True)
    for key in ("ICONS", "LIST"):
        sub.prop_enum(wm, "allset_hs_swatch", key, text="", icon=SWATCH_ICONS[key])
    sub = bar.row(align=True)
    for key in ("SMALL", "MEDIUM", "LARGE", "XLARGE"):
        sub.prop_enum(wm, "allset_hs_swatch", key, text="", icon=SWATCH_ICONS[key])
    sub = bar.row(align=True)
    for key, _l, _d in SORTS:
        sub.prop_enum(wm, "allset_hs_sort", key, text="", icon=SORT_ICONS[key])
    sub.prop(wm, "allset_hs_reverse", text="", icon='SORT_DESC', toggle=True)
    sub = bar.row(align=True)
    sub.prop(wm, "allset_hs_filter", text="", icon='VIEWZOOM', placeholder="Search...")
    _greyed(sub, f"{HS}/Browser/Show", text="Show")
    # the ten Maya tabs (the last three greyed)
    tabs = layout.row(align=True)
    tabs.prop(wm, "allset_hs_tab", expand=True)
    for t in MAYA_ONLY_TABS:
        _greyed(tabs, f"{HS}/Browser/{t}", text=t)
    tab = wm.allset_hs_tab
    items = browser_items(context, tab)
    text = wm.allset_hs_filter.strip().lower()
    if text:
        items = [it for it in items if text in it[1].lower()]
    if not items:
        layout.label(text=f"No {dict((t[0], t[1]) for t in TABS)[tab].lower()} in the scene")
        return
    cur = current(context)
    size = next(s for s in SWATCHES if s[0] == wm.allset_hs_swatch)
    region = context.region
    s = context.preferences.system.ui_scale or 1.0
    if size[3] == 0.0:       # As List
        col = layout.column(align=True)
        for key, label, icon, _t in items:
            _item_button(col, tab, key, label, icon, cur, list_row=True)
        return
    cell = size[3] * 20 * s + 12
    width = region.width if region is not None else 300
    columns = max(1, min(24, int(width // cell))) if region is not None else COLUMNS
    grid = layout.grid_flow(row_major=True, columns=columns, even_columns=True, align=False)
    for key, label, icon, _t in items:
        col = grid.column(align=True)
        value = icon_value(icon) if isinstance(icon, str) else layout.icon(icon)
        col.template_icon(icon_value=value, scale=size[3])
        _item_button(col, tab, key, label, icon, cur)


def _item_button(layout, tab, key, label, icon, cur, list_row=False):
    picked = (tab in {'MATERIALS', 'SHADING_GROUPS'} and cur is not None and key == cur.name)
    if tab == 'MATERIALS':
        kw = {"icon_value": layout.icon(icon)} if list_row else {}
        mat = bpy.data.materials.get(key)
        if mat is not None and mat.library is None:
            # a property button, not an operator one: the hovered property is the only button a keymap operator
            # can read (``context.property``; ``button_operator`` and ``context_pointer_set`` don't reach keymap
            # handlers) -- the MMB swatch drag (ui/hs_drag.py) needs to know the swatch
            layout.prop(mat, PICK_PROP, text=label, toggle=True, **kw)
            return
        op = layout.operator("allset.hs_pick", text=label, depress=picked, **kw)
        op.material = key
        return
    kw = {}
    if list_row:
        kw = {"icon": icon} if isinstance(icon, str) else {"icon_value": layout.icon(icon)}
    op = layout.operator("allset.hs_item", text=label, depress=picked, **kw)
    op.tab, op.key = tab, key


def draw_create(layout, context):
    from . import menu_sets
    wm = context.window_manager
    layout.prop(wm, "allset_hs_create_filter", text="", icon='VIEWZOOM', placeholder="Search...")
    split = layout.split(factor=0.32)
    left = split.column(align=True)
    for key, label, subs in CREATE_CATEGORIES:
        if subs is None:           # tree roots: Favorites, Maya
            left.prop_enum(wm, "allset_hs_create_cat", key, text=label, icon='DISCLOSURE_TRI_DOWN')
        else:
            left.prop_enum(wm, "allset_hs_create_cat", key, text="    " + label)
    right = split.column(align=True)
    text = wm.allset_hs_create_filter.strip().lower()
    items = create_items('MAYA' if text else wm.allset_hs_create_cat)
    if text:
        items = [it for it in items if text in it[0].lower()]
    seen = set()
    for label, path in items:
        if path in seen:
            continue
        seen.add(path)
        menu_sets.draw_item(right, path, label)
    if not items:
        right.label(text="No node type matches")
    # Maya's bottom tab row: Create | Bins
    tabs = layout.row(align=True)
    tabs.operator("allset.hs_noop", text="Create", depress=True)
    _greyed(tabs, f"{HS}/Bins", text="Bins")


def draw_viewer(layout, context):
    mat = current(context)
    row = layout.row(align=True)
    engine = context.scene.render.engine
    names = {e.identifier: e.name for e in context.scene.render.bl_rna.properties["engine"].enum_items}
    row.label(text=names.get(engine, engine), icon='SHADING_RENDERED')
    if mat is None:
        layout.label(text="Pick a material in the Browser")
        return
    row.prop(mat, "preview_render_type", text="")
    row.prop(mat, "use_preview_world", text="", icon='WORLD')
    if engine == 'BLENDER_WORKBENCH':
        layout.label(text="Workbench draws no material previews: switch the render engine to EEVEE or Cycles",
                     icon='INFO')
        return
    layout.template_preview(mat, show_buttons=False)


def draw_property_editor(layout, context):
    from . import attribute_editor
    mat = current(context)
    if mat is None:
        layout.label(text="Pick a material")
        return
    tab = layout.row(align=True)
    tab.alignment = 'LEFT'
    tab.operator("allset.hs_noop", text=mat.name, depress=True)
    name = attribute_editor.material_type(mat)
    head = layout.row(align=True)
    head.label(text=f"{name}:")
    head.prop(mat, "name", text="")
    _greyed(head, f"{HS}/Property Editor/Presets", text="Presets")
    sections = ae_layout.BY_KIND[name][0]
    attribute_editor.draw_sections(layout, context, None, mat, sections, f"hs_{name}")


class ALLSET_OT_hs_noop(bpy.types.Operator):
    """Current tab"""
    bl_idname = "allset.hs_noop"
    bl_label = "Tab"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        return {'CANCELLED'}


class ALLSET_PT_hypershade_pane(bpy.types.Panel):
    """A Hypershade pane: Browser, Create, Material Viewer or Property Editor (a marked Properties Tool tab)"""
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Tool"           # = drawn by the Properties Tool tab
    bl_label = "Hypershade"
    bl_options = {'HIDE_HEADER'}
    bl_order = -300

    @classmethod
    def poll(cls, context):
        return context_pane(context) is not None

    def draw(self, context):
        layout = self.layout
        name = context_pane(context)
        draw_title(layout, name)
        if name == 'BROWSER':
            draw_browser(layout, context)
            cur = current(context)
            row = layout.row()
            row.enabled = cur is not None
            op = row.operator("allset.assign_material", text="Assign Material To Selection", icon='MATERIAL')
            op.material = cur.name if cur is not None else ""
        elif name == 'CREATE':
            draw_create(layout, context)
        elif name == 'VIEWER':
            draw_viewer(layout, context)
        else:
            draw_property_editor(layout, context)


# --- Graph: toolbar actions ------------------------------------------------------------------------------------

def _linked(tree, nodes, upstream):
    """Nodes reachable from ``nodes`` against (upstream) or along (downstream) the links."""
    found = set()
    todo = list(nodes)
    while todo:
        n = todo.pop()
        for link in tree.links:
            a, b = (link.to_node, link.from_node) if upstream else (link.from_node, link.to_node)
            if a == n and b not in found:
                found.add(b)
                todo.append(b)
    return found


class ALLSET_OT_hs_graph(bpy.types.Operator):
    """Maya Hypershade graph command, run in the Hypershade's graph (Shader Editor)"""
    bl_idname = "allset.hs_graph"
    bl_label = "Hypershade Graph"
    bl_options = {'REGISTER', 'UNDO'}

    action: EnumProperty(items=(
        ("UPSTREAM", "Input Connections", "Select and frame the selected nodes' input network"),
        ("BOTH", "Input and Output Connections", "Select and frame the selected nodes' whole network"),
        ("DOWNSTREAM", "Output Connections", "Select and frame the nodes the selected ones feed"),
        ("FRAME_ALL", "Frame All", "Frame the whole graph"),
        ("FRAME_SELECTED", "Frame Selected", "Frame the selected nodes"),
        ("COLLAPSE", "Hide Attributes", "Collapse the selected nodes (Blender: Node > Collapse)"),
        ("CONNECTED", "Show Connected Attributes", "Hide the unconnected sockets of the selected nodes"),
        ("SHOW_ALL", "Show Primary Attributes", "Expand the selected nodes and show all their sockets"),
        ("PREVIEW", "Toggle Swatch Size", "Show / hide the selected nodes' preview swatch"),
    ), name="Action", options={'SKIP_SAVE'})

    def execute(self, context):
        area = context.area if context.area is not None and context.area.type == 'NODE_EDITOR' else None
        area = area or graph_area(context.screen)
        if area is None:
            self.report({'WARNING'}, "Open the Hypershade (Windows > Rendering Editors > Hypershade)")
            return {'CANCELLED'}
        space = area.spaces.active
        tree = space.edit_tree
        if tree is None:
            self.report({'WARNING'}, "No material in the graph")
            return {'CANCELLED'}
        act = self.action
        selected = [n for n in tree.nodes if n.select]
        if act in {"UPSTREAM", "BOTH", "DOWNSTREAM"}:
            start = selected or ([tree.nodes.active] if tree.nodes.active else list(tree.nodes))
            keep = set(start)
            if act != "DOWNSTREAM":
                keep |= _linked(tree, start, True)
            if act != "UPSTREAM":
                keep |= _linked(tree, start, False)
            for n in tree.nodes:
                n.select = n in keep
            act = "FRAME_SELECTED"
        elif act == "SHOW_ALL":
            for n in selected:
                n.hide = False
                for sock in (*n.inputs, *n.outputs):
                    sock.hide = False
            area.tag_redraw()
            return {'FINISHED'}
        ops = {"FRAME_ALL": bpy.ops.node.view_all, "FRAME_SELECTED": bpy.ops.node.view_selected,
               "COLLAPSE": bpy.ops.node.hide_toggle, "CONNECTED": bpy.ops.node.hide_socket_toggle,
               "PREVIEW": bpy.ops.node.preview_toggle}
        region = next((r for r in area.regions if r.type == 'WINDOW'), None)
        if bpy.app.background or region is None:
            return {'FINISHED'}            # selection done; view ops need a drawn region
        with context.temp_override(area=area, region=region, space_data=space):
            ops[act]()
        area.tag_redraw()
        return {'FINISHED'}


def _redraw(context):
    for area in context.screen.areas if context.screen else ():
        area.tag_redraw()


# --- headers: menu strip and Graph -----------------------------------------------------------------------------

def _node_header(self, context):
    """``NODE_HT_header``'s own draw while the kit is on: in a Hypershade window the menu strip shows Maya's menu
    bar, the Graph Maya's graph toolbar; elsewhere Blender's header."""
    from . import editor_chrome, editor_menu_data, menu_sets, own_draw
    area = context.area
    screen = context.screen
    if editor_chrome.enabled(context) and area is not None and is_hypershade(screen):
        layout = self.layout
        if area == menu_area(screen):
            row = layout.row(align=True)
            for i, (title, _items) in enumerate(editor_menu_data.EDITORS[HS]):
                row.menu(menu_sets.editor_menu_idname(HS, i), text=title)
            return
        if area == graph_area(screen):
            editor_chrome.draw_icons(layout, context, HS)
            layout.separator_spacer()
            layout.menu(editor_chrome._BLENDER[HS].bl_idname, text="Blender")
            layout.prop(context.space_data, "pin", text="", emboss=False)
            return
    return own_draw.original("NODE_HT_header", _node_header)(self, context)


TAB_TEXT = "Untitled_1"
TAB_BACK = (68 / 255, 68 / 255, 68 / 255, 1.0)     # Maya's current tab #444444
TAB_STRIP = (55 / 255, 55 / 255, 55 / 255, 1.0)    # tab row #373737
TAB_INK = (0.78, 0.78, 0.78, 1.0)


def draw_graph_tab():
    """Maya's graph tab row ("Untitled_1") over the top of the Hypershade Graph (node editors have no tool header
    region to hold a tab row)."""
    context = bpy.context
    area = context.area
    if area is None or area.type != 'NODE_EDITOR' or graph_area(context.screen) != area:
        return
    import blf
    import gpu
    from gpu_extras.batch import batch_for_shader
    region = context.region
    s = context.preferences.system.ui_scale or 1.0
    h = round(20 * s)
    top = region.height
    font = 0
    blf.size(font, 11 * s)
    tw = blf.dimensions(font, TAB_TEXT)[0]
    w = round(tw + 34 * s)
    x0 = round(6 * s)
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')

    def rect(x, y, rw, rh, color):
        batch = batch_for_shader(shader, 'TRIS', {"pos": ((x, y), (x + rw, y), (x + rw, y + rh), (x, y + rh))},
                                 indices=((0, 1, 2), (0, 2, 3)))
        shader.uniform_float("color", color)
        batch.draw(shader)
    gpu.state.blend_set('ALPHA')
    rect(0, top - h, region.width, h, TAB_STRIP)
    rect(x0, top - h, w, h, TAB_BACK)
    blf.color(font, *TAB_INK)
    blf.position(font, x0 + 8 * s, top - h + 6 * s, 0)
    blf.draw(font, TAB_TEXT)
    blf.position(font, x0 + w - 14 * s, top - h + 6 * s, 0)
    blf.draw(font, "×")
    blf.position(font, x0 + w + 12 * s, top - h + 6 * s, 0)
    blf.draw(font, "+")
    gpu.state.blend_set('NONE')


# --- Maya menu bar in other Shader Editor headers ---------------------------------------------------------------

def draw_collapsible(cls, context, layout):
    """``NODE_MT_editor_menus.draw_collapsible`` while the kit is on: Maya's Hypershade menus in a Shader Editor."""
    from . import editor_chrome
    space = context.space_data
    if editor_chrome.enabled(context) and getattr(space, "tree_type", "") == 'ShaderNodeTree':
        return editor_chrome.draw_menus(layout, context, "Hypershade")
    return bpy.types.Menu.draw_collapsible.__func__(cls, context, layout)


def patch_header():
    bpy.types.NODE_MT_editor_menus.draw_collapsible = classmethod(draw_collapsible)


def unpatch_header():
    cls = bpy.types.NODE_MT_editor_menus
    if "draw_collapsible" in cls.__dict__:
        del cls.draw_collapsible


classes = (ALLSET_OT_hypershade, ALLSET_OT_hs_pick, ALLSET_OT_hs_item, ALLSET_OT_hs_create, ALLSET_OT_hs_node,
           ALLSET_OT_hs_edit, ALLSET_OT_hs_graph, ALLSET_OT_hs_noop, ALLSET_PT_hypershade_pane)
_handles = []
_WM_PROPS = ("allset_hs_material", "allset_hs_tab", "allset_hs_swatch", "allset_hs_sort", "allset_hs_reverse",
             "allset_hs_filter", "allset_hs_create_cat", "allset_hs_create_filter")


def register():
    from . import notices, own_draw
    wm = bpy.types.WindowManager
    wm.allset_hs_material = StringProperty(name="Hypershade Material", options={'SKIP_SAVE'})
    wm.allset_hs_tab = EnumProperty(name="Browser Tab", items=TABS, options={'SKIP_SAVE'})
    wm.allset_hs_swatch = EnumProperty(name="Swatch Size", items=[s[:3] for s in SWATCHES], default='MEDIUM',
                                         options={'SKIP_SAVE'})
    wm.allset_hs_sort = EnumProperty(name="Sort", items=SORTS, options={'SKIP_SAVE'})
    wm.allset_hs_reverse = BoolProperty(name="Reverse Order", description="Sort in reverse order",
                                          options={'SKIP_SAVE'})
    wm.allset_hs_filter = StringProperty(name="Search", description="Show only the swatches whose name has this text",
                                          options={'SKIP_SAVE', 'TEXTEDIT_UPDATE'})
    wm.allset_hs_create_cat = EnumProperty(
        name="Create Category", items=[(k, label, f"Maya Create > {label}") for k, label, _s in CREATE_CATEGORIES],
        default='MAYA', options={'SKIP_SAVE'})
    wm.allset_hs_create_filter = StringProperty(name="Search Node Types",
                                                 description="List the node types whose name has this text",
                                                 options={'SKIP_SAVE', 'TEXTEDIT_UPDATE'})
    bpy.types.Material.allset_hs_pick = BoolProperty(
        name="Pick Material", description=ALLSET_OT_hs_pick.__doc__, get=_get_pick, set=_set_pick,
        options={'SKIP_SAVE'})
    for cls in classes:
        bpy.utils.register_class(cls)
    patch_header()
    own_draw.swap("NODE_HT_header", _node_header)
    _handles.append(bpy.types.SpaceNodeEditor.draw_handler_add(draw_graph_tab, (), 'WINDOW', 'POST_PIXEL'))
    notices.PANEL_NOTICES.update(PANE_NOTICES)


def unregister():
    from . import notices, own_draw
    for key in PANE_NOTICES:
        notices.PANEL_NOTICES.pop(key, None)
    while _handles:
        bpy.types.SpaceNodeEditor.draw_handler_remove(_handles.pop(), 'WINDOW')
    own_draw.restore("NODE_HT_header", _node_header)
    unpatch_header()
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    for name in _WM_PROPS:
        delattr(bpy.types.WindowManager, name)
    del bpy.types.Material.allset_hs_pick
