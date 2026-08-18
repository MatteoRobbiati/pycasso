"""
Group a colour histogram into perceptually independent hues.

Anti-aliasing, gradients and partial transparency turn a handful of "real"
series colours into thousands of distinct RGB values. Clustering by hue angle
alone collapses shades, tints and blends of the same colour back into one
group, so counting groups answers "how many colours does this figure actually
use", not "how many RGB values does it contain".
"""

import logging

import numpy as np
from scipy.optimize import linear_sum_assignment

from pycasso.color import is_achromatic, parse, to_lab

log = logging.getLogger(__name__)

DEFAULT_MERGE_DEGREES = 25.0

# A bit more generous than the 0.04 used when actually restyling a pixel: a
# near-black anti-aliasing artefact that just clears that tighter threshold
# shouldn't be counted as one of a figure's independent colours, even though
# it's still fine to retint it once it's lumped in with a real cluster.
DEFAULT_CLUSTER_GREY_TOLERANCE = 0.06


class ColorCluster:
    """One perceptually independent colour, possibly merged from several shades."""

    def __init__(self, lab, weight:float, representative:str):
        self._lab_sum = np.array(lab, dtype=float) * weight
        self.weight = float(weight)
        self.representative = representative
        self._representative_weight = float(weight)

    def _absorb(self, lab, weight:float, representative:str):
        """Fold one more colour into this cluster."""
        self._lab_sum += np.array(lab, dtype=float) * weight
        self.weight += float(weight)
        if weight > self._representative_weight:
            self.representative = representative
            self._representative_weight = float(weight)

    def _absorb_cluster(self, other):
        """Merge another cluster into this one."""
        self._lab_sum += other._lab_sum
        self.weight += other.weight
        if other._representative_weight > self._representative_weight:
            self.representative = other.representative
            self._representative_weight = other._representative_weight

    @property
    def lab(self):
        """Weighted mean CIELAB of every colour merged into this cluster."""
        return self._lab_sum / self.weight

    @property
    def hue(self):
        """Weighted mean hue angle, in radians."""
        lab = self.lab
        return float(np.arctan2(lab[2], lab[1]))

    @property
    def lightness(self):
        """Weighted mean L*."""
        return float(self.lab[0])

    @property
    def chroma(self):
        """Weighted mean chroma."""
        lab = self.lab
        return float(np.hypot(lab[1], lab[2]))

    def __repr__(self):
        return f"ColorCluster({self.representative}, weight={self.weight:.0f})"


def _circular_distance(a, b):
    """Shortest distance between two hue angles (radians), wraparound-safe."""
    return np.abs(np.arctan2(np.sin(a - b), np.cos(a - b)))


def assign_hues(source_hues, target_hues, priority=None):
    """
    One target index per source hue, preferring a distinct target for each.

    Matching each source to whichever target is independently nearest can
    send two different sources to the *same* target even when a unique,
    only-slightly-farther alternative exists for one of them -- concretely:
    a pale blue-violet source hue sits, on the CIELAB hue circle, closer to
    orange than to green (the wrap towards red/magenta is the short way
    round), so nearest-independently would put it on the same orange a
    warmer source already claimed, even with green sitting right there
    unused. Solving this as a linear assignment problem instead finds the
    one-to-one matching that minimises *total* distance, so two genuinely
    different source hues land on genuinely different targets whenever
    there are enough of them to go around.

    Args:
        source_hues: hue angles (radians) to assign targets to;
        target_hues: candidate replacement hue angles;
        priority: optional weight per source. When there are more sources
            than targets, uniqueness isn't achievable for everyone; the
            highest-priority sources (heaviest first, if this is left as
            the default) get first claim on a unique target, and the rest
            fall back to their own nearest target, sharing where they must.

    Returns:
        An array of target indices, one per source, same order as ``source_hues``.
    """
    source_hues = np.asarray(source_hues, dtype=float)
    target_hues = np.asarray(target_hues, dtype=float)
    cost = _circular_distance(source_hues[:, None], target_hues[None, :])
    n, m = cost.shape

    if n <= m:
        row, col = linear_sum_assignment(cost)
        result = np.zeros(n, dtype=int)
        result[row] = col
        return result

    # more sources than targets: a fully unique assignment is impossible.
    # Give the top `m` sources (by priority) an optimal unique assignment
    # among themselves, and let the rest just take their own nearest target.
    order = np.argsort(-priority) if priority is not None else np.arange(n)
    head, tail = order[:m], order[m:]
    row, col = linear_sum_assignment(cost[head])
    result = np.zeros(n, dtype=int)
    result[head[row]] = col
    if len(tail):
        result[tail] = cost[tail].argmin(axis=1)
    return result


def hue_families(hues, merge_degrees:float = 30.0):
    """
    Group a set of hues (radians) into families by proximity alone.

    Unlike :func:`cluster_hues`, every hue counts equally regardless of how
    many near-duplicates of it exist -- this describes a *palette*, not a
    weighted colour histogram, so a family with four members shouldn't look
    "bigger" than one with a single member for that reason alone.

    Returns:
        A list of ``(representative_hue, member_indices)`` tuples, member
        indices referring to positions in the input ``hues`` array.
    """
    hues = np.asarray(hues, dtype=float)
    threshold = np.radians(merge_degrees)
    centers, members = [], []
    for index in range(len(hues)):
        if centers:
            distance = _circular_distance(hues[index], np.array(centers))
            nearest = int(np.argmin(distance))
            if distance[nearest] <= threshold:
                members[nearest].append(index)
                vectors = np.stack([np.cos(hues[members[nearest]]), np.sin(hues[members[nearest]])], axis=-1)
                mean = vectors.mean(axis=0)
                centers[nearest] = float(np.arctan2(mean[1], mean[0]))
                continue
        centers.append(float(hues[index]))
        members.append([index])
    return list(zip(centers, members))


def assign_families(source_hues, target_hues, priority=None, family_degrees:float = 30.0):
    """
    Assign each source hue a target index, preferring a distinct hue
    *family* for each source over doubling up within one that merely
    happens to have more members available.

    A plain :func:`assign_hues` over individual target swatches will
    legitimately -- correctly, by minimum total hue distance -- put every
    source on the same hue family if that family happens to offer several
    close shades and no source's hue is *individually* nearer to any other
    family: e.g. three pale, warm-leaning document colours against a
    palette of four oranges and four greens, none of which happen to be
    particularly green-leaning themselves, can all optimise onto oranges,
    never touching green at all. Assigning at the family level first (one
    family per source, when there are enough), then picking the best
    matching shade within that family, keeps genuinely different sources on
    genuinely different families whenever the palette actually offers them.

    Returns:
        Target indices into the original ``target_hues`` array, one per source.
    """
    source_hues = np.asarray(source_hues, dtype=float)
    target_hues = np.asarray(target_hues, dtype=float)
    priority = np.asarray(priority, dtype=float) if priority is not None else None
    families = hue_families(target_hues, merge_degrees=family_degrees)
    family_centers = np.array([center for center, _ in families])

    nearest_family = assign_hues(source_hues, family_centers, priority=priority)

    # within whichever family each source landed on, apply the same
    # prefer-a-distinct-target logic again -- otherwise a single-family
    # (monochrome) palette would pick the same one "nearest" shade
    # independently for every source instead of spreading across the
    # family's own lightness/chroma variants
    picks = np.zeros(len(source_hues), dtype=int)
    for family_index in np.unique(nearest_family):
        source_indices = np.flatnonzero(nearest_family == family_index)
        member_indices = np.array(families[family_index][1])
        sub_priority = priority[source_indices] if priority is not None else None
        sub_picks = assign_hues(source_hues[source_indices], target_hues[member_indices], priority=sub_priority)
        picks[source_indices] = member_indices[sub_picks]
    return picks


def cluster_hues(counts, merge_degrees:float = DEFAULT_MERGE_DEGREES,
                  grey_tolerance:float = DEFAULT_CLUSTER_GREY_TOLERANCE,
                  min_weight_fraction:float = 0.005, consolidate:bool = False):
    """
    Group a colour histogram into independent hues.

    Args:
        counts: mapping of hex colour to pixel/operator weight, e.g. the
            output of :meth:`~pycasso.workshop.Painter.colors`;
        merge_degrees: hue difference, in degrees, below which two colours
            are folded into the same cluster. Shades, tints and partially
            transparent blends of one series colour typically differ by a
            few degrees; distinct series colours in a colourblind-safe
            palette are usually 25-60 degrees apart, so this is the default;
        grey_tolerance: colours this close to grey are excluded -- they are
            axes, rules and text, not series colours;
        min_weight_fraction: clusters accounting for less than this fraction
            of the total chromatic weight are dropped as noise -- a single
            anti-aliased edge pixel that happens to sit just past
            ``grey_tolerance`` should not count as an independent colour;
        consolidate: also merge any two *final* clusters that end up within
            ``merge_degrees`` of each other, even though neither was ever
            compared directly against the other during the main pass (see
            :func:`consolidate_hues`). Correct for finding the anchors of
            one genuinely continuous gradient, where far-apart clusters
            bridged by intermediate shades really are one thing -- wrong
            for counting how many independent *categorical* colours a
            figure (or a whole document's worth of unrelated figures) uses,
            where unrelated colours from different sources can easily
            happen to chain together across the hue wheel with no real
            relationship between them. Defaults to off for exactly that
            reason; :func:`~pycasso.cmap.anchors` turns it on explicitly.

    Returns:
        Clusters, heaviest first.
    """
    if not counts:
        return []

    hexes = list(counts)
    weights = np.array([counts[h] for h in hexes], dtype=float)
    rgb = np.array([parse(h) for h in hexes])
    lab = to_lab(rgb)
    grey = is_achromatic(rgb, grey_tolerance)
    hue = np.arctan2(lab[:, 2], lab[:, 1])
    threshold = np.radians(merge_degrees)

    clusters = []
    # heaviest colour first: clusters form around the dominant shade of each
    # series, so a single stray anti-aliased pixel can't seed its own cluster
    for index in np.argsort(-weights):
        if grey[index]:
            continue
        if clusters:
            centers = np.array([c.hue for c in clusters])
            distance = _circular_distance(hue[index], centers)
            nearest = int(np.argmin(distance))
            if distance[nearest] <= threshold:
                clusters[nearest]._absorb(lab[index], weights[index], hexes[index])
                continue
        clusters.append(ColorCluster(lab[index], weights[index], hexes[index]))

    if consolidate:
        clusters = consolidate_hues(clusters, merge_degrees)

    clusters.sort(key=lambda c: c.weight, reverse=True)

    total = sum(c.weight for c in clusters)
    minimum = total * min_weight_fraction
    kept = [c for c in clusters if c.weight >= minimum]
    dropped = len(clusters) - len(kept)
    if dropped and kept:
        log.debug(
            "dropped %d noise cluster%s below %.1f%% of total weight: %s",
            dropped, "" if dropped == 1 else "s", min_weight_fraction * 100,
            describe([c for c in clusters if c.weight < minimum]),
        )
    clusters = kept or clusters  # never drop everything

    log.debug(
        "clustered %d distinct colours into %d independent hue%s (merge_degrees=%.0f)",
        len(hexes), len(clusters), "" if len(clusters) == 1 else "s", merge_degrees,
    )
    return clusters


def consolidate_hues(clusters, merge_degrees:float):
    """
    Merge clusters repeatedly while the closest pair is within ``merge_degrees``.

    Intended for a *single* genuinely continuous gradient (see
    :func:`~pycasso.cmap.anchors`), where two clusters seeded from opposite
    ends of the same smooth ramp can end up within threshold of each
    other's centre without ever being compared during
    :func:`cluster_hues`'s single greedy pass -- which only ever checks a
    new colour against clusters that already exist, never two existing
    clusters against each other. Chain-merging across a *combined*
    histogram from several unrelated figures is a different matter: any
    two clusters this repeated nearest-pair merge brings together, however
    indirectly, end up combined, so a handful of intermediate shades can
    chain together colours with no real relationship to one another.
    """
    threshold = np.radians(merge_degrees)
    clusters = list(clusters)
    while len(clusters) > 1:
        hues = np.array([c.hue for c in clusters])
        distance = _circular_distance(hues[:, None], hues[None, :])
        np.fill_diagonal(distance, np.inf)
        i, j = np.unravel_index(np.argmin(distance), distance.shape)
        if distance[i, j] > threshold:
            break
        i, j = (i, j) if i < j else (j, i)
        clusters[i]._absorb_cluster(clusters[j])
        del clusters[j]
    return clusters


def merge_to(clusters, k:int):
    """Agglomeratively merge the closest-hue clusters until only ``k`` remain."""
    if k <= 0:
        raise ValueError("k must be positive")
    clusters = list(clusters)
    while len(clusters) > k:
        hues = np.array([c.hue for c in clusters])
        distance = _circular_distance(hues[:, None], hues[None, :])
        np.fill_diagonal(distance, np.inf)
        i, j = np.unravel_index(np.argmin(distance), distance.shape)
        i, j = (i, j) if i < j else (j, i)
        clusters[i]._absorb_cluster(clusters[j])
        del clusters[j]
    return clusters


DEFAULT_CONTINUOUS_MIN_DISTINCT = 50
DEFAULT_CONTINUOUS_MAX_CONCENTRATION = 0.5
DEFAULT_CONTINUOUS_TOP_N = 3


def looks_continuous(counts, min_distinct:int = DEFAULT_CONTINUOUS_MIN_DISTINCT,
                      max_concentration:float = DEFAULT_CONTINUOUS_MAX_CONCENTRATION,
                      top_n:int = DEFAULT_CONTINUOUS_TOP_N):
    """
    Heuristic: does this colour histogram look like a continuous colormap?

    A categorical figure -- a handful of line-plot series, a schematic's
    fills, a small circuit diagram -- concentrates almost all its weight in
    a few exact colours, however many distinct RGB values anti-aliasing
    scatters around their edges: a block-filled diagram's top 3 colours
    typically hold 70-100% of its total weight. A continuous colormap (a
    heatmap, a density plot, a colourbar) has neither property: it uses many
    distinct colours *and* spreads its weight thinly across all of them,
    because adjacent pixels are rarely exactly equal.

    Both conditions matter together -- a figure with only a handful of
    distinct colours split close to evenly between two series (low
    concentration, but few colours) is still categorical, not continuous.

    This only decides whether :func:`~pycasso.fit.fit` treats a figure as
    fair game for automatic restyling -- it never affects
    :meth:`~pycasso.workshop.Painter.colors`.
    """
    if len(counts) < min_distinct:
        return False
    total = sum(counts.values())
    if total == 0:
        return False
    top = sum(weight for _, weight in counts.most_common(top_n))
    return (top / total) < max_concentration


def describe(clusters, limit:int = 6):
    """Short human-readable summary of a cluster list, for logging."""
    shown = ", ".join(f"{c.representative} ({c.weight:,.0f})" for c in clusters[:limit])
    if len(clusters) > limit:
        shown += ", ..."
    return shown
