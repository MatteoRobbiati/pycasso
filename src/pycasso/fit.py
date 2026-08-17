"""
Fit a palette to the colours a document actually uses.

Mapping every original colour independently onto the nearest palette entry
(:meth:`Palette.map <pycasso.palette.Palette.map>`) works pixel by pixel and
has no notion of "how many colours does this document really need" -- a
palette with too many entries can spread near-identical original hues across
several outputs, and one with too few silently collapses distinct series onto
the same replacement.

:func:`fit` decides that question first:

1. cluster each figure's colours independently -- shades, tints and partial
   transparency of one series colour count once -- and report the largest
   count found in any single figure as a diagnostic: how many colours does
   the busiest figure need to keep visually distinct. Figures that look like
   a continuous colormap (a heatmap, a density plot) rather than a handful
   of series colours are excluded here and left untouched by ``restyle()``
   -- see :func:`~pycasso.cluster.looks_continuous`;
2. cluster the whole document's colours together in one pass, so the same
   real-world series colour is recognised consistently across figures
   rather than independently per figure;
3. assign each document-wide colour the *nearest hue* available in the
   palette. This is deterministic and stable: a given original hue always
   gets the same replacement regardless of what other colours exist
   elsewhere in the document, so adding or removing a figure never
   reshuffles colours that were already assigned.

The result is a :class:`PaletteFit`, which answers ``.map()`` exactly like a
:class:`~pycasso.palette.Palette` and can be passed anywhere one is expected.
"""

import logging
from collections import Counter

import numpy as np

from pycasso.cluster import (
    DEFAULT_CLUSTER_GREY_TOLERANCE,
    DEFAULT_MERGE_DEGREES,
    assign_families,
    cluster_hues,
    describe,
    looks_continuous,
)
from pycasso.color import from_lab, is_achromatic, to_hex, to_lab

log = logging.getLogger(__name__)


class PaletteFit:
    """A palette assigned to match one document's own colours."""

    def __init__(self, clusters, assigned_rgb, source_name:str, skip=()):
        self.clusters = clusters
        self.assigned = np.asarray(assigned_rgb, dtype=float)
        self.name = f"{source_name} (fit to {len(clusters)} colour{'' if len(clusters) == 1 else 's'})"
        self.skip = frozenset(skip)
        self._cluster_lab = np.array([c.lab for c in clusters]) if clusters else np.zeros((0, 3))

    def _nearest_cluster(self, lab):
        """
        Classify colours by nearest *original* cluster hue.

        The comparison is against the document's own discovered hues, not
        against the target palette: the two are unrelated sets of hues, so
        classifying against the target would place decision boundaries in
        the wrong place.
        """
        hue = np.arctan2(lab[..., 2], lab[..., 1])
        centers = np.arctan2(self._cluster_lab[:, 2], self._cluster_lab[:, 1])
        best_distance = np.full(lab.shape[:-1], np.inf)
        best_index = np.zeros(lab.shape[:-1], dtype=np.intp)
        for index, center in enumerate(centers):
            distance = np.abs(np.arctan2(np.sin(hue - center), np.cos(hue - center)))
            closer = distance < best_distance
            best_distance = np.where(closer, distance, best_distance)
            best_index = np.where(closer, index, best_index)
        return best_index

    def map(self, rgb, mode:str = "hue", keep_greys:bool = True, grey_tolerance:float = 0.04):
        """Same contract as :meth:`Palette.map <pycasso.palette.Palette.map>`."""
        rgb = np.asarray(rgb, dtype=float)
        lab = to_lab(rgb)
        index = self._nearest_cluster(lab)
        target_lab = to_lab(self.assigned)[index]

        if mode == "hue":
            chroma = np.hypot(lab[..., 1], lab[..., 2])
            angle = np.arctan2(target_lab[..., 2], target_lab[..., 1])
            mapped = from_lab(np.stack(
                [lab[..., 0], chroma * np.cos(angle), chroma * np.sin(angle)], axis=-1
            ))
        elif mode == "tint":
            target = target_lab.copy()
            target[..., 0] = lab[..., 0]
            mapped = from_lab(target)
        elif mode == "snap":
            mapped = self.assigned[index]
        else:
            raise ValueError(f"unknown mode {mode!r}; expected 'snap', 'tint' or 'hue'")

        changed = np.ones(rgb.shape[:-1], dtype=bool)
        if keep_greys:
            changed &= ~is_achromatic(rgb, grey_tolerance)
        return np.where(changed[..., None], mapped, rgb), changed

    def __repr__(self):
        return f"PaletteFit({len(self.clusters)} colours, {self.name!r})"


def fit(document, palette, merge_degrees:float = DEFAULT_MERGE_DEGREES,
        grey_tolerance:float = DEFAULT_CLUSTER_GREY_TOLERANCE):
    """
    Assign ``palette`` colours to match ``document``'s own colours.

    Args:
        document: anything with a ``.figures`` list of objects answering
            ``.colors()`` -- a :class:`~pycasso.paper.PdfPainter` or a plain
            :class:`~pycasso.workshop.ImagePainter`;
        palette: the target :class:`~pycasso.palette.Palette` to assign
            colours from;
        merge_degrees: hue tolerance used to treat two colours as the same
            series -- see :func:`~pycasso.cluster.cluster_hues`;
        grey_tolerance: how close to grey a colour must be to be excluded
            from the colour count. This only governs *counting*; the later
            ``document.restyle(fitted, ...)`` call has its own
            ``grey_tolerance`` for deciding which pixels actually get
            repainted, and the two need not match.

    Returns:
        A :class:`PaletteFit`, usable wherever a
        :class:`~pycasso.palette.Palette` is::

            fitted = pycasso.fit(document, palette)
            document.restyle(fitted, mode="hue")

        Figures that look like a continuous colormap are recorded on
        ``fitted.skip`` and left alone by ``restyle()`` automatically.

    Raises:
        ValueError: if ``palette`` has no chromatic colours to assign (e.g.
            ``grayscale``) -- there is no hue for a document colour to match.
    """
    if not palette.supports_hue:
        raise ValueError(
            f"palette {palette.name!r} is entirely achromatic (e.g. a grayscale "
            "palette), so pycasso.fit() has no hue to assign document colours "
            "to; use a palette with at least one chromatic colour instead"
        )

    figures = document.figures
    per_figure = {}
    skipped = []
    for figure in figures:
        counts = figure.colors()
        if not counts:
            log.debug("%s: no chromatic colours", figure)
            continue
        if looks_continuous(counts):
            log.warning(
                "%s looks like a continuous colormap (many distinct colours, none "
                "dominant) rather than a handful of series colours -- leaving it "
                "untouched; see pycasso.cluster.looks_continuous to tune this",
                figure,
            )
            skipped.append(figure)
            continue
        clusters = cluster_hues(counts, merge_degrees, grey_tolerance)
        per_figure[figure] = clusters
        if clusters:
            log.info("%s: %d independent colour%s -- %s", figure,
                      len(clusters), "" if len(clusters) == 1 else "s", describe(clusters))

    needed = max((len(clusters) for clusters in per_figure.values()), default=0)
    if needed == 0:
        raise ValueError(
            "no chromatic colours found to fit a palette to "
            + ("(every figure looks like a continuous colormap)" if skipped else "")
        )

    busiest = max(per_figure, key=lambda figure: len(per_figure[figure]))
    log.info("busiest figure is %s with %d independent colours", busiest, needed)

    # one clustering pass over the whole document's raw histogram, not over
    # per-figure representatives: the same real series colour can pick a
    # slightly different representative shade in different figures, and
    # reclustering representatives risked treating those as separate colours
    combined = Counter()
    for figure in per_figure:
        combined.update(figure.colors())
    document_clusters = cluster_hues(combined, merge_degrees, grey_tolerance)
    log.info("document as a whole resolves to %d independent colour%s",
              len(document_clusters), "" if len(document_clusters) == 1 else "s")

    chromatic_rgb = palette.rgb[palette._chromatic]
    chromatic_lab = palette.lab[palette._chromatic]
    cluster_lab = np.array([c.lab for c in document_clusters])

    # target hue per cluster, preferring a distinct hue *family* for each --
    # see assign_families for why plain nearest-hue-per-cluster isn't enough
    source_hue = np.arctan2(cluster_lab[:, 2], cluster_lab[:, 1])
    target_hue = np.arctan2(chromatic_lab[:, 2], chromatic_lab[:, 1])
    weight = np.array([cluster.weight for cluster in document_clusters])
    nearest = assign_families(source_hue, target_hue, priority=weight)
    assigned = chromatic_rgb[nearest]

    sharing = Counter(nearest.tolist())
    if any(count > 1 for count in sharing.values()):
        log.warning(
            "palette %r has only %d chromatic colours for %d independent document "
            "colours -- some will share a replacement",
            palette.name, len(chromatic_rgb), len(document_clusters),
        )

    for cluster, target_index, color in zip(document_clusters, nearest, assigned):
        note = f" (shared with {sharing[target_index] - 1} other colour(s))" if sharing[target_index] > 1 else ""
        log.info("  %s (L*=%.0f, weight=%.0f) -> %s%s",
                  cluster.representative, cluster.lightness, cluster.weight, to_hex(color), note)

    return PaletteFit(document_clusters, assigned, palette.name, skip=(f.name for f in skipped))
