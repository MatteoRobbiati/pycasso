"""
Named colour palettes and nearest-colour mapping.

A palette is an ordered list of colours plus a name. Built-in palettes ship as
TOML files next to this module; user palettes are ordinary TOML files loaded
from anywhere, so a project can keep its own house style under version control.
"""

import logging
from pathlib import Path

import numpy as np

try:
    import tomllib
except ModuleNotFoundError:  # python < 3.11
    import tomli as tomllib

from pycasso.color import delta_e, from_lab, is_achromatic, parse, to_hex, to_lab

log = logging.getLogger(__name__)

_BUILTIN_DIR = Path(__file__).parent / "palettes"


def available():
    """Names of the palettes bundled with pycasso."""
    return sorted(path.stem for path in _BUILTIN_DIR.glob("*.toml"))


class Palette:
    def __init__(self, name:str, colors, description:str = ""):
        """
        An ordered set of colours to map artwork onto.

        Args:
            name: identifier used when loading and reporting;
            colors: iterable of hex strings or RGB triplets;
            description: free text shown in ``repr`` and audit reports.
        """
        if not len(colors):
            raise ValueError(f"palette {name!r} has no colours")
        self.name = name
        self.description = description
        self.rgb = np.array([parse(entry) for entry in colors])
        self.colors = tuple(to_hex(entry) for entry in self.rgb)
        self.lab = to_lab(self.rgb)
        chroma = np.hypot(self.lab[:, 1], self.lab[:, 2])
        self._chromatic = np.flatnonzero(chroma > 1.0)
        log.debug(
            "built palette %r: %d colours (%d chromatic, %d achromatic)",
            name, len(self), len(self._chromatic), len(self) - len(self._chromatic),
        )

    @property
    def supports_hue(self):
        """Whether this palette has at least one non-grey colour to match hue against."""
        return len(self._chromatic) > 0

    @classmethod
    def load(cls, name:str):
        """Load a built-in palette by name."""
        path = _BUILTIN_DIR / f"{name}.toml"
        if not path.is_file():
            raise KeyError(f"unknown palette {name!r}; available: {', '.join(available())}")
        log.debug("loading built-in palette %r from %s", name, path)
        return cls.from_file(path)

    @classmethod
    def from_file(cls, path):
        """Load a palette from a TOML file."""
        path = Path(path)
        with path.open("rb") as handle:
            data = tomllib.load(handle)
        return cls(
            name=data.get("name", path.stem),
            colors=data["colors"],
            description=data.get("description", ""),
        )

    def nearest_index(self, color):
        """Index of the palette entry perceptually closest to ``color``."""
        return int(np.argmin(delta_e(self.lab, to_lab(parse(color)))))

    def nearest(self, color):
        """Hex of the palette entry perceptually closest to ``color``."""
        return self.colors[self.nearest_index(color)]

    def nearest_indices(self, rgb):
        """
        Nearest palette entry for an ``(..., 3)`` array of float RGB.

        Distances are accumulated one palette entry at a time rather than as a
        single ``(pixels, entries)`` array, which would need gigabytes on a
        full-page bitmap.
        """
        lab = to_lab(rgb)
        best_distance = np.full(lab.shape[:-1], np.inf)
        best_index = np.zeros(lab.shape[:-1], dtype=np.intp)
        for index, entry in enumerate(self.lab):
            distance = delta_e(lab, entry)
            closer = distance < best_distance
            best_distance = np.where(closer, distance, best_distance)
            best_index = np.where(closer, index, best_index)
        return best_index

    def nearest_hue_indices(self, lab):
        """
        Nearest palette entry by hue angle alone, for CIELAB input.

        Lightness and chroma are ignored, so a pale cream and a saturated gold
        both land on the palette's yellow rather than on whichever entry
        happens to sit closest in full CIELAB. Achromatic palette entries are
        excluded: their hue angle is noise.
        """
        if not self.supports_hue:
            raise ValueError(
                f"palette {self.name!r} is entirely achromatic (e.g. a grayscale "
                "palette), so mode='hue' has nothing to match hue against; "
                "use mode='snap' or 'tint' instead"
            )

        source = np.arctan2(lab[..., 2], lab[..., 1])
        best_distance = np.full(lab.shape[:-1], np.inf)
        best_index = np.zeros(lab.shape[:-1], dtype=np.intp)
        for index in self._chromatic:
            angle = np.arctan2(self.lab[index, 2], self.lab[index, 1])
            # shortest way round the hue circle
            distance = np.abs(np.arctan2(np.sin(source - angle), np.cos(source - angle)))
            closer = distance < best_distance
            best_distance = np.where(closer, distance, best_distance)
            best_index = np.where(closer, index, best_index)
        return best_index

    def map(self, rgb, mode:str = "snap", keep_greys:bool = True,
            grey_tolerance:float = 0.04):
        """
        Map an ``(..., 3)`` array of float RGB onto this palette.

        Args:
            rgb: colours to map;
            mode: how much of the original colour to keep --

                ``"snap"``
                    replace with the exact palette colour. Strongest
                    standardisation, but flattens tints and shading.
                ``"tint"``
                    palette hue and chroma, original lightness. Pale fills
                    stay pale, though colours close in lightness can merge.
                ``"hue"``
                    palette hue only, original lightness *and* chroma. Gentlest:
                    the whole tonal structure of the figure survives and only
                    the hues move onto the palette. Needs at least one
                    chromatic colour in the palette -- see :attr:`supports_hue`;
                    raises on a purely achromatic palette such as ``grayscale``.

            keep_greys: leave achromatic colours untouched, so axes, rules and
                text survive unchanged;
            grey_tolerance: how close to grey a colour must be to count.

        Returns:
            A tuple of the mapped array and a boolean mask of what changed.
        """
        rgb = np.asarray(rgb, dtype=float)
        lab = to_lab(rgb)

        if mode == "hue":
            target = self.lab[self.nearest_hue_indices(lab)]
            # adopt the palette's hue angle, keep the original L* and chroma
            chroma = np.hypot(lab[..., 1], lab[..., 2])
            angle = np.arctan2(target[..., 2], target[..., 1])
            mapped = from_lab(np.stack(
                [lab[..., 0], chroma * np.cos(angle), chroma * np.sin(angle)], axis=-1
            ))
        elif mode == "tint":
            target = self.lab[self.nearest_indices(rgb)].copy()
            target[..., 0] = lab[..., 0]
            mapped = from_lab(target)
        elif mode == "snap":
            mapped = self.rgb[self.nearest_indices(rgb)]
        else:
            raise ValueError(f"unknown mode {mode!r}; expected 'snap', 'tint' or 'hue'")

        changed = np.ones(rgb.shape[:-1], dtype=bool)
        if keep_greys:
            changed &= ~is_achromatic(rgb, grey_tolerance)
        return np.where(changed[..., None], mapped, rgb), changed

    def __len__(self):
        return len(self.colors)

    def __iter__(self):
        return iter(self.colors)

    def __getitem__(self, index):
        return self.colors[index]

    def __repr__(self):
        return f"Palette({self.name!r}, {len(self)} colours)"
