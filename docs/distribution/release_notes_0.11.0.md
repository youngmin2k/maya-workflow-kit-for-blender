# Release notes 0.11.0 (GitHub release)

Text for the GitHub release of v0.11.0. Full list: the 0.11.0 section of `CHANGELOG.md`.

---

**0.11.0 — Trax Editor clips, Maya's UV Editor marking menus, camera rigs, a Maya / Blender keyboard switch, your own translations, and the fixes from your reports** (Blender 5.2 LTS)

Install it over 0.10.0 (or 0.8.0 / 0.9.0) as usual; shelves, hotkeys, scenes and the kit's settings are kept. (Removing
the kit before installing deletes them: use Export Settings first.)
Supported: Blender 5.2 LTS. Other versions are not tested: the extension still installs on Blender 5.0 and 5.1,
but they may have problems. For Blender 4.5 LTS keep using 0.6.2.

## New

- Trax Editor and animation clips on Blender's NLA: Create > Animation Clip, Insert Clip, Clip Library, Duplicate,
  Split, Trim, Blend and the other Trax menu items (#287).
- UV Editor Shift+RMB marking menus like Maya's, for UVs / edges / vertices, UV shells and faces (#298).
- Create > Cameras > Camera and Aim / Camera, Aim and Up: the camera, its aim and up nodes in camera1_group (#299).
- Keyboard: Maya / Blender in the add-on preferences and the Hotkey Editor: keep the Maya layout, menus and tools with
  your Blender keymap (#309).
- Time for new scenes: File > New Scene and Ctrl+N start at the fps you pick, like Maya's New Scene Options (#308).
- Click a manipulator handle to make it the active handle, then middle-drag anywhere (#304).
- The kit's own Rotate manipulator, resized with = / - like Move and Scale (#283).
- RMB marking menu in Sculpt Mode; middle-drag a camera from the Outliner onto a view to look through it (#294).
- Your own translations: write a template of every kit text and drop `<language code>.json` files in the
  translations folder; the kit follows Blender's interface language (#293). Japanese menu terms follow Japanese Maya
  (#286).

## Fixed

- Alt+LMB stopped tumbling after a ViewCube click or after pressing Alt again mid-tumble (#288).
- Alt+RMB dolly follows Invert Zoom Direction (#295).
- Space tap no longer splits the view again and again on high-DPI screens (#302).
- Switching to Blender after File > New Scene in Maya mode no longer mixes Maya and Blender tabs (#307).
- View > Select Camera works in scenes made in Blender mode (#297).
- No empty strip between the Status Line and the Shelf when the window is maximized (#305).
- Cut UVs shows the cut edge as a border right away (#298).
- Joints stay visible after switching workspaces (#289); the Outliner button docks the Outliner instead of opening a
  new window (#290); hair under a parent hidden with Blender's eye shows up (#291).
- Edit-mode vertices keep their size on Vulkan and Metal.
- G keeps the last modeling command after display and selection changes (PR #279); local Bevel is much faster on
  large meshes (PR #300).

## Known differences

- Graph Editor: a non-weighted tangent keeps Maya's curve shape, but Blender draws the handle at its real point, so
  it looks longer when turned steeply (#296).
- The known differences listed in `CHANGELOG.md` still apply.

## Thank you

Thanks for the pull requests: @youngmin2k (#279, #300) and @onlykshitij (#304, #306). Thanks for the reports and ideas:
@Fizkefaaz (#283, #291, #297), @DAI3rd (#286, #287, #299, #305, #307, #308), @Adrian-Jansen (#288), @zzador (#289,
#290), @Banditik777 (#293), @andych56 (#294), @meanGoreng (#295), @meggaimg70-a11y (#296), @Bit-Nugget (#298),
@showtime56521 (#302) and @TomerM7 (#309). Please keep telling us what breaks or feels off in real work.

Maya Workflow Kit is a free, personal open-source project: no paid version, no donations requested, and no commercial
goal behind it.

Autodesk and Maya are registered trademarks or trademarks of Autodesk, Inc. This extension is not affiliated with or
endorsed by Autodesk, Inc.
