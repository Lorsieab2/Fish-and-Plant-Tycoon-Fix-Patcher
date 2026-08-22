# Fish & Plant Tycoon Fix Patcher

<img src="assets/fish.png" alt="Fish" width="96"> <img src="assets/plant.png" alt="Potted plant" width="96">

🪴 Created with Codex AI. Made with love by Lorsieab2 :) 🐟

An offline Windows patcher combining the current Fish Tycoon Fix Patcher and
Plant Tycoon Fix Patcher in the same player-facing format as the Virtual
Villagers Fun Patcher.

## Included fixes

### Fish Tycoon

- Crimson Comet 20% curing fix.
- Unknown Chemical: 3 uses.
- Universal supply slots 2-4 for the eight supported medicine, chemical, and
  egg types.
- Optional Golden Seahorse repurchase after it has already been owned.

### Plant Tycoon

- No old-age plant deaths. The original age check and `Random(1000)` call remain;
  the eligible death range is empty.

## Use

1. Extract the release ZIP.
2. Double-click `Launch Fish and Plant Tycoon Fix Patcher.bat`.
3. Click **Autodetect Games**, or select the vanilla folder for each game
   yourself.
4. Select **One Game** or **Both Games**.
5. Choose the fixes you want, using **Defaults**, **Enable All**, or
   **Disable All** if it is quicker.
6. Validate, dry run, or create the fixed copy/copies.

The GUI remembers separate vanilla and modded paths for both games. Every blue
underlined path is a direct File Explorer link to that folder.

### Finding your games

**Autodetect Games** searches your usual Windows install locations, such as
Downloads, Documents, Desktop, both Program Files folders, and the common Steam
and GOG library paths, for the exact `Fish Tycoon.exe` and `Plant Tycoon.exe`,
and fills in the vanilla and modded folder fields for whatever it finds. It
skips Windows system folders and any folder ending in `- Modded`, so a copy the
patcher created earlier is never offered back as a vanilla source. If one game
turns up in more than one place, the patcher asks which install to use.

If the game lives somewhere unusual, **Scan a Folder...** runs the same search,
deeper, in one folder or drive you choose. The per-game
**Find [Game]...** buttons still accept an exact parent folder. The search only
reads folder listings, runs on a background thread with live progress, and
stops at a folder and time budget so a slow or cloud-synced location cannot
hang the patcher.

Choose one parent location in the GUI. The patcher creates complete separate
output folders named `Fish Tycoon - Modded` and `Plant Tycoon - Modded`.
Their executables are named `Fish Tycoon - Modded.exe` and
`Plant Tycoon - Modded.exe`, so the two modified games use only their matching
`- Modded` save locations. Original folders and executables are not replaced.
The **One Game** tab also retains each original patcher's verified
restore-from-backup operation.

## Safety

Each engine remains bound to the exact supported stock executable identity,
including SHA-256, size, PE fields, and resource-section hash. Every changed
byte is guarded, expected output hashes are pinned, backups are created, output
files are read back, and the original icon resources remain intact.

When both games are selected, both inputs are dry-run validated before either
output folder is written.

No game executable, save, or original game asset is included in this
repository or release.
