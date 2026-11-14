# README media

The README uses local assets so its layout does not depend on a third-party banner service.

| Asset | Source |
| --- | --- |
| `readme-hero.svg` | Vector artwork using the existing DM mark and the bundled retry-demo edit |
| `readme-hero-mobile.svg` | Narrow-screen composition of the same artwork |
| `readme-demo.gif` | Two unmodified five-second excerpts from `demo-walkthrough.mp4`: 8–13s and 23–28s |
| `demo-preview.png` | Existing static browser capture, used when reduced motion is requested |

The hero is an illustration, not a screenshot of a new interface. Lettering is outlined from
the bundled Geist fonts, licensed under [SIL OFL](../../web/public/geist-OFL.txt); the SVG needs
no external font requests. The GIF preserves the original recorded UI and subtitles. Its
assistant decisions are scripted; the underlying file tools and unittest checks really ran.
The original recording and full-length GIF remain unchanged.

## Rebuild the derived assets

From the repository root, with FFmpeg on `PATH`:

```bash
uv run --no-project --with fonttools --with brotli python scripts/build_readme_media.py --output build/readme-media
```

The output directory must not exist. Inspect the generated SVGs and GIF, then copy the three
derived files into this directory. The media-only font dependencies are not needed to install
or run DM-Code-Agent.

GitHub-compatible `<picture>` elements select the narrow hero on small screens and the static
demo image for `prefers-reduced-motion: reduce`. The regular image elements retain useful alt
text and act as fallbacks. The README uses native headings, tables, links, and `<details>`;
it requires no JavaScript or custom CSS in GitHub.
