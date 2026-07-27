# Generated main-scene artwork

These PNG assets are the painted decoration layer for the main companion scene. Dynamic text, hit targets, loading states, and accessibility semantics remain in HTML/CSS.

| Asset | Purpose | Final size |
| --- | --- | --- |
| `status-frame-ornate.png` | Ornate glass frame behind the three companion status cells | 1800 × 600 |
| `input-frame-glass.png` | Water-glass chat input frame with an integrated droplet socket | 1600 × 359 |
| `send-button-crystal.png` | Crystal paper-plane send button artwork | 512 × 512 |

## Production method

- Generated with the built-in image generation tool using `docs/front_design/main/ui.png` as the visual-language reference.
- Generated on a flat green chroma background, then converted locally to RGBA PNG with the imagegen chroma-key helper.
- Source chroma images are intentionally excluded; only the validated transparent production assets live here.
- Production files are downsampled with Lanczos filtering to a high-DPI web ceiling; the three PNGs total roughly 1.7 MB instead of the 3.5 MB generation output.
- Existing SVG assets under `assets/frames/` and `assets/icons/` remain lightweight fallback and state-icon resources.

## Prompt intent

- Status frame: midnight-blue glass, silver-blue luminous border, celestial filigree, fixed side caps, central faceted jewels, no text or embedded status icons.
- Input frame: long pill-shaped water glass, quiet center for live text, left droplet-crystal socket, no text or send button.
- Send button: circular sapphire glass, large centered silver-white paper plane, subtle droplets and constellation glints, no text.

Do not bake user-facing copy into these files. If layout or copy changes, update the HTML layer instead of regenerating the artwork.
