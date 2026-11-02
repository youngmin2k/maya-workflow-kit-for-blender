# Release notes 0.10.0 (GitHub release)

Text for the GitHub release of v0.10.0. Full list: the 0.10.0 section of `CHANGELOG.md`.

---

**0.10.0 — a fuller UV Toolkit, Auto Key and Channel Box work on components, a calmer Graph Editor, and the fixes from your reports** (Blender 5.2 LTS)

Install it over 0.9.0 as usual; shelves, hotkeys, scenes and the kit's settings are kept. (Removing the kit before
installing deletes them: use Export Settings first.)
Supported: Blender 5.2 LTS. Other versions are not tested: the extension still installs on Blender 5.0 and 5.1,
but they may have problems. For Blender 4.5 LTS keep using 0.6.2.

## UV editing

- Every UV Toolkit button now works: Select By Type (Back-Facing, Front-Facing, Overlapping, Non-Overlapping,
  Texture Borders, Unmapped), all Create, Cut and Sew and Arrange and Layout commands with their option boxes,
  Align Min / Avg / Max, Unfold Along U / V, Straighten UVs with U / V buttons and an angle tolerance, Stack Similar
  (#264).
- UV Edge and UV Face selection apart from the mesh; in the UV Editor a double-click selects a UV edge loop,
  Ctrl+double-click an edge ring, a double-click on a UV or UV face its shell (#264).
- Pre-selection for single UVs, UV edges and UV faces, not only whole shells; in UV mode the 3D View shows only
  the vertices of the picked UVs as selected; no face centre dots in UV mode (#264).
- Maya-style Move / Rotate / Scale handles in the UV Editor: U / V arrows, a rotate ring, U / V scale boxes at the
  centre of the selected UVs (#264).
- Ctrl+Up / Ctrl+Down change the checker density (#264).
- Straighten UVs and Randomize Shells work like Maya; with several meshes in edit mode the UV commands keep to the
  shells you picked (#264).

## Animation and the Channel Box

- Auto Key on points: moving keyed points in component mode keys them on the axes that changed; the Time Slider
  shows the keys of the selected points (#272).
- blendShape weights go into animation layers, character sets and Set Driven Key; their keys show in the Time
  Slider (#271).
- Click the name at the top of the Channel Box to rename the object (#283).
- Channel Box middle-drag follows the selected Translate axis on screen; Rotate turns 0.36 degrees per pixel (#273).
- Custom attributes change by 0.1 per pixel when middle-dragged from the Channel Box, like Maya.
- Lattice points in the Channel Box CVs table, and the Maya manipulator for curve and surface CVs (#274).
- Auto Key keys only values that change while it is on (#276).

## Graph Editor

- Bigger keys and tangent handles (the Key Size preference; 0 = Blender's own), a toolbar that folds into a » menu
  when the editor is narrow, and a picture of its own for every toolbar button (#277).
- Scale Keys box: Shift+drag on a corner scales in time or value only, a drag inside moves the keys; w / e / r work
  anywhere over the Graph Editor; a snapped key move is one undo (#270).
- Blender's own Insert Keyframe gets the Default In / Out Tangent too (#267).

## Modeling

- Transform Constraint: Along Normals (#262), and Surface follows the Move handle you drag (#280).
- Box and Lasso select pick joints with nothing selected (#276); points of a bent lattice are picked where you see
  them (#274).
- Bevel at box corners with tilted faces and at three-edge corners follows Maya in more cases (#213).
- Bevel with Segments 2 or more: round profiles at any face angle, Depth like Maya, and box corners closed with one
  polygon (#213).
- Bevel options: Offset space (World) and Chamfer, like Maya's Bevel Options; long absolute offsets slide past
  short edges like Maya (#213).
- Type Manipulator: pick single characters of a type and move, rotate or scale them (#258).

## Layout, keys and rendering

- IPR opens its own render window, like Maya's IPR render window (#277).
- Save your own workspaces: Windows > Workspaces > Save Current Workspace As..., Reset, Delete (#277).
- Shift+drag on the manipulator shows "Shift Duplicate" / "Shift Extrude" (#277).
- Numpad digits work like the top row, numpad + / - size the manipulator (#283); Assign Existing Material lists the
  scene's materials in the marking menu (#283).
- Other add-ons' top-bar menus and toolbar tools stay in reach in Maya mode (#221).

## Fixed

- Switching from Maya mode back to Blender no longer leaves Maya panels in Blender's Sculpting, UV Editing and
  Animation workspaces (#282).
- No TypeError from the kit's timers while Preferences or another temporary window is open (#281).
- Hotkeys imported with Maya mode off are applied when Maya mode starts (#275).
- Mesh > Booleans work with three or more objects selected: the first object meets all the others, like Maya
  (#284).
- Help menus open the Blender 5.2 manual.

## Known differences

- Bevel: corners where the faces' angles differ strongly (the new corner can sit up to a few percent of the bevel
  width away), corners whose third edge leans far over and three-edge corners whose face angles differ by more than
  about 10% still differ from Maya (#213). With Segments 2 or more, corners of three or more bevelled edges where a
  face holds an unbevelled edge at a sharp tip differ too.
- The known differences listed in `CHANGELOG.md` still apply.

## Thank you

Thanks for the reports and ideas: @Fizkefaaz (#270, #271, #272, #273, #274, #283), @LoongVeeng (#264),
@swarnava05 (#277), @dillanjmurillo (#276), @Marlon90 (#262), @meggaimg70-a11y (#267), @rethink-studios (#275),
@martin8762 (#221), @GUYVERZERO (#280), @DAI3rd (#281), @Dark2774 (#282), @slacer (#284) and @gsvetlin-beep (#258).
Please keep telling us what breaks or feels off in real work.

Maya Workflow Kit is a free, personal open-source project: no paid version, no donations requested, and no commercial
goal behind it.

Autodesk and Maya are registered trademarks or trademarks of Autodesk, Inc. This extension is not affiliated with or
endorsed by Autodesk, Inc.
