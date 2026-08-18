"""
PDF backend for :class:`~matexxe.workshop.Painter`.

Figures placed with ``\\includegraphics`` land in their own Form XObject, and
bitmaps in their own Image XObject. Restyling only those objects means the body
text of a paper cannot be touched by accident: the colour operators that set it
live in the page content stream, which is never rewritten here.
"""

import logging
import zlib
from collections import Counter

import numpy as np
import pikepdf
from pikepdf import Name, Operator, parse_content_stream, unparse_content_stream

from matexxe.cmap import fit_colormap
from matexxe.color import to_hex
from matexxe.workshop import ImagePainter, Painter, backend

log = logging.getLogger(__name__)

# Colour operators, split by whether they set the fill or the stroke colour.
_FILL_OPS = {"rg", "g", "k", "sc", "scn"}
_STROKE_OPS = {"RG", "G", "K", "SC", "SCN"}
_COLOUR_OPS = _FILL_OPS | _STROKE_OPS

#: XObjects ignored by default. arXiv stamps every page with a watermark.
DEFAULT_SKIP = ("ArXivWatermark",)


def _cmyk_to_rgb(cyan, magenta, yellow, black):
    return np.array([(1 - cyan) * (1 - black),
                     (1 - magenta) * (1 - black),
                     (1 - yellow) * (1 - black)])


def _operands_to_rgb(operator:str, operands):
    """
    Read colour operands as float RGB, or ``None`` if they are not a colour.

    ``sc``/``scn`` are interpreted by operand count rather than by resolving
    the colourspace in force, which would need full graphics-state tracking.
    Operands that are not numbers at all -- a pattern name -- are skipped.
    """
    try:
        values = [float(operand) for operand in operands]
    except (TypeError, ValueError):
        return None

    kind = operator.lower()
    if kind == "g" and len(values) == 1:
        return np.array(values * 3)
    if kind == "rg" and len(values) == 3:
        return np.array(values)
    if kind == "k" and len(values) == 4:
        return _cmyk_to_rgb(*values)
    if kind in ("sc", "scn"):
        if len(values) == 1:
            return np.array(values * 3)
        if len(values) == 3:
            return np.array(values)
        if len(values) == 4:
            return _cmyk_to_rgb(*values)
    return None


def _reachable(container, subtype, seen, path=""):
    """
    Yield ``(path, obj)`` for every XObject of ``subtype`` reachable from
    ``container``, once each.

    ``path`` threads the nesting into a readable label, e.g. ``/Im4/x9``, so
    a figure's own eight nested icons don't all report under its own name.
    """
    resources = container.get("/Resources", {})
    for name, obj in resources.get("/XObject", {}).items():
        key = obj.objgen
        if key in seen:
            continue
        label = f"{path}/{str(name).lstrip('/')}" if path else str(name)
        kind = str(obj.get("/Subtype", ""))
        if kind == subtype:
            seen.add(key)
            yield label, obj
        if kind == "/Form":
            # nested artwork: matplotlib puts markers and insets in sub-forms
            yield from _reachable(obj, subtype, seen, path=label)


class PdfFigure(Painter):
    def __init__(self, name:str, page:int, obj):
        """
        One figure inside a paper.

        Args:
            name: XObject name as it appears in the page resources;
            page: 1-based number of the page the figure sits on;
            obj: the underlying pikepdf object.
        """
        self.name = name
        self.page = page
        self.obj = obj
        self.changes = None

    def save(self, title:str = None, format:str = None):
        raise TypeError("a figure is saved with the paper that contains it")

    def __repr__(self):
        return f"{type(self).__name__}({self.name!r}, page={self.page})"


class PageFigure(PdfFigure):
    """
    A standalone asset's own page content stream.

    A page assembled by LaTeX draws its body text directly in the page's own
    content stream, which restyling must never touch. A standalone figure
    file exported straight from matplotlib/TikZ (typical of an
    ``\\includegraphics`` target opened on its own, as :class:`~matexxe.project.Project`
    does) often has no such distinction: axes, frames and paths can be drawn
    directly on the page rather than wrapped in a Form XObject, so the page
    *is* the figure. This type covers only the page's own operators --
    nested Form/Image XObjects are already covered by their own
    :class:`VectorFigure`/:class:`RasterFigure`, so this never recurses into
    them and nothing is double-counted.
    """

    def __init__(self, name:str, page:int, obj, pdf):
        super().__init__(name, page, obj)
        # a Page, unlike a Form/Image XObject, isn't itself a writable stream
        # -- its /Contents can even be an array of several -- so rewriting it
        # needs the owning Pdf to mint a fresh, single replacement stream
        self._pdf = pdf

    def colors(self):
        tally = Counter()
        for instruction in parse_content_stream(self.obj):
            operator = str(instruction.operator)
            if operator not in _COLOUR_OPS:
                continue
            rgb = _operands_to_rgb(operator, instruction.operands)
            if rgb is not None:
                tally[to_hex(rgb)] += 1
        return tally

    def restyle(self, palette, **options):
        self.changes = _restyle_stream(self.obj, palette, options, pdf=self._pdf)
        return self


class VectorFigure(PdfFigure):
    """Drawn artwork, recoloured by rewriting its content stream operators."""

    def _streams(self):
        seen = {self.obj.objgen}
        return [self.obj, *(obj for _, obj in _reachable(self.obj, "/Form", seen, path=self.name))]

    def _bitmaps(self):
        # a vector figure can still embed bitmaps, e.g. a rasterised heatmap
        return [RasterFigure(label, self.page, obj)
                for label, obj in _reachable(self.obj, "/Image", set(), path=self.name)]

    def colors(self):
        tally = Counter()
        for stream in self._streams():
            for instruction in parse_content_stream(stream):
                operator = str(instruction.operator)
                if operator not in _COLOUR_OPS:
                    continue
                rgb = _operands_to_rgb(operator, instruction.operands)
                if rgb is not None:
                    tally[to_hex(rgb)] += 1
        for bitmap in self._bitmaps():
            tally.update(bitmap.colors())
        return tally

    def restyle(self, palette, **options):
        self.changes = Counter()
        for stream in self._streams():
            self.changes.update(_restyle_stream(stream, palette, options))
        for bitmap in self._bitmaps():
            self.changes.update(bitmap.restyle(palette, **options).changes)
        return self


class RasterFigure(PdfFigure):
    """An embedded bitmap, recoloured by handing its pixels to a Painter."""

    def _painter(self):
        """The bitmap as an in-memory ImagePainter, or None if unreadable."""
        try:
            image = pikepdf.PdfImage(self.obj).as_pil_image()
        except Exception as error:
            log.warning(
                "could not decode image %s on page %d (%s); skipping",
                self.name, self.page, error,
            )
            return None
        return ImagePainter.from_image(image, imagepath=self.name)

    def colors(self):
        painter = self._painter()
        return painter.colors() if painter else Counter()

    def restyle(self, palette, **options):
        self.changes = Counter()
        painter = self._painter()
        if painter is None:
            return self
        painter.restyle(palette, **options)
        if not painter.changes:
            return self
        self.changes.update(painter.changes)

        rgba = np.array(painter.image)
        self.obj.write(zlib.compress(rgba[:, :, :3].tobytes()), filter=Name.FlateDecode)
        self.obj.ColorSpace = Name.DeviceRGB
        self.obj.BitsPerComponent = 8
        self.obj.Width, self.obj.Height = painter.width, painter.height
        for key in ("/Decode", "/DecodeParms"):
            if key in self.obj:
                del self.obj[key]
        return self


def _restyle_stream(stream, palette, options, pdf=None):
    """
    Rewrite the colour operators of one content stream in place.

    ``stream`` is normally a Form/Image XObject, itself a writable stream.
    A Page is not one -- and its ``/Contents`` can be an array of several --
    so when ``pdf`` is given, ``stream`` is instead treated as a Page and
    rewritten by minting one fresh replacement stream via ``pdf``.
    """
    instructions = []
    changes = Counter()

    for instruction in parse_content_stream(stream):
        operator = str(instruction.operator)
        operands, emit = instruction.operands, instruction.operator

        if operator in _COLOUR_OPS:
            rgb = _operands_to_rgb(operator, operands)
            if rgb is not None:
                mapped, changed = palette.map(rgb, **options)
                if changed:
                    changes[(to_hex(rgb), to_hex(mapped))] += 1
                    # k/K and scn are re-emitted as plain RGB. That is legal,
                    # and saves resolving the colourspace they were set in.
                    emit = Operator("rg" if operator in _FILL_OPS else "RG")
                    operands = [float(round(value, 6)) for value in mapped]

        instructions.append((operands, emit))

    if changes:
        data = unparse_content_stream(instructions)
        if pdf is None:
            stream.write(zlib.compress(data), filter=Name.FlateDecode)
        else:
            new_stream = pdf.make_stream(b"")
            new_stream.write(zlib.compress(data), filter=Name.FlateDecode)
            stream.Contents = new_stream
    return changes


@backend(".pdf")
class PdfPainter(Painter):
    def __init__(self, imagepath:str, skip=DEFAULT_SKIP):
        """
        A PDF whose figures can be inspected and restyled.

        Args:
            imagepath: path to the PDF;
            skip: XObject names to ignore, matched without the leading slash.
        """
        self.imagepath = imagepath
        # allow_overwriting_input: Painter.save() defaults to writing back to
        # the same path it opened (e.g. Project flushing an asset in place)
        self.pdf = pikepdf.open(imagepath, allow_overwriting_input=True)
        self.skip = tuple(skip)
        self.changes = None
        log.info("opened %s: %d pages", imagepath, len(self.pdf.pages))

    @property
    def figures(self):
        """
        Every figure in the document, in page order.

        A single-page document is assumed to be a standalone figure asset
        (matplotlib/TikZ export) rather than an assembled paper, so its own
        page content stream is included as a :class:`PageFigure` alongside
        whatever Form/Image XObjects it references -- see its docstring for
        why that would be wrong to do for a multi-page paper.
        """
        found = []
        standalone = len(self.pdf.pages) == 1
        for number, page in enumerate(self.pdf.pages, start=1):
            if standalone:
                found.append(PageFigure(f"page{number}", number, page, self.pdf))
            resources = page.get("/Resources", {})
            for name, obj in resources.get("/XObject", {}).items():
                if str(name).lstrip("/") in self.skip:
                    continue
                subtype = str(obj.get("/Subtype", ""))
                if subtype == "/Form":
                    found.append(VectorFigure(str(name), number, obj))
                elif subtype == "/Image":
                    found.append(RasterFigure(str(name), number, obj))
        return found

    def colors(self):
        """Count of every colour used across all figures, keyed by hex."""
        figures = self.figures
        log.info("scanning %d figures in %s for colours", len(figures), self.imagepath)
        tally = Counter()
        for figure in figures:
            tally.update(figure.colors())
        log.info("found %d distinct colours across %d figures", len(tally), len(figures))
        return tally

    def restyle(self, palette, mode:str = "snap", keep_greys:bool = True,
                grey_tolerance:float = 0.04, recolor_colormaps:bool = True):
        """
        Snap every figure onto ``palette``.

        Args:
            palette: the target :class:`~matexxe.palette.Palette`;
            mode: how much of the original colour to keep -- see
                :meth:`Palette.map <matexxe.palette.Palette.map>`;
            keep_greys: leave achromatic colours alone, so axes, rules and
                labels keep their original neutral tone;
            grey_tolerance: how close to grey a colour must be to count;
            recolor_colormaps: figures ``palette`` flagged as a continuous
                colormap (see ``.skip``, set by :func:`~matexxe.fit.fit`) are
                recoloured separately with :func:`~matexxe.cmap.fit_colormap`
                instead of being left untouched. That reuses ``palette``'s
                own assigned colours as the colormap's anchors, so a
                colourbar ends up built from the same colours the rest of
                the document settled on. Set to ``False`` to leave them
                untouched instead.
        """
        options = dict(mode=mode, keep_greys=keep_greys, grey_tolerance=grey_tolerance)
        figures = self.figures
        name = getattr(palette, "name", repr(palette))

        skip = set(getattr(palette, "skip", ()))
        colormap_figures = []
        if skip:
            colormap_figures = [figure for figure in figures if figure.name in skip]
            figures = [figure for figure in figures if figure.name not in skip]
            log.info("%d figure(s) flagged as continuous colormaps by matexxe.fit(): %s",
                      len(colormap_figures), ", ".join(sorted(f.name for f in colormap_figures)))

        log.info("restyling %d figures in %s with palette %r (mode=%r)", len(figures), self.imagepath, name, mode)

        self.changes = Counter()
        for figure in figures:
            changed = figure.restyle(palette, **options).changes
            if changed:
                log.info("  %s: %s recolourings (%d distinct mappings)",
                          figure, f"{sum(changed.values()):,}", len(changed))
            else:
                log.debug("  %s: no matching colours", figure)
            self.changes.update(changed)

        if recolor_colormaps:
            for figure in colormap_figures:
                try:
                    colormap_fit = fit_colormap(figure, palette)
                except ValueError as error:
                    log.warning("could not build a colormap fit for %s (%s); leaving it untouched", figure, error)
                    continue
                changed = figure.restyle(colormap_fit, **options).changes
                if changed:
                    log.info("  %s: %s recolourings (%d distinct mappings) [continuous colormap]",
                              figure, f"{sum(changed.values()):,}", len(changed))
                self.changes.update(changed)

        if self.changes:
            log.info("done: %s recolourings across %d distinct mappings",
                      f"{sum(self.changes.values()):,}", len(self.changes))
        else:
            log.warning(
                "restyle changed nothing in %s (palette=%r, mode=%r) -- "
                "check the palette against the document's actual colours (see .colors())",
                self.imagepath, name, mode,
            )
        return self

    def save(self, title:str = None, format:str = None):
        """Write the document out."""
        if title is None:
            title = f"{self.imagepath}_processed"
        self.pdf.save(title)
        log.info("saved %s", title)

    def close(self):
        self.pdf.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def __repr__(self):
        return f"PdfPainter({self.imagepath!r}, {len(self.pdf.pages)} pages)"
