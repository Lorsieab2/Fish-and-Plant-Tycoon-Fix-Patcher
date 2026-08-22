# Changelog

## v1.0.7

- Added an `Autodetect Games` button that searches the usual Windows install
  locations for the exact `Fish Tycoon.exe` and `Plant Tycoon.exe` and fills in
  the vanilla and modded folder fields for whatever it finds.
- Added a `Scan a Folder...` button that runs the same search, deeper, in one
  folder or drive you choose.
- The search skips Windows system folders and any existing `- Modded` folder,
  runs on a background thread with live progress, and stops at a folder and
  time budget so a slow or cloud-synced location cannot hang the patcher.
- When one game is found in more than one place, the patcher asks which install
  to use instead of guessing.
- Added `Defaults`, `Enable All`, and `Disable All` buttons to each game's
  patch list.
- Moved the per-game `Find [Game]...` buttons up beside the new autodetect
  controls, so they work on both tabs, and every action button is now locked
  while a scan, patch, or restore is running.

## v1.0.5

- Added separate `Find Fish Tycoon in Parent Folder...` and
  `Find Plant Tycoon in Parent Folder...` buttons to the Both Games tab,
  alongside the existing combined finder.
- The finder accepts one exact vanilla executable in the selected folder or
  one of its immediate subfolders and refuses missing or ambiguous matches.

## v1.0.4

- Renamed generated game folders to exactly `Fish Tycoon - Modded` and
  `Plant Tycoon - Modded`.
- Renamed generated executables to exactly `Fish Tycoon - Modded.exe` and
  `Plant Tycoon - Modded.exe` so each modified game uses its matching isolated
  save location.
- Added a remembered GUI option for choosing the parent location where the
  modified game folders are created.
- Removed the vanilla executable filename from each generated modded folder.

## v1.0.3

- Replaced both picture assets with the final transparent PNGs supplied by
  Lorsieab2.
- Added emoji-sized plant and fish pictures around the creator sentence.
- Surrounded the main patcher title with the plant and fish pictures.
- Added a paired plant-and-fish application icon to the native window title
  bar.

## v1.0.2

- Replaced the text emoji banner with the two exact fish and potted-plant
  pictures supplied by Lorsieab2.
- Removed the pictures' dark square backgrounds and preserved transparent PNG
  assets in the GUI and release package.

## v1.0.1

- Added the requested `🐟🪴` picture-style emoji banner.
- Added the exact creator description:
  `🪴 Created with Codex AI. Made with love by Lorsieab2 :) 🐟`

## v1.0.0

- Combined the current Fish Tycoon Fix Patcher v1.2.4 and Plant Tycoon Fix
  Patcher v1.0.0 engines and manifests.
- Added One Game and Both Games workflows modeled on the Virtual Villagers Fun
  Patcher.
- Added remembered, auto-filled vanilla/modded paths and clickable folder
  links.
- Preserved exact-build validation, guarded patches, pinned hashes, backups,
  restore, full-folder copying, readback verification, and original icon
  resources.
## v1.0.7

- Added an opt-in Golden Seahorse repurchase setting targeting store item
  index 18 and its two already-owned purchase gates.
