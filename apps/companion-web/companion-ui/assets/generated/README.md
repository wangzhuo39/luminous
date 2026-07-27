# Generated main-scene artwork

These PNG assets are the painted decoration layer for the main companion scene. Dynamic text, hit targets, loading states, and accessibility semantics remain in HTML/CSS.

| Asset | Purpose | Final size |
| --- | --- | --- |
| `status-frame-ornate.png` | Ornate glass frame behind the three companion status cells | 1800 × 600 |
| `status-heart-orb.png` | Sapphire heart and pulse orb for the heartbeat status | 384 × 384 |
| `status-rain-orb.png` | Sapphire umbrella and rain orb for the activity status | 384 × 384 |
| `status-quiet-orb.png` | Sapphire crescent and ripple orb for the mood status | 384 × 384 |
| `portal-today-orb.png` | Extracted celestial crescent portal for 今日 | 384 × 384 |
| `portal-memory-orb.png` | Extracted faceted memory crystal portal for 记忆 | 384 × 384 |
| `portal-letter-orb.png` | Extracted luminous envelope portal for 来信 | 384 × 384 |
| `portal-heart-orb.png` | Extracted lotus-heart portal for 心迹 | 384 × 384 |
| `input-frame-glass.png` | Water-glass chat input frame with an integrated droplet socket | 1600 × 359 |
| `send-button-crystal.png` | Crystal paper-plane send button artwork | 512 × 512 |

## Production method

- Generated with the built-in image generation tool using `docs/front_design/main/ui.png` as the visual-language reference.
- The four portal PNGs are local crops derived from the supplied `ui.png` reference after the built-in generation service became unavailable; they preserve the target's original orbital glass and crystal details while the surrounding square is feathered to transparency.
- Generated on a flat green chroma background, then converted locally to RGBA PNG with the imagegen chroma-key helper.
- Source chroma images are intentionally excluded; only the validated transparent production assets live here.
- Production files are downsampled with Lanczos filtering to a high-DPI web ceiling; large chroma-key generation sources are not shipped to the browser.
- Existing SVG assets under `assets/frames/` and `assets/icons/` remain lightweight fallback and state-icon resources.

## Prompt intent

- Status frame: midnight-blue glass, silver-blue luminous border, celestial filigree, fixed side caps, central faceted jewels, no text or embedded status icons.
- Heart status: sapphire glass sphere, silver-white crystal heart, heartbeat trace, orbital rings and restrained constellation glints.
- Rain status: sapphire glass sphere, silver-blue umbrella, gentle droplets, water ripples and sparse constellation lines.
- Quiet status: sapphire glass sphere, slim silver crescent, quiet stars, calm ripple and fine orbital rings.
- Input frame: long pill-shaped water glass, quiet center for live text, left droplet-crystal socket, no text or send button.
- Send button: circular sapphire glass, large centered silver-white paper plane, subtle droplets and constellation glints, no text.

Do not bake user-facing copy into these files. If layout or copy changes, update the HTML layer instead of regenerating the artwork.
