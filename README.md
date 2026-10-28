<div align="center">

# Maya Workflow Kit for Blender

### for Maya users, in Blender

**The whole Maya workflow in Blender, in one install.**

[![Blender 4.5 – 5.2](https://img.shields.io/badge/Blender-4.5%20LTS%20%E2%80%93%205.2-5285a6)](#requirements)
[![License: GPL-3.0-or-later](https://img.shields.io/badge/license-GPL--3.0--or--later-blue)](LICENSE)

![Maya Workflow Kit — for Maya users, in Blender. The whole Maya workflow in Blender, in one install.](docs/distribution/marketing/kit/readme_hero.png)

</div>

**The tutorial ends. Your Channel Box comes back.**

Maya Workflow Kit is a free, open-source Blender extension for people who learned 3D in Maya. It brings the Maya
workflow to Blender — hotbox and marking menus, Channel Box and Attribute Editor, menu sets, shelves and option
windows, Maya-style navigation and selection, and Maya scene concepts such as Freeze Transformations, Delete History,
groups, centimetres and `pCube1` — rebuilt on top of Blender's own tools. **Installing it changes nothing until you
choose Maya**, and one click on the Maya | Blender switch gives you plain Blender back whenever a tutorial uses
Blender's own keys.

▶ **[Watch the half-minute tour (MP4)](docs/distribution/marketing/clips/00_trailer.mp4)** · [Website](https://5hyuns.github.io/maya-workflow-kit-for-blender/) <!-- live once the repository is public and Pages is enabled -->
· [Install](#installation) · [Quick start](#quick-start-for-maya-users) · [FAQ](#faq)

📥 **Free download:** [Blender Extensions](https://extensions.blender.org/add-ons/allset/), or in Blender: *Edit → Preferences → Get Extensions* → search "Maya Workflow Kit"

---

## 👋 Hi, a quick note from me

I spent years in Maya. When I finally tried to move to Blender, the software wasn't really the problem. My hands
were. I'd hold Space and nothing would pop up, I'd look for the Channel Box that wasn't there, and every few minutes
I'd catch myself reaching for a shelf. I made this hoping that people like me, who are used to Maya, can settle into
Blender a little more easily.

To be honest, it's still rough in places. Some Maya tools aren't there yet, and some don't feel quite right. I use it
myself and I'll keep improving it, but I can only fix what I know about. So if something breaks, feels off, or you
miss a Maya feature you use every day, please [leave an issue](https://github.com/5hyuns/maya-workflow-kit-for-blender/issues/new).
Even a one-liner helps a lot. Want to help in other ways? Anything goes — see [CONTRIBUTING.md](CONTRIBUTING.md).

Thanks for giving it a try 🙂

---

## Contents

- [Features](#features)
- [Known limits](#known-limits)
- [Installation](#installation)
- [First run: turning Maya mode on and off](#first-run-turning-maya-mode-on-and-off)
- [Recommended setup](#recommended-setup)
- [Quick start for Maya users](#quick-start-for-maya-users)
- [FAQ](#faq)
- [Development](#development)
- [Credits](#credits) · [License](#license) · [Trademarks](#trademarks)

---

## Features

Everything below is in the current version. Maya menu items that Blender cannot do are still shown — greyed, with a
one-line note saying why and what to use instead.

### Look & layout

- **Maya layout**, added to the open file as workspaces when you choose Maya: menu bar, Status Line, Shelf, Tool Box,
  Outliner, Channel Box / Layer Editor tab stack, Time Slider and Range Slider, Help Line and Command Line.
- **Maya's docking**: Channel Box, Attribute Editor and Modeling Toolkit share one tab stack next to the viewport and
  tear off into floating windows by their `:::::` handle; Outliner and Tool Settings dock on the left.
- The Maya **Move / Scale manipulator**.
- **Alt+B** cycles the background of every 3D view through Maya's solid background colours.
- The kit uses your own Blender theme; see [Recommended setup](#recommended-setup) for a Maya-like look.

### Navigation & selection

- **Alt + LMB / MMB / RMB** tumble, track and dolly; **F / A** frame selected / all in the visible part of the view;
  **Shift+F / Shift+A** in all views; **`[` `]`** view undo / redo; **Space** tap toggles one view / four views.
- **Q W E R T Y** tools (Y = last non-QWERT tool), Maya selection modifiers (Shift toggles, Ctrl deselects, Ctrl+Shift
  adds), **F8** object / component toggle, **F9–F12** vertex / edge / face / UV.
- Pre-selection highlight, edit-mode box select through occluded elements, selection priority, arrow-key **pick-walk**
  (edge loops / rings, joints), soft select and symmetry.
- **Hold keys**: **X / C / V** snap to grid / edge / vertex while held, **J** step snap, **D / Insert** toggle pivot editing (**D** can also be held temporarily),
  **B** soft select.

![Edit the pivot, snap with V](docs/distribution/marketing/gif/05_pivot_snap.gif)

*Insert edits the pivot; hold V while dragging and it snaps to a vertex. Insert again, and the object rotates around its new pivot.*

During pivot editing, click a vertex, edge or face to snap and align the pivot.
Shift-click changes position; Ctrl-click changes orientation.
See [custom pivot editing](docs/pivot_component_picking.md) for the full controls.

### Hotbox, marking menus & menu sets

- **Space-hold hotbox** with every menu of the current menu set, Recent Commands and the marking-menu zones.
- **Right-click, Shift+right-click and Ctrl+right-click marking menus** over objects and components, in Maya's radial
  positions, with gestures, click mode, submenus and option boxes; **Q / W / E / R + LMB** tool option menus;
  **Shift+Q / Alt+Q / Shift+S** hold menus.
- **Menu sets** Modeling / Rigging / Animation / FX / Rendering on **F2–F6**, Maya's menu order and names, Maya hotkeys
  shown in the menus, dotted tear-off lines.
- **Option boxes (❒)** open Maya option windows with Maya 2022's factory values — Save Settings, Reset Settings, Apply
  and the command button; a plain click then uses your saved values.
- **Shelves**: the factory shelves (Polygons, Rigging, Animation, Rendering, FX …) with every button in its Maya slot,
  plus your own Python shelves.

![Hold Space for the hotbox](docs/distribution/marketing/gif/01_hotbox.gif)

*Tap Space to toggle one view and four views; hold Space for the hotbox. Here: Select > All, straight from the hotbox.*

![Right-click marking menus](docs/distribution/marketing/gif/02_marking_menu.gif)

*Right-click over an object for its marking menu in Maya's positions: drag to Vertex for component mode, right-click again for Object Mode.*

### Channel Box & editors

- **Channel Box / Layer Editor**: Translate / Rotate / Scale / Visibility of every selected object, SHAPES and INPUTS
  (history), keyed / locked / driven colours, `+=5` and `*=2` entry, middle-drag virtual slider in the viewport for
  selected channels, Channels menu and right-click menu, display layers.
- **Attribute Editor** with Maya's node tabs and sections (transform, shape, history, material, shading group) and
  Notes; **Ctrl+A** toggles Channel Box ↔ Attribute Editor.
- **Outliner** with Maya's Display / Show menus (DAG hierarchy, Shapes toggle), sets and Maya's default rows.
- Maya menu bars in the **Graph Editor, Dope Sheet, UV Editor, Hypershade, Render Settings and Script Editor**; a
  **Tool Settings** dock; the **Modeling Toolkit**.
- **Command Line** and **Script Editor** run Python with a small `maya.cmds` look-alike (e.g. `cmds.polyCube()`,
  `cmds.move(5, 0, 0)`).

![Key it in the Channel Box](docs/distribution/marketing/gif/03_channel_box_keys.gif)

*S keys every channel and the Channel Box turns red; type `+=90` into Rotate Z, right-click › Key Selected, then scrub the Time Slider.*

### Modeling & UV

- **Maya creation defaults**: Maya names (`pCube1`, `pCubeShape1`, `group1`, `polySmooth1`), Maya sizes in
  centimetres, a default `lambert1` material; optional **Maya Units** preference (1 Blender unit = 1 cm).
- **Maya concepts**: Freeze Transformations (channels back to 0 / 0 / 1, pivot kept), Reset Transformations, Center
  Pivot, Delete History and Delete by Type, Maya-style parenting (**P / Shift+P** keep the Channel Box values),
  **Ctrl+G** groups, Duplicate Special.
- **Smooth Mesh Preview** on **1 / 2 / 3**, display modes on **4 / 5 / 6 / 7**.
- Mesh tools including Combine / Separate / Mirror / Boolean, extrude with editable history, **Ctrl+B** Bevel,
  Circularize, Connect and Make Hole, Maya's convert-selection rules.
- **UV**: Cut / Sew UV Edges, 3D Cut and Sew, Unfold, Layout, UV shell selection, Maya UV Editor menus and UV Toolkit.

### Animation

- **S** sets a key on every keyable channel; **Shift+W / E / R** key translate / rotate / scale.
- **Time Slider** with key ticks and **Range Slider**; **K**-drag to scrub; **, / .** previous / next key;
  **Alt+V** play; Time Slider bookmarks.
- **Graph Editor** with Maya menus and the tangent toolbar (Spline, Linear, Clamped, Stepped, Flat …), **Shift+S**
  tangents marking menu, **I** insert-key tool.
- **Auto Key** and **Playblast**.

![Navigate the Maya way](docs/distribution/marketing/gif/04_navigation.gif)

*Alt + left drag tumbles, Alt + middle drag tracks, Alt + right drag dollies; click an object and press F to frame it, A to frame everything.*

### Rigging

- **Joint Tool**, **IK Handle** and IK Spline, joint pick-walk, Reroot and Preferred Angle.
- **Bind Skin** and **Paint Skin Weights** (influence list, Replace / Add / Scale / Smooth), Hammer weights.
- **Set Driven Key**, constraints, Cluster and Soft Modification.

![Joints, IK and skin weights](docs/distribution/marketing/gif/06_rigging.gif)

*From the Rigging shelf: Create Joints by clicking, an IK Handle from shoulder to wrist, Bind Skin, pull the handle, then Paint Skin Weights.*

### Rendering & FX

- **Hypershade** menus and Browser tabs, Maya shader types with their Attribute Editor sections, shading groups.
- **Render Settings** window with Maya's Common tab; Rendering menu set (Render Current Frame, Keep Image in the
  render view).
- **FX** menu set with Maya's simulation scale: nucleus gravity, nParticles emitters, nCloth.

### Scene & files

- **Maya projects**: Set Project / Project Window; file dialogs start in the current project's folders (default
  project `Documents/Maya Workflow Kit/projects/default`).
- **Ctrl+S / Ctrl+Shift+S** save in the project's scenes folder; **Ctrl+Alt+S** increment and save the Maya way
  (`shot_v001` → `shot_v001.0001`).
- **Ctrl+R** Create Reference: links a `.blend` with a library override and `namespace:name` naming.
- **File > Import / Export** with Files of type (FBX, OBJ, Alembic, USD …) and Maya presets (cm, Y-up).

### Switch & revert

- A **Maya | Blender** switch at the right of the top bar, an Edit menu entry and **Ctrl+Alt+Shift+M**.
- Switching to Blender unregisters the Maya keys and Maya UI and gives Blender's own back — with the same scene open;
  switch again whenever you like.
- Maya mode never changes your preferences, theme or active keymap, so there is nothing to restore.

![Maya or Blender, one click](docs/distribution/marketing/gif/07_switch.gif)

*One click on Blender in the top-bar switch gives plain Blender back with the same scene; one click on Maya brings the Maya layout and keys back.*

All clips as MP4 (1920 × 1080): [docs/distribution/marketing/clips/](docs/distribution/marketing/clips/).

### Known limits

Some Maya behaviour needs Blender's C++ code; the kit does not fork Blender, so these are worked around or left out:

- **Z-up world.** Blender is Z-up; Y-up applies only to the import / export presets.
- **One pivot per object.** Maya's separate rotate and scale pivots have no Blender equivalent.
- **No middle-drag on fields.** Select channels in the Channel Box and middle-drag in the viewport instead.
- **No MEL.** Scripting is Python, with a small `maya.cmds` look-alike.
- **No Maya scene files.** `.ma` / `.mb` can't be read — export FBX (or OBJ / Alembic / USD) from Maya.
- **No theme.** Maya's grey UI and green lead selection come from a theme you install yourself
  ([Recommended setup](#recommended-setup)); extensions.blender.org add-ons may not change themes.
- **Docking stays inside Blender's areas.** Maya's side tabs and OS-level docking of panels are not imitated.
- Not every Maya menu item has a Blender counterpart; those items are greyed with a note.
- Blender versions after 5.2 are not offered the extension until they are tested.

---

## Installation

### Requirements

- **Blender 4.5 LTS through 5.2.x** (`blender_version_min = "4.5.0"`, `blender_version_max = "5.3.0"` exclusive).
  The full test suites and the clean install → enable → disable → remove round trip were run on 4.5.4, 5.0.1, 5.1.2
  and 5.2.2 ([docs/compat_5x.md](docs/compat_5x.md)). Blender 4.2 – 4.4 are not supported.
- Pure Python, no compiled code, no network access. On Windows, hold keys read the keyboard state with one read-only
  system call; elsewhere Blender's own key-release event is used. Development and testing so far have been on Windows
  only.

### Option 1 — Blender Extensions platform *(not yet listed)*

Maya Workflow Kit is not on extensions.blender.org yet. Once it is, install it from inside Blender:
*Edit > Preferences > Get Extensions*, search **Maya Workflow Kit**, click **Install**.
<!-- TODO: add the listing URL when it is live -->

### Option 2 — Install the zip from disk

1. Get `maya-workflow-kit-<version>.zip` (current version: 0.2.1) from
   [GitHub Releases](https://github.com/5hyuns/maya-workflow-kit-for-blender/releases) — or build it as in option 3.
2. In Blender: *Edit > Preferences > Get Extensions > ▾ (top-right menu) > Install from Disk…* and pick the zip — or
   drag the zip onto the Blender window.

Command line (installs into the user repository and enables it):

```sh
blender --command extension install-file -r user_default --enable maya-workflow-kit-<version>.zip
```

### Option 3 — Build from source

```sh
git clone https://github.com/5hyuns/maya-workflow-kit-for-blender.git
cd maya-workflow-kit-for-blender
python tools/build.py            # -> dist/maya-workflow-kit-<version>.zip (+ dist/maya-workflow-kit-<version>-legacy.zip)
python tools/build.py --blender "/path/to/blender"   # if Blender is not at the default Windows 4.5 path
```

The build runs `blender --command extension build` (which also validates the manifest) in a throwaway user config;
then install `dist/maya-workflow-kit-<version>.zip` as in option 2.

---

## First run: turning Maya mode on and off

**Enabling the extension does not change your keymap, preferences, theme or layout.** It only adds the Maya | Blender
switch at the right of the top bar, an Edit menu entry, the shortcut **Ctrl+Alt+Shift+M** and, once, a welcome dialog.

**Turn Maya mode on** — click **Make Blender feel like Maya** in the welcome dialog or in
*Preferences > Add-ons > Maya Workflow Kit*, or click **Maya** in the top-bar switch. The kit then adds its Maya-style
keys (as add-on keymap items: your active keymap stays selected), its Maya menus and panels, and the Maya layout as
workspaces appended to the open file. It does not change your theme or your Blender preferences.

**Go back** — any of these:

| Want | Do |
|---|---|
| Plain Blender for a while | Click **Blender** in the switch (or Ctrl+Alt+Shift+M). The Maya keys and UI go away; switch again any time. |
| Uninstall | Disable or **Remove** the extension (*Preferences > Add-ons*). Everything it registered is unregistered; there is nothing else to undo. |
| Drop the Maya layout from a file | Delete its workspace tabs, or don't save the file — they are ordinary file data. |

The kit never saves your preferences.

**Files it writes outside the extension**

- The extension's user folder — your shelves.
- Maya project folders — the default project `Documents/Maya Workflow Kit/projects/default` the first time a
  project-aware dialog opens, and folders you choose with Set Project.
- Playblast writes its movie to Blender's temporary folder; exports and saves go where you choose.

---

## Recommended setup

Optional — the kit leaves your theme and preferences to you. Maya users usually like:

- **A dark grey theme.** *Edit > Preferences > Get Extensions*, filter by *Themes*, and install a dark grey theme you
  like (or pick one in *Preferences > Themes > Presets*).
- **Navigation** (*Preferences > Navigation*): Orbit Method *Turntable*, Orbit Around Selection *off*, Zoom to Mouse
  Position *off*, Auto Perspective *on*, Zoom Method *Dolly* with Zoom Axis *Horizontal*.
- **Undo Steps 256** (*Edit > Preferences > System > Memory & Limits > Undo Steps*) — Maya's undo queue is unlimited,
  Blender keeps only 32 steps by default, so a long modeling session runs out of undo much sooner than in Maya. 256 is
  Blender's maximum; the kit can't set it for you (extensions may not change Blender's preferences) and shows this hint
  in its preferences while Undo Steps is lower.
- **Emulate 3 Button Mouse off** (*Preferences > Input*). When it is on, Blender turns Alt+left drag into a middle
  drag before any key map sees it, so Maya's Alt+LMB tumble can't work (the kit shows a hint while it is on).
- **Linux:** many desktops (GNOME, KDE, Xfce) move windows on Alt+drag before Blender gets the mouse. Set the window
  manager's move modifier to Super (as for Maya on Linux) to tumble / track / dolly with Alt.
- **Region Overlap off** (*Preferences > Interface > Editors*), so side panels sit beside the viewport like Maya's.
- **Only Insert Available** (*Preferences > Animation > Keyframes*) for Maya-like auto key.

---

## Quick start for Maya users

With Maya mode on. The table of all 468 Maya 2022 factory hotkeys, their Blender counterparts and the status of each:
[docs/keymap_mapping.md](docs/keymap_mapping.md).

| Action | Keys / mouse |
|---|---|
| Tumble / track / dolly | Alt + LMB / MMB / RMB drag |
| Frame selected / all | F / A (Shift+F / Shift+A: all views) |
| One view ↔ four views | Space (tap) |
| Hotbox | Space (hold) |
| Marking menus | RMB, Shift+RMB, Ctrl+RMB over an object or component |
| Select / Move / Rotate / Scale | Q / W / E / R (hold + LMB for the tool's marking menu) |
| Last tool | Y |
| Add / toggle / remove from selection | Ctrl+Shift+click / Shift+click / Ctrl+click |
| Object ↔ component mode | F8; F9 vertex, F10 edge, F11 face, F12 UV |
| Pick-walk | Arrow keys |
| Edit pivot | D (hold) or Insert (toggle) |
| Snap to grid / edge / vertex | X / C / V (hold while dragging) |
| Soft select | B |
| Smooth preview / display modes | 1 / 2 / 3 · 4 / 5 / 6 / 7 |
| Channel Box ↔ Attribute Editor | Ctrl+A |
| Menu sets | F2 Modeling · F3 Rigging · F4 Animation · F5 FX · F6 Rendering |
| Undo / redo | Z or Ctrl+Z / Shift+Z |
| Duplicate / with transform / special | Ctrl+D / Shift+D / Ctrl+Shift+D |
| Group / parent / unparent | Ctrl+G / P / Shift+P |
| Delete history | Alt+Shift+D |
| Hide / show | Ctrl+H / Shift+H |
| Set key / key T, R, S | S / Shift+W, Shift+E, Shift+R |
| Previous / next key · play | , / . · Alt+V |
| Scrub time | K + LMB drag |
| Tangent marking menu | Shift+S (hold) + LMB |
| Background colour | Alt+B |
| Save / increment and save | Ctrl+S / Ctrl+Alt+S |
| Create Reference | Ctrl+R |
| Switch Maya ↔ Blender | Ctrl+Alt+Shift+M |

---

## FAQ

**Does it change my Blender settings?**
No. Maya mode adds add-on keymap items, menus, panels and layout workspaces in the open file; it never writes your
preferences, theme or active keymap. The settings Maya users usually change are listed under
[Recommended setup](#recommended-setup) for you to set yourself.

**Is it reversible?**
Yes. Click **Blender** in the top-bar switch, or disable / remove the extension — everything the kit registered is
unregistered, and nothing else was changed. See
[First run](#first-run-turning-maya-mode-on-and-off).

**Can I follow Blender tutorials with it installed?**
Yes — switch to Blender, follow along with Blender's own keys, and switch back to Maya.

**Which Blender versions are supported?**
Blender 4.5 LTS through 5.2.x. 4.2 – 4.4 are not offered; versions after 5.2 are added once they are tested.

**Does it open Maya `.ma` / `.mb` files?**
No. Export FBX (or OBJ, Alembic, USD) from Maya; the kit's Import uses Maya presets (cm, Y-up).

**Does it include any Maya code or files?**
No. It contains no Autodesk code, icons, MEL scripts or other Autodesk assets; behaviour is re-implemented on
Blender's own tools. It does not need Maya installed.

**Is it affiliated with Autodesk?**
No. Maya Workflow Kit is an independent, free and open-source project, not affiliated with or endorsed by Autodesk or
the Blender Foundation. See [Trademarks](#trademarks).

**Does it use the network?**
No network access and no auto-updater. Help menu items open Blender manual pages in your browser only when you click
them.

---

## Development

The extension's internal id is `allset` (package `src/allset/`, operators `allset.*`, classes `ALLSET_*`, environment
variables `ALLSET_*`); the id stays the same whatever the display name.

### Repository layout

| Path | What |
|---|---|
| `src/allset/` | The extension: `blender_manifest.toml`, `preferences.py`, `switch.py`, `keymap/`, `marking/`, `operators/`, `ui/`, `compat.py` (all Blender-version differences) |
| `tests/` | Headless harness `run.py`, GUI tests `gui/`, helpers `kit.py`, tests `test_*.py` |
| `tools/` | `build.py` (packages), `release_check.py`, `build_repo.py` (static extension repository), generators for the keymap doc, menus, shelves and layout |
| `docs/` | `keymap_mapping.md`, `compat_5x.md`, `manual_checks.md`, `distribution/`, user guides |

### Build and test

Every Blender run uses a sandbox user config under `tmp/` — your real Blender settings are never read or written.

```sh
python tools/build.py              # build dist/maya-workflow-kit-<version>.zip and the legacy zip
python tests/run.py                # build + install into tmp/test_env + run all headless tests
python tests/run.py -k enable      # only matching test files
python tests/run.py --no-build     # reuse the zip in dist/
python tests/gui/run.py            # GUI tests with simulated key / mouse events (a Blender window opens briefly)
python tools/release_check.py      # build, extension validate, clean-config install + enable, screenshots
python tools/gen_keymap_mapping.py # regenerate docs/keymap_mapping.md
python tools/build_repo.py         # static extension repository in dist/repo/ (zip + index.json + index.html)
```

Per-version results: [docs/compat_5x.md](docs/compat_5x.md). Things automated tests can't prove (feel, visuals) are
listed in [docs/manual_checks.md](docs/manual_checks.md).

---

## Credits

The scenes in the screenshots and clips use third-party models and images under their own licences; every asset, its
author, source and licence is listed in
[docs/distribution/marketing/CREDITS.md](docs/distribution/marketing/CREDITS.md). Captions are set in Inter (SIL OFL).
These assets are used only in the marketing media and are not shipped in the extension.

## License

Code: **GPL-3.0-or-later** ([LICENSE](LICENSE)). The kit-made images and data files in the extension (welcome PNGs,
the Maya layout `startup.blend`) are **CC0-1.0**
([src/allset/ASSETS_LICENSE.txt](src/allset/ASSETS_LICENSE.txt)). Copyright 2026 ohnsk.

## Trademarks

Autodesk and Maya are registered trademarks or trademarks of Autodesk, Inc., and/or its subsidiaries and/or affiliates
in the USA and/or other countries. This project is an independent, free and open-source (GPL) extension for Blender.
It is not affiliated with, endorsed by, sponsored by, or otherwise approved by Autodesk, Inc. or the Blender
Foundation. It contains no Autodesk code, icons, MEL scripts or other Autodesk assets; references to Maya are solely to
describe compatibility and the intended audience.
