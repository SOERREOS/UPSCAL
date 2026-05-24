from __future__ import annotations

import struct
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont


ROOT = Path(__file__).resolve().parents[1]
ICON_SOURCE = ROOT / "Icon.png"
INSTALLER_DIR = ROOT / "installer"
ICO_PATH = INSTALLER_DIR / "UPSCAL.ico"
ICNS_PATH = INSTALLER_DIR / "UPSCAL.icns"
WIZARD_LARGE = INSTALLER_DIR / "UPSCAL_WizardLarge.bmp"
WIZARD_SMALL = INSTALLER_DIR / "UPSCAL_WizardSmall.bmp"


def make_dib_ico(source: Image.Image, out_path: Path):
    sizes = [16, 24, 32, 48, 64, 128, 256]
    images: list[bytes] = []
    directory: list[tuple[int, int, bytes]] = []

    for size in sizes:
        img = source.resize((size, size), Image.Resampling.LANCZOS).convert("RGBA")
        xor_rows: list[bytes] = []
        pixels = img.load()
        for y in range(size - 1, -1, -1):
            row = bytearray()
            for x in range(size):
                r, g, b, a = pixels[x, y]
                row.extend((b, g, r, a))
            xor_rows.append(bytes(row))

        mask_stride = ((size + 31) // 32) * 4
        mask = b"\x00" * (mask_stride * size)
        header = struct.pack(
            "<IIIHHIIIIII",
            40,  # BITMAPINFOHEADER
            size,
            size * 2,
            1,
            32,
            0,
            size * size * 4 + len(mask),
            0,
            0,
            0,
            0,
        )
        payload = header + b"".join(xor_rows) + mask
        images.append(payload)
        directory.append((size, size, payload))

    offset = 6 + len(directory) * 16
    data = bytearray(struct.pack("<HHH", 0, 1, len(directory)))
    for width, height, payload in directory:
        data.extend(
            struct.pack(
                "<BBBBHHII",
                0 if width == 256 else width,
                0 if height == 256 else height,
                0,
                0,
                1,
                32,
                len(payload),
                offset,
            )
        )
        offset += len(payload)
    for payload in images:
        data.extend(payload)

    out_path.write_bytes(bytes(data))


def make_wizard_images(source: Image.Image):
    try:
        font_big = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", 25)
    except Exception:
        font_big = ImageFont.load_default()

    large = Image.new("RGB", (164, 314), "#08080b")
    draw = ImageDraw.Draw(large)
    for y in range(314):
        mix = y / 313
        draw.line([(0, y), (164, y)], fill=(int(8 + 9 * mix), int(8 + 8 * mix), int(11 + 24 * mix)))
    for x in range(13, 164, 22):
        for y in range(18, 314, 22):
            draw.ellipse((x, y, x + 1, y + 1), fill=(45, 45, 62))
    for offset, color in [(0, (99, 102, 241)), (10, (16, 185, 129))]:
        draw.line([(18, 230 + offset), (54, 196 + offset), (106, 214 + offset), (146, 166 + offset)], fill=color, width=1)

    shadow = Image.new("RGBA", large.size, (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow)
    shadow_draw.rounded_rectangle((34, 42, 130, 138), radius=24, fill=(99, 102, 241, 85))
    shadow = shadow.filter(ImageFilter.GaussianBlur(14))
    large_rgba = Image.alpha_composite(large.convert("RGBA"), shadow)
    large_rgba.alpha_composite(source.resize((88, 88), Image.Resampling.LANCZOS), (38, 46))
    draw = ImageDraw.Draw(large_rgba)
    draw.text((82, 164), "UPSCAL", anchor="mm", fill=(242, 237, 236), font=font_big)
    large_rgba.convert("RGB").save(WIZARD_LARGE)

    small = Image.new("RGB", (55, 55), "#08080b").convert("RGBA")
    small.alpha_composite(source.resize((45, 45), Image.Resampling.LANCZOS), (5, 5))
    small.convert("RGB").save(WIZARD_SMALL)


def make_icns(source: Image.Image):
    sizes = [(16, 16), (32, 32), (64, 64), (128, 128), (256, 256), (512, 512), (1024, 1024)]
    source.save(ICNS_PATH, format="ICNS", sizes=sizes)


def main() -> int:
    INSTALLER_DIR.mkdir(exist_ok=True)
    source = Image.open(ICON_SOURCE).convert("RGBA")
    make_dib_ico(source, ICO_PATH)
    make_icns(source)
    make_wizard_images(source)
    print(f"Wrote {ICO_PATH}")
    print(f"Wrote {ICNS_PATH}")
    print(f"Wrote {WIZARD_LARGE}")
    print(f"Wrote {WIZARD_SMALL}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
