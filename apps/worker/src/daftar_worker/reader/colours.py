"""Resolve OOXML colours (rgb, theme plus tint, indexed) to #RRGGBB."""

import colorsys
from typing import Any

from openpyxl.styles.colors import COLOR_INDEX


# The Office default theme, used when a file carries no theme part. Order is the theme index order.
DEFAULT_THEME = [
    "FFFFFF", "000000", "E7E6E6", "44546A", "4472C4", "ED7D31",
    "A5A5A5", "FFC000", "5B9BD5", "70AD47", "0563C1", "954F72",
]  # fmt: skip


def apply_tint(rgb: str, tint: float) -> str:
    red, green, blue = (int(rgb[i : i + 2], 16) / 255 for i in (0, 2, 4))
    hue, light, sat = colorsys.rgb_to_hls(red, green, blue)
    light = light * (1 + tint) if tint < 0 else light * (1 - tint) + tint
    channels = colorsys.hls_to_rgb(hue, min(max(light, 0.0), 1.0), sat)
    return "".join(f"{round(channel * 255):02X}" for channel in channels)


def resolve_parts(
    *,
    rgb: Any = None,
    theme: Any = None,
    indexed: Any = None,
    tint: Any = 0.0,
    palette: list[str],
    custom_index: Any = None,
) -> str | None:
    base: str | None = None
    if isinstance(rgb, str) and len(rgb) in (6, 8):
        base = rgb[-6:].upper()
    elif isinstance(theme, int) and 0 <= theme < len(palette):
        base = palette[theme]
    elif isinstance(indexed, int):
        table = custom_index or COLOR_INDEX
        if 0 <= indexed < len(table) and indexed < 64:  # 64 and 65 are the system colours.
            base = str(table[indexed])[-6:].upper()
    if base is None:
        return None
    try:
        int(base, 16)
    except ValueError:
        return None
    return "#" + (apply_tint(base, float(tint)) if tint else base)


def resolve(color: Any, palette: list[str], custom_index: Any = None) -> str | None:
    """Resolve an openpyxl Color. None means no usable colour (automatic or system)."""
    if color is None:
        return None
    kind = getattr(color, "type", None)
    return resolve_parts(
        rgb=color.rgb if kind == "rgb" else None,
        theme=color.theme if kind == "theme" else None,
        indexed=color.indexed if kind == "indexed" else None,
        tint=getattr(color, "tint", 0.0),
        palette=palette,
        custom_index=custom_index,
    )
