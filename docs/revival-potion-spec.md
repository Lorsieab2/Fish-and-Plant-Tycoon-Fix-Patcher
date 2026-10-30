# Revival Potion: the owner's spec (2026-10-30)

- **Name:** "Revival Potion"
- **Description:** "This magical potion instantly revives dead fish/plants and restores them to full health. Contains 3 doses."
  - In the store, each game names only its own subject: "dead fish" in Fish Tycoon, "dead plants" in Plant Tycoon.
- **Games:** both Fish Tycoon and Plant Tycoon, on the patcher's Upgrades screen.
- **Price and doses:** $10,000 for 3 doses ($0 with Free upgrades).
- **Effect:** instantly revives dead fish or plants and restores them to full health.
- **Use:** like each game's chemicals. In Fish Tycoon a dose acts on the tank on screen; in Plant Tycoon a dose acts on the plant it is dropped on.
- **Expanded tanks and greenhouses:** it must work identically in the extra tanks, fish slots 26–29 and the extra greenhouses.
- **Icon:** `assets/revival_potion/revival_potion_source.png` (the owner's amber flask, 37×67 RGBA), resized to each Upgrades screen's item size.

# ClonaFish (was "Fish Cloner"): Fish Tycoon only (owner, 2026-10-30)

- **Name:** "ClonaFish"
- **Description:** "A wonder drug that instantly clones all unique fish in the tank. Make sure there's enough space in the tank! Contains 3 doses."
- **Price and doses:** $2,500 for 3 doses ($0 with Free upgrades), on the Upgrades screen.
- **Unique fish:** a live fish whose species (fin AND body together) no other live fish in the same tank shares. Two fish with the same fin but different bodies are both unique.
- **Effect** (each dose, on the tank on screen): every unique fish gets one clone, an **exact copy**: same species, age, health, hunger, sickness and gender, and the same everything else the game stores, except whatever must be unique per fish (a slot or index, an id).
  - Clones are added one at a time through the game's own add-fish path (AddFish 0x419C50).
  - If the tank runs out of room, it stops: unique fish are processed in slot order and the rest get no clone.
  - The game's "tank is full" message shows if nothing could be cloned.
- **Expanded tanks:** it must work identically in the extra tanks and with 30 fish per tank (read the tank's slot limit the way the Radioactive Growth Hormone reads its loop end).
- **Icon:** the owner will send one, saved as `assets/clonafish/clonafish_source.png`. Until then use a marked placeholder that a release build refuses.

# Revita-Seed: Plant Tycoon only (owner, 2026-10-30)

- **Name:** "Revita-Seed"
- **Description:** "Revitalizes depleted plants so they can produce more seeds. Contains 3 doses."
- **Price and doses:** $2,500 for 3 doses ($0 with Free upgrades), on the Upgrades screen.
- **Effect:** a plant that has used up its seed-giving can give seeds again, exactly as a fresh plant can by the game's own rules. Find the "depleted" state in the code and reset only that.
- **Use:** like the other Plant chemicals, a dose acts on the plant it is dropped on.
- **Expanded greenhouses:** it works identically in the extra greenhouses.
- **Icon:** the owner will send one, to be saved as `assets/revita_seed/revita_seed_source.png`. Until it arrives, build with a clearly marked placeholder that a release build refuses.
