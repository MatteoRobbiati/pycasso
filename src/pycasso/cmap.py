"""
Recolour a continuous colormap (a heatmap, a density plot, a colourbar).

The cluster-and-snap approach in :mod:`pycasso.fit` treats a figure's colours
as a handful of discrete, independent series -- exactly the wrong model for
a continuous colormap, where colour encodes a continuous quantity and every
pixel's hue carries meaning. Recolouring one that way either flattens the
gradient onto a few discrete colours (banding) or, worse, buckets nearby
parts of the ramp onto the wrong discrete colour entirely -- see
:func:`~pycasso.cluster.looks_continuous` for how such figures are detected
and skipped by :func:`~pycasso.fit.fit`.

:func:`fit_colormap` instead:

1. finds the figure's own dominant hue "anchors" -- a diverging map
   (blue-white-red) resolves to two, one per side; a sequential map usually
   resolves to one;
2. assigns each anchor the nearest hue available as a target -- preferably
   a colour the rest of the document already settled on (pass the
   :class:`~pycasso.fit.PaletteFit` from an earlier :func:`~pycasso.fit.fit`
   call), so the colormap's anchors read as the same colours used elsewhere;
3. recolours every pixel by *continuously* blending between the assigned
   anchor hues, weighted by angular closeness to each anchor (inverse-
   distance weighting around the hue circle), while keeping the pixel's own
   lightness and chroma untouched. This is the same "keep lightness and
   chroma, change hue" recipe as ``Palette.map(mode="hue")``, generalised
   from a single nearest anchor to a smooth blend of all of them -- the
   gradient stays a gradient, with no discrete jumps.
"""

import logging
from collections import Counter

import numpy as np

from pycasso.cluster import assign_families, cluster_hues
from pycasso.color import from_lab, is_achromatic, to_hex, to_lab

log = logging.getLogger(__name__)

DEFAULT_ANCHOR_DEGREES = 45.0
DEFAULT_MIN_ANCHOR_WEIGHT = 0.02


class ColormapFit:
    """A continuous hue remapping, built from a figure's own anchor hues."""

    def __init__(self, source_hues, target_hues, name:str, power:float = 2.0):
        """
        Args:
            source_hues: hue angles (radians) found in the original figure;
            target_hues: the corresponding replacement hue angles, same order;
            name: label, used in logging and ``repr``;
            power: inverse-distance-weighting exponent. Higher values make
                each anchor's influence fall off faster with angular
                distance, giving a sharper handoff between anchors.
        """
        self.source_hues = np.asarray(source_hues, dtype=float)
        self.target_hues = np.asarray(target_hues, dtype=float)
        self.name = name
        self.power = power
        # so it plugs into restyle() the same way a PaletteFit does when
        # nothing else needs skipping downstream of this figure
        self.skip = frozenset()

    def _blend_target_hue(self, hue):
        """
        Inverse-distance-weighted blend of the target hues, per pixel.

        The ``+ 1e-9`` below only guards the degenerate case of a pixel's
        hue landing exactly on an anchor: without it that anchor's distance
        is exactly zero and its weight divides by zero. Because it is only
        ever added to a small power-law term, it also happens to do the
        right thing as distance shrinks towards zero -- the weight grows
        smoothly towards its (large, finite) cap instead of blowing up, so
        that one anchor still ends up dominating the blend as it should.
        """
        distance = np.abs(np.arctan2(
            np.sin(hue[..., None] - self.source_hues), np.cos(hue[..., None] - self.source_hues)
        ))
        weight = 1.0 / (distance ** self.power + 1e-9)
        vector = np.stack([np.cos(self.target_hues), np.sin(self.target_hues)], axis=-1)
        blended = np.tensordot(weight, vector, axes=([-1], [0])) / weight.sum(axis=-1, keepdims=True)
        return np.arctan2(blended[..., 1], blended[..., 0])

    def map(self, rgb, mode:str = "hue", keep_greys:bool = True, grey_tolerance:float = 0.04):
        """Same contract as :meth:`Palette.map <pycasso.palette.Palette.map>`."""
        rgb = np.asarray(rgb, dtype=float)
        lab = to_lab(rgb)
        hue = np.arctan2(lab[..., 2], lab[..., 1])
        target_hue = self._blend_target_hue(hue)

        chroma = np.hypot(lab[..., 1], lab[..., 2])
        mapped = from_lab(np.stack(
            [lab[..., 0], chroma * np.cos(target_hue), chroma * np.sin(target_hue)], axis=-1
        ))

        changed = np.ones(rgb.shape[:-1], dtype=bool)
        if keep_greys:
            changed &= ~is_achromatic(rgb, grey_tolerance)
        return np.where(changed[..., None], mapped, rgb), changed

    def __repr__(self):
        degrees = np.degrees(self.source_hues).round(0).tolist()
        return f"ColormapFit({len(self.source_hues)} anchors at {degrees} deg, {self.name!r})"


def anchors(counts, merge_degrees:float = DEFAULT_ANCHOR_DEGREES,
            grey_tolerance:float = 0.06, min_weight_fraction:float = DEFAULT_MIN_ANCHOR_WEIGHT):
    """
    The dominant hue anchors of a continuous colormap's colour histogram.

    ``consolidate=True`` here (unlike plain :func:`~pycasso.cluster.cluster_hues`):
    this is one figure's own single gradient, so two clusters that end up
    close to each other's centre after the main pass -- typically the two
    ends of one smooth ramp, split apart by a greedy processing-order
    artefact -- really are one thing and should fold back together.
    """
    return cluster_hues(counts, merge_degrees=merge_degrees, grey_tolerance=grey_tolerance,
                         min_weight_fraction=min_weight_fraction, consolidate=True)


def fit_colormap(figure, palette, merge_degrees:float = DEFAULT_ANCHOR_DEGREES):
    """
    Build a :class:`ColormapFit` for one continuous-colormap figure.

    Args:
        figure: the figure to recolour -- typically one named in a
            :class:`~pycasso.fit.PaletteFit`'s ``.skip``;
        palette: the target palette. Pass the :class:`~pycasso.fit.PaletteFit`
            from an earlier :func:`~pycasso.fit.fit` call on the same
            document if you have one -- its own discovered colours become
            the assignment targets, so the colormap's anchors line up with
            the rest of the document; a plain :class:`~pycasso.palette.Palette`
            works too, assigning from its chromatic colours directly;
        merge_degrees: hue tolerance used to find the figure's own anchors --
            see :func:`anchors`.

    Returns:
        A :class:`ColormapFit`, usable anywhere a
        :class:`~pycasso.palette.Palette` is::

            colormap_fit = pycasso.cmap.fit_colormap(figure, fitted)
            figure.restyle(colormap_fit, mode="hue")
    """
    found = anchors(figure.colors(), merge_degrees=merge_degrees)
    if not found:
        raise ValueError(f"{figure!r} has no chromatic colours to anchor a colormap on")

    # prefer assigning onto colours the rest of the document already settled
    # on (a PaletteFit's own assigned replacements), falling back to the raw
    # palette's chromatic colours
    if hasattr(palette, "clusters") and hasattr(palette, "assigned") and palette.clusters:
        target_rgb = palette.assigned
    else:
        target_rgb = palette.rgb[palette.target_pool(len(found))]
    # the hue that matters here is the *replacement* colour's own hue, not
    # whatever hue the original document cluster happened to have before
    # being reassigned -- using the latter picks anchors by an accident of
    # which original colour a target used to stand in for, not by what the
    # target actually looks like now
    target_hue_all = np.arctan2(to_lab(target_rgb)[:, 2], to_lab(target_rgb)[:, 1])

    source_hues = np.array([cluster.hue for cluster in found])
    weight = np.array([cluster.weight for cluster in found])
    picks = assign_families(source_hues, target_hue_all, priority=weight)

    sharing = Counter(picks.tolist())
    for cluster, pick in zip(found, picks):
        note = f" (shared with {sharing[pick] - 1} other anchor(s))" if sharing[pick] > 1 else ""
        log.info("  colormap anchor %s (hue=%.0f deg, weight=%.0f) -> %s%s",
                  cluster.representative, np.degrees(cluster.hue) % 360, cluster.weight,
                  to_hex(target_rgb[pick]), note)

    name = getattr(palette, "name", repr(palette))
    return ColormapFit(source_hues, target_hue_all[picks], f"{name} (colormap, {len(source_hues)} anchor(s))")
