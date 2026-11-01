# Changelog

All notable changes to Maya Workflow Kit (earlier versions were called Allset for Maya Users and, before that, Maya Kit). Format: [Keep a Changelog](https://keepachangelog.com/), versions follow
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- **Save your own workspaces** (#277): Windows > Workspaces > Save Current Workspace As... saves the current
  layout (areas, editors and their sizes) under a name. Your saved workspaces are listed after Maya's in
  Windows > Workspaces and the Status Line workspace menu, in every scene; choosing one brings that layout into
  the open scene without changing its contents. Reset Current Workspace returns it to its saved state and
  Delete Current Workspace removes it. Only the layout is saved, in the extension's user folder; new scenes
  still start in Maya Classic.
- **UV-only edge and face selection, double-click loops** (#264): the UV Toolkit has UV Edge and UV Face
  buttons next to UV and UV Shell: they pick UV edges / UV faces apart from the mesh (UV Sync Selection off), so a
  shell border picks one side only. In the UV Editor a double-click on a UV edge selects its UV edge loop,
  Ctrl+double-click its edge ring, and a double-click on a UV or a UV face its whole UV shell; Shift adds to the
  selection. Loops stop at UV seams. The Vertex / Edge / Face buttons still pick mesh components.
- **Checker density** (#264): in the UV Editor Ctrl+Up / Ctrl+Down make the checker map finer or coarser, one
  step at a time (never below 1); the density stays with the checker when you turn it off and on.
- **Fuller UV Toolkit** (#264): every UV Toolkit button now works. Select By Type has Back-Facing, Front-Facing,
  Overlapping, Non-Overlapping, Texture Borders and Unmapped; Create, Cut and Sew and Arrange and Layout list all
  of their UV Editor menu commands (Auto Seams, Split, Stitch Together, Merge, Gather Shells, Layout Along,
  Randomize, Stack Similar, Unitize ...), with the same option boxes as the menus. New: Align Min / Avg / Max U and
  V (with the UV Shell mask whole shells move), Unfold Along U / Unfold Along V (the other coordinate stays),
  and Straighten UVs with U / V buttons and an angle tolerance (30 degrees). Stack Similar lays shells of the same
  shape onto each other.
- **Straighten UVs and Randomize Shells work like Maya** (#264): UV Editor > Modify > Straighten UVs lines up the
  selected UV edges that run within 30 degrees of U or V (each connected run on its own line) instead of putting
  every selected UV on one line, and Randomize Shells moves, turns and scales each shell within the ranges of its
  option window (by default it moves shells up to 0.1 along U and V). Both have their option windows.

### Changed
- **IPR opens its own render window** (#277): Render > IPR Render Current Frame, Redo Previous IPR Render and the
  Status Line IPR button now open a separate window with a 3D View in Rendered shading, like Maya's IPR render
  window, instead of switching your viewport to Rendered. The window shows only the picture (no overlays or
  toolbars), looks where the main view looks and follows it while you tumble, and the IPR button looks pressed
  while it is open. IPR again, or closing the window, stops it; your viewport keeps its own shading throughout.
- **Shift+drag names what it does** (#277): while you Shift+drag the Move / Rotate / Scale manipulator, an in-view
  message says "Shift Duplicate" (objects are copied) or "Shift Extrude" (components are extruded). A Shift+click
  shows nothing; the add-on preference In-View Messages turns it off.
- **Other add-ons stay in reach in Maya mode** (#221): menus other add-ons add to Blender's top bar now follow
  the Maya menus in the menu bar (or sit at the end of the » menu when the bar is full), and tools other add-ons
  add to the 3D View toolbar stay there after the Maya tools.
- **Bigger keys in the Graph Editor** (#277): keys are drawn as 11 px dots (Blender's theme draws 6 px) in their
  own colour, so they are easier to see and to grab; a selected key keeps Blender's active-key dot in the middle.
  The add-on preference Key Size (also in Windows > Settings/Preferences > Preferences > Animation) sets the size;
  0 shows Blender's own keys. Toolbar buttons that do different things no longer share an icon (Center current
  time, Auto load, Unconstrained drag, Re-normalize curves).
- **Graph Editor / Dope Sheet toolbar fits narrow editors** (#277): when the editor is too narrow for every
  toolbar button, the button groups that fit stay in Maya's order and the rest move into a » menu at the
  right end of the row (with their Maya names), instead of being cut off.
- **Bigger tangent handles in the Graph Editor** (#277): tangent handle points are drawn as bold rings that
  grow with the Key Size preference, black when unselected and in the selected colour when selected, so
  they are easier to see and to grab and never look like keys. Key Size 0 shows Blender's own handles.
- **Graph Editor / Dope Sheet toolbar pictures** (#277): every toolbar button now has its own picture that
  shows what it does: tangent buttons draw the curve shape they give around a key (Auto, Spline, Clamped,
  Linear, Flat, Stepped, Plateau ...), key tools draw keys with the tool's motion, the view buttons show how
  curves are laid out and the infinity buttons show the repeated curve. Hover a button for its Maya name.
- **The 3D View shows the UV selection in UV mode** (#264): after F12 (UV), the vertices of the UVs you pick in
  the UV Editor are drawn as selected in the 3D View and every other vertex as unselected, like Maya, instead of
  the whole mesh looking selected. Mesh component colours now also follow selection changes after you open or
  start a scene.
- **Pre-selection for single UVs, edges and faces** (#264): in the UV Editor the UV, UV edge or UV face a click
  would pick is drawn in the pre-selection red under the mouse, like Maya, not only whole UV shells. The add-on
  preference UV Pre-selection (formerly UV Shell Pre-selection) turns it off.
- **Bevel at box corners with tilted faces** (#213): Edit Mesh > Bevel on two edges that meet at a corner with one
  more edge now places the new corner, the new vertex on the third edge and both far ends like Maya when the side
  faces lean in or out, as long as the two edges' face angles differ by up to about 10.9 degrees (the same
  point where Maya changes how it builds the corner). Steeper differences keep the previous result for now.
  With Offset As Fraction off (an absolute Offset) such corners follow Maya at any face angle when the faces are
  flat.
  A corner where three bevelled edges meet (all three edges of a box corner) now gets Maya's width and puts
  each face's new corner where Maya does when the corner's face angles stay close (their half-angle sines
  within 10% of each other), whatever the mesh's vertex numbering.

### Fixed
- **Box select picks joints with nothing selected** (#276): in the Maya layout a box drawn over joints in Object
  Mode now selects them even when nothing was selected before, like Maya; one Ctrl+Z undoes the selection.
- **Help opens the Blender 5.2 manual**: the main Help menu, the Layer Editor and Outliner help, and the Help menus
  of the UV Editor, UV Toolkit, Graph Editor, Dope Sheet and the other Maya editor windows pointed at the Blender 4.5
  manual, API and release notes; the Component Editor's help page link is fixed.
- **UV commands keep to the picked mesh** (#264): with several meshes in edit mode, Unfold, Layout, Texel
  Density Get / Set, Stack, Orient, Distribute, Unstack, Layout Along and Stack Similar work only on the shells you
  picked; the other meshes' UVs are left alone (all shells are used only when nothing is picked).
- **Lattice points on a bent lattice are picked where you see them** (#274): when a Bend or another deformer
  bends a lattice, a click or a marquee in lattice edit mode now picks the points where they are drawn, not where
  they were before the deformer (Shift toggles, Ctrl removes, Ctrl+Shift adds; one Ctrl+Z undoes a marquee).
- **w / e / r anywhere in the Graph Editor** (#270): the keys now pick the Move / Rotate / Scale key tool with the
  mouse over the Graph Editor's outliner, menu bar, toolbar row or sidebar too, not only over the curves.
- **One undo for a snapped key move** (#270): with time snap on, moving a key that sat between two frames in the
  Graph Editor puts it on a whole frame as part of the move, so one Ctrl+Z undoes it (it took two before).
- **Default In / Out Tangent on Blender's own keys** (#267): keys made with Blender's Insert Keyframe (the I key,
  the Insert Keyframe menu and button, the Graph Editor / Dope Sheet insert) now get the Default In / Out Tangent
  too, like the kit's keys. A key set again on a frame that already had one keeps its tangents.
- **Hotkeys imported with Maya mode off wait for it** (#275): Import Settings with Maya mode off now keeps the
  file's kit hotkeys and gives them the next time Maya mode starts, instead of leaving them out.
- **Time Slider ticks for blendShape keys** (#271): keys on a mesh's blendShape target weights now show as ticks
  in the Time Slider when the mesh is selected, with the rest of its keys.
- **Lasso picks joints with nothing selected** (#276): like the box, the Lasso Select tool drawn around joints in
  the Maya layout now selects them even when nothing was selected before; one Ctrl+Z undoes the selection.

## [0.9.0] — 2026-11-01

FX, rendering and lighting run Blender's own features from the Maya menus, S keys components, blend shape weights
are channels, settings can be exported and imported, and the fixes from your reports. Supported: Blender 5.2 LTS.
Other versions are not tested (the extension still installs on 5.0 and 5.1). Files saved with older versions are tidied once when they are
opened (see Changed).

### Added
- **Export / Import Settings** (#275): save the kit's settings to one JSON file and load them again after a
  reinstall, in a new Blender or on another computer — the kit preferences (option window values included), the
  hotkeys you changed in the Hotkey Editor, your shelves and your marking menus. The buttons are in Preferences >
  Add-ons > Maya Workflow Kit and in the Preferences window's Edit menu (Windows > Settings/Preferences >
  Preferences); the import dialog lets you pick which parts to load. The Hotkey Editor has an Export button for the
  hotkeys alone, and its Import also reads such a file. Updating the kit already keeps these settings; the file is
  for when the kit is removed and installed again or Blender starts without its previous settings.
- **Scale Keys manipulator in the Graph Editor** (#270): with the Scale Keys tool (r) a box with handles is drawn
  around the selected keys. Drag a left / right side to scale the keys in time (speed up or slow down an animation),
  the bottom / top side to scale their values, or a corner for both; the opposite side stays where it is, time snap
  lands the keys on whole frames, and one undo takes the drag back. Turn it off in the preferences (Graph Editor >
  Scale Keys Manipulator).
- **Edge / Surface slide with the Move tool** (#262): Ctrl+Shift+middle-drag slides the selected vertices along
  their edges (edges and faces with Edge Slide). The Move tool's **Transform Constraint** (Tool Settings, Modeling
  Toolkit, and the W + left-click menu > Transform Constraints) turns every Move handle and the plain middle-drag
  into Edge Slide or Surface Slide until you set it back to Off.

- **UV shell pre-selection** (#264): in the UV Editor the shell under the mouse is highlighted while clicks pick
  whole shells, so you see what a click will select.
- **Type in the Attribute Editor** (#258): the type tab has Maya's Text section (the text itself, font, size,
  alignment, tracking, leading, word spacing, slant) and Geometry (extrude distance and offset, bevel distance and
  divisions, curve resolution); Generator, Texturing and Animation say what to use in Blender instead.
- **polyCylinder attributes** (#259): Height Baseline (−1 puts the bottom on the origin, 1 the top), Create UVs
  (None turns the UVs off) and Round Cap Height Compensation (round caps stay inside the height) in the Channel Box
  INPUTS and the Attribute Editor, in Maya's order, next to Subdivisions Caps and Round Cap.
- **More Fields/Solvers items** (#123): Set Rigid Body Interpenetration (Blender's Generic rigid body constraint with
  Disable Collisions between the selected bodies and the active one) and Use Selected as Source (Blender's force
  field on the selected object).
- **Set Key on components** (#272): S in component mode keys the selected points' X / Y / Z at the current time,
  like Maya — mesh vertices (selected edges and faces key their vertices), NURBS curve and surface CVs, Bezier
  points with their handles, and lattice points. Keyed vertices follow the time in edit mode too, and one undo
  removes the keys. In object mode S keys the object's channels as before.

### Changed
- **FX, Rendering and lighting run Blender's own features**: the Maya FX and Rendering menus stay where a Maya user
  looks for them, and each item now calls Blender's own simulation, light or render operator or opens the Blender
  editor for it; items Blender has nothing for are greyed with a note. Modeling, animation, rigging, UV, texturing,
  the Hypershade, lambert1 and the Channel Box Intensity / Decay rows of lights are unchanged. See
  [Maya FX and Rendering in Blender](docs/fx_render_concepts.md) for every item.
- **Render items call Blender's render**: Render > Render Current Frame / Redo Previous Render / Render Sequence,
  the Status Line Render button and the Render View's Render button run Blender's Render Image / Render Animation
  through the scene camera at the Output properties size. A scene without a camera still renders through persp,
  placed where the view looks from, like Maya (#277).
  Render > Batch Render renders the frame range in this session, Show Batch Render opens Blender's Render window and
  Test Resolution sets Blender's Resolution % (the size of every render). F12 / Ctrl+F12 and Ctrl+Alt+Enter are Blender's own
  render keys again (F12 over the 3D View and the UV Editor stays Maya's UV selection mask).
- **Light linking uses Blender's light linking**: Lighting/Shading > Make / Break Light Links and Make / Break Shadow
  Links link the selected objects to the **active** light (Make = Include, Break = Exclude; once one object is
  included, the light reaches only the included objects), Select Objects Illuminated / Shadowed by Light select the
  active light's linked objects. The Light Linking Editor (Lighting/Shading and Windows > Relationship Editors >
  Light Linking) opens Blender's Light Linking panel (Object Properties > Shading).
- **Light Editor** (Windows > Rendering Editors and the Status Line) opens an Outliner window that lists only the
  scene's lights; **Render Settings** opens Blender's Properties > Render in a window of its own.
- **FX menus call Blender's simulations at real size**: nCloth > Create nCloth / Create Passive Collider and
  nParticles > Emit from Object / Make Collide add Blender's Cloth / Collision modifier or particle system to every
  selected mesh, Create Active / Passive Rigid Body are Blender's rigid bodies, the Fields/Solvers fields are
  Blender's force fields (Gravity and Uniform = a Wind field turned down / along X), Fluids > 3D Container and
  Effects > Fire / Smoke are Blender's Quick Smoke (meshes that already are fluids are left out; when every selected
  mesh is one, a warning says so instead of a Python error), nConstraint > Transform Constraint is Blender's Hook to New
  Object, Fluids > Add/Edit Contents > Emitter makes the selected meshes smoke flows and Effects > Flow > Create
  Curve Flow a Curve Guide field. Nothing is rescaled: Blender simulates one unit as one metre, so FX works in metre
  scenes (the creating items say so in their tooltip).
- **Files saved with older versions** are tidied once when they are opened: a leftover `defaultLight` goes, the
  World's "Maya Ambient" nodes are taken out, old Ambient / Volume Lights become point lights with the same intensity and a Light Editor
  Isolate left on is undone. FX goes back to real size: a scene gravity the kit had scaled to the centimetre layout
  (0.098) goes back to Blender's 9.81 unless it was changed by hand, and kit nCloth stiffness and damping lose their
  rescale.
- **Prevent Negative Scale on every Scale handle** (#261): in component mode the centre handle and the plane
  handles stop at zero too, so a selection scales onto its pivot (ready to merge) or onto a line through it
  without flipping. Object Mode still scales past zero.

### Removed
- **Default light for renders**: a scene without lights no longer gets a light from the camera while it renders
  (Render Settings > Render Options > Enable Default Light and the Preferences row are gone); add a light to the
  scene instead.
- **Batch Render in a background Blender**, Cancel Batch Render (greyed: Esc stops a running render) and the Render
  Sequence / Batch Render option windows (camera choice, All Render-Enabled Cameras, alternate output folder,
  processors); the camera **Renderable** check went with them. Render Options > Skip existing frames is now Blender's
  own Overwrite / Placeholders.
- **Test Resolution** preference (a separate size for kit renders): Blender's Resolution % sets the size of every
  render.
- **Ambient Light and Volume Light** (Create > Lights, the Hypershade's Create > Lights, the Rendering shelf): greyed
  with a note, Blender has neither (raise the World colour, or use a Point Light).
- **Kit light linking rules**: making links for several lights at once, Illuminates by Default and Select Lights
  Illuminating / Shadowing Object (greyed: each light's Light Linking panel lists its objects).
- **Kit Light Editor and Render Settings windows**: the Light Editor's list with Isolate, and the Render Settings
  window's Common tab, image size presets and its Edit / Presets / Help menus.
- **FX unit scaling and the nucleus**: the kit no longer scales gravity, cloth stiffness and damping, collision
  distances, particle sizes, field strengths or fluid containers to the Maya unit, and the Attribute Editor's
  nucleus1 tab (Gravity, Space Scale, Substeps) is gone; Blender's Scene > Gravity and each object's Physics
  settings are the controls.
- **Kit-only FX items** (greyed with a note on what to use in Blender): nParticles > Create Emitter (the one-point
  emitter; use Emit from Object on a mesh) and Create Options, Initial State (Set for Selected / All Dynamic, Clear
  Initial State, Set From Mesh) and nCache > Transfer Cache To Input Mesh (apply the Cloth modifier instead), the
  other nConstraint items, Set Rigid Body Collision, Assign to Selected and Effects > Flow > Delete Selected Flow;
  the FX shelf's Emitter follows Create Emitter and 3D Fluid Container with Emitter runs Fluids > 3D Container.

### Fixed
- **One undo per move with Auto Key on** (#276): moving or rotating a keyed control with the Time Slider's Auto Key
  on made two undo steps (the move, then its key), so the first Ctrl+Z only took the key away and the pose seemed not
  to change. Now, like Maya, one Ctrl+Z takes back the move together with its key and one Shift+Z brings both back —
  for manipulator drags, rotations, Blender's own transforms and Rigify controls alike.
- **Time Slider keys follow the selection** (#277): after deselecting everything the Time Slider no longer shows
  the keys of the last selected object; like Maya it shows the keys of the selected objects only.
- **Smaller current-frame key mark** (#277): a key at the current frame is marked one frame wide (red above and
  below the current-frame box) instead of a red frame around the whole box, so the keys of nearby frames stay
  visible.
- **Tool Box Outliner button** (#277): the button shows and hides the Outliner like Maya's: in the Maya layout it
  hides the docked Outliner and the next click docks it back beside the Tool Box, instead of opening a second
  Outliner in a new window. It looks pressed while an Outliner is shown.
- **Lattice points get the Maya manipulator** (#274): in lattice edit mode the Move (w) and Scale (r) tools show
  the same Maya-style manipulator as objects and mesh components, at the selected points, instead of Blender's
  transform gizmo.
- **Channel Box middle-drag after a tool change** (#273): channels picked in the Channel Box change with a
  middle-drag in a view only until you pick another tool (Q / W / E / R or the toolbar), like Maya. The channels stay
  highlighted, but the middle-drag is the tool's own again (W moves, E rotates); click a channel to drive it again.
  To deselect channels, Ctrl+click a selected one, click the empty space under the channels, or deselect everything.
- **Graph Editor key drags with Auto Key on** (#270): dragging keys in the Graph Editor no longer sometimes adds a
  key at the current time (with the value the curve had before the drag), and one undo takes the whole drag back.
  Editing the curves themselves is not a channel change, like Maya; changing a keyed channel still sets its key.
- **Keying blend shape weights** (#271): the target weights of a blendShape node in the Channel Box INPUTS are
  channels now, like Maya: click to select them, Channels > Key Selected / Breakdown / Mute / Delete and Cut / Copy /
  Paste act on them, typed values and the middle-drag slider change every selected mesh with that target, and the
  row shows its keyed / animated state. The keys go on the mesh's shape keys, so the Graph Editor shows the curve.
- **Project autosave in the Maya layout** (#254): the autosave copy is written in the Maya layout too; before,
  the Channel Box's own scroll handling counted as a running tool and the copy never got written there. Auto,
  Clamped and Plateau tangents also keep Maya's shape again after an edit in the Maya layout.
- **Non-weighted tangents in the Graph Editor** (#267): dragging a tangent handle of a non-weighted curve only turns
  it, like Maya: the tangent stays a third of the way to the next key while you drag (it used to follow the mouse in
  length), and the rule also holds after every other edit. Curves made with Blender's own keying (the I key, Insert
  Keyframe, Blender's auto keying) get Curves > Default Tangent Weight too (non-weighted unless set to Weighted);
  animation loaded from a file, imported or appended keeps its tangents.
- **Joints inside a mesh in wireframe** (#266): a wireframe view (4) shows every joint and bone again, also the ones
  inside a mesh, like Maya; X-Ray shading draws them through the surfaces too. In a shaded view a mesh hides the
  joints inside it, as in Maya — Shading > X-Ray Joints shows them.
- **Smart Extrude / Smart Duplicate on Linux and macOS** (#265): a Shift+drag on a manipulator handle extrudes (or
  duplicates) every time, also when the mouse stays still for a moment before the drag; before, the extrusion was
  often taken back as if it had been a Shift+click and the drag only moved the faces.
- **Translated tooltips** (thanks to @RIPTIDE-z for spotting it in #260): the tooltips of the kit's own buttons and
  menu items now follow the interface language too (Japanese, Simplified Chinese).
- **Vertex size** (#263): edit-mode vertices follow Blender's theme Vertex Size (selected ones one pixel larger)
  instead of a fixed 3 px.
- **Pivot after component mode** (#263): a pivot moved or turned with D / Insert in Edit Mode no longer stays on
  the object in Object Mode — Center Pivot and the Move manipulator work on the object pivot again.
- **F12 UV mode when the UV Editor window reopens at its last place**: F12 in component mode now always ends in
  Maya's UV mode (UV Sync Selection off), and F9 / F10 / F11 afterwards bring back the vertices / edges / faces
  selected before. Before, once a UV Editor window had been closed somewhere else, the next F12 opened it there with
  UV Sync Selection still on and the earlier mesh selection was lost.

## [0.8.0] — 2026-10-31

Maya 2026 marking menus, Hypershade and shelves, the Marking Menu Editor from @TMouraille, Quad Draw from
@youngmin2k, Channel Box value dragging from Tom Pilott, and the fixes from your reports. Supported on Blender 5.2
LTS; 5.0 and 5.1 install but are not tested.

### Added
- **Marking Menu Editor** from @TMouraille (#239) — thank you! (Windows > Settings/Preferences > Marking Menu
  Editor): edit the kit's marking menus in Maya's 3×3 grid plus the list under it — label, command (Blender operator,
  Maya menu item, Python like a shelf button, submenu, or the kit's own item), option box, move, add or remove items,
  open submenus in place; Restore Default puts a kit menu back. **Your own marking menus** (New / Duplicate) open
  with a hotkey the Maya way: hold the key and press LMB, drag and release. Saved at once in the extension's user
  folder, so they survive kit updates; untouched items of an edited kit menu keep following the kit. Both styles
  (Maya Engine / Blender Pies).
- **Render Sequence with All Render-Enabled Cameras** (#252): every camera has a Renderable check (Attribute Editor
  camera tab > Output Settings, and Render Settings > Common > Renderable Cameras), on for new cameras and for
  persp, off for top / front / side, like Maya. Render > Render Sequence ❒ > All Render-Enabled Cameras renders the
  animation once per renderable camera; with more than one camera each camera's frames go into a folder named after
  the camera inside the output folder (for example `images/camFront/shot_0001.png`). The output path, render camera
  and render size come back afterwards.
- **Skip existing frames** (#252) in Render Settings > Common > Render Options: animation renders leave frames that
  already exist and mark the frame in progress with an empty file (Blender's Overwrite off, Placeholders on), so a
  stopped render picks up where it stopped and several computers can render the same frame range into one folder.
- **Project autosave** (#254): Windows > Settings/Preferences > Preferences > Files/Projects > AutoSave (also in the
  add-on preferences) saves a copy of the scene every few minutes into the current project's `autosave` folder,
  like Maya, instead of only Blender's recovery file in the system temp folder. Copies are named
  `<scene>.0001.blend`, `<scene>.0002.blend` ... (`untitled` for a scene never saved) and follow the project when
  you set another one; a Named Folder can be chosen instead. Limit Autosaves keeps only the newest copies of each
  scene. The scene's own file and its unsaved state are left alone, and nothing is written while the scene is
  unchanged or a tool drag / render is running. Blender still writes its own `.blend1` backups next to the file.
- **Sweep Mesh stays editable** (#238): Create > Sweep Mesh now keeps a live sweepMeshCreator1 node, like Maya.
  Its tab in the Attribute Editor sets the profile (Poly circle or star with sides and inner radius, Rectangle with
  corner radius and segments, Line, Arc, Wave), Scale Profile (also X / Y), Rotate / Translate Profile, Twist,
  Taper, Caps, Reverse Normals and the interpolation along the curve (Start to End, EP to EP, Distance, Precision);
  the Channel Box INPUTS show Profile Poly Sides, Scale / Rotate Profile, Twist, Taper, the interpolation values and
  Caps. Editing or moving the curve updates the mesh. Delete History (or Construction History off) makes it a plain
  mesh, and deleting the curve keeps the mesh.
- **Graph Editor key tools and value lines** (#211): w / e / r over the Graph Editor pick what a middle-mouse drag
  does to the selected keys — move them, turn their tangents, or scale them around the point where you pressed —
  instead of starting a move / rotate / scale at once; the toolbar shows the current one, and Edit >
  Transformation Tools > Move Keys Tool / Scale Keys Tool pick it too. l shows the value lines: the zero line and
  the lowest / highest value of the selected curves (also in Blender's View menu). The toolbar's new Unconstrained
  drag button (on by default) lets middle drags move keys in time and value; off, the first move picks one of them.
- **Japanese and Simplified Chinese** (#197): the kit's own labels and tooltips follow Blender's Preferences >
  Interface > Language. With Japanese (ja_JP) or Simplified Chinese (zh_HANS) chosen, the Maya menu bar and every
  Maya menu, the Graph Editor / Dope Sheet / UV Editor / Hypershade menu bars, the viewport panel menus, marking
  menus and the hotbox, the shelf tabs, the dock tabs, the "not in Blender" notes and many window and preference
  labels are shown in that language. Blender's Translate switches decide: Interface for labels, Tooltips for
  tooltips. Menu hotkeys and option boxes stay lined up with the translated labels. `tools/i18n_strings.py` lists
  every translatable string and the coverage of each language; corrections from native speakers are welcome.
- **Hypergraph: Hierarchy** (#232): Windows > General Editors > Hypergraph: Hierarchy (and the viewport's
  Panels > Hypergraph Panel, the hotbox's Hypergraph) opens a window with the scene hierarchy as a graph of nodes,
  like Maya: children in the row below their parent, lines from parent to child, an icon for groups, meshes,
  joints, cameras, lights, curves and locators, and each node filled with its display layer's colour. Click a node
  to select it (Shift toggles, Ctrl removes, Ctrl+Shift adds), drag on empty space for a marquee; the selection
  follows the scene both ways. Middle-mouse drag a node onto another to parent it there (the whole selection when
  the dragged node is selected), onto empty space to unparent it; world positions stay. Double-click a node to
  collapse or expand its children. Alt+middle-mouse tracks, Alt+right-mouse dollies, the wheel zooms, F / A frame
  the selection / everything; the strip at the top and the right-click menu hold Frame All, Frame Selection,
  Expand All and Collapse All. Nothing is stored in the scene file.
- **More Maya FX and Rendering menu items run Blender's own systems** (#123): 75 items that were greyed now
  work, each with a tooltip naming the Blender feature it uses. nParticles: Fill Object, Instancer, Create Options.
  Fluids: Add/Edit Contents > Emitter, Edit Fluid Resolution. nCloth: Rest Shape, Paint Vertex Properties (Input
  Attract, Stretch, Compression, Bend, Rest Length Scale on the cloth's vertex groups). nConstraint: Transform
  Constraint (pinned vertices hooked to a dynamicConstraint empty), Disable Collision, Add / Remove / Replace / Select
  Members, Remove Dynamic Constraint. nCache: Create Particle Disk Cache, Transfer Cache To Input Mesh, cache settings.
  Fields/Solvers: Volume Curve, Initial State, Set Active / Passive Key, Break Rigid Body Connections, Create Rigid
  Body Solver and its attributes. Effects: Create / Delete Selected Flow, Collide with Effect. Rendering: Transfer
  Maps (Cycles Bake), Toon > Assign Fill Shader (seven EEVEE toon materials), Set Camera Background Color, Reverse
  Surfaces, Stereo > Create. Hypershade: volume, hair, USD Preview Surface and Shading Map materials, Env Fog, UV
  chooser, particle sampler, environment and sky textures, colour / float correct and composite, Image Plane,
  Connection Editor. The new page docs/fx_render_concepts.md lists which Blender system stands for each Maya one.
- **Skin Tools** (#127): skin weight layers on a skinned mesh, like Maya's Skin Tools. Open it from the Skin
  Clusters card of Paint Skin Weights' Tool Settings and click Initialize Skin Layers: the current weights become
  the base layer. Add, duplicate, delete, reorder, rename, switch off and fade layers; each layer has its own
  weights and a Mask (painted like a joint) that sets where it covers the layers below. The skin's weights are
  always the stack's result. Pick a joint (or the Mask) in Influences and click Paint to weight paint that layer
  (Ctrl+click on a joint switches joints); Set Weights (Replace / Add / Scale / Smooth with an intensity) works on
  the selected vertices, Mirror copies one side of the layer onto the other (joints paired by label, then by place),
  Assign from Closest Joint gives a layer starting weights. Layers are saved with the file and every edit is one
  undo step. Once a mesh has layers, Skin > Paint Skin Weights opens Skin Tools; Delete Skin Layers goes back to the
  classic tool.
- **Time Slider middle-mouse drag** (#255): a middle-mouse click or drag on the Time Slider moves the time
  without updating the scene, like Maya: everything keeps its current pose, so S keys that pose at the new frame.
  The next ordinary time change (left-click, playback, arrow keys) shows the animation again.
- **Interactive Creation** (#225; the first notice change from @A2wkiller, #234 — thank you!): turn on Create > Polygon Primitives > Interactive Creation and the Create menu,
  shelf and option boxes let you draw a polygon primitive in a view, like Maya: drag to place it and size its base,
  then drag again for its height (torus: section radius; pipe: height and thickness; helix: height and coils).
  Perspective views draw on the grid; orthographic views draw on their own plane with the primitive's Axis facing
  you. A single click makes a default-size primitive centred there, a click on a later step leaves that size at its
  default, Esc drops an unfinished primitive and keeps the tool. Shift gives equal sides (a cylinder or cone in one
  drag), Ctrl grows a cube or plane from its centre. The result is the usual pCube1 with its polyCube1 node, one
  undo step each. Exit On Completion (on) ends the tool after one primitive; turn it off to draw several.
- **Hotkey Editor > Import...** (#219): read a hotkey set exported from Maya's Hotkey Editor (.mhk). Its keys
  replace the kit keys of the same commands; keys that are already Maya's stay, and commands the kit doesn't bind
  are listed in the system console. Only the key bindings are read — nothing in the file is run. Restore puts the
  Maya keys back.
- **RMB marking menu over a lattice** (from @A2wkiller, #236 — thank you! #227): Lattice Point enters lattice edit
  mode so its points can be moved, Object Mode goes back, and the usual object list follows, in object and lattice
  edit mode, instead of Blender's own context menu.
- **Shift+W / E / R from any editor** (#212): key Translate / Rotate / Scale from the Graph Editor, Dope Sheet,
  Outliner, Channel Box / Attribute Editor or Time Slider; edit, paint and sculpt modes keep their own keys. The
  Attribute Editor's Translate / Rotate / Scale fields show the Channel Box key colours.
- **UV Editor Shaded shows flipped UVs** (#246): 5 or View > Shaded colours front-facing UV faces blue and
  flipped (clockwise) ones red, like Maya's shaded UV display; 4 or View > Wireframe turns the faces off.
- **Channel Box value dragging** from Tom Pilott (#224) — thank you! Left-drag a Channel Box value sideways to change
  it: Ctrl snaps to whole displayed units, Shift is 10× finer, Alt 100× finer; the wheel adjusts the value during a
  drag and Ctrl+wheel over a value steps it. Esc or right-click puts the starting values back, one drag is one undo
  step, and Auto Key keys channels that already have keys. Clicking a value still edits it, a drag down the values
  still selects channels, and the middle-mouse virtual slider is unchanged.
- **Viewport extras** from Tom Pilott (#224) — thank you!
  - **Alt+B gradient**: the background cycle is now grey, light grey, Maya's blue gradient, black (#216). The kit
    draws the gradient itself in Solid and Wireframe shading, per view and saved with the file; your Blender theme
    is never changed.
  - **ViewCube**: a softer perspective, shaded faces and hover controls — Home, roll arrows on a face-aligned view,
    small orbit arrows and a menu.
  - **Selected wire**: a selected object's back edges no longer show through its faces, also when zoomed far
    out in a centimetre scene (#243, #229).

### Changed
- **Channel Box INPUTS attributes work like channels** (#230, #222): click a history attribute's name (polyCube1
  Subdivisions Height, a Subdivision's Levels, a Bevel's Width ...) to select it, then middle-drag in the viewport
  (Maya's virtual slider) or left-drag its value sideways to change it on every selected object with the same node.
  Whole-number attributes step by whole numbers, and a drag stops at the attribute's usual range (typing can go
  further). Modifier attributes can be keyed and show their key state like Translate X.
- **Joint Tool feedback** (#230): hold the button after a click and drag to position the new joint — the bone from
  the previous joint follows, release fixes it. While the tool runs the placed joints are drawn as joint circles
  with bones between them (the joint the next click attaches to in green), a ghost joint and bone show where the next
  click goes, pointing at an existing joint before the first click highlights the joint you would branch from, the
  cursor is a crosshair over the views and the Help Line shows the Joint Tool's help.
- **Double-click a vertex or face** selects its whole shell (the connected piece), like Maya 2026; an edge still
  selects its loop. Pick a face, then Shift+double-click its neighbour to select the whole face loop through both
  (a face further along still selects only the faces between) (#222).
- **Quad Draw options (Ctrl+Shift+RMB)** are Maya's marking menu: Multi-Cut Tool, Auto-weld, Clear Dots,
  Soften/Harden Edges, Relax and Extend submenus, then Snap to Backfaces and Reset Settings (#89).
- **Quad Draw strip width by Tab + middle-drag** (#89): hold Tab and middle-drag in empty space; dragging right
  widens the quad strip and dragging left narrows it, like Maya. A preview strip of the new width shows while you
  drag, the width stays for the next Tab + left-drag strips and is the Quad Strip Width in Tool Settings; Esc puts
  the old width back.
- **Display > Polygons is Maya's submenu** (from @TMouraille, #240 — thank you!) instead of opening Blender's overlay popover. Face Normals, Vertex Normals,
  Backface Culling, Crease Edges, Texture Border Edges (seams), Face Centers and Hard Edges (color) are check boxes
  that show and change the overlays of the 3D View (the largest one when the menu is in the top bar); Standard Edges /
  Soft/Hard Edges turn the sharp edge display off / on. Normals Size... is a small window whose slider (down to 0.001)
  changes the normal length while you drag and stays open until OK, Reset Display puts these back to Blender's
  defaults, and Custom Polygon Display opens the full overlay popover. Blender draws normals and edge display on
  meshes in edit mode. Vertex Size... and Edge Width... open the theme preferences searched for that setting; the
  other items are greyed with a note on the closest Blender feature.
- **Menus follow Maya 2026**: the Rigging menu set lists the Bifrost rigging menu and the FX set no longer lists
  Bifrost Fluids / Boss; Stereo > Create opens a submenu with Stereo Camera and Multi Stereo Rig; Select > Components
  shows the keys Multi-Component F7, Vertex F9, Edge F10, Face F11, UV F12 and UV Shell Alt+F12.
- **Marking menus follow Maya 2026**: the Move / Rotate / Scale / Select tool option menus (q / w / e / r hold,
  Ctrl+Shift+RMB) have Maya's Select submenu (pre-selection, Marquee, Camera-Based Selection, Clear Selection, Soft
  Select), the Custom axis submenu (Set to Component / Point / Edge / Face / Object, Reset), Rotate / Scale Center,
  Tweak Mode, Relative and the Shift Extrude / Shift Duplicate check boxes; the Select tool menu is Paint Select (W),
  Lasso (E), Symmetry (N) and Select (S). The hotbox centre shows Right View and New Camera, its south zone Sets;
  Lattice Point sits at N over a lattice; RMB over empty space puts Select All at S and Complete Tool at N; the a-hold
  menu has Reset Transforms. The Shift+RMB lists have Maya's full lists (Offset Edge Loop Tool, Remesh, Retopologize,
  Transform Component, Mapping with Planar Map X / Y / Z, Polygon Display ...), and RMB in the UV Editor lists the UV
  Editor's menus like Maya.
- **Space tap maximizes any panel** (#214): a Space tap over a panel of the four view keeps that panel alone
  whatever editor it shows (Graph Editor, render view, Outliner), and the next tap brings the four panels back with
  each panel's editor kept.
- **Ctrl first, then drag a Move manipulator handle** (#215): an axis arrow moves along its axis with grid snapping,
  and plane / centre handles move with snapping instead of starting a box select.
- **Graph Editor tangents** (#210): Spline, Clamped, Plateau and Flat each give Maya's own slope, with handles at a
  third of each interval, and keep their type when Blender edits the curve.
- **Joints draw like Maya's** in the Maya layout, and marquee / lasso selection picks them.
- **Reset Pivot Position puts an object's pivot on its centre**, like Maya: the pivot-edit RMB menu (D held) has
  Maya's Center Position on Reset (the default) and Zero Position on Reset, which puts the pivot back on the
  object's own origin as before. The Move / Rotate / Scale Tool Settings Reset button follows the same choice.
- **Hypershade > Create follows Maya 2026**: Math Utilities and Math Linear Utilities create the matching Blender
  Math / Vector Math / Map Range / Mix / Clamp / Vector Rotate node with its operation set (Sum, Cross Product, Sin
  ...); Multiply Divide, Plus Minus Average, Distance Between, Vector Product and the Double Linear nodes moved there
  like in Maya.
- **Graph Editor toolbar in Maya 2026 order**: the curve sculpting buttons (Smooth Keys, Reduce Keys) after the
  Retime tool and the drag constraint button before Time snap; the w / e / r key tools stay on their keys and in
  Edit > Transformation Tools.
- **Animation shelf** has Maya's Ghost Selected, Unghost Selected and Open Ghosting Editor buttons; Mesh > Booleans >
  Difference, the UV menu's Auto Seams / Cut UV Edges / Delete UVs / UV Set Editor and Visualize > Ghosting Editor /
  Unghost All use their shelf pictures, like Maya.

### Fixed
- **Surfaces like Maya**: Extrude (Tube) turns a profile drawn clockwise the right way round and turns it about the
  path's start when the path doesn't start at the profile; Extrude (Distance) uses the best-fit plane of a non-planar
  profile; Boundary / Square give each direction the mean parameter range of its two sides; Birail 1 with two
  different curved rails follows the rails exactly.
- **Loft > Polygons** UVs run along the curves (u) and across them (v), like Maya's Loft, instead of turned 90°.
- **UV > Normalize** with UVs or edges selected scales every face those UVs belong to, like Maya, instead of only
  the picked UVs.
- **Alt+LMB tumble with Emulate 3 Button Mouse on** (#242): Blender turns Alt+left drag into a middle drag when
  that preference is on; on Windows the kit now tumbles on it anyway (a real middle drag is left alone).
- **Panels > Tear Off / Tear Off Copy** (#255) opened nothing (an error in the console): they now open a copy of
  the view in a new window, with the same camera and display.
- **Graph Editor drags** (#211): Shift+left-drag that starts on an already selected key moves the selected keys
  along time or value only (before, the key was toggled off and a box started); a Shift+click still toggles it. A
  plain middle drag now counts from where you pressed, like Maya, instead of from a few pixels later.
- **Bevel, more cases like Maya** (#213): a lone rim edge of an n-gon cap with many sides gets the narrower
  width Maya gives it; a lone edge next to a non-planar face bevels with one width along the whole edge; border
  edges in the selection are left as they are, so a loop that runs along a mesh border bevels only its inner
  edges; vertex numbers stay in Maya's order after Merge Vertices joins new vertices to old ones; and faces come
  in Maya's order at the ends of open chains and lone edges too. Still different: the corner points where a
  bevelled spoke of a flat cap meets bevelled rim edges, and the corners of chains on meshes whose faces don't
  meet at right angles.
- **Undo while the Joint Tool runs** (#256): z / Ctrl+Z take back the last joint placed and the tool keeps
  running (undoing the first joint removes the new skeleton); Shift+Z / Ctrl+Y place it again. Before, Ctrl+Z
  undid the whole skeleton and the tool stopped with an error.
- **Group a joint, move the group, the skin follows** (#230): Edit > Group / Ctrl+G with a skeleton's root joint
  selected (in the viewport or the Outliner) puts the skeleton under `group1` and selects the group, like Maya.
  A skinned mesh now moves with its skeleton however the skeleton moves — its root joint, the skeleton itself or a
  group above it — while the mesh keeps its own place in the hierarchy and its own channel values. Grouping a joint
  inside a chain warns and changes nothing (Blender can't put a group between two joints of one skeleton).
  Unbind Skin and Delete History remove the skin's link to the skeleton with it. Skins bound with an older version
  get the link when their skeleton is grouped.
- **A group's pivot moves and snaps in pivot editing** (from @TMouraille, #253 — thank you!): D + V (or X / C) then a drag, or a middle-mouse drag, left
  a group's pivot where it was, because Blender's Affect Only Origins skips Empties. It now moves and snaps onto
  any vertex, its own children's included; the children, the group's channels and the pivot edit stay as they were.
- **Quad Draw workflow** from @youngmin2k (#231) — thank you!
  - **Quad Draw surface inference and symmetry**: rank candidate quads in 3D as well as screen space; resolve
    competing snap targets across multi-point strips. Pick Reference Seam supports posed live meshes away from an
    axis, with a mirrored Topology fill preview matching committed points and shared, bounded correspondence caches.
    Paired cuts skip duplicate topology replay; deletes capture local rings while retaining full native rollback.
  - **Component shading after reopening Quad Draw files**: save native viewport settings instead of temporary
    Retopology overrides; restore each owned view on tool/mode/workspace changes and failed saves. Shading >
    Restore Modeling Display repairs the affected viewport in older files without editing the mesh or materials.
  - **Quad Draw symmetry**: World/Object and bound Topology symmetry cover drawing, extensions, cuts, relaxation,
    deletion and welding. Seam captures share vertices; Ctrl loop cuts pair source edges before live projection,
    preventing valid cuts from being cancelled on slightly asymmetric references.
  - **Quad Draw gestures**: complete-loop Ctrl+Shift delete/tweak previews, continuous-border relaxation,
    Soft Selection influence preview and reversible Shift+MMB relaxation share the Modeling Toolkit settings.
  - **Quad Draw connections**: Shift previews use boundary edges and reject overlapping faces, skipped boundary
    vertices and non-manifold edges. Auto-weld previews vertex/edge targets while dragging, then welds the same targets
    on release, including Tab extensions. Escape cancels without merging; tolerance uses actual screen pixels.
  - **Quad Draw drag preview**: dragging a vertex or dot no longer leaves its cyan hover marker at the original position.
  - **Quad Draw**: activating the tool opens its options in the Modeling Toolkit. Retopology has a temporary cyan
    face tint with editable wire color, opacity and surface offset, without changing materials or the theme.
    Component drags keep their cursor offset and stay on the live surface when the cursor leaves its silhouette;
    view projection avoids jumping to hidden sheets during relax and extension. With no live surface, dots use the grid.
    Relax includes All Vertices, Auto-Lock keeps its choice for the stroke, and Extend distinguishes Loop from Border.
- **Frame Selection (F)** (from @youngmin2k, #237 — thank you!): Object and mesh component modes keep Maya's
  framing shortcut ahead of another add-on's mode-specific F menu. Turning Maya mode off restores that menu without changing its binding.
- **Hiding a group from the Outliner hides its children** (from @A2wkiller, #235 — thank you, and thanks @Kevorama for the report, #223). Ctrl+H, Shift+H,
  Ctrl+Shift+H, h and Alt+H in the Outliner run Maya's visibility commands like in the viewport, and a node hidden
  with Blender's own hide (or parented under one) hides everything below it.
- **Torn-off menus read like the menu** (from @TMouraille, #241 — thank you!): the items' text starts at the left edge instead of being centred, with
  the hotkeys and option boxes still lined up on the right.
- **Hypershade Delete Unused Nodes no longer crashes Blender** (#251, thanks @DAI3rd for the report and the crash
  logs). Shader Editors showing a deleted material let go of it first, and a material that only a deleted object's
  leftover data still held counts as unused, like Maya.
- **Target Weld skips hidden components in shaded mode** (#233, thanks @Troyzerk for the report and the fix idea):
  the press and the drop only pick vertices / edges you can see, like the pre-selection highlight; with X-ray or
  wireframe they pick through the mesh again.
- **Bind Skin keeps the mesh where it is** (#230): binding to joints that are posed, or bent by an IK handle / pole
  vector, no longer moves the mesh — like Maya, the current pose is the bind pose.
- **Other add-ons' keys no longer run before the kit's Maya keys** when both could take the same key press (#218,
  #250). Switching between Maya and Blender stops playback first; the Maya button while Maya mode is on puts the Maya
  keys back and opens the Maya layout.
- **UV Shell picks show in the UV Editor** with UV Sync Selection on, instead of the faces picked before (#245).
- **Tool Box column on Retina displays** is wide enough for the toolbar without widening it by hand (#248).
- **Translated menu bar labels** (Japanese and others) fit instead of being cut off (#249).
- **Channel Box**: a Shift or Ctrl click on a value (without a drag) selects like a click on the channel name, and a
  node the Show menu hides as a type doesn't hide its children.
- **View > Select Camera** in a view that doesn't look through a camera picks that panel's own Maya camera — persp,
  top, front or side — in scenes made with File > New Scene, instead of doing nothing (#229).

## [0.7.0] — 2026-10-29

Modeling and animation fixes from your reports, pivot editing / Smart Extrude / Make Live from @youngmin2k, and
Supported on Blender 5.2 LTS only for now; 5.0 and 5.1 still install but are untested and may have problems (0.6.2
stays the version for Blender 4.5 LTS).

### Changed
- **Supported on Blender 5.2 LTS only, for now.** The extension needs Blender 5.0 or newer to install, but only 5.2 is
  tested; on 5.0 and 5.1 there may be problems. 0.6.2 is the last version for Blender 4.5 LTS: keep using 0.6.2
  there. Versions after 5.2 are added once they are tested.

### Added
Pivot editing, component scale, Smart Extrude and Make Live from @youngmin2k (#207) — thank you!
- **Pivot editing (D)**: tap D (or Insert) to keep pivot editing on; hold D for a temporary edit as before. While
  editing, click a vertex, edge or face to move the pivot there and turn it to that component (Ctrl = turn only,
  Shift = move only); Move and Rotate handles follow the edited pivot, and the Rotate rings turn it live. Hold J for
  step snapping during pivot drags. Choosing a transform tool (Q / W / E / R) ends a latched pivot edit, like Maya.
  See [component picking](docs/pivot_component_picking.md).
- **Prevent Negative Scale**: the Scale tool option (on by default, as in Maya; Tool Settings, the tool popup and the
  R marking menu) stops a single-axis component scale at zero instead of flipping the selection.
  See [scope and behavior](docs/component_scale.md).
- **Smart Extrude**: Edit Mesh > Smart Extrude, the Polygons shelf button and the face marking menu grow or carve the
  selected faces inside a closed mesh; pushed through the mesh it cuts a hole, and where it meets another part of the
  same mesh the two are joined. The result keeps the existing edge loops and, like Maya, has no extra points on
  straight edges (a hole through a cube has quad walls). Move / Rotate / Scale handles, J snapping, typed values,
  Esc, Undo / Redo and G. Ordinary Extrude (Ctrl+E) and Shift+drag extrusion are unchanged.
  See [usage and limits](docs/smart_extrude.md).
- **Make Live**: several meshes can be live at once. The Status Line magnet makes the selection live and, while
  something is live, turns Make Live off; its arrow lists recent live surfaces. Live meshes can't be picked in the
  viewport or edited as components, show a dark green wire and Outliner name, and the Move centre / plane handles
  and Quad Draw snap only onto them. A deleted live mesh is let go (it no longer stays in the file).
  See [usage and limits](docs/make_live.md).
- **Blender navigation gizmo instead of the ViewCube** (#209): the add-on preference Viewport Navigation (also on the
  ViewCube page of Windows > Settings/Preferences > Preferences) switches the Maya views between the Maya ViewCube
  (default) and Blender's navigation gizmo, at once in every open view; saved files keep the Maya view. Thanks to
  @invader-zimm for the suggestion.
- **Snapping in the curve tools** (#208): while the EP / CV Curve Tool or a circular arc tool places or drags a
  point, hold X for the grid, C for the nearest curve or edge (drag to slide along it) or V for the nearest CV,
  vertex or pivot, like Maya. Middle drag moves the last point; Ctrl+click inverts Blender's scene snapping for that
  click. Thanks to @Oxiidus for the report.
- **Create > Lights > Dome Light** (#201): an image-based dome light (Blender World environment texture) with a
  domeLight1 locator in the Outliner; its Rotate turns the image and its Intensity sets the strength. Thanks to
  @leo2ard for the suggestion.

### Fixed
- **Scale manipulator like Maya** (#200): the centre handle scales uniformly by the horizontal drag, axis and plane
  handles scale along them, Ctrl+drag on an axis scales the other two axes, middle drag is half speed and each
  object scales about its own pivot. Thanks to @Fizkefaaz for the report.
- **Kit windows remember their size and place** (#203): Hypershade, Render Settings, the editor windows and the
  other kit windows open again where you left them. Thanks to @leo2ard for the report.
- **Set Driven Key on one channel twice** (#186): two driven keys on the same transform channel no longer show a
  stale value; files made with an earlier version are updated when opened.
- **Graph Editor, first week** (#192): selected objects without keys are listed, the tangent buttons sit on their
  own row, only selected keys show handles, S sets keys, F / A frame like Maya and Shift+middle drag locks to time or
  value. Thanks to @swarnava05 for the report.
- **IK on chains of three or more bones** (#181): a Rotate Plane IK handle splits the bend between the joints like
  Maya.
- **Bevel part of a cylinder cap rim** (#182): the ends of an open edge chain bevel like Maya; Delete History can be
  undone and brings the node back.
- **Skin weights from a Maya FBX** (#189): imported joint weights add up to 1 per vertex, like Maya's own import of
  the same file (Maya's FBX export leaves out weights of 0.001 and below; the mesh already matched).
- **Scene updates with many objects** (#191): moving, editing or selecting no longer makes the kit go over every
  object; on a 620-object scene an update costs about 0.6 ms more than plain Blender (was 2.9 ms).
- **Shift+drag duplicate and the Outliner** (#217): a duplicate goes last among its siblings, like Maya, and the
  Outliner rows no longer swap back and forth. Thanks to @Weeliano for the report and the video.
- **Settings kept when the add-on is switched off and on**: Blender drops an add-on's preferences when it is unticked
  in Preferences > Add-ons; the kit now keeps a copy in its own user folder and puts it back when it is ticked again
  (Remove still resets everything).
- **Maya operations in the Channel Box INPUTS** (#204): Edit Mesh > Bevel, Extrude and Mesh > Smooth (main menu,
  hotbox and shelf) leave their node (polyBevel1, polyExtrudeFace1, polySmoothFace1 …) in INPUTS in object mode too,
  and typing a new value there rebuilds the operation, as long as it is the latest kit operation and the mesh hasn't
  been changed since. A blend shape shows as blendShape1 with a weight per target. The shelf Smooth button now runs
  Mesh > Smooth. Thanks to @Fizkefaaz for the report.
- **Marquee with Move / Rotate / Scale** (#205): a drag off the manipulator draws a marquee even when the tool's Drag
  setting in a saved file is Tweak; nothing moves and the file isn't changed. Thanks to @Kevorama for the report, the
  analysis and the test scenario.
- **Maya menus and switching back on Blender 5.1** (#199, #198): when one part of Maya mode fails to start, the kit now
  takes back everything it had started and stays in plain Blender, and says why (console, a message and the add-on
  preferences) instead of leaving a Maya menu bar whose menus don't open. Switching back to Blender always removes the
  Maya menu bar, the Workspace menu and the Tool Box tools. A menu whose command is missing still draws. Thanks to
  @Zhadowcode99 for the reports.
- **Commands on a hidden object** (#187): component modes (F7 / F9 / F10 / F11), F8, the component marking menu,
  the Status Line selection mode, the Tool Box joint modes and menu / shelf / marking-menu items no longer print
  Blender's "Cannot edit hidden object" or a Python error when the active object is hidden; they warn
  "<name> is hidden: show it (Display > Show) first" and change nothing. Thanks to @youngmin2k for the component-mode
  fix and its tests (#196).
- **Maya mode at Blender startup** (#207): a saved Maya mode now starts completely when Blender opens.
- **Select > Similar with nothing selected** and other component commands Blender refuses now give Blender's message
  instead of a Python error.
- **Effects > Fire / Smoke with a fluid container selected**: the other selected meshes become the emitters instead of
  the command failing inside Blender.
- **Quad Draw behind many back faces** (#207): drawing keeps looking past stacked back faces to the first front face.
- **Pivot editing keeps the selection**: starting or ending a pivot edit in edge or face mode no longer selects
  extra components.

## [0.6.2] — 2026-10-28

Fixes and small additions for the reports after 0.6.1. Blender 4.5 LTS through 5.2.x (the last version for Blender 4.5).

### Fixed
- **G after an extrude** (#184): dragging the extrude manipulator and then pressing G extrudes the new selection
  again, like Maya, instead of rebuilding the first extrusion.
- **Switching back to Blender** (#185): after starting in the Maya layout, switching to Blender brings back the
  workspaces of your own startup file (read only, nothing is written) and shows the one you had open, without a
  restart.
- **Taller Time Slider** (#190): the frame numbers stay at the top in their normal size, the ticks grow only in the
  lower part and the current frame number stays at the bottom, as in Maya.
- **Attribute Editor sections** (#194): an open section draws its controls in a framed area that starts under the
  section arrow, so the hierarchy reads like Maya's Attribute Editor.

### Added
- **Shift+drag extrudes vertices** (#183): with vertices selected, Shift+drag on the Move / Rotate / Scale
  manipulator extrudes them like Maya, and the new vertices move with the drag (faces and edges already did).
- **Quad Draw corner fill** (#180): Tab+drag from a border vertex in an inner corner makes the quad from that vertex,
  its two border neighbours and the point under the mouse, with a preview while dragging.
- **Panels > Perspective > New** (#193): makes `persp1`, `persp2` … with the settings and starting place of the
  scene's persp camera, selects it, looks through it in that panel and lists it in the menu; one undo removes it.

## [0.6.1] — 2026-10-28

A small update to 0.6.0. Blender 4.5 LTS through 5.2.x.

### Fixed
- **Time Slider frame numbers** keep their size when the timeline is made taller and follow the UI scale instead
  (#179, pull request #188 by @LSKianhao).

### Added
- `CONTRIBUTING.md`: the ways to help (reports, "this feels different from Maya" notes, pull requests). Tests that
  need reference data a fresh clone doesn't have are reported as skipped instead of failing.

## [0.6.0] — 2026-10-28

The rigging release: joints, IK, skinning and constraints follow Maya 2026, a
rig made in the kit reaches a game engine and Maya 2026 the way a Maya rig does, and the reports that came in after
0.5.0 are fixed. Reference data (hotkeys, shelves, editor menus) now follows Maya 2026. Blender 4.5 LTS through 5.2.x.

### Added
- **Four View as four real panels** (#148): each panel has its own shading, Show menu, camera and menu bar like
  Maya's; Space taps between Four View and the panel under the mouse, the layout survives save / open, and switching
  to Blender folds it back to one view.
- **Joints move after placement** (#156, #160): with the Move tool an unskinned skeleton is edited like Maya's joint
  translate (children follow, every joint keeps its orientation; Preserve Children keeps the children where they are);
  the Channel Box shows the lead joint's Translate for typing. Skin > **Move Skinned Joints** moves joints of a bound
  skeleton without moving the mesh.
- **Skeleton menu with Maya's meaning** (#163): Insert Joints is a click-and-drag tool; Remove Joints, Disconnect
  Joint and Connect Joint (connect / parent mode) work like Maya's; Mirror Joints defaults to the XY plane.
- **Skinning methods** (#167): Classic Linear, Dual Quaternion and Weight Blended, chosen in the Bind Skin options or
  the Attribute Editor skinCluster tab (all three as in Maya 2026).
- **Bind Skin options** (#164): skinning method, dropoff rate, Maintain max influences and Closest in hierarchy;
  Mirror Skin Weights gets Normalize and works from component mode.
- **Spline IK Twist and Roll** (#166): the Spline IK handle is a selectable `ikHandleN` with Twist, Roll and Twist
  Type (Linear / Ease In / Ease Out / Ease In Out) in the Channel Box.
- **Constraint Interp Type and aim world up types** (#168): orient / parent constraints with several targets have
  Maya's Interp Type (No Flip, Average, Shortest, Longest, Cache) as a Channel Box drop-down; Aim has every Maya world
  up type and a World up object.
- **Joint display** (#165): the Channel Box shows a joint's Radius; Display > Local Rotation Axes and Display >
  Animation > Joint Size work.
- **UV Shell selection** (#172): RMB > UV > UV Shell, Select > Components > UV Shell or Alt+F12 select whole UV shells
  by click, box or lasso in the 3D View and the UV Editor (Shift / Ctrl / Ctrl+Shift as Maya).
- **UV Automatic history** (#150): the command leaves a polyAutoProj node in the Channel Box INPUTS and the Attribute
  Editor (Planes, Optimize, Percentage Space), editable afterwards and removed by Delete History.
- **Game Exporter as a window** (#154): File > Game Exporter stays open while you work, starts with Maya 2026's
  first-open presets per tab, and shows Maya's file-name hints and export errors.
- **Animation layers on joints** (#143): Create Layer from Selected / Add / Remove Selected take the picked joints, S
  keys joints (quaternion joints too) on the selected layer, and Bake Simulation bakes to BaseAnimation with the
  layers combined so the result looks the same as before baking.
- **Received Rigify rigs to the engine** (#145): FBX export writes only the deforming joints (re-chained through the
  DEF bones), Maya-safe names (no `FBXASC`), and leaves the metarig out; pick walk on Rigify controls follows the rig's
  hierarchy (upper_arm_fk.L ↑ → shoulder.L). New FBX options "Deforming Joints Only" and "Maya-Safe Names" (on).
- **Blend shapes next to deformers in FBX** (#144): in-between targets are written as Maya blendShape in-betweens
  (Maya 2026 reads `blendShape1` like its own FBX), and other deformers are paused while the file is written.
- **Dope Sheet keys from Maya 2026**: g frames the playback range, t centres the current time, h / j lock / unlock the
  selected channels.

### Changed
- **Joint orientation like Maya 2025+** (#161): the Joint Tool and Skeleton > Orient Joint orient with Maya's
  auto orient secondary axis; new joints have Segment Scale Compensate on and Maya's joint radius.
- **IK RP like Maya** (#162): a new RP handle gets a pole vector like Maya, Pole Vector X / Y / Z and Twist channels;
  Constrain > Pole Vector turns the plane to the target, and straight chains bend by their preferred angle like Maya.
- **Skin commands** (#164): Prune Small Weights, Set Max Influences, Go to Bind Pose and Mirror Skin Weights follow
  Maya 2026 (Mirror Skin Weights takes the closest surface point and writes only the selected destination vertices).
- **Pick walk order** (#165): arrows follow Maya's child order (Down = first child, Left / Right = siblings in
  creation order, wrapping), for joints and for objects.
- **Joint orientation the Maya way** (#141): a plain click on Orient Joint / Mirror Joints runs at once with the saved
  options (❒ opens the window); FBX joints carry Maya's jointOrient.
- **Constraints on child joints** (#142) move the joint like Maya: position constraints detach only that joint, and
  rotation-following joints get Maya's axes (a 90° offset is gone).
- **Game Exporter clips** (#140) are written as timeline takes: Maya scale, IK arms in place, only the clip takes in
  the file, and several clips in one file keep their own names and ranges.
- **Kit FBX back into the kit** (#144): File > Import of a kit FBX puts skinned meshes at the file's world position and
  sets the Time Slider to the take's range, like Maya.
- **Maya's vertex and face order** (#149): Create > Cylinder / Cube, Edit Mesh > Extrude and Edit Mesh > Bevel number
  their vertices, edges and faces like Maya 2026, so a cylinder → extrude → bevel chain matches Maya by index.
- **UV Automatic layout** (#150) uses Maya's "Into square" packing and "Fewer pieces" plane rule.
- **Auto tangents** (#151): keys the kit sets (S, Channel Box, Auto Key, scripts) get Maya 2026's auto tangents, and
  neighbouring keys are recomputed when a key is added or deleted.
- **Step Snap per tool** (#153): Move, Rotate and Scale keep their own Step Snap Relative / Absolute; Move offers
  Absolute only with World axes, like Maya.
- **Maya errors on wrong selections** (#152): commands run on a selection they don't apply to print Maya 2026's own
  error text (Bind Skin, constraints, Remesh / Reduce / Conform, Move IK to FK and more) instead of a Python error or
  nothing; cases Maya handles silently work silently.
- **Fresh-eye polish** (#155): F / A / Shift+F frame like Maya in perspective; Status Line snap toggles are no undo
  step; the Symmetry box opens its drop-down; the Maya layout views show no redo panel; the layout no longer re-flows
  after Four View or a dialog; a root joint's Translate shows its position and the Outliner names skeletons after
  their root joint.
- **Rig and animation polish** (#146): Enable IK Solver shows its check mark; the first Paint Skin Weights entry picks
  the first influence in hierarchy order; importing an animation FBX sets the Time Slider to the file's range; typing a
  value in the Set Driven Key window is no longer overwritten before Key.
- **Hotkeys, shelves and editor menus follow Maya 2026**: the Hotkey Editor lists Maya 2026's standard hotkeys;
  shelves have the 2026 tabs (Curves, Surfaces, UV Editing) and buttons; Graph Editor and Dope Sheet menu bars and icon
  rows follow Maya 2026.
- **Alt navigation with Emulate 3 Button Mouse** (#177): the preferences and the welcome dialog explain that Blender's
  Emulate 3 Button Mouse turns Alt+LMB into a middle drag (the kit never changes Blender preferences); the welcome
  dialog comes back once at the next start when it was closed without turning Maya mode on.

### Fixed
- **Shift+drag on the manipulator** runs Smart Duplicate / Smart Extrude again (it did nothing in 0.5.0) (#175, #183).
- **Hotbox** (#174): a click on a hotbox menu name opens the menu instead of running the row under the pointer (Edit >
  Cut deleted the selection), and a held Space keeps the hotbox up instead of cycling Four View.
- **UV Editor freeze and crash** (#172, #170): clicking faces, dragging a shell or Cut UV Edges on a large mesh froze
  Blender for seconds, and moving UVs in the UV Editing workspace could crash Blender.
- **Top menus not responding after install** (#170): the welcome dialog no longer opens over the menu bar.
- **Install error on Blender builds with Python 3.14** (some Linux distributions) (#176).
- **Rigify controls keep Pose mode** (#171): clicking a control no longer drops the rig into Object or Edit mode; a
  click just off a control clears the selection and stays in Pose, like Maya.
- **Show > Selection Highlighting** turns the highlight off (#173); Show > NURBS Curves also hides curve-shaped bone
  controls, and picking a control bone no longer highlights the meshes under the rig.
- **D pivot edit** grabs the manipulator at once (also the X / C / V snap holds), and another add-on that binds the
  same key no longer takes it from the kit in Maya mode (#178).
- **Skeleton menu and P with the Move tool** act on the joints you clicked, not their whole subtree; Set IK/FK Key also
  keys the handle's Twist and Pole Vector (#169).
- **Bevel on a cylinder cap rim** gives Maya's width (it was a sixth of it) (#124).
- **Delete History** also removes the kit's Extrude / Bevel history (the Channel Box INPUTS emptied like Maya) (#124).
- Step Snap stays off when the last grid / point snap is turned off; Circularize works from object mode; UV Pin works
  in edit mode; undo keeps the current time like Maya; the Game Exporter's default path exists; the Outliner stays fast
  with hundreds of objects (#147).

## [0.5.0] — 2026-10-27

The animation release. Blender 4.5 LTS through 5.2.x.

### Added
- **Joints feel like Maya objects** (PR #125 by @cnzim): clicking a joint selects that joint (Shift toggles,
  Ctrl removes, Ctrl+Shift adds), clicking another object or empty space releases the skeleton, Alt+D clears
  everything (Maya SelectNone), F8 switches a skeleton between joint editing and posing, Q/W/E/R finish Joint Tool
  placement and switch tools, and selecting a skeleton enters joint picking (Pose) directly.
- **Live Channel Box** while dragging the manipulator, and Channel Box wheel / trackpad scrolling that never changes
  values or moves the Layer Editor (PR #125 by @cnzim).
- **Paint Skin Weights workspace** in Tool Settings: influence list with sort / lock menus, brush, mask, flood that
  respects locks and the current operation, weight actions and display; Q/W/E/R leave painting with the mesh kept
  selected (PR #125 by @cnzim).
- Tool Box **Search** button under the layout / Outliner buttons, as in Maya 2022.1+ (PR #125 by @cnzim).
- **Rig controls from NURBS curves** (#136): parenting a curve shape to a joint draws it as the joint's control (clicks
  hit the drawn wire, exports leave the shapes out), Maya Wireframe Color / Drawing Overrides colour index, Match to a
  joint.
- **Constraints**: several targets blend as Maya's weighted average (#136); Normal / Tangent constraints, Remove
  Target, Set Rest Position, Modify Constrained Axis (#106); UV Pin / Proximity Pin (#112).
- **Set Driven Key** with Maya's auto tangents; a second driver adds to the first like Maya's blendWeighted (#136).
- **Blend shapes** (#137): Shape Editor in-between targets, combination targets (multiply / lowest / smooth) and
  corrective shapes; **Pose Space Deformation** with a Pose Interpolator on a joint's swing and a Pose Editor window.
- **Paint Skin Weights numbers** (#134 #126): Visualization > Numeric shows each vertex's weight; Brush Profile, Weight
  Type, Normalize Weights and Min / Max follow Maya 2026; a second Bind Skin asks Maya's question; the Skin Clusters
  list shows every skin on the mesh.
- **Skin tools**: Move Weights to Influences, the three Normalize Weights modes, Export / Import Weight Maps,
  Substitute Geometry, Bake Deformation to Skin Weights (#106); Add Influence with Maya's distance weights (#109).
- **Rig FBX round trip with Maya** (#132 #133): exports write joint orientation the way Maya does (joints and
  skinned vertices open in Maya 2026 where they were); imports rebuild Maya's curves, tangents, Euler keys and
  the frame range without converting the skeleton.
- **IK / FK switching** (#133): IK handles get Ik Blend; Set IK/FK Key, Enable IK Solver and Move IK to FK work like
  Maya. IK Spline can use an existing curve, and a cluster on curve CVs moves exactly those CVs (#129).
- **Quaternion bones** in received rigs show Maya's Rotate X / Y / Z in the Channel Box and key with S, Shift+E and
  Auto Key (#131).
- **Game Exporter** (#135): Maya's clip list, one FBX take per clip or one file per clip, the same defaults as Maya.
- **Motion Trail Editor** (#135) with Maya's settings, and **motion paths** (#138): Attach to Motion Path with Maya's
  offset keys, Set Motion Path Key, Flow Path Object, Loft with polygon output.
- **Preferences window and Hotkey Editor** (#121): Maya's categories with the kit's settings in Maya's pages;
  Maya's standard hotkeys with search and rebinding.
- **Component, Shape and Connection Editors** (#119) with Maya's menu bars: editable skin weights and vertex
  positions, blend shape targets, attribute connections as drivers.
- **Reference Editor** (#116): reload, unload / load, replace, import, remove, duplicate, lock, clean up and offline
  edits on Blender links, with Maya's reference node names.
- **Graph Editor** (#105 #110): Retime Tool, buffer curves, weighted tangents, Add Key Tool; Load / Add Selected
  Objects, Pin Channel, Show filters, Change Rotation Interp, Key Sync and Peak Removal.
- **Animation layers** (#111): Extract, Duplicate, Empty, Delete Empty Layers, Zero / Full Weight keys, Zero Key Layer,
  Merge Layers; several layers selected with their curves drawn in the Graph Editor.
- **Deform** (#112): Tension, Solidify, Sculpt, Morph and Jiggle deformers with Channel Box inputs, Attribute Editor
  tabs, option windows and Paint Weights; Display / Hide Intermediate Objects, Wrap influences.
- **UV Editor** (#113): Cycle, Split, Create Shell (Grid), Auto Seams, UV set commands and Maya's three heads-up
  displays. **Curves** (#114): Bend, Curl, Scale Curvature, Lock Length, CV Hardness, Fit B-spline, Align, Duplicate
  Surface Curves, Intersect.
- **Lights**: Ambient Light and Volume Light (#120).
- **Command Line / Script Editor** `maya.cmds` (#115 #122): parenting, grouping, keys, files, constraints, joints,
  connections, sets and more; Script Editor History options.
- **34 Maya option windows** for primitives, character sets, curves and UV commands (#103); Mesh > Cleanup with its
  Cleanup Options window (#104).

### Changed
- **Menus follow Maya 2026** (#130): renamed items, dropped items gone, new items open the Blender counterpart
  (Unsmooth, Smart Extrude, Zero Pivot, Bifrost Graph = Geometry Nodes ...) or explain what's missing.
- **Bake Simulation follows Maya 2026** (#128): constraints are muted, never deleted. The Joint Tool ends on the new
  chain's root and branches only from a joint clicked while it runs; picking a skeleton selects its root joint; pick
  walk skips hidden bone collections.
- **Paint Skin Weights**: flood uses Maya 2026's Replace / Add / Scale / Smooth with locks (#129), the Influences
  menu has Maya's items, Alt+F and Maya's paint keys work; the Channel Box keeps showing channels while painting.
- Reorder Deformers follows Maya's rule; Set Blend Shape Target Weight Keys keys the targets (#129).
- **Renders match Maya's brightness** (#120): lambert-family materials render like Maya Software; F12 adds the default
  light, like Maya.
- **Names and scenes like Maya** (#117): sets, layers, characters and bookmarks number one past the highest; Ctrl+V
  pastes `pasted__` copies under a new group; new scenes have Maya's hidden startup cameras; the Outliner lists
  objects in creation order; Attribute Editor tabs stay in one row.
- Docks are Maya's grey and the Time Slider's current-time cell looks like Maya's.
- Channel Box wheel scrolls 3 lines per notch.
- Select Priority off now only steps in for joint picking; other clicks are Blender's own pick.
- The armature mode picker and its highlight are optional (add-on preferences, off by default).

### Fixed
- Snapping works again after Step Snap Off; scenes saved in that state snap again (#139).
- The RMB marking-menu ring stays at the press point, so flicks pick the right item everywhere.
- Animation layer keys show in the Channel Box, Time Slider, Graph Editor and Dope Sheet.
- Non-Deformer History keeps the kit's wire and skin deformers; Delete removes constraint helpers; the Time Slider
  height follows the UI scale; the Channel Box menu bar wraps instead of cutting (#109).
- Morph / Jiggle deformers on Blender 5.2; Blender 5.x test passes (#107 #118).
- Stale Undo / Redo text in the result field; the Attribute Editor wraps instead of cutting (#104).
- Component highlight refreshes on selection changes Blender doesn't report to the depsgraph (PR #125 by @cnzim).
- Timers and watchers added by PR #125 no longer keep window / area references across ticks (closing a window could
  crash Blender, #36 class); the Channel Box redraws only when values change.
- Edit Mesh no longer lists "Split Faces by Edges" (not a Maya item; use Detach).

## [0.4.1] — 2026-10-25

A Maya parity release. Blender 4.5 LTS through 5.2.x. Quad Draw leftovers (#89) stay in
0.5.0.

### Added
- **Polygon primitives**: Pipe, Helix, Gear, Soccer Ball, Super Ellipse, Spherical Harmonics and Ultra Shape with
  Maya's geometry, names and Channel Box INPUTS.
- **Surfaces menu** on Blender NURBS surfaces: Loft, Revolve, Extrude, Birail 1, Boundary, Square, Attach, Detach,
  Insert Isoparms, Duplicate NURBS Patch, Reverse Direction, Rebuild, with Maya option windows.
- **UV Editor**: Map / Straighten Border, Match Grid, Layout Along, Stack Similar Shells, Distribute UVs; Back- /
  Front-Facing, Texture Borders, Non-Overlapping and Unmapped selection, Filter Connected / Contained, Isolate Add /
  Remove.
- **Light Linking**: Make / Break Light and Shadow Links, Select Objects / Lights, Light Linking Editor.
- **Animation Layers** on NLA tracks with the Layer Editor's Anim tab (Lock / Solo / Mute, Weight, Add to / Remove
  From Selected Layers, layered Auto Key).
- **Character Sets** on Keying Sets: create, add / remove members, merge, select, set current; S keys the current
  character; Time Slider character field.
- **Mesh Display**: Set Vertex Normal, Lock / Unlock Normals on the selection, Maya's Average and Set to Face, Apply
  Color, Rename / Modify Current Set, colour keys, Prelight with vertex bake sets, Select Shared Instances.
- **Status Line**: Construction History toggle (off = new primitives, extrusions and bevels keep no history node).
- Repeat Last (G) repeats menu, shelf, marking-menu and option-window commands too.

### Changed
- Component mode keeps the transform tool (Q / W / E / R) like Maya.
- Maya Time Slider ruler (ticks, labels, current frame) in the Maya layout.
- Selected faces / edges and manipulator planes look like Maya; four-view camera labels.
- The RMB marking menu list stays under the ring; near the window bottom the whole menu moves up.
- Undo / Redo show what they undid in the Command Line result field.
- Viewport panel Show menu: IK Handles and Image Planes work; more panel items explained or connected.
- Main UV > Delete UVs and nHair > Modify Curves Smooth / Straighten work like their twins elsewhere.

### Fixed
- Clicking a Maya menu item's option box (❒) opens its window (#82).
- Insert Isoparms' option box opens Maya's window instead of a generic one.
- Alt+RMB zoom in the UV / Image Editor works again (broken since the camera tools change).
- A quick marking-menu flick near the window bottom picks the direction you flicked, not the higher-drawn box.

## [0.4.0] — 2026-10-25

A Maya parity release. Blender 4.5 LTS through 5.2.x. Quad Draw leftovers (#89) move to
0.5.0.

### Added
- **Modeling tools** (#30 #31): Quad Draw, Create Polygon and Append to Polygon are Maya-style kit tools with Maya's
  clicks, modifier keys and Tool Settings; Insert Edge Loop inserts where you click, Offset Edge Loop drags two loops,
  Slide Edge slides with the middle mouse button.
- **Deform menu** (#34): Maya-like deformers (Lattice fitted around the selection, Delta Mush, Wrap, ShrinkWrap,
  Nonlinear with handles, Cluster, Soft Modification, Texture, Curve Warp, Wire with dropoff locators) with Maya option
  windows, Channel Box INPUTS attributes, Paint Weights on the deformer's own weights, Wire / ShrinkWrap / Lattice
  edit items, Prune Membership, Point On Curve; Export / Import Deformer Weights (Maya XML).
- **UV Editor shell tools**: Stack, Orient, Snap, Distribute, Normalize, Move and Sew, Create Shell, Delete UVs,
  Unstack with Maya's results; display keys, shell / texture borders, Ctrl+1 isolate, Move UV Shell.
- **Curves**: CV / EP Curve Tool, three / two point arcs, Rebuild, Attach, Detach, Cut, Fillet, Straighten, Move Seam
  with Maya's results.
- **Skeleton / skin**: joint labelling (Left / Right / types, Label pairs for mirroring), Enable / Disable IK Handles,
  closest-distance Bind Skin like Maya (#94).
- **Workspaces** (#81): Maya's standard workspaces (Maya Classic, Modeling, Sculpting, UV Editing, Rigging, Animation,
  Rendering) in Windows > Workspaces and the Status Line dropdown, Reset Current Workspace.
- **Render and display** (#101): the default light (like Maya) for kit renders, Render Sequence / Batch Render windows, Test
  Resolution, Batch Render in the background, Display > Grid options.
- **Visualize**: Create Animation Snapshot / Update Snapshot and Maya ghosting (Ghost Selected / Unghost Selected /
  Unghost All, Ghosting Editor) with Maya's frames, colours and opacity.
- **Modify menu**: Smooth Mesh Preview to Polygons keeps skinning, Default Object Manipulator, Align Tool, Position
  Along Curve, Geometry to Bounding Box, Evaluate Nodes.
- **Shelves and menus**: Ctrl+Shift+click adds a menu item to the shelf, double-click a shelf button opens its option
  box, shelves wrap into rows with Maya's scroll bar; Hypershade swatch middle-drag assigns a material; option windows
  for Toggle Show/Hide and Non-Deformer History.

### Changed
- **Option boxes open with a click** (#82): the ❒ part of a menu item opens the Maya window without a hold.
- **One undo step per Maya command, no Blender redo panel** (#86 #88 #92).
- **Channel Box** (#83 #85 #87 #95 #97): Maya's Channels / Edit menus on RMB anywhere in the Channel Box, rows that fit
  the narrow dock, Maya numbers (lattice Scale, light Intensity / Color), skinCluster names, SHAPES channels, component
  mode shows the shape and CVs; RMB node submenus (Inputs / Outputs / DG Traversal).
- **Graph Editor in Maya terms** (#96): Maya channel names, joint / blend shape nodes, highlight, scroll, View / Show
  items, Maya key commands (mute, select masks, default tangents), Maya selection modifiers in the Graph Editor, Dope
  Sheet, UV Editor and Outliner.
- **Marking menus and manipulators** (#98 #99 #100): Maya's ring size, Maya's extrude manipulator, no Blender tooltips
  on manipulators, no Blender report texts in the status bar; results go to the Command Line field.
- **Views**: Maya orthographic cameras and grid in the four-view layout, hierarchy highlight, one-column RMB list.
- **Parents act like Maya** (DAG): hiding a parent hides its children, Delete / Export Selection / Isolate take the
  hierarchy.
- Greyed menu items that work elsewhere under the same name now work everywhere.

### Fixed
- The selection wire follows skinned / simulated meshes while playing (#91).
- A new cube after Delete is pCube1 again (#93).
- Paint Skin Weights option window on Blender 5.x (#90).

## [0.3.0] — 2026-10-24

A Maya parity release. Blender 4.5 LTS through 5.2.x. Quad Draw, the
edge-loop tools and the Deform menu move to 0.4.0 (#30 #31 #34).

### Changed
- **Viewport looks like Maya without a theme** (#58 #59 #61 #75 #76): kit-drawn lead green / white selection,
  Maya component colours, Maya grid, no 3D cursor in the Maya layout, Maya Move / Scale manipulator axis colours and
  dark-blue dormant wireframe; no redo panel after display / mode keys; Smooth Mesh Preview shades smooth.
- **Dock and Channel Box** (#55 #60 #78): INPUTS collapsed until clicked, Layer Editor always visible, wheel scroll;
  Maya's vertical tab strip with a dock as narrow as Maya's (Channel Box) that widens for the Attribute Editor.
- **Marking menus** (#56 #62 #74): stay inside the window, 128 → 73 greyed entries (the rest explain why), Ctrl+RMB
  convert menu on meshes.
- **Animation / render** (#66 #67 #71): Graph Editor values in centimetres, Render Current Frame through the view
  camera or Maya's persp, Maya Blinn / Phong / light decay and render size defaults.
- **Scenes and files** (#57 #63 #64 #69): Save / Don't Save / Cancel on New Scene, the Maya layout after Open, tool
  settings kept across New / Open, FBX / OBJ / Alembic / USD round trips with Maya's axes, scale and names.
- **Edit Mesh / UV** (#16 #68 #70): Connect, Merge, Symmetrize and Smooth give Maya's results; Ctrl+B and Ctrl+E on
  edges / vertices act at once and stay editable; UV Automatic / Contour Stretch from object mode.
- **Maya option windows** (#32 #33 #35): 26 more windows with Maya 2022's fields and factory defaults (Create Joints,
  IK Handle, Bind / Unbind / Copy / Paint Skin Weights, Blend Shape, Parent, Cut / Copy / Paste / Delete / Snap / Scale
  Keys, Connect, Circularize, Make Hole, Insert Edge Loop, Aim / Pole Vector / Scale constraints, Duplicate Special);
  Aim aims +X with world up Y like Maya; Key > Scale Keys is new.
- **Keys and selection** (#65 #72 #73): Ctrl+A switches Attribute Editor / Channel Box in every mode, UV Editor
  Alt+RMB dolly, 13 Select / Ctrl+RMB conversions (Grow / Shrink Along Loop, perimeters, To Face Path, To UVs ...),
  joint names restart at joint1, Gravity / Newton fields with Maya magnitudes; an undo-depth hint (Blender keeps 32
  steps unless you raise it).
- **UI fit and icons** (#54 #77): the menu bar folds into » at 150 % UI scale, Set Driven Key fits, 485 more Maya menu
  icons.
- Store media, marketing images and clips retaken in Blender's own theme (#41).

### Fixed — reported by users
- Maya mode failed to switch on when another add-on's Render panel module had a non-list `classes` (#79).
- Double-click edge loop select raised an error in Blender 5.1 / 5.2 (#84).
- After extruding, Q / W / E / R bring the Move manipulator back; F12 no longer leaves UV sync on for F9–F11 (#80).

### Known issues
- Menu option boxes (❒) open on press-and-hold → Option Box, not on a click (#82, 0.4.0).
- Narrow dock truncates a few labels at 125 % (#85); Channel Box spacing at 150 % (#83); redo panel over the shelf
  after Create Joints (#86); Channel Box channel-name RMB shows Blender's menu (#87).

## [0.2.1] — 2026-10-21

A bug-fix and store-compliance release. Blender 4.5 LTS through 5.2.x.

**Thank you** to everyone who used the kit in real work and reported what felt wrong — most fixes below come from
those reports (labelled `user-report` on GitHub).

### Changed — store review (extensions.blender.org, #40)
- **Nothing outside the extension changes any more** (#40, #42, #43, #46): no theme is shipped or applied, Blender
  preferences and your active keymap are never written (Maya keys are add-on keymap items that disappear when Maya mode
  or the extension is off), no app template is copied into your scripts folder, no `exec` / `eval` or import hooks
  (scripts run as Text blocks through Blender's Run Script). Disabling or removing the extension is a plain unregister.
  Recommended theme / navigation settings are listed in the README instead.
- Alt+RMB dolly works without Blender's zoom preference (#51); Maya menu items that used to write preferences open
  Blender's Preferences instead (#43).
- Store tags: User Interface only.
- **Renamed to Maya Workflow Kit**: store / display
  name "Maya Workflow Kit" (no "Blender" in the store name), repository "Maya Workflow Kit for Blender"
  (`maya-workflow-kit-for-blender`), release zip `maya-workflow-kit-<version>.zip`, default project folder
  `Documents/Maya Workflow Kit/projects/default`. Unchanged: extension id `allset` (updates keep working), package
  `src/allset`, `allset.` / `ALLSET_` prefixes, tagline. README rewritten for GitHub.

### Fixed — reported by users
- Soft Select: middle-mouse drag changes the falloff radius, soft select is off by default (#1); vertices are coloured
  by influence (#2).
- Tool Box: double-clicking a tool opens its Tool Settings (#3).
- Torn-off panels open at a size that fits their content (#4).
- Marking menus no longer close while dragging or over the Time Slider (#5).
- Channel Box: drag over value fields to select channels; one typed value goes into all of them (#6).
- Layer Editor rows, V / P boxes, toolbar icons and tabs follow Maya (#7).
- Quick Layout: Single Perspective shows the perspective view; Four View back to persp works (#8).
- F frames with the camera you look through (#9).
- Viewport panel toolbar buttons toggle on and off and all do something (#10).
- Primitives show their creation INPUTS in the Channel Box (#11) and use Maya's topology (cap fans, Subdivisions
  Caps) (#12).
- UV Editor checker toggles off again (#13).
- Material colour changes show in shaded mode (#14).
- Double-click loop selection and "pick two, select the run between" for edges / vertices / faces (#22).
- **Icons**: every shelf button, Status Line / panel toolbar glyph, Tool Box tool, Layer Editor button and Outliner
  set / camera row is redrawn after Maya 2022's icons (kit-drawn, one picture per button, sharp at 100 / 125 / 150 %);
  190 Maya menu items show icons (#23).
- **Hypershade** opens as its own window in Maya's layout: Browser, Create, Material Viewer, Graph with Maya's toolbar,
  Property Editor (#25).
- Multi-Cut works like Maya's (click / drag points, Shift snap %, Ctrl loop cut, Backspace, RMB finish) (#27); tools
  have Maya Tool Settings (#28).
- Auto Key button (#37) and key ticks on the Time Slider (#38).
- Crash when closing an editor window opened from a Maya menu within 2 s (#36).

### Fixed — found by our own audit
- Soft Select shared between object and component mode (#15); Ctrl+D in component mode duplicates the object (#17);
  Delete History works in component mode (#18); Edit menu items work in component mode (#39).
- Switching Maya → Blender leaves no empty Maya strips (#19).
- Paint Skin Weights normalizes like Maya (#20).
- Torn-off Display menu: Hide / Show work (#21).
- Status Line IPR off restores the previous shading (#24).
- One Maya visibility: h, Channel Box Visibility and display layer V agree (#26).
- Select / Lasso / Paint Selection Tool Settings have Maya's sections (#29).
- Viewport background / selection colours without the kit theme (#45), Hypershade opening (#47), top-bar test and
  dogfood session after the store changes (#48, #49, #50).
- Blender 4.5 crashed on quit with the new Tool Box vector icons (fixed before release).
- Ctrl+N (New Scene) opens a new scene in the Maya layout again, like File > New Scene (#44).
- At 125 % UI scale, opening and closing Tool Settings no longer narrows the viewport (#53).
- The viewport panel toolbar folds the groups that don't fit into a Maya-style » menu, so every button is reachable at 125 % / 150 % (#52).

## [0.2.0] — 2026-10-19

The first version prepared for extensions.blender.org. Blender 4.5 LTS (4.5.x).

### Added
- **Navigate & Select**: framing in the visible part of the view (17), Maya mesh keys and convert selection (18), edit-mode
  selection through occluded elements and pre-selection (30, 74), selection priority (76), component pick-walk and
  axis lock (39), Move / Scale manipulator with Maya pivot editing (59, 77, 94), soft select and symmetry (36, 63),
  selection masks (93), snap holds (95).
- **Hotbox & Marking Menus**: menus kept inside the view (33), whole-window drawing and RMB fidelity (52), more
  marking menus (78, 94).
- **Channel Box & Attribute Editor**: text entry with `+=` / `*=` (38), joints and pose bones (55), constraints, Set
  Driven Key (62), extrusion history tab (65, 106), default material and shading groups (100), Maya docking model with
  tear-off panels and floating windows (116).
- **Menu Sets & Shelves**: every factory shelf button in its Maya slot (109), menu hotkeys in the labels (108), honest
  greyed items with notes (54, 101), Graph Editor / Dope Sheet / UV Editor / Hypershade / Render Settings / Script
  Editor menus (104, 105), Time Slider and Range Slider (20, 56, 73), Modeling Toolkit (63), Tool Settings (106), Maya
  top area (113), tear-off menus (116).
- **Maya concepts**: Maya length units (21), Smooth Mesh Preview (15), visibility (16), Combine / Separate / Mirror /
  Boolean (63), editable extrude history (65), UV tools (66, 79), render and look-dev (67), FX scale (68), projects and
  references (69), playblast (70), sets (96), file import / export (102), rigging (57, 58, 110).
- **Option windows** with the same defaults as Maya, Save / Reset Settings and Apply (103).
- **Listing package** (117): form fields, long description, media captions, technical
  disclosure, `docs/distribution/media/` (icon, featured image, six workflow screenshots; `tools/make_listing_media.py`).

### Changed
- **Opt-in**: enabling changes nothing until you choose Maya; no automatic preference saves; the layout template holds
  no code and is removed on disable (115). Maya | Blender switch (60).
- Supported Blender is now **4.5.x** (was 4.2.0 – 5.2.x): Blender 4.2.23 fails 25 of 869 headless tests and 5.0.1
  fails 19 (layered actions, layout template dock), so the manifest offers 4.5.0 – 4.5.x only until a 5.x update (117).
- Permission reason: "Layout template, settings backup, shelves, Maya project folders"; tag Rigging added (117).
- Extension guidelines: no `sys.modules` entries, CC0 assets, no `bl_info` in the extension build (114); the
  moderation ruff command passes on the extension source (117).
- **Renamed to Allset for Maya Users**: extension id `allset`, tagline "The whole Maya
  workflow in Blender, in one install", Python package `src/allset`, operator / class prefixes `allset.` /
  `ALLSET_`, app template `Allset` (an old `MayaKit` template install is removed), keymap "Maya-style", theme
  "Studio Grey (Maya-inspired)", Help > Blender Extensions; trademark notice in the README and the preferences.

## [0.1.0] — 2026-10-16

First release (Blender 4.2+, built and tested on Blender 4.5.4 LTS).

### Added
- **Packaging**: Blender extension `maya_kit` plus a legacy add-on zip from the same source
  (`tools/build.py`); `blender --command extension validate` passes; GPL-3.0-or-later `LICENSE`;
  `tools/release_check.py` (build → validate → clean-config install + enable → screenshot set).
- **Maya keymap**: "Maya" keyconfig generated from Industry Compatible data with Maya patches, Maya selection
  modifiers, 4/5/6/7 display modes, Ctrl+G group, keymap mapping document.
- **Hold / tap keys**: X/C/V/J snapping while held, D/Insert pivot editing, B soft select, A tap, arrow pick-walk.
- **Camera and view feel**: Maya navigation preferences preset with backup/restore, ortho tumble lock,
  Shift+F/Shift+A framing in all views, view undo, Space four views, 1/2/3 smooth preview, F7–F11 component modes.
- **Layout and theme**: Maya General layout application template, Maya grey theme.
- **Channel Box and Layer Editor**: multi-object editing, viewport MMB virtual slider, Channels menu,
  display layers on collections.
- **Top UI**: Maya menu bar and menu sets, Status Line, Python command line with a `cmds` shim, Help Line.
- **Marking menus** and **hotbox / marking menu engine**: Maya radial layouts, gestures, click mode,
  in-place submenus, option boxes; Space-hold hotbox.
- **Scene concepts**: Freeze Transformations (pivot kept), Reset Transformations, Center Pivot, Delete History
  and Delete (All) by Type, Maya-style parenting (P / Shift+P), Duplicate Special / with Transform, Maya creation names
  and defaults, optional Maya units.
- **Outliner and Attribute Editor**: sidebar Outliner (DAG, shapes, rename), Attribute Editor node tabs with
  Maya template sections, Ctrl+A dock toggle, Ctrl+Shift+A / Alt+D selection keys.
- **Shelf**: Status Line + Shelf strip, Maya's standard shelves as Blender operators, user Python shelves.

### Fixed (found by the clean-install release check)
- Installing and enabling from the command line left the first GUI start on the Blender keymap.
- Installing the layout in a brand-new config did not run the template's script until a restart, so loading the layout
  dropped the Maya keymap.

### Known limitations
- Things Blender only allows in C++ (Y-up, MMB-drag on fields, gizmo extension, new region types, Outliner tree drawing,
  timeline drawing, separate pivots, MEL) — see README "Limits".
