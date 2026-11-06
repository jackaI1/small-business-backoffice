# Drawing and delivery details

I keep the wording and vector artwork in `assets/game-night.svg`. The sample is synthetic and contains no external photographs, linked assets, team logos or private records. It uses DejaVu Sans with a generic sans-serif fallback. Install the same font on each machine if exact text metrics matter.

## Layout

The six top-level SVG groups carry stable IDs. Each can contain text, shapes, strokes and its own transform. `toolkit/export.py` asks Inkscape for their real bounds, then fits a wrapper around each group. The proportions inside the group stay intact. Four arrangements in `SLOTS` define non-overlapping rectangles within the target's safe area. A target chooses an arrangement and its own pixel dimensions and margins. The background and bottom accent extend to the full canvas.

The example master is itself a readable 1600 × 900 layout. The output uses the same objects, rather than screenshots of the master or separate drawings for each size. The story has larger top and bottom margins to leave space for interface overlays. The ribbon places event information side by side. Those are example production rules, not promises about a particular platform or venue. A very long replacement phrase will shrink; review readability after changing it.

## Pipeline

1. Validate the campaign and target names, dimensions, margins and layout. Names permit lowercase letters, numbers and hyphens. Dimensions have an upper bound to avoid accidental giant renders.
2. Refuse an existing destination. Record the master hash and the real tool versions.
3. Query master bounds, write each temporary SVG, query it again and check all six groups against the safe rectangle. The comparison permits 0.1 pixel of printed-number rounding.
4. Inkscape renders each page at the requested pixel size.
5. One isolated GIMP 3 batch loads the PNGs and uses its PNG and JPEG export procedures. The exporter prefers `gimp-console` so Linux batches do not need a display. Each image is deleted after processing. GIMP writes a completion receipt so a silently failed batch cannot count as success.
6. Pillow independently decodes the resulting files and checks dimensions and file format. It computes byte counts and hashes. Pillow does not generate the deliverables.
7. Write `manifest.json`. The overall status is `passed` only after every output succeeds. On failure, planned entries are marked `failed`; partial images may remain for diagnosis and must not be delivered.

Temporary rendered files and the GIMP profile live in a temporary directory which Python removes on success or failure. Commands have time limits. No HTTP server or browser is needed.

## Hand-off

The filename pattern is:

```text
{campaign}_{target}_{width}x{height}_{revision}.{png|jpg}
```

The JSON manifest contains `campaign`, `revision`, `master_sha256`, `tools`, `status` and `deliverables`. Each deliverable has `file`, `target`, `width`, `height`, `format`, `status`, `safe_area`, `safe_insets_ltrb`, `content_bounds`, `bytes` and `sha256`. Bounds are pixel-space `[x, y, width, height]` values after layout. Byte counts and hashes appear only once files have been decoded successfully.

I deliver the complete folder, including the manifest. I check the receiving screen's pixel dimensions and margin rules first, then inspect text at its intended display size. There is no automatic readability, overlap or venue certification check. This toolkit is for trusted local SVGs, not for processing drawings uploaded by strangers.

## Reproducing checks

The CI image is Debian 13 because it packages GIMP 3. The workflow installs the real editors and GIMP's Python bindings rather than substituting mock image converters. `ASSET_REQUIRE_TOOLS=1` prevents accidental integration skips. Unit tests cover the failure paths; a shared integration run exports seven full-size presets, and another exports an edited master. CI also exports a separate hand-off as a downloadable artifact.

Useful references: [Inkscape command-line manual](https://inkscape.org/doc/inkscape-man.html), [GIMP command-line manual](https://www.gimp.org/man/gimp.html), [GIMP 3 scripting API](https://developer.gimp.org/api/3.0/libgimp/).
