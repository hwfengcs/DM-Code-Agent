"""Build README artwork and a short cut of the real walkthrough. Needs fontTools/Brotli and FFmpeg."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont

ROOT = Path(__file__).resolve().parents[1]


def lettering(font, value: str, x: float, y: float, size: float, color: str) -> str:
    """Outline the bundled Geist font so GitHub needs no external font requests."""
    glyphs = font.getGlyphSet()
    cmap = font.getBestCmap()
    scale = size / font["head"].unitsPerEm
    paths = []
    for character in value:
        name = cmap[ord(character)]
        pen = SVGPathPen(glyphs)
        glyphs[name].draw(pen)
        paths.append(
            f'<path transform="translate({x:.2f} {y}) scale({scale:.5f} {-scale:.5f})" '
            f'd="{pen.getCommands()}"/>'
        )
        x += font["hmtx"][name][0] * scale
    return f'<g fill="{color}">' + "".join(paths) + "</g>"


def hero(display, mono, *, mobile: bool) -> str:
    width, height = (640, 420) if mobile else (1280, 440)
    left = 36 if mobile else 64
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">',
        "<title>DM-Code-Agent — Every change. In plain sight.</title>",
        "<desc>A local coding agent with inspectable changes and test evidence. The code illustration uses the bundled retry demo.</desc>",
        '<defs><radialGradient id="glow"><stop stop-color="#197d58" stop-opacity=".5"/><stop offset="1" stop-color="#0b1117" stop-opacity="0"/></radialGradient>',
        '<linearGradient id="edge"><stop stop-color="#70dc98"/><stop offset="1" stop-color="#70dc98" stop-opacity="0"/></linearGradient></defs>',
        f'<rect width="{width}" height="{height}" rx="18" fill="#0b1117"/>',
        f'<ellipse cx="{width - 70}" cy="150" rx="420" ry="330" fill="url(#glow)"/>',
        f'<path d="M{width - 300} 0  {width - 590} {height}M{width - 230} 0 {width - 520} {height}" stroke="#70dc98" stroke-opacity=".08" fill="none"/>',
        f'<g transform="translate({left} 36)"><rect width="40" height="40" rx="11" fill="#152b23" stroke="#2f5141"/><path d="M10 12h7c8 0 8 16 0 16h-7V12Z" stroke="#ecf5ef" stroke-width="2.5" fill="none"/><path d="m24 27 4-14 4 14" stroke="#70dc98" stroke-width="2.5" stroke-linecap="round" fill="none"/></g>',
        lettering(mono, "DM-CODE-AGENT", left + 56, 63, 20, "#c5d4cc"),
        lettering(display, "Every change.", left, 168, 68 if mobile else 78, "#f3f7f4"),
        lettering(display, "In plain sight.", left, 249, 68 if mobile else 78, "#81ecb0"),
        lettering(mono, "LOCAL-FIRST  /  INSPECTABLE  /  OPEN SOURCE", left, 304, 15, "#a3b8ae"),
        f'<path d="M{left} 337h{width - 2 * left}" stroke="url(#edge)" stroke-opacity=".5"/>',
        lettering(mono, "READ THE CODE.  FOLLOW THE EVIDENCE.", left, 379, 15, "#c5d4cc"),
    ]
    if not mobile:
        parts.extend(
            [
                '<rect x="761" y="96" width="454" height="207" rx="14" fill="#101c21" stroke="#385348"/>',
                '<path d="M761 142h454" stroke="#263d34"/>',
                '<circle cx="786" cy="119" r="4" fill="#70dc98"/>',
                lettering(mono, "retry.py", 800, 125, 17, "#c5d4cc"),
                lettering(mono, "BUNDLED DEMO", 1077, 125, 12, "#94b1a1"),
                '<rect x="781" y="163" width="414" height="43" rx="5" fill="#35212a"/>',
                '<rect x="781" y="213" width="414" height="43" rx="5" fill="#173b2c"/>',
                lettering(mono, "- attempt <= max_attempts", 796, 190, 20, "#f5a9b2"),
                lettering(mono, "+ attempt < max_attempts", 796, 240, 20, "#92efb8"),
                lettering(mono, "A SMALL CHANGE. A CHECKABLE TRAIL.", 782, 283, 12, "#a3b8ae"),
                '<path d="M1146 74v-14h-14M1227 272h14v-14" stroke="#81ecb0" stroke-width="2" fill="none"/>',
            ]
        )
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, required=True, help="New directory for derived media"
    )
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Choose a new directory; existing media is preserved.")
    args.output.mkdir(parents=True)
    display = instantiateVariableFont(
        TTFont(ROOT / "web/src/fonts/Geist-Variable.woff2"), {"wght": 600}
    )
    mono = instantiateVariableFont(
        TTFont(ROOT / "web/src/fonts/GeistMono-Variable.woff2"), {"wght": 450}
    )
    for mobile in (False, True):
        name = "readme-hero-mobile.svg" if mobile else "readme-hero.svg"
        (args.output / name).write_text(hero(display, mono, mobile=mobile), encoding="utf-8")
    # 两段均来自既有真实浏览器录屏；保留录屏内的字幕，不伪造终端或模型输出。
    filters = (
        "[0:v]trim=start=8:end=13,setpts=PTS-STARTPTS[a];"
        "[0:v]trim=start=23:end=28,setpts=PTS-STARTPTS[b];"
        "[a][b]concat=n=2:v=1:a=0,fps=6,scale=880:-1:flags=lanczos,split[c][d];"
        "[c]palettegen=stats_mode=diff[p];[d][p]paletteuse=dither=bayer:bayer_scale=3"
    )
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-n",
            "-i",
            str(ROOT / "docs/media/demo-walkthrough.mp4"),
            "-filter_complex",
            filters,
            "-loop",
            "0",
            str(args.output / "readme-demo.gif"),
        ],
        check=True,
    )
    print(f"README artwork and 10-second demo cut: {args.output}")


if __name__ == "__main__":
    main()
