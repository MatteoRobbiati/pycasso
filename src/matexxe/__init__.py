import logging

from matexxe import cmap
from matexxe.cluster import ColorCluster, cluster_hues
from matexxe.cmap import ColormapFit, fit_colormap
from matexxe.fit import PaletteFit, fit
from matexxe.palette import Palette, available
from matexxe.project import Project
from matexxe.workshop import ImagePainter, Painter, supported

# registers the .pdf backend with Painter
from matexxe.paper import PdfPainter, RasterFigure, VectorFigure  # noqa: E402

# library best practice: stay silent unless the caller opts in, either with
# their own logging.basicConfig(...) or with matexxe.enable_logging() below.
logging.getLogger(__name__).addHandler(logging.NullHandler())


def enable_logging(level=logging.INFO):
    """
    Print matexxe's progress to the terminal.

    A convenience for scripts that don't want to reach for
    ``logging.basicConfig`` themselves. Call once, near the top:

        import matexxe
        matexxe.enable_logging()

    Returns the ``matexxe`` logger, in case the caller wants to adjust it
    further (add a file handler, change the level, ...).
    """
    logger = logging.getLogger(__name__)
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
    logger.setLevel(level)
    logger.propagate = False
    return logger


__all__ = [
    "Painter",
    "ImagePainter",
    "PdfPainter",
    "VectorFigure",
    "RasterFigure",
    "Palette",
    "PaletteFit",
    "Project",
    "ColorCluster",
    "cluster_hues",
    "fit",
    "cmap",
    "ColormapFit",
    "fit_colormap",
    "available",
    "supported",
    "enable_logging",
]
