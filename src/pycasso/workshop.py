"""
The painter: anything whose colours can be inspected and changed.

``Painter(path)`` picks an implementation from the file extension, so a bitmap
and a paper are opened the same way and answer the same methods. Backends
register themselves with :func:`backend`, and ``pycasso.paper`` adds PDF
support on import.
"""

import logging
from collections import Counter
from pathlib import Path

import numpy as np
from PIL import Image

from pycasso.cmap import fit_colormap
from pycasso.color import to_hex

log = logging.getLogger(__name__)

_BACKENDS = {}


def backend(*suffixes):
    """Register a Painter implementation for the given file extensions."""
    def register(cls):
        for suffix in suffixes:
            _BACKENDS[suffix.lower()] = cls
        return cls
    return register


def supported():
    """File extensions Painter knows how to open."""
    return sorted(_BACKENDS)


class Painter:
    """
    Artwork whose colours can be inspected and changed.

    Instantiating ``Painter`` directly dispatches on the file extension and
    returns the matching implementation, which is still a ``Painter``.
    """

    def __new__(cls, *args, **kwargs):
        if cls is not Painter:
            return object.__new__(cls)
        path = kwargs.get("imagepath", args[0] if args else None)
        if path is None:
            raise TypeError("Painter() needs a path")
        suffix = Path(path).suffix.lower()
        try:
            implementation = _BACKENDS[suffix]
        except KeyError:
            raise ValueError(
                f"no Painter backend for {suffix or 'files without an extension'}; "
                f"supported: {', '.join(supported())}"
            ) from None
        log.debug("Painter(%r) -> %s", path, implementation.__name__)
        return object.__new__(implementation)

    #: Sub-painters this one contains. A bitmap contains only itself.
    @property
    def figures(self):
        return [self]

    def colors(self):
        """Count of every colour used, keyed by hex string."""
        raise NotImplementedError

    def restyle(self, palette, **options):
        """Snap colours onto ``palette``. Returns ``self`` so calls chain."""
        raise NotImplementedError

    def save(self, title:str = None, format:str = None):
        """Write the artwork out."""
        raise NotImplementedError


@backend(".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tif", ".tiff", ".webp")
class ImagePainter(Painter):
    def __init__(self, imagepath:str):
        """
        Image processing tool.

        Args:
            image: path to the image which has to be processed.
        """
        self.imagepath = imagepath
        with Image.open(imagepath) as handle:
            # convert() drops the attribute, so read it while the file is open
            self.source_format = handle.format
            image = handle.convert("RGBA")
        self.set_image(image)
        # make a copy of the original image
        self.original_image = image.copy()
        self.changes = None
        # so a standalone image conforms to the same minimal "figure" contract
        # (.name) as a PDF's VectorFigure/RasterFigure -- used by PaletteFit.skip
        self.name = imagepath
        log.info("opened %s (%dx%d px, %s)", imagepath, self.width, self.height, self.format)

    @classmethod
    def from_image(cls, image:Image, imagepath:str = None):
        """Build a painter around an in-memory image rather than a file."""
        painter = cls.__new__(cls)
        painter.imagepath = imagepath
        painter.source_format = image.format
        painter.set_image(image.convert("RGBA"))
        painter.original_image = painter.image.copy()
        painter.changes = None
        painter.name = imagepath
        log.debug("wrapped in-memory image as painter (%dx%d px)", painter.width, painter.height)
        return painter

    def set_image(self, image:Image):
        """Set new image as default."""
        self.image = image
        self.format = image.format or self.source_format
        self.pixels = image.load()
        self.width, self.height = image.size

    def _as_array(self):
        """Pixel data as a ``(height, width, 4)`` array of uint8 RGBA values."""
        return np.array(self.image)

    def _set_array(self, array):
        """Adopt ``array`` as the current image."""
        self.set_image(Image.fromarray(array))

    def _match(self, array, color:tuple, shadow_range:int=None, min_alpha:int=1):
        """
        Boolean mask selecting the pixels that ``color`` should act on.

        Pixels below ``min_alpha`` are excluded whatever their RGB values are:
        a transparent pixel stores an arbitrary colour (encoders usually write
        black), so matching on RGB alone would select the whole background.
        """
        rgb, opacity = array[:, :, :3], array[:, :, 3]
        target = np.asarray(color, dtype=np.int16)
        if shadow_range is None:
            matches = (rgb == target).all(axis=-1)
        else:
            matches = (np.abs(rgb.astype(np.int16) - target) <= shadow_range).all(axis=-1)
        return matches & (opacity >= min_alpha)

    def resize(self, size:tuple):
        """Resize image."""
        image = self.image.resize(size)
        self.set_image(image)

    def remove_color(self, color:tuple, shadow_range:int=None, min_alpha:int=1):
        """
        Remove color provided in RGB form.

        Args:
            color: tuple containing the RGB code of the color to be removed;
            shadow_range: tolerance applied to each channel when matching;
            min_alpha: pixels less opaque than this are skipped. Already
                transparent pixels carry an arbitrary RGB value (often black),
                so without this guard they match every color.
        """
        array = self._as_array()
        array[self._match(array, color, shadow_range, min_alpha)] = (0, 0, 0, 0)
        self._set_array(array)

    def replace_colors(self, old_color:tuple, new_color:tuple, alpha:int = 255, min_alpha:int = 1):
        """
        Replace ``old_color`` with ``new_color``.

        Args:
            old_color: tuple containing RGB code of the color to be replaced;
            new_color: tuple containing RGB code of the new color to be set;
            alpha: opacity of the new color. Pass ``None`` to keep each pixel's
                original opacity, which preserves antialiased edges;
            min_alpha: pixels less opaque than this are skipped. Already
                transparent pixels carry an arbitrary RGB value (often black),
                so without this guard they match every color.
        """
        if alpha is not None and (alpha < 0 or alpha > 255):
            raise ValueError(f"Opacity value {alpha} is not allowed. Please set one integer in [0, 255].")

        array = self._as_array()
        mask = self._match(array, old_color, min_alpha=min_alpha)
        array[mask, :3] = new_color
        if alpha is not None:
            array[mask, 3] = alpha
        self._set_array(array)

    def colors(self, min_alpha:int = 1):
        """Count of every visible colour in the image, keyed by hex."""
        array = self._as_array()
        visible = array[array[:, :, 3] >= min_alpha][:, :3]
        if not len(visible):
            return Counter()
        values, counts = np.unique(visible, axis=0, return_counts=True)
        return Counter({to_hex(value / 255): int(count) for value, count in zip(values, counts)})

    def restyle(self, palette, mode:str = "snap", keep_greys:bool = True,
                grey_tolerance:float = 0.04, min_alpha:int = 1, recolor_colormaps:bool = True):
        """
        Snap every visible pixel onto ``palette``.

        Args:
            palette: the target :class:`~pycasso.palette.Palette`;
            mode: how much of the original colour to keep -- see
                :meth:`Palette.map <pycasso.palette.Palette.map>`;
            keep_greys: leave achromatic pixels alone, so axes and text keep
                their neutral tone;
            grey_tolerance: how close to grey a colour must be to count;
            min_alpha: pixels less opaque than this are left untouched;
            recolor_colormaps: if ``palette`` flagged this whole image as a
                continuous colormap (see ``.skip``, set by
                :func:`~pycasso.fit.fit`), recolour it separately with
                :func:`~pycasso.cmap.fit_colormap` instead of leaving it
                untouched. That reuses ``palette``'s own assigned colours as
                the colormap's anchors, so it ends up built from the same
                colours the rest of the document settled on.
        """
        if self.name in getattr(palette, "skip", ()):
            if recolor_colormaps:
                try:
                    colormap_fit = fit_colormap(self, palette)
                except ValueError as error:
                    log.warning("%s: could not build a colormap fit (%s); leaving untouched", self.name, error)
                else:
                    log.info("%s: recolouring as a continuous colormap", self.name)
                    return self.restyle(colormap_fit, mode=mode, keep_greys=keep_greys,
                                         grey_tolerance=grey_tolerance, min_alpha=min_alpha)
            log.info("%s: skipped (flagged by pycasso.fit())", self.name)
            self.changes = Counter()
            return self

        array = self._as_array()
        rgb = array[:, :, :3] / 255.0
        mapped, changed = palette.map(
            rgb,
            mode=mode,
            keep_greys=keep_greys,
            grey_tolerance=grey_tolerance,
        )
        changed &= array[:, :, 3] >= min_alpha

        self.changes = Counter()
        if changed.any():
            before = array[:, :, :3][changed]
            after = (mapped[changed] * 255).round().astype(np.uint8)
            pairs, counts = np.unique(np.hstack([before, after]), axis=0, return_counts=True)
            for pair, count in zip(pairs, counts):
                self.changes[(to_hex(pair[:3] / 255), to_hex(pair[3:] / 255))] += int(count)
            array[:, :, :3] = np.where(
                changed[..., None], (mapped * 255).round().astype(np.uint8), array[:, :, :3]
            )
            self._set_array(array)
            log.info(
                "%s: restyled %s pixels across %d colour mappings (palette=%r, mode=%r)",
                self.imagepath or "<image>", f"{sum(self.changes.values()):,}",
                len(self.changes), palette.name, mode,
            )
        else:
            log.warning(
                "%s: restyle changed nothing (palette=%r, mode=%r, keep_greys=%s) -- "
                "check the palette against the image's actual colours (see .colors()), "
                "or relax grey_tolerance",
                self.imagepath or "<image>", palette.name, mode, keep_greys,
            )
        return self

    def save(self, title:str = None, format:str = None):
        """Save processed image."""
        if format is None:
            format = self.format
        if title is None:
            title = f"{self.imagepath}_processed"
        self.image.save(fp=title, format=format)
        log.info("saved %s", title)

    def back_to_original(self):
        """Restore initial image."""
        self.set_image(self.original_image.copy())
        log.debug("restored %s to its original colours", self.imagepath or "<image>")

    def __repr__(self):
        return f"ImagePainter({self.imagepath!r}, {self.width}x{self.height})"
