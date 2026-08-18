"""
Restyle every figure in a paper onto a standard colour palette.

The approach (`matexxe.fit`):

  1. cluster each figure's own colours to find how many *independent*
     colours it uses -- shades, tints and partial transparency of one
     series colour count once. A figure that looks like a continuous
     colormap (a heatmap, a density plot) rather than a handful of series
     colours is left untouched entirely -- see matexxe.cluster.looks_continuous;
  2. cluster the whole document's colours together in one pass, so the same
     real-world series colour is recognised consistently across figures,
     not independently per figure;
  3. assign each document-wide colour the *nearest hue* available in the
     target palette. Deterministic: a given original hue always gets the
     same replacement, so adding or removing a figure never reshuffles a
     colour that was already assigned.

The result is a `PaletteFit`, which plugs into `restyle()` exactly like a
plain `Palette`. NOTE: mode="hue" (the default here) needs a palette with
at least one chromatic colour -- it has no hue to assign onto a purely
achromatic one like "grayscale"; use mode="snap" for that, or a different
palette.

A figure `fit()` recognises as a continuous colormap (a heatmap, a
colourbar) is not simply left untouched: discrete cluster-and-snap is the
wrong tool for a continuous quantity (see matexxe.cluster.looks_continuous),
so `restyle()` recolours it separately, via `matexxe.fit_colormap()`. That
finds the figure's own dominant hue anchors (two, for a diverging blue/red
map) and blends *continuously* between their replacements -- no banding, no
discrete jumps -- reusing `fitted`'s own assigned colours as those anchors'
replacements, so a colourbar ends up built from the same colours the rest
of the document settled on. Pass recolor_colormaps=False to restyle() to
leave such figures untouched instead.

Run from this directory:

    uv run python restyle_pdf.py

PDF_IN below is the synthetic toy paper (see toy_paper/make_toy_paper.py) --
point it at any other compiled PDF to try this on a paper of your own.
"""

from pathlib import Path

import matexxe

# print matexxe's progress to the terminal; comment out for silence
matexxe.enable_logging()

PDF_IN = "toy_paper/main.pdf"
PDF_OUT = "toy_paper/main_restyled.pdf"
PALETTE_NAME = "chalmers"      # matexxe.available() lists the built-ins
MODE = "hue"                    # "snap" | "tint" | "hue" -- see Palette.map

paper = matexxe.Painter(PDF_IN)
palette = matexxe.Palette.load(PALETTE_NAME)

fitted = matexxe.fit(paper, palette)
paper.restyle(fitted, mode=MODE)   # also recolours continuous colormaps, see above
paper.save(PDF_OUT)

print(f"\nsaved -> {Path(PDF_OUT).resolve()}")
