# Changelog

All notable changes to Maya Workflow Kit (called Allset for Maya Users in steps 111–124 and Maya Kit before step 111). Format: [Keep a Changelog](https://keepachangelog.com/), versions follow
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Fixed
- **Component shading after reopening Quad Draw files**: save native viewport settings instead of temporary
  Retopology overrides; restore each owned view on tool/mode/workspace changes and failed saves. Shading >
  Restore Modeling Display repairs the affected viewport in older files without editing the mesh or materials.
- **Quad Draw connections**: Shift previews use boundary edges and reject overlapping faces, skipped boundary
  vertices and non-manifold edges. Auto-weld previews vertex/edge targets while dragging, then welds the same targets
  on release, including Tab extensions. Escape cancels without merging; tolerance uses actual screen pixels.
- **Quad Draw drag preview**: dragging a vertex or dot no longer leaves its cyan hover marker at the original position.
- **Quad Draw**: activating the tool opens its options in the Modeling Toolkit. Retopology has a temporary cyan
  face tint with editable wire color, opacity and surface offset, without changing materials or the theme.
  Component drags keep their cursor offset and stay on the live surface when the cursor leaves its silhouette;
  view projection avoids jumping to hidden sheets during relax and extension. With no live surface, dots use the grid.
  Relax includes All Vertices, Auto-Lock keeps its choice for the stroke, and Extend distinguishes Loop from Border.

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
  compare against Maya reference data a fresh clone doesn't have are reported as skipped instead of failing.

## [0.6.0] — 2026-10-28

The rigging release (steps 230–270): joints, IK, skinning and constraints follow Maya 2026, a
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
  the Attribute Editor skinCluster tab (all three within 3.5e-6 of Maya 2026).
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
- **Joint orientation = Maya 2025+ factory** (#161): the Joint Tool and Skeleton > Orient Joint orient with Maya's
  auto orient secondary axis; new joints have Segment Scale Compensate on and Maya's joint radius.
- **IK RP like Maya** (#162): a new RP handle gets Maya's default pole vector, Pole Vector X / Y / Z and Twist channels;
  Constrain > Pole Vector turns the plane to the target, and straight chains bend by their preferred angle like Maya.
- **Skin commands** (#164): Prune Small Weights, Set Max Influences, Go to Bind Pose and Mirror Skin Weights follow
  Maya 2026 (Mirror Skin Weights takes the closest surface point and writes only the selected destination vertices).
- **Pick walk order** (#165): arrows follow Maya's child order (Down = first child, Left / Right = siblings in
  creation order, wrapping), for joints and for objects.
- **Joint orientation the Maya way** (#141): a plain click on Orient Joint / Mirror Joints runs at once with the saved
  options (❒ opens the window); FBX joints carry Maya's jointOrient (within 4e-5° of Maya 2026).
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
- **Hotkeys, shelves and editor menus follow Maya 2026**: the Hotkey Editor lists Maya 2026's 495 factory bindings;
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

The release after audits 14–16 and the animation chain (steps 192–228). Blender 4.5 LTS through 5.2.x.

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
- **Rig FBX round trip with Maya** (#132 #133): exports write joint orientation the way Maya does (joints open in
  Maya 2026 within 5e-6 cm, skinned vertices within 1e-6 cm); imports rebuild Maya's curves, tangents, Euler keys and
  the frame range without converting the skeleton.
- **IK / FK switching** (#133): IK handles get Ik Blend; Set IK/FK Key, Enable IK Solver and Move IK to FK work like
  Maya. IK Spline can use an existing curve, and a cluster on curve CVs moves exactly those CVs (#129).
- **Quaternion bones** in received rigs show Maya's Rotate X / Y / Z in the Channel Box and key with S, Shift+E and
  Auto Key (#131).
- **Game Exporter** (#135): Maya's clip list, one FBX take per clip or one file per clip, Maya's defaults.
- **Motion Trail Editor** (#135) with Maya's settings, and **motion paths** (#138): Attach to Motion Path with Maya's
  offset keys, Set Motion Path Key, Flow Path Object, Loft with polygon output.
- **Preferences window and Hotkey Editor** (#121): Maya's 38 categories with the kit's settings in Maya's pages;
  Maya's factory hotkeys with search and rebinding.
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
  connections, sets and more, checked against Maya; Script Editor History options.
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
- **Renders match Maya's brightness** (#120): lambert-family materials render like Maya Software; F12 adds Maya's
  default light.
- **Names and scenes like Maya** (#117): sets, layers, characters and bookmarks number one past the highest; Ctrl+V
  pastes `pasted__` copies under a new group; new scenes have Maya's hidden startup cameras; the Outliner lists
  objects in creation order; Attribute Editor tabs stay in one row.
- Docks are Maya's grey and the Time Slider's current-time cell looks like Maya's.
- Channel Box wheel scrolls 3 lines per notch (Maya: 15 px × 3 wheel lines).
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

The release after audits 12 and 13 (steps 173–190). Blender 4.5 LTS through 5.2.x. Quad Draw leftovers (#89) stay in
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

The release after audits 10 and 11 (steps 144–171). Blender 4.5 LTS through 5.2.x. Quad Draw leftovers (#89) move to
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
- **Workspaces** (#81): Maya's factory workspaces (Maya Classic, Modeling, Sculpting, UV Editing, Rigging, Animation,
  Rendering) in Windows > Workspaces and the Status Line dropdown, Reset Current Workspace.
- **Render and display** (#101): Maya's default light for kit renders, Render Sequence / Batch Render windows, Test
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

The Maya parity release after the eighth audit (steps 133–143). Blender 4.5 LTS through 5.2.x. Quad Draw, the
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

A bug-fix and store-compliance release (steps 125–132). Blender 4.5 LTS through 5.2.x.

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
- **Renamed to Maya Workflow Kit** (step 125, user decision — `docs/user_decisions.md` 12 revision): store / display
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
- Blender 4.5 crashed on quit with the new Tool Box vector icons (fixed before release, step 131).
- Ctrl+N (New Scene) opens a new scene in the Maya layout again, like File > New Scene (#44).
- At 125 % UI scale, opening and closing Tool Settings no longer narrows the viewport (#53).
- The viewport panel toolbar folds the groups that don't fit into a Maya-style » menu, so every button is reachable at 125 % / 150 % (#52).

## [0.2.0] — 2026-10-19

The first version prepared for extensions.blender.org (steps 14–117). Blender 4.5 LTS (4.5.x).

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
- **Option windows** with Maya 2022's factory values, Save / Reset Settings and Apply (103).
- **Listing package** (117): `docs/distribution/listing.md` (form fields, long description, media captions, technical
  disclosure), `docs/distribution/media/` (icon, featured image, six workflow screenshots; `tools/make_listing_media.py`).

### Changed
- **Opt-in**: enabling changes nothing until you choose Maya; no automatic preference saves; the layout template holds
  no code and is removed on disable (115). Maya | Blender switch (60).
- Supported Blender is now **4.5.x** (was 4.2.0 – 5.2.x): Blender 4.2.23 fails 25 of 869 headless tests and 5.0.1
  fails 19 (layered actions, layout template dock), so the manifest offers 4.5.0 – 4.5.x only until a 5.x update (117).
- Permission reason: "Layout template, settings backup, shelves, Maya project folders"; tag Rigging added (117).
- Extension guidelines: no `sys.modules` entries, CC0 assets, no `bl_info` in the extension build (114); the
  moderation ruff command passes on the extension source (117).
- **Renamed to Allset for Maya Users** (step 111, decision 12): extension id `allset`, tagline "The whole Maya
  workflow in Blender, in one install", Python package `src/allset`, operator / class prefixes `allset.` /
  `ALLSET_`, app template `Allset` (an old `MayaKit` template install is removed), keymap "Maya-style", theme
  "Studio Grey (Maya-inspired)", Help > Blender Extensions; trademark notice in the README and the preferences.

## [0.1.0] — 2026-10-16

First release (Blender 4.2+, built and tested on Blender 4.5.4 LTS).

### Added
- **Packaging** (step 1, 13): Blender extension `maya_kit` plus a legacy add-on zip from the same source
  (`tools/build.py`); `blender --command extension validate` passes; GPL-3.0-or-later `LICENSE`;
  `tools/release_check.py` (build → validate → clean-config install + enable → screenshot set).
- **Maya keymap** (step 2): "Maya" keyconfig generated from Industry Compatible data with Maya patches, Maya selection
  modifiers, 4/5/6/7 display modes, Ctrl+G group, keymap mapping document (`docs/keymap_mapping.md`).
- **Hold / tap keys** (step 3): X/C/V/J snapping while held, D/Insert pivot editing, B soft select, A tap, arrow pick-walk.
- **Camera and view feel** (step 4): Maya navigation preferences preset with backup/restore, ortho tumble lock,
  Shift+F/Shift+A framing in all views, view undo, Space four views, 1/2/3 smooth preview, F7–F11 component modes.
- **Layout and theme** (step 5): Maya General layout application template, Maya grey theme.
- **Channel Box and Layer Editor** (step 6): multi-object editing, viewport MMB virtual slider, Channels menu,
  display layers on collections.
- **Top UI** (step 7): Maya menu bar and menu sets, Status Line, Python command line with a `cmds` shim, Help Line.
- **Marking menus** (step 8) and **hotbox / marking menu engine** (step 9): Maya radial layouts, gestures, click mode,
  in-place submenus, option boxes; Space-hold hotbox.
- **Scene concepts** (step 10): Freeze Transformations (pivot kept), Reset Transformations, Center Pivot, Delete History
  and Delete (All) by Type, Maya-style parenting (P / Shift+P), Duplicate Special / with Transform, Maya creation names
  and defaults, optional Maya units.
- **Outliner and Attribute Editor** (step 11): sidebar Outliner (DAG, shapes, rename), Attribute Editor node tabs with
  Maya template sections, Ctrl+A dock toggle, Ctrl+Shift+A / Alt+D selection keys.
- **Shelf** (step 12): Status Line + Shelf strip, Maya factory shelves as Blender operators, user Python shelves.

### Fixed (found by the clean-install release check, step 13)
- Installing and enabling from the command line left the first GUI start on the Blender keymap.
- Installing the layout in a brand-new config did not run the template's script until a restart, so loading the layout
  dropped the Maya keymap.

### Known limitations
- Things Blender only allows in C++ (Y-up, MMB-drag on fields, gizmo extension, new region types, Outliner tree drawing,
  timeline drawing, separate pivots, MEL) — see README "Limits".
