# Release notes 0.9.0 (GitHub release)

Text for the GitHub release of v0.9.0. Full list: the 0.9.0 section of `CHANGELOG.md`.

---

**0.9.0 — FX and rendering on Blender's own features, keys on components and blend shapes, and the fixes from your reports** (Blender 5.2 LTS, also 5.0 / 5.1)

Install it over 0.8.0 as usual; shelves, hotkeys, scenes and the kit's settings are kept. (Removing the kit before
installing deletes them: use the new Export Settings first.)
For Blender 4.5 LTS keep using 0.6.2.

## FX and rendering now run Blender's own features

Maya Workflow Kit keeps building modeling, animation, rigging, UV and texturing the Maya way. For FX and rendering
the Maya menus stay where you look for them, and each item now runs **Blender's own** simulation, light or render
feature (or opens the Blender editor for it). Items Blender has nothing for are greyed, and their tooltip says what to
use instead. Every item is listed in [Maya FX and Rendering in Blender](../fx_render_concepts.md).

- Render > Render Current Frame / Render Sequence, the Status Line and Render View buttons run Blender's Render Image /
  Render Animation through the scene camera (a scene needs a camera, like any Blender render). F12 / Ctrl+F12 are
  Blender's render keys again; F12 over the 3D View and the UV Editor stays Maya's UV selection mask.
- Light linking is Blender's light linking (Make = Include, Break = Exclude, on the active light); the Light Editor
  is an Outliner that lists the lights, Render Settings opens Blender's Render properties.
- nCloth, nParticles, rigid bodies, fields, fluids and effects add Blender's Cloth / Collision / particle / rigid body
  / force field / Quick Smoke setups to the selected objects.
- **Removed** with this change: the default light for renders without lights, Batch Render in a background Blender,
  the Test Resolution preference, Ambient and Volume Lights, the kit's own Light Editor and Render Settings windows,
  multi-light linking rules, the nucleus tab and the FX unit scaling, and a few kit-only FX items (greyed with a note).

### FX in the centimetre layout

Blender simulates one unit as one metre, and the kit no longer rescales gravity, cloth, collisions, particles or
fields. In the Maya Workflow Kit layout (centimetres, 100 units = 1 m) a 100-unit cube is a 1 m cube to the
simulation, so small objects fall and fold like small real objects. For FX work, model at metre scale, or simulate in
a metre scene (Blender's own startup scene, or the **Maya Units** preference off).

### Files saved with older versions

Opening a file saved with 0.8.0 or earlier tidies it once: the hidden `persp` render camera and a leftover
`defaultLight` are removed, the World's "Maya Ambient" nodes are taken out, old Ambient / Volume Lights become point
lights with the same intensity, a Light Editor Isolate left on is undone, a scene gravity the kit had scaled goes back
to Blender's 9.81 (unless you changed it by hand) and kit nCloth stiffness / damping lose their rescale. Save the file
to keep the tidied state.

## Added
- Set Key on components: S in component mode keys the selected vertices, CVs, Bezier points and lattice points (#272).
- Blend shape target weights in the Channel Box INPUTS are channels: select, key, mute and copy / paste them (#271).
- Graph Editor Scale Keys manipulator: a box with handles around the selected keys scales them in time and value (#270).
- Edge / Surface slide with the Move tool: Ctrl+Shift+middle-drag, and the Move tool's Transform Constraint (#262).
- UV shell pre-selection: the shell under the mouse is highlighted while clicks pick whole shells in the UV Editor (#264).
- Type in the Attribute Editor (text, font, size, alignment, extrude, bevel) (#258); polyCylinder Height Baseline,
  Create UVs and Round Cap Height Compensation (#259).
- More Fields/Solvers items (#123).
- Export / Import Settings: save the kit preferences (option window values included), the hotkeys you changed, your
  shelves and your marking menus to one file, and load them after a reinstall, in a new Blender or on another
  computer (Preferences > Add-ons > Maya Workflow Kit, the kit's Preferences window, the Hotkey Editor) (#275).

## Fixed
- Dragging keys in the Graph Editor with Auto Key on no longer adds a stray key; one undo takes the drag back (#270).
- Non-weighted tangents only turn while you drag them, like Maya (#267).
- Joints and bones inside a mesh show again in wireframe and X-Ray views (#266).
- Smart Extrude / Smart Duplicate on Linux and macOS extrude every time (#265).
- Project autosave writes its copy in the Maya layout too; Auto / Clamped / Plateau tangents keep Maya's shape after
  an edit there.
- Channel Box middle-drag goes back to the tool after a tool change; click empty space to deselect channels (#273).
- Lattice points get the Maya manipulator in edit mode (#274).
- Every Scale handle stops at zero in component mode (#261); edit-mode vertices follow the theme Vertex Size and a
  component pivot no longer sticks in Object Mode (#263).
- The kit's tooltips follow the interface language too (Japanese, Simplified Chinese).

The known differences listed in `CHANGELOG.md` still apply.

## Thank you

Thanks for the reports and ideas: @Fizkefaaz (#270, #271, #272, #273, #274), @gsvetlin-beep (#258, #259),
@XeonG (#261), @Marlon90 (#262), @andych56 (#263), @LoongVeeng (#264), @CommonDirt (#265), @zzador (#266),
@meggaimg70-a11y (#267), @rethink-studios (#275) and @RIPTIDE-z for spotting the untranslated tooltips (#260).
Please keep telling us what breaks or feels off in real work.

Maya Workflow Kit is a free, personal open-source project: no paid version, no donations requested, and no commercial
goal behind it.

Autodesk and Maya are registered trademarks or trademarks of Autodesk, Inc. This extension is not affiliated with or
endorsed by Autodesk, Inc.
