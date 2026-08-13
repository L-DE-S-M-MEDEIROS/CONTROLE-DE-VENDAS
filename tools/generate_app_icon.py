from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

CANVAS_SIZE = 1024
ICON_SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)


def rounded_mask(size, bounds, radius):
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle(bounds, radius=radius, fill=255)
    return mask


def vertical_gradient(size, top, bottom):
    image = Image.new("RGBA", (size, size))
    pixels = image.load()
    for y in range(size):
        factor = y / max(1, size - 1)
        color = tuple(
            round(start + (end - start) * factor)
            for start, end in zip(top, bottom, strict=True)
        )
        for x in range(size):
            pixels[x, y] = (*color, 255)
    return image


def create_icon():
    size = CANVAS_SIZE
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))

    shadow = Image.new("RGBA", image.size, (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow)
    shadow_draw.rounded_rectangle(
        (70, 82, 954, 966),
        radius=210,
        fill=(3, 19, 34, 105),
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(24))
    image.alpha_composite(shadow)

    bounds = (56, 48, 968, 960)
    mask = rounded_mask(size, bounds, 220)
    gradient = vertical_gradient(size, (9, 43, 76), (6, 153, 213))
    image.alpha_composite(Image.composite(gradient, Image.new("RGBA", image.size), mask))

    sheen = Image.new("RGBA", image.size, (0, 0, 0, 0))
    sheen_draw = ImageDraw.Draw(sheen)
    sheen_draw.ellipse((-180, -390, 1030, 560), fill=(255, 255, 255, 24))
    image.alpha_composite(Image.composite(sheen, Image.new("RGBA", image.size), mask))

    symbol_shadow = Image.new("RGBA", image.size, (0, 0, 0, 0))
    symbol_shadow_draw = ImageDraw.Draw(symbol_shadow)
    symbol_shadow_draw.rounded_rectangle(
        (229, 374, 815, 838),
        radius=88,
        fill=(1, 28, 49, 54),
    )
    symbol_shadow = symbol_shadow.filter(ImageFilter.GaussianBlur(14))
    image.alpha_composite(symbol_shadow)

    draw = ImageDraw.Draw(image)
    white = (250, 253, 255, 255)
    draw.arc(
        (304, 174, 720, 526),
        start=188,
        end=352,
        fill=white,
        width=70,
    )
    draw.rounded_rectangle(
        (210, 350, 814, 824),
        radius=92,
        fill=white,
    )

    bar_colors = ((20, 125, 174, 255), (13, 151, 188, 255), (52, 185, 148, 255))
    bars = ((326, 620, 408, 714), (471, 542, 553, 714), (616, 454, 698, 714))
    for bounds, color in zip(bars, bar_colors, strict=True):
        draw.rounded_rectangle(bounds, radius=34, fill=color)

    draw.line(
        ((344, 523), (498, 446), (642, 350)),
        fill=(6, 82, 126, 255),
        width=38,
        joint="curve",
    )
    draw.polygon(
        ((615, 332), (700, 319), (678, 402)),
        fill=(6, 82, 126, 255),
    )

    return image


def main():
    root = Path(__file__).resolve().parent.parent
    asset_dir = root / "assets"
    asset_dir.mkdir(parents=True, exist_ok=True)
    image = create_icon()
    image.save(asset_dir / "app_icon.png", optimize=True)
    image.save(
        asset_dir / "app_icon.ico",
        format="ICO",
        sizes=[(size, size) for size in ICON_SIZES],
        bitmap_format="png",
    )


if __name__ == "__main__":
    main()
