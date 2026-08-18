![pycasso](https://github.com/MatteoRobbiati/pycasso/assets/62071516/5e0a7459-692f-4e2d-9a9b-fcf881e3399a)

Automatic recolouring for images, PDFs and whole LaTeX papers, built on
[pillow](https://github.com/python-pillow/Pillow), [pikepdf](https://github.com/pikepdf/pikepdf)
and [numpy](https://numpy.org).

I was tired of using graphical apps to remove backgrounds and replace
colours by hand and, later, of manually hunting down every mismatched
colour across a paper's figures, hyperlinks and code listings every time a
co-author changed the house style. `pycasso` does both automatically.

## Install it

`pycasso` is managed with [uv](https://docs.astral.sh/uv/). Clone this repo and let
`uv` set up the environment for you:

```sh
uv sync
```

This creates a `.venv` with `pycasso` installed in editable mode. Run anything
inside it with `uv run`, e.g. `uv run python examples/basic_recolor/recolor_logo.py`.

To add `pycasso` to an environment of your own instead:

```sh
uv pip install .
```

Regenerating the example plots in `examples/paper_restyling/toy_paper/` needs
matplotlib/seaborn, which plain `pycasso` does not otherwise depend on:

```sh
uv sync --extra examples
```

## What it does

Three ways to recolour something, depending on what you give it:

```python
import pycasso

# a single image or PDF
painter = pycasso.Painter("logo.png")            # or "figure.pdf"

# pycasso.fit() looks at the colours actually used and assigns each one a
# replacement from the target palette -- no need to know the exact colours
# up front, and no risk of guessing a palette that's too big or too small
palette = pycasso.Palette.load("okabe-ito")       # pycasso.available() lists the rest
fitted = pycasso.fit(painter, palette)
painter.restyle(fitted, mode="hue")
painter.save("logo_restyled.png")
```

```python
# a whole paper's Overleaf source (a "Source" download, or an already-
# extracted project directory) -- not just the compiled PDF, but every
# figure asset, hyperlink colour and code-listing syntax colour too
project = pycasso.Project("paper.zip")
fitted = pycasso.fit(project, palette)
project.restyle(fitted, mode="hue")
project.save("paper_restyled.zip")   # re-upload to Overleaf and recompile,
                                      # or project.compile(...) locally
```

See [examples/](examples/) for complete, runnable versions of both, plus a
synthetic "toy paper" restyled through four different palettes.

## How `fit()` decides what to do

1. **Cluster.** Each figure's colours are grouped into independent hues --
   shades, tints and antialiasing of one series colour count once. A figure
   that turns out to be a continuous colormap (a heatmap, a density plot)
   rather than a handful of series colours is set aside for step 4.
2. **Combine.** Every figure's colours are pooled into one document-wide
   picture, so the same real series colour is recognised consistently
   across figures rather than independently per figure.
3. **Assign.** Each independent colour gets a *distinct* hue from the
   palette whenever the palette offers enough hue families -- not just
   whichever palette entry happens to be nearest, which can otherwise pile
   several unrelated colours onto the same replacement even when a clearly
   different, only slightly farther option was sitting right there unused.
4. **Blend.** A figure identified as a continuous colormap in step 1 is
   recoloured separately, by finding its own one or two dominant hues and
   blending *continuously* between their replacements -- snapping a smooth
   gradient onto a handful of discrete colours would band it.

The result is a `PaletteFit`: pass it to `.restyle()` exactly like a plain
`Palette`. `mode` controls how much of the original colour survives:

| mode | keeps | use for |
| --- | --- | --- |
| `"hue"` (default) | original lightness *and* chroma, only the hue changes | the gentlest option; a figure recoloured this way still looks like itself |
| `"tint"` | original lightness, palette's hue and chroma | pale fills stay pale instead of flattening to the target's exact tone |
| `"snap"` | nothing -- the exact palette colour | strict brand compliance, every instance of a colour must match precisely |

Achromatic pixels (axes, rules, body text) are left untouched by default
(`keep_greys=True`) regardless of mode.

## Palettes

Built in (`pycasso.available()`):

| name | notes |
| --- | --- |
| `okabe-ito` | colourblind-safe qualitative, the standard choice for scientific figures |
| `tol-bright`, `tol-muted` | Paul Tol's colourblind-safe qualitative schemes |
| `chalmers` | approximate Chalmers institutional palette -- check against the real brand manual before publishing |
| `persian` | yellow/red/blue/lavender; yellow, red and blue are marked `primary` (see below) |
| `grayscale` | luminance-separated greys for black-and-white print; has no hue, so only `mode="snap"` works with it |
| `green-orange`, `violet` | deliberately narrow diagnostic palettes, useful for confirming a restyle actually changed something |

Load one with `pycasso.Palette.load("name")`, or write your own as a small
TOML file (see `src/pycasso/palettes/*.toml` for the format) and load it with
`pycasso.Palette.from_file("mine.toml")`. A palette can optionally mark a
few colours `primary` -- its signature colours, which get first claim
whenever a document doesn't need every colour available; the rest of the
palette only joins once a document genuinely has more independent colours
than the primary set covers.

## Logging

`pycasso` stays silent by default. Turn on progress messages -- what was
found, what got mapped to what, and clear warnings when something looks
off -- with:

```python
pycasso.enable_logging()
```

## Tutorial

A notebook walkthrough of the low-level image API is in
[examples/pycasso_tutorial.ipynb](examples/pycasso_tutorial.ipynb); for the
palette/`fit()`/`Project` workflow, see [examples/](examples/).
