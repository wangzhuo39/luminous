# Generated main-scene artwork

These PNG assets are the painted decoration layer for the main companion scene. Dynamic text, hit targets, loading states, and accessibility semantics remain in HTML/CSS.

| Asset | Purpose | Final size |
| --- | --- | --- |
| `status-frame-ornate.png` | Ornate glass frame behind the three companion status cells | 1800 × 600 |
| `status-heart-orb.png` | Sapphire heart and pulse orb for the heartbeat status | 384 × 384 |
| `status-rain-orb.png` | Sapphire umbrella and rain orb for the activity status | 384 × 384 |
| `status-quiet-orb.png` | Sapphire crescent and ripple orb for the mood status | 384 × 384 |
| `today.png` | Transparent celestial glass orb with a faceted crescent for 今日 | 1024 × 1024 |
| `memory.png` | Transparent celestial glass orb with a faceted memory crystal for 记忆 | 1024 × 1024 |
| `letter.png` | Transparent celestial glass orb with a crystal envelope for 来信 | 1024 × 1024 |
| `heart.png` | Transparent celestial glass orb with a seven-petal crystal lotus for 心迹 | 1024 × 1024 |
| `input-frame-glass.png` | Water-glass chat input frame with an integrated droplet socket | 1600 × 359 |
| `send-button-crystal.png` | Crystal paper-plane send button artwork | 512 × 512 |

## Production method

- The status and composer artwork was generated with the built-in image generation tool using `docs/front_design/main/ui.png` as the visual-language reference.
- `today.png` is the approved transparent style master. The remaining portals were generated through the configured `gpt-image-1.5` API with portal-specific production prompts matched to its glass, glow, scale, and orbital language.
- All four production portal files are validated RGBA PNGs with transparent corners and partial alpha retained for glass edges, glow falloff, star tracks, and particles.
- Existing SVG assets under `assets/frames/` and `assets/icons/` remain lightweight fallback and state-icon resources.

## Prompt intent

- Status frame: midnight-blue glass, silver-blue luminous border, celestial filigree, fixed side caps, central faceted jewels, no text or embedded status icons.
- Heart status: sapphire glass sphere, silver-white crystal heart, heartbeat trace, orbital rings and restrained constellation glints.
- Rain status: sapphire glass sphere, silver-blue umbrella, gentle droplets, water ripples and sparse constellation lines.
- Quiet status: sapphire glass sphere, slim silver crescent, quiet stars, calm ripple and fine orbital rings.
- Input frame: long pill-shaped water glass, quiet center for live text, left droplet-crystal socket, no text or send button.
- Send button: circular sapphire glass, large centered silver-white paper plane, subtle droplets and constellation glints, no text.

Do not bake user-facing copy into these files. If layout or copy changes, update the HTML layer instead of regenerating the artwork.
