#!/usr/bin/env python3
"""Generate high-resolution multi-size .ico and .png brand and action icons for BSA Trading Bridge."""

import io
import math
from pathlib import Path
from PIL import Image, ImageDraw

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ASSETS_DIR = PROJECT_ROOT / "assets"
ICONS_DIR = ASSETS_DIR / "icons"
BRAND_DIR = Path("/Users/bhavinamesara/Projects/bhavin_brand_assets")

ICONS_DIR.mkdir(parents=True, exist_ok=True)

# Shared Brand Palette
NAVY = (11, 25, 51, 255)       # #0B1933
CYAN = (8, 182, 222, 255)      # #08B6DE
BLUE = (22, 135, 232, 255)     # #1687E8
AMBER = (245, 166, 35, 255)    # #F5A623
WHITE = (247, 250, 252, 255)   # #F7FAFC
SLATE = (169, 184, 204, 255)   # #A9B8CC
EMERALD = (16, 185, 129, 255)  # #10B981
CRIMSON = (239, 68, 68, 255)   # #EF4444
DARK_BG = (16, 17, 20, 255)    # #101114

ICO_SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64)]
MASTER_ICO_SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]


def render_svg_cocoa(svg_path: Path, width: int = 512, height: int = 512) -> Image.Image:
    """Render SVG using macOS AppKit to PIL Image."""
    from AppKit import (
        NSImage,
        NSBitmapImageRep,
        NSGraphicsContext,
        NSMakeRect,
        NSCompositeCopy,
        NSBitmapImageFileTypePNG,
    )

    ns_img = NSImage.alloc().initWithContentsOfFile_(str(svg_path))
    rep = NSBitmapImageRep.alloc().initWithBitmapDataPlanes_pixelsWide_pixelsHigh_bitsPerSample_samplesPerPixel_hasAlpha_isPlanar_colorSpaceName_bytesPerRow_bitsPerPixel_(
        None, width, height, 8, 4, True, False, "NSCalibratedRGBColorSpace", 0, 0
    )
    context = NSGraphicsContext.graphicsContextWithBitmapImageRep_(rep)
    NSGraphicsContext.setCurrentContext_(context)
    ns_img.drawInRect_fromRect_operation_fraction_(
        NSMakeRect(0, 0, width, height),
        NSMakeRect(0, 0, ns_img.size().width, ns_img.size().height),
        NSCompositeCopy,
        1.0,
    )
    NSGraphicsContext.setCurrentContext_(None)
    data = rep.representationUsingType_properties_(NSBitmapImageFileTypePNG, None)
    return Image.open(io.BytesIO(data.bytes()))


def save_ico(image: Image.Image, output_path: Path, sizes=ICO_SIZES):
    """Save PIL Image as multi-resolution .ico file."""
    image.save(output_path, format="ICO", sizes=sizes)
    print(f"  [OK] Saved {output_path.name} ({len(sizes)} resolutions)")


# =============================================================================
# 1. Generate Master Product & Monogram Icons
# =============================================================================
def generate_master_icons():
    print("[*] Generating Master Brand & Product Icons...")
    bridge_svg = BRAND_DIR / "products" / "trading-bridge" / "bridge-symbol.svg"
    monogram_svg = BRAND_DIR / "master" / "ba-monogram-dark.svg"

    if bridge_svg.exists():
        bridge_img = render_svg_cocoa(bridge_svg, 512, 512)
        # Main application icons
        bridge_img.save(ASSETS_DIR / "app_icon.png")
        save_ico(bridge_img, ASSETS_DIR / "app_icon.ico", sizes=MASTER_ICO_SIZES)
        save_ico(bridge_img, ICONS_DIR / "bridge_logo.ico", sizes=MASTER_ICO_SIZES)
        bridge_img.save(ICONS_DIR / "bridge_logo.png")

    if monogram_svg.exists():
        mono_img = render_svg_cocoa(monogram_svg, 512, 512)
        save_ico(mono_img, ICONS_DIR / "ba_monogram.ico", sizes=MASTER_ICO_SIZES)
        mono_img.save(ICONS_DIR / "ba_monogram.png")


# =============================================================================
# 2. Generate Dedicated Action .ico Icons (256x256 supersampled)
# =============================================================================
def draw_play_icon() -> Image.Image:
    img = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # Circle badge background in dark emerald
    d.rounded_rectangle([10, 10, 246, 246], radius=50, fill=(16, 185, 129, 45), outline=EMERALD, width=12)
    # Right pointing play triangle
    points = [(90, 65), (195, 128), (90, 191)]
    d.polygon(points, fill=EMERALD)
    return img


def draw_simulate_icon() -> Image.Image:
    img = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # Circle badge background in dark cyan
    d.rounded_rectangle([10, 10, 246, 246], radius=50, fill=(8, 182, 222, 45), outline=CYAN, width=12)
    # Flask / beaker symbol
    # Neck: x 112 to 144, y 60 to 110
    d.rectangle([114, 55, 142, 110], fill=WHITE)
    d.rounded_rectangle([106, 50, 150, 66], radius=4, fill=WHITE)
    # Body triangle
    points = [(114, 110), (55, 200), (201, 200), (142, 110)]
    d.polygon(points, fill=WHITE)
    # Inner fluid in Signal Cyan / Amber
    liquid_pts = [(100, 135), (68, 190), (188, 190), (156, 135)]
    d.polygon(liquid_pts, fill=CYAN)
    # Bubbles
    d.ellipse([115, 150, 127, 162], fill=AMBER)
    d.ellipse([135, 168, 143, 176], fill=WHITE)
    return img


def draw_stop_icon() -> Image.Image:
    img = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # Circle badge in crimson
    d.rounded_rectangle([10, 10, 246, 246], radius=50, fill=(239, 68, 68, 45), outline=CRIMSON, width=12)
    # Center square
    d.rounded_rectangle([76, 76, 180, 180], radius=16, fill=CRIMSON)
    return img


def draw_settings_icon() -> Image.Image:
    img = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cx, cy = 128, 128
    outer_r = 95
    inner_r = 72
    teeth = 8
    # Draw gear teeth
    for i in range(teeth):
        angle = i * (2 * math.pi / teeth)
        x1 = cx + (outer_r + 14) * math.cos(angle - 0.16)
        y1 = cy + (outer_r + 14) * math.sin(angle - 0.16)
        x2 = cx + (outer_r + 14) * math.cos(angle + 0.16)
        y2 = cy + (outer_r + 14) * math.sin(angle + 0.16)
        x3 = cx + (inner_r) * math.cos(angle + 0.28)
        y3 = cy + (inner_r) * math.sin(angle + 0.28)
        x4 = cx + (inner_r) * math.cos(angle - 0.28)
        y4 = cy + (inner_r) * math.sin(angle - 0.28)
        d.polygon([(x1, y1), (x2, y2), (x3, y3), (x4, y4)], fill=CYAN)

    d.ellipse([cx - outer_r, cy - outer_r, cx + outer_r, cy + outer_r], fill=CYAN)
    # Center hole
    d.ellipse([cx - 40, cy - 40, cx + 40, cy + 40], fill=(0, 0, 0, 0))
    return img


def draw_excel_icon() -> Image.Image:
    img = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # Excel folder / workbook body (forest green / emerald)
    d.rounded_rectangle([30, 40, 226, 216], radius=24, fill=(16, 124, 65, 255), outline=EMERALD, width=8)
    # Sheet grid lines
    d.rectangle([54, 80, 202, 185], fill=(245, 247, 250, 255))
    # Grid cells
    d.line([(54, 115), (202, 115)], fill=(16, 124, 65, 255), width=5)
    d.line([(54, 150), (202, 150)], fill=(16, 124, 65, 255), width=5)
    d.line([(103, 80), (103, 185)], fill=(16, 124, 65, 255), width=5)
    d.line([(152, 80), (152, 185)], fill=(16, 124, 65, 255), width=5)
    # "X" badge on top left
    d.rounded_rectangle([20, 60, 85, 125], radius=10, fill=(16, 124, 65, 255), outline=WHITE, width=4)
    d.line([(35, 75), (70, 110)], fill=WHITE, width=8)
    d.line([(70, 75), (35, 110)], fill=WHITE, width=8)
    return img


def draw_add_icon() -> Image.Image:
    img = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # Circle
    d.rounded_rectangle([15, 15, 241, 241], radius=60, fill=(8, 182, 222, 45), outline=CYAN, width=12)
    # Plus bars
    d.rounded_rectangle([112, 60, 144, 196], radius=10, fill=CYAN)
    d.rounded_rectangle([60, 112, 196, 144], radius=10, fill=CYAN)
    return img


def draw_search_icon() -> Image.Image:
    img = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # Magnifier glass circle
    d.ellipse([45, 45, 165, 165], outline=CYAN, width=22)
    # Handle
    d.line([(145, 145), (215, 215)], fill=CYAN, width=24)
    d.ellipse([200, 200, 225, 225], fill=CYAN)
    return img


def draw_clock_icon() -> Image.Image:
    img = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cx, cy = 128, 128
    # Outer circle
    d.ellipse([25, 25, 231, 231], outline=CYAN, width=16)
    # Hour hand (pointing to 2 o'clock)
    d.line([(cx, cy), (cx + 50, cy - 35)], fill=WHITE, width=14)
    # Minute hand (pointing to 12 o'clock)
    d.line([(cx, cy), (cx, cy - 75)], fill=CYAN, width=12)
    # Center pin
    d.ellipse([cx - 12, cy - 12, cx + 12, cy + 12], fill=AMBER)
    return img


def draw_token_icon() -> Image.Image:
    img = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # Security Key / Shield emblem in Amber
    d.ellipse([50, 60, 150, 160], outline=AMBER, width=20)
    d.ellipse([80, 90, 120, 130], fill=AMBER)
    # Key blade
    d.rectangle([135, 98, 215, 122], fill=AMBER)
    # Teeth
    d.rectangle([180, 122, 196, 152], fill=AMBER)
    d.rectangle([200, 122, 215, 142], fill=AMBER)
    return img


def draw_feed_icon() -> Image.Image:
    img = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # Central transmitter tower / broadcast dot
    cx, cy = 128, 180
    d.ellipse([cx - 16, cy - 16, cx + 16, cy + 16], fill=WHITE)
    # Tower stand
    d.line([(cx, cy), (cx, 220)], fill=WHITE, width=10)
    d.line([(cx - 30, 240), (cx, 215), (cx + 30, 240)], fill=WHITE, width=10)
    # Broadcast arcs
    for r in [55, 95, 135]:
        d.arc([cx - r, cy - r, cx + r, cy + r], start=210, end=330, fill=BLUE, width=14)
    return img


def draw_market_icon() -> Image.Image:
    img = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # Bull candlestick (Emerald)
    d.line([(80, 40), (80, 215)], fill=EMERALD, width=6)
    d.rectangle([60, 80, 100, 175], fill=EMERALD)
    # Bear candlestick (Crimson)
    d.line([(176, 50), (176, 225)], fill=CRIMSON, width=6)
    d.rectangle([156, 95, 196, 190], fill=CRIMSON)
    return img


def draw_terminal_icon() -> Image.Image:
    img = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # Console box
    d.rounded_rectangle([25, 40, 231, 216], radius=20, fill=(20, 22, 28, 255), outline=SLATE, width=8)
    # Prompt >
    d.line([(55, 85), (95, 128), (55, 171)], fill=CYAN, width=12)
    # Underscore cursor _
    d.line([(115, 171), (170, 171)], fill=WHITE, width=12)
    return img


def draw_clear_icon() -> Image.Image:
    img = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # Trash can body
    d.rounded_rectangle([65, 80, 191, 220], radius=16, fill=(40, 42, 50, 255), outline=SLATE, width=10)
    # Can lid
    d.rounded_rectangle([50, 55, 206, 75], radius=6, fill=SLATE)
    d.rounded_rectangle([100, 38, 156, 55], radius=4, fill=SLATE)
    # Vertical rib lines
    d.line([(95, 105), (95, 195)], fill=SLATE, width=8)
    d.line([(128, 105), (128, 195)], fill=SLATE, width=8)
    d.line([(161, 105), (161, 195)], fill=SLATE, width=8)
    return img


# =============================================================================
# Main Execution
# =============================================================================
def main():
    print("=" * 60)
    print("   GENERATING HIGH-RESOLUTION .ICO ASSETS FOR BSA TRADING BRIDGE")
    print("=" * 60)

    # 1. Master product and brand icons
    generate_master_icons()

    # 2. Dedicated action and utility icons
    actions = {
        "play": draw_play_icon(),
        "simulate": draw_simulate_icon(),
        "stop": draw_stop_icon(),
        "settings": draw_settings_icon(),
        "excel": draw_excel_icon(),
        "add": draw_add_icon(),
        "search": draw_search_icon(),
        "clock": draw_clock_icon(),
        "token": draw_token_icon(),
        "feed": draw_feed_icon(),
        "market": draw_market_icon(),
        "terminal": draw_terminal_icon(),
        "clear": draw_clear_icon(),
    }

    print("\n[*] Generating Action & Utility .ico Icons...")
    for name, img in actions.items():
        ico_file = ICONS_DIR / f"{name}.ico"
        png_file = ICONS_DIR / f"{name}.png"
        save_ico(img, ico_file, sizes=ICO_SIZES)
        img.save(png_file)

    print("\n[SUCCESS] All .ico assets generated successfully in assets/icons/")


if __name__ == "__main__":
    main()
