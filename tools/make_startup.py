"""Generate the Maya layout startup.blend bundled inside the extension (in a GUI Blender; read from there by
switch.enter_layout and "New Scene in Maya Layout", never copied out of the extension).

    python tools/make_startup.py          # re-runs itself in `blender --factory-startup` (a window opens briefly)

Writes src/allset/app_template/Maya_Workflow_Kit/startup.blend (a Maya-style General layout).
It runs in a GUI Blender because the factory right column
(Outliner + Properties) can only be removed there: in `-b` screen.area_close hangs and area_join crashes
or adds empty areas. The window is 1600x900 at effective UI scale
1.0, so area sizes are pixels at scale 1; the sidebar width is set by dragging
its edge with simulated events (no API). User dirs point into tmp/build_env (tools/build.sandbox_env).
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "src" / "allset" / "app_template" / "Maya_Workflow_Kit" / "startup.blend"

# Widget sizes at effective scale 1.0:
# Outliner 260, Channel Box / Layer Editor dock 260 (+ tab strip), Time Slider 36 (the timeline WINDOW region); the
# Range Slider is the timeline header, flipped under it.
OUTLINER_PX = 260
# The right dock column (Channel Box / Layer Editor + a side tab strip) = the kit's tab-stack area, its own Properties editor right of the viewport (ui/maya_dock.py).
# #60: the kit's tabs are one horizontal row, so the stack is as wide as its tab row / Channel Box labels /
# AE menu bar need = src/allset/ui/toolbox.dock_width(1.0) (277 <= width <= 480; kept in sync by
# tests/test_step135_width.py); toolbox.fit_columns refits it at other UI scales. #78: the tabs are Maya's
# vertical strip on the stack's right edge, so the stack with the Channel Box raised is narrow again
# (toolbox.dock_width(1.0) = the Channel Box labels + the strip).
DOCK_PX = 286
# Tool Box column = room for one toolbar column up to UI scale 1.6: area sizes are pixels scaled with
# the window, not with the UI scale, and a toolbar wider than its area is not drawn at all (an empty strip, the
# tools fell back into the main view). ui/toolbox.fit_columns fits it to one toolbar column when it can; until
# then the extra width is the toolbar colour (toolbox.settle). 1.6 = 125 % display in a window down to 1280 px.
TOOLBOX_ROOM = 1.6
# = ui/maya_dock.ROLE_FLAGS['STACK']: Tool tab + this hidden tab flag marks the tab-stack area
STACK_FLAG = "show_properties_world"
# Time Slider right end: current time field (90) + 8 transport buttons (22 each) and padding.
TIME_CONTROLS_PX = 300   # = ui/channel_box.py CATEGORY
TIME_SLIDER_PX = 36
# Shelf: tab row + 32 px icon row = 64 (one WINDOW region draws both)
SHELF_PX = 64
WINDOW_SIZE = (1600, 900)
EDGE = 3                  # px the area edges take from a split
# Persp view = focal length 35 on a 36 mm film back. Blender's viewport lens is on a 72 mm sensor
# (tan(fov/2) = 36 / lens), so the same angle is lens 70; lens 35 was a 91.6 deg view.
MAYA_LENS = 70.0
MAYA_FRAME_END = 120      # playback 1-120
MAYA_RANGE_END = 200      # animation range 1-200 (Range Slider outer fields)
MAYA_RESOLUTION = (960, 540)   # HD 540
STRIP_MARKER = ".AllsetStrip"  # = ui/shelf.py MARKER (Status Line row)
SHELF_MARKER = ".AllsetShelf"  # = ui/shelf.py SHELF_MARKER (Shelf row)
# Maya lengths are cm: 1 Maya unit = 0.01 BU with m scene units + cm display.
MAYA_UNIT = 0.01
# Flat viewport grey #5c5c5c as a scene-linear View3DShading.background_color (sRGB 92/255 -> linear; #45)
MAYA_BG_LINEAR = round(((92 / 255 + 0.055) / 1.055) ** 2.4, 5)
MAYA_CLIP = (0.1, 10000.0)        # cm (= operators/units.py CLIP)
MAYA_PERSP_EYE = (28.0, -28.0, 21.0)  # cm, new-scene persp eye (= units.PERSP_EYE)

# Maya-style workspaces the template carries (#81): Windows > Workspaces / the Status Line dropdown
# (= src/allset/ui/workspaces.py MAYA_WORKSPACES); "General" is shown as "Maya Classic".
# name -> (menu set linkedMenu, raised tab of the right tab stack, recipe)
MAYA_WORKSPACES = {
    "General": ("", 'CHANNEL_BOX', ()),
    "Modeling - Standard": ("modelingMenuSet", 'MODELING_TOOLKIT', ("no_outliner", "no_timeline")),
    "Modeling - Expert": ("modelingMenuSet", 'MODELING_TOOLKIT',
                          ("no_outliner", "no_timeline", "no_dock", "no_toolbox", "no_strip", "no_toolheader")),
    "Sculpting": ("modelingMenuSet", 'CHANNEL_BOX', ("no_outliner", "no_timeline", "tool_settings")),
    "UV Editing": ("modelingMenuSet", 'ATTRIBUTE_EDITOR', ("no_outliner", "no_timeline", "uv_editor")),
    "Rigging": ("riggingMenuSet", 'CHANNEL_BOX', ("shape_editor",)),
    "Animation": ("animationMenuSet", 'CHANNEL_BOX', ("graph_editor",)),
    "Rendering - Standard": ("renderingMenuSet", 'ATTRIBUTE_EDITOR', ("render_column", "script_editor")),
}
# fractions of the main view
ANIMATION_GRAPH = 300 / (637 + 300)        # Animation: Graph Editor under the main view
RIGGING_EDITOR = 279 / (633 + 279)         # Rigging: Node / Shape Editor under the main view
UV_EDITOR = 842 / (626 + 842)              # UV Editing: UV Editor beside the main view
RENDER_SCRIPT = 231 / (494 + 231)          # Rendering - Standard: Script Editor under the main view
RENDER_COLUMN_PX = 346                     # Render Setup / Property Editor column


def run_outside_blender():
    import subprocess
    sys.path.insert(0, str(ROOT / "tools"))
    import build
    w, h = WINDOW_SIZE
    r = subprocess.run([os.environ.get("BLENDER", build.DEFAULT_BLENDER), "--factory-startup",
                        "--enable-event-simulate", "--window-geometry", "0", "0", str(w), str(h),
                        "--python-exit-code", "1", "--python", __file__],
                       env=build.sandbox_env(), stdin=subprocess.DEVNULL,
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
    ok = False
    for line in r.stdout.splitlines():
        if line.startswith("make_startup"):
            print(line)
            ok = ok or line.startswith("make_startup: wrote")
    if r.returncode or not ok:
        sys.stderr.write(r.stdout[-4000:] + r.stderr[-3000:])
        return r.returncode or 1
    return 0


def log(*args):
    print("make_startup:", *args)
    sys.stdout.flush()


def _region(area, kind):
    return next((r for r in area.regions if r.type == kind), None)


def is_toolbox_space(space):
    """= src/allset/ui/toolbox.py is_toolbox (kept in sync by tests/test_step49_layout.py)."""
    return (space.type == 'VIEW_3D' and space.show_region_toolbar and not space.show_region_header
            and not space.show_region_ui and not space.show_object_viewport_mesh)


class Builder:
    """Layout edits, one per timer tick (screen operators and simulated events need a redraw in between)."""

    def __init__(self):
        import bpy
        self.bpy = bpy
        self.win = bpy.context.window_manager.windows[0]
        self.areas = {}

    @property
    def scr(self):
        return self.win.screen

    def ov(self, area, region_type='WINDOW'):
        return self.bpy.context.temp_override(window=self.win, screen=self.scr, area=area,
                                              region=_region(area, region_type))

    def only(self, area_type):
        found = [a for a in self.scr.areas if a.type == area_type]
        assert len(found) == 1, (area_type, len(found))
        return found[0]

    def biggest_view(self):
        return max((a for a in self.scr.areas if a.type == 'VIEW_3D'), key=lambda a: a.width * a.height)

    def split(self, area, direction, px, side):
        """Split ``area`` so the part on ``side`` ('TOP'/'BOTTOM'/'LEFT'/'RIGHT') is ``px`` pixels; return it
        (a generator: ``part = yield from self.split(...)``)."""
        bpy = self.bpy
        size = area.height if direction == 'HORIZONTAL' else area.width
        frac = px / size
        factor = {'TOP': 1 - frac, 'BOTTOM': frac, 'LEFT': frac, 'RIGHT': 1 - frac}[side]
        before = {a.as_pointer() for a in self.scr.areas}
        with self.ov(area):
            assert bpy.ops.screen.area_split(direction=direction, factor=factor) == {'FINISHED'}
        new = next((a for a in self.scr.areas if a.as_pointer() not in before), None)
        assert new is not None, ("split made no area", direction, px, side, size, factor,
                                 [(a.type, a.x, a.y, a.width, a.height) for a in self.scr.areas])
        pair = (new, area)
        yield   # area rectangles update on the next redraw
        if direction == 'HORIZONTAL':
            top, bottom = sorted(pair, key=lambda a: -a.y)
            return top if side == 'TOP' else bottom
        left, right = sorted(pair, key=lambda a: a.x)
        return left if side == 'LEFT' else right

    def steps(self):
        bpy = self.bpy
        prefs = bpy.context.preferences
        # Maya density: effective scale 1.0 (= tests/gui --ui-scale 0.8 on a 125 % display)
        prefs.view.ui_scale = prefs.view.ui_scale / prefs.system.ui_scale
        for value in ('PRESS', 'RELEASE'):  # close the splash (it eats simulated events)
            self.win.event_simulate(type='ESC', value=value, x=800, y=450)
        yield
        ws = bpy.data.workspaces["Layout"]
        assert self.win.workspace == ws, "factory startup should open the Layout workspace"
        # 1. Remove the factory timeline and the right column: one 3D View is left.
        for kind in ('DOPESHEET_EDITOR', 'OUTLINER', 'PROPERTIES'):
            with self.ov(self.only(kind)):
                assert bpy.ops.screen.area_close() == {'FINISHED'}, kind
            yield
        assert [a.type for a in self.scr.areas] == ['VIEW_3D'], [a.type for a in self.scr.areas]
        view = self.scr.areas[0]
        hdr = _region(view, 'HEADER').height
        # 2. Maya strip: Status Line row, then the Shelf row, over everything, full width. The Status
        #    Line is a header-only area (Blender keeps it one header high at any UI scale); the
        #    Shelf area = tab row (header) + icon row (WINDOW, ui/shelf.py gizmos).
        strip = yield from self.split(view, 'HORIZONTAL', hdr + 3 + SHELF_PX + EDGE, 'TOP')
        strip.type = 'IMAGE_EDITOR'
        yield
        shelf = yield from self.split(strip, 'HORIZONTAL', SHELF_PX + 2, 'BOTTOM')
        strip = max((a for a in self.scr.areas if a.type == 'IMAGE_EDITOR'), key=lambda a: a.y)  # the top part
        yield
        # 3. Time Slider (timeline WINDOW) + Range Slider (its header, flipped under it), full width.
        timeline = yield from self.split(self.biggest_view(), 'HORIZONTAL', TIME_SLIDER_PX + hdr + EDGE, 'BOTTOM')
        timeline.type = 'DOPESHEET_EDITOR'
        timeline.ui_type = 'TIMELINE'
        yield
        with self.ov(timeline, 'HEADER'):
            assert bpy.ops.screen.region_flip() == {'FINISHED'}
        yield
        # 4. Tool Box column (a 3D View showing only its toolbar, ui/toolbox.py), then the Outliner.
        view = self.biggest_view()
        toolbox = yield from self.split(view, 'VERTICAL', round(_region(view, 'TOOLS').width * TOOLBOX_ROOM) + 1, 'LEFT')
        yield
        outliner = yield from self.split(self.biggest_view(), 'VERTICAL', OUTLINER_PX + EDGE, 'LEFT')
        outliner.type = 'OUTLINER'
        yield
        # 5. Maya's right tab stack (Channel Box / Layer Editor | Attribute Editor | Modeling Toolkit): its own area,
        #    not the viewport's sidebar.
        dock = yield from self.split(self.biggest_view(), 'VERTICAL', DOCK_PX + EDGE, 'RIGHT')
        dock.type = 'PROPERTIES'
        yield
        yield from self.make_stack(dock)
        view = self.biggest_view()
        self.areas = {"strip": strip, "shelf": shelf, "timeline": timeline, "toolbox": toolbox, "outliner": outliner,
                      "view3d": view, "dock": dock}
        self.configure()
        yield
        # 6. The timeline's sidebar = the Time Slider's current frame field and transport buttons: drag
        #    its left edge (region size has no API).
        yield from self.drag_region_edge(timeline, TIME_CONTROLS_PX)
        yield from self.maya_workspaces()
        self.report()
        shot = os.environ.get("MAKE_STARTUP_SHOT")
        if shot:
            with bpy.context.temp_override(window=self.win):
                bpy.ops.screen.screenshot(filepath=shot)
        self.save()

    def find(self, kind):
        """An area of the active screen by role (strip / shelf / timeline / toolbox / outliner / dock / view3d)."""
        areas = list(self.scr.areas)
        if kind in ("strip", "shelf"):
            rows = sorted((a for a in areas if a.type == 'IMAGE_EDITOR' and a.spaces.active.mask is not None),
                          key=lambda a: -a.y)
            return rows[0 if kind == "strip" else 1] if len(rows) > (kind == "shelf") else None
        if kind == "timeline":
            return next((a for a in areas if a.type == 'DOPESHEET_EDITOR' and a.ui_type == 'TIMELINE'), None)
        if kind == "toolbox":
            return next((a for a in areas if a.type == 'VIEW_3D' and is_toolbox_space(a.spaces.active)), None)
        if kind == "outliner":
            return next((a for a in areas if a.type == 'OUTLINER'), None)
        if kind == "dock":
            return next((a for a in areas if a.type == 'PROPERTIES' and getattr(a.spaces.active, STACK_FLAG, False)),
                        None)
        views = [a for a in areas if a.type == 'VIEW_3D' and not is_toolbox_space(a.spaces.active)]
        return max(views, key=lambda a: a.width * a.height) if views else None

    def close(self, kind):
        area = self.find(kind)
        if area is None:
            return
        with self.ov(area):
            assert self.bpy.ops.screen.area_close() == {'FINISHED'}, kind
        yield

    def maya_workspaces(self):
        """Maya-style workspaces (#81): each is a copy of the finished General layout with Maya's
        changes (closed panels, an editor beside / under the viewport, the raised tab), marked with its template name
        so the kit can list, append and reset it (src/allset/ui/workspaces.py). Blender's factory workspaces go:
        a Maya scene lists Maya's workspaces."""
        bpy = self.bpy
        general = bpy.data.workspaces["General"]
        for ws in [w for w in bpy.data.workspaces if w != general]:
            bpy.data.batch_remove(ids=[ws])
        yield
        for name, (menu_set, tab, recipe) in MAYA_WORKSPACES.items():
            if name == "General":
                ws = general
            else:
                self.win.workspace = general
                yield
                before = set(bpy.data.workspaces)
                with bpy.context.temp_override(window=self.win, screen=self.scr):
                    assert bpy.ops.workspace.duplicate() == {'FINISHED'}
                yield
                ws = next(w for w in bpy.data.workspaces if w not in before)
                ws.name = name
                self.win.workspace = ws
                yield
                yield from self.apply_recipe(recipe)
            ws["allset_template"] = name
            ws["allset_menu_set"] = menu_set
            ws["allset_dock_tab"] = tab
            log("workspace", name, [(a.ui_type, a.width, a.height) for a in ws.screens[0].areas])
        self.win.workspace = general
        maya_views()
        yield

    def apply_recipe(self, recipe):
        bpy = self.bpy
        for step in recipe:
            if step.startswith("no_") and step != "no_toolheader":
                kind = step[3:]
                if kind == "strip":
                    yield from self.close("shelf")
                yield from self.close(kind)
            elif step == "no_toolheader":
                # Modeling - Expert: Status Line and Shelf closed; the panel toolbar row goes with them
                self.find("view3d").spaces.active.show_region_tool_header = False
            elif step == "tool_settings":
                # Sculpting: Tool Settings on the right (the kit's Tool Settings dock = Tool tab, no role flag)
                dock = self.find("dock")
                setattr(dock.spaces.active, STACK_FLAG, False)
            elif step == "uv_editor":
                view = self.find("view3d")
                uv = yield from self.split(view, 'VERTICAL', round(view.width * UV_EDITOR), 'RIGHT')
                uv.type = 'IMAGE_EDITOR'
                uv.ui_type = 'UV'
                yield
            elif step == "graph_editor":
                view = self.find("view3d")
                ge = yield from self.split(view, 'HORIZONTAL', round(view.height * ANIMATION_GRAPH), 'BOTTOM')
                ge.type = 'GRAPH_EDITOR'
                ge.ui_type = 'FCURVES'
                ge.spaces.active.show_region_ui = False     # Maya's Graph Editor has no side panel
                yield
            elif step == "shape_editor":
                # Rigging: Node Editor / Shape Editor tabs under the viewport; Blender's rig data has no node
                # graph, its Shape Key Editor is the Shape Editor
                view = self.find("view3d")
                se = yield from self.split(view, 'HORIZONTAL', round(view.height * RIGGING_EDITOR), 'BOTTOM')
                se.type = 'DOPESHEET_EDITOR'
                se.ui_type = 'DOPESHEET'
                se.spaces.active.mode = 'SHAPEKEY'
                yield
            elif step == "script_editor":
                view = self.find("view3d")
                te = yield from self.split(view, 'HORIZONTAL', round(view.height * RENDER_SCRIPT), 'BOTTOM')
                te.type = 'TEXT_EDITOR'
                yield
            elif step == "render_column":
                # Render Setup + Property Editor column = Blender's Render properties
                view = self.find("view3d")
                col = yield from self.split(view, 'VERTICAL', RENDER_COLUMN_PX, 'LEFT')
                col.type = 'PROPERTIES'
                yield
                for _i in range(20):
                    try:
                        col.spaces.active.context = 'RENDER'
                        break
                    except TypeError:
                        col.tag_redraw()
                        yield
            else:
                raise ValueError(step)
        yield

    def drag_region_edge(self, area, width):
        ui = _region(area, 'UI')
        x0, y = ui.x, ui.y + ui.height // 2
        target = area.x + area.width - width
        self.win.event_simulate(type='MOUSEMOVE', value='NOTHING', x=x0 + 1, y=y)
        yield
        self.win.event_simulate(type='LEFTMOUSE', value='PRESS', x=x0 + 1, y=y)
        yield
        for i in range(1, 6):
            self.win.event_simulate(type='MOUSEMOVE', value='NOTHING', x=x0 + 1 + (target - x0) * i // 5, y=y)
            yield
        self.win.event_simulate(type='LEFTMOUSE', value='RELEASE', x=target + 1, y=y)
        yield
        yield
        log("sidebar", area.ui_type, _region(area, 'UI').width)

    def make_stack(self, area):
        """The tab-stack area = a Properties editor on its Tool tab, header and tab column hidden, marked by
        ``STACK_FLAG`` (= ui/maya_dock.set_role; the Tool tab can be chosen once the editor has drawn)."""
        bpy = self.bpy
        space = area.spaces.active
        for _i in range(20):
            try:
                space.context = 'TOOL'
                break
            except TypeError:
                area.tag_redraw()
                yield
        assert space.context == 'TOOL', space.context
        for prop in space.bl_rna.properties:
            if prop.identifier.startswith("show_properties_"):
                setattr(space, prop.identifier, prop.identifier in ("show_properties_tool", STACK_FLAG))
        space.show_region_header = False
        with self.ov(area, 'NAVIGATION_BAR'):
            assert bpy.ops.screen.region_toggle(region_type='NAVIGATION_BAR') == {'FINISHED'}
        yield
        log("stack", area.width, [(r.type, r.width) for r in area.regions])

    def configure(self):
        a = self.areas
        so = a["outliner"].spaces.active
        so.display_mode = 'VIEW_LAYER'
        so.use_filter_object_content = False   # Maya: DAG only, no shapes
        so.use_filter_children = True
        # Maya's Outliner lists the DAG from the world: no collection rows (display layers are the
        # Layer Editor's) and no per-row render toggle.
        so.use_filter_collection = False
        so.show_restrict_column_render = False
        so.show_restrict_column_hide = False   # no eye column: Maya hides with H (= ui/maya_outliner.setup)
        so.show_mode_column = False             # no Blender mode column in component mode (#109)
        so.use_sort_alpha = False               # Maya order: startup cameras, then creation order (#117)

        st = a["timeline"].spaces.active       # Time Slider: no channel list; sidebar = its buttons
        st.show_region_channels = False
        st.show_region_ui = True

        for key, name in (("strip", STRIP_MARKER), ("shelf", SHELF_MARKER)):   # = ui/shelf.py markers
            sp = a[key].spaces.active
            marker = self.bpy.data.masks.new(name)
            marker.use_fake_user = True
            sp.mask = marker
            sp.mode = 'VIEW'
            # the shelf row draws tab strip + icons in its WINDOW region (ui/shelf.py)
            sp.show_region_header = key == "strip"
            sp.show_region_tool_header = False
            sp.show_region_ui = False
            sp.show_region_toolbar = False
            # no image navigation gizmo — invisible under the kit's drawing, it took clicks at the right
            # end of the row (the shelf scroll bar)
            sp.show_gizmo_navigate = False

        v3d = a["view3d"].spaces.active
        v3d.show_region_ui = False             # Maya panels are their own areas, not the viewport's sidebar
        v3d.show_region_toolbar = False        # the Tool Box column replaces it
        v3d.show_region_tool_header = True     # = Maya's panel toolbar (ui/panel_toolbar.py)
        v3d.show_region_header = True          # Maya panel menu bar
        v3d.lens = MAYA_LENS
        v3d.region_3d.view_perspective = 'PERSP'

        tb = a["toolbox"].spaces.active        # = ui/toolbox.py is_toolbox
        tb.show_region_toolbar = True
        tb.show_region_header = False
        tb.show_region_tool_header = False
        tb.show_region_ui = False
        tb.show_gizmo = False
        tb.overlay.show_overlays = False       # no kit grid / furniture / wire either (they check it)
        # No object type is visible in this view: nothing is drawn behind the tools, and a click under
        # them (it reaches the WINDOW region) selects or deselects nothing (BKE_base_is_visible checks
        # object_type_exclude_viewport). An empty local view would do the same but Blender drops it on load.
        for name in dir(tb):
            if name.startswith("show_object_viewport_"):
                setattr(tb, name, False)
        assert is_toolbox_space(tb)
        maya_views()
        self.bpy.data.workspaces["Layout"].name = "General"   # Maya workspace name

    def report(self):
        for a in self.scr.areas:
            regions = {r.type: (r.x, r.y, r.width, r.height) for r in a.regions if r.width > 1 and r.height > 1}
            log("area", a.ui_type, (a.x, a.y, a.width, a.height), regions)

    def save(self):
        import bpy
        setup_scene()
        OUT.parent.mkdir(parents=True, exist_ok=True)
        bpy.ops.wm.save_as_mainfile(filepath=str(OUT), compress=True, check_existing=False)
        OUT.with_suffix(".blend1").unlink(missing_ok=True)  # Blender's backup of the previous file
        log(f"wrote {OUT.relative_to(ROOT)} ({OUT.stat().st_size} bytes)")


def maya_views():
    """Every 3D view of every workspace sees Maya's new-scene persp view in cm: a default
    pCube1 (1 cm) looks the size it does in Maya."""
    import bpy
    from mathutils import Vector
    eye = Vector(MAYA_PERSP_EYE) * MAYA_UNIT
    for screen in bpy.data.screens:
        for area in screen.areas:
            for space in area.spaces:
                if space.type != 'VIEW_3D':
                    continue
                space.clip_start, space.clip_end = (c * MAYA_UNIT for c in MAYA_CLIP)
                space.lens = MAYA_LENS        # every view (and Four View's persp quadrant) = Maya's persp angle
                # Finest perspective grid step = 1 cm (= units.grid_scale):
                # grid lines every 1 cm.
                space.overlay.grid_scale = MAYA_UNIT
                # Maya's grid axes are grey like the grid; Blender colours them with
                # the user's theme axis colours (the kit ships no theme).
                space.overlay.show_axis_x = space.overlay.show_axis_y = False
                # a finite Maya-style grid instead of Blender's floor, also in ortho side views
                # (src/allset/ui/maya_grid.py: show_floor / show_ortho_grid off, grid_lines 0).
                space.overlay.show_floor = space.overlay.show_ortho_grid = False
                space.overlay.grid_lines = 0
                # Maya view furniture (ViewCube, axis triad, camera name; ui/view_furniture.py)
                # replaces Blender's navigation gizmo and text info.
                space.show_gizmo_navigate = False
                space.overlay.show_text = False
                # Maya highlights a selection with its wireframe (ui/selection_wire.py), no outline.
                space.overlay.show_outline_selected = False
                # Maya draws no line from a child to its parent; Blender's dashed relationship lines go.
                space.overlay.show_relationship_lines = False
                # Maya has no 3D cursor: hidden; the component pivot edit (D / Insert,
                # operators/hold.ComponentPivotEdit) shows it while the cursor is the pivot (#59).
                space.overlay.show_cursor = False
                # Maya has no redo panel: no Blender "Move" Adjust Last Operation after a manipulator / tool drag
                # (#155 QA 240 H1-9). Kit option boxes of the "redo" kind open F9's popup
                # (marking/modal._call screen.redo_last), which doesn't need the HUD region.
                space.show_region_hud = False
                # Flat viewport grey #5c5c5c. Without the kit
                # theme that is view data: the view's own background colour, scene linear (#45).
                space.shading.background_type = 'VIEWPORT'
                space.shading.background_color = (MAYA_BG_LINEAR,) * 3
                rv3d = space.region_3d
                rv3d.view_location = (0.0, 0.0, 0.0)
                rv3d.view_rotation = eye.normalized().to_track_quat('Z', 'Y')
                rv3d.view_distance = eye.length


def setup_scene():
    import bpy
    scene = bpy.context.scene
    us = scene.unit_settings
    us.system = 'METRIC'
    us.length_unit = 'CENTIMETERS'         # display cm, keep 1 BU = 1 m
    us.scale_length = 1.0
    # Maya animation range = frame range, playback range = preview range.
    scene.frame_start, scene.frame_end = 1, MAYA_RANGE_END
    scene.use_preview_range = True
    scene.frame_preview_start, scene.frame_preview_end = 1, MAYA_FRAME_END
    scene.render.fps, scene.render.fps_base = 24, 1.0
    # Render Settings image size: 960 x 540, pixel aspect 1 (#71). Blender's scale stays 100 %.
    scene.render.resolution_x, scene.render.resolution_y = MAYA_RESOLUTION
    scene.render.resolution_percentage = 100
    scene.render.pixel_aspect_x = scene.render.pixel_aspect_y = 1.0
    # Tool defaults:
    # axis mode per tool (Move World, Rotate/Scale Object), the manipulator at the lead
    # object's pivot (edit mode switches to the bbox centre, operators/pivot.py), rotate
    # snap 15 degrees.
    ts = scene.tool_settings
    slots = scene.transform_orientation_slots
    slots[0].type = 'GLOBAL'
    slots[1].type, slots[2].type, slots[3].type = 'GLOBAL', 'LOCAL', 'LOCAL'
    ts.transform_pivot_point = 'ACTIVE_ELEMENT'
    ts.snap_angle_increment_3d = 0.2617993877991494
    # Maya's new scene is empty.
    for ob in list(bpy.data.objects):
        data = ob.data
        bpy.data.objects.remove(ob)
        if data is not None and data.users == 0:
            for coll in (bpy.data.meshes, bpy.data.cameras, bpy.data.lights):
                if data.name in coll and coll[data.name] == data:
                    coll.remove(data)
                    break
    for mat in list(bpy.data.materials):
        if mat.users == 0:
            bpy.data.materials.remove(mat)


def main():
    import bpy
    gen = Builder().steps()

    def tick():
        try:
            next(gen)
        except StopIteration:
            bpy.ops.wm.quit_blender()
            return None
        except Exception:
            import traceback
            traceback.print_exc()
            sys.stdout.flush()
            os._exit(1)
        return 0.3

    bpy.app.timers.register(tick, first_interval=1.5)


if __name__ == "__main__":
    try:
        import bpy  # noqa: F401
    except ImportError:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
        import hidden_desktop  # noqa: E402  (test Blenders never show on screen)
        hidden_desktop.ensure_hidden()
        sys.exit(run_outside_blender())
    if bpy.app.background:
        sys.exit("make_startup: needs a GUI Blender (see the module docstring)")
    main()
