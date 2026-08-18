"""
Colour conversion and perceptual distance.

Colours are handled internally as float RGB triplets in ``[0, 1]``. Matching is
done in CIELAB rather than RGB: RGB distance is not perceptual, so a nearest
colour picked there routinely looks wrong to the eye.
"""

import numpy as np

# sRGB (D65) <-> CIEXYZ
_WHITE = np.array([0.95047, 1.0, 1.08883])
_RGB_TO_XYZ = np.array([
    [0.4124564, 0.3575761, 0.1804375],
    [0.2126729, 0.7151522, 0.0721750],
    [0.0193339, 0.1191920, 0.9503041],
])
_XYZ_TO_RGB = np.linalg.inv(_RGB_TO_XYZ)
_EPSILON = 216 / 24389
_KAPPA = 24389 / 27


def parse(color):
    """
    Normalise a colour to a float RGB triplet in ``[0, 1]``.

    Accepts ``"#RRGGBB"``, ``"#RGB"``, an integer triplet in ``[0, 255]`` or a
    float triplet already in ``[0, 1]``. Integers and floats are told apart by
    dtype, so ``(1, 0, 0)`` is near-black and ``(1.0, 0.0, 0.0)`` is red.
    """
    if isinstance(color, str):
        text = color.lstrip("#")
        if len(text) == 3:
            text = "".join(char * 2 for char in text)
        if len(text) != 6:
            raise ValueError(f"{color!r} is not a hex colour")
        return np.array([int(text[i:i + 2], 16) for i in (0, 2, 4)], dtype=float) / 255

    values = np.asarray(color)
    if values.shape[-1] != 3:
        raise ValueError(f"expected 3 channels, got shape {values.shape}")
    if values.dtype.kind in "iub":
        return values.astype(float) / 255
    return values.astype(float)


def to_hex(rgb):
    """Format a float RGB triplet as ``#RRGGBB``."""
    channels = np.clip(np.asarray(rgb, dtype=float), 0.0, 1.0) * 255
    return "#{:02X}{:02X}{:02X}".format(*(int(round(v)) for v in channels))


def to_lab(rgb):
    """Convert float sRGB to CIELAB, over arrays of any leading shape."""
    rgb = np.clip(np.asarray(rgb, dtype=float), 0.0, 1.0)
    linear = np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)
    xyz = (linear @ _RGB_TO_XYZ.T) / _WHITE
    f = np.where(xyz > _EPSILON, np.cbrt(xyz), (_KAPPA * xyz + 16) / 116)
    return np.stack([
        116 * f[..., 1] - 16,
        500 * (f[..., 0] - f[..., 1]),
        200 * (f[..., 1] - f[..., 2]),
    ], axis=-1)


def from_lab(lab):
    """Convert CIELAB back to float sRGB, clipped to gamut."""
    lab = np.asarray(lab, dtype=float)
    fy = (lab[..., 0] + 16) / 116
    f = np.stack([fy + lab[..., 1] / 500, fy, fy - lab[..., 2] / 200], axis=-1)
    cubed = f ** 3
    xyz = np.where(cubed > _EPSILON, cubed, (116 * f - 16) / _KAPPA) * _WHITE
    linear = xyz @ _XYZ_TO_RGB.T
    srgb = np.where(
        linear <= 0.0031308,
        linear * 12.92,
        1.055 * np.clip(linear, 0.0, None) ** (1 / 2.4) - 0.055,
    )
    return np.clip(srgb, 0.0, 1.0)


def delta_e(lab_a, lab_b):
    """CIE76 perceptual distance between two CIELAB colours."""
    return np.linalg.norm(np.asarray(lab_a) - np.asarray(lab_b), axis=-1)


def is_achromatic(rgb, tolerance:float=0.04):
    """
    True where a colour is grey, black or white within ``tolerance``.

    Used to leave axes, rules and body text alone: they carry no hue, so
    snapping them onto a palette would restyle the whole document.
    """
    rgb = np.asarray(rgb, dtype=float)
    return (rgb.max(axis=-1) - rgb.min(axis=-1)) <= tolerance
