![MaTeXXe](docs/public/matexxe_wordmark_only_pastel.svg)

**Your last co-author before arXiv.**

Automatic recolouring for images, PDFs and whole LaTeX papers, built on
[pillow](https://github.com/python-pillow/Pillow), [pikepdf](https://github.com/pikepdf/pikepdf)
and [numpy](https://numpy.org).

I was tired of using graphical apps to remove backgrounds and replace
colours by hand and, later, of manually hunting down every mismatched
colour across a paper's figures, hyperlinks and code listings every time a
co-author changed the house style. `matexxe` does both automatically.

This project was fully conceived by its human author and built together
with Claude Sonnet 5.

## Why "MaTeXXe"

The name folds together **Ma**tisse, the painter who pushed colour further
than almost anyone and leader of the Fauvist ("wild beast") movement that
used raw, unmixed colour as the whole subject of a painting, not just a
detail of it, with **TeX**, since a paper's `.tex` source is exactly what
this tool works from. The lowered "e" nods to the TeX logo itself, and the
two tilted X's double as two Greek chi (χ), a quieter nod to the physics
papers this started out recolouring.

## Install it

`matexxe` is managed with [uv](https://docs.astral.sh/uv/). Clone this repo and let
`uv` set up the environment for you:

```sh
uv sync
```

This creates a `.venv` with `matexxe` installed in editable mode. Run anything
inside it with `uv run`, e.g. `uv run python examples/basic_recolor/recolor_logo.py`.

To add `matexxe` to an environment of your own instead:

```sh
uv pip install .
```

Regenerating the example plots in `examples/paper_restyling/toy_paper/` needs
matplotlib/seaborn, which plain `matexxe` does not otherwise depend on:

```sh
uv sync --extra examples
```

## What it does

A few ways to recolour something, depending on what you give it and how
much control you want.

For a single image where you already know exactly which colour needs to
go, skip palettes and `fit()` entirely:

```python
import matexxe

icon = matexxe.Painter("icon.png")

# swap one exact colour for another
icon.replace_colors(old_color=(143, 163, 220), new_color=(230, 81, 0), alpha=None)
icon.save("icon_recoloured.png")

# or make a colour transparent instead, shadow_range also catches
# antialiased pixels that are a slightly different shade of the same
# colour, not an exact match
icon = matexxe.Painter("icon.png")
icon.remove_color(color=(143, 163, 220), shadow_range=30)
icon.save("icon_transparent.png")
```

<table>
<tr><th>before</th><th>replace_colors</th><th>remove_color</th></tr>
<tr>
<td><img src="docs/public/matexxe-icon-512.png" width="160" alt="icon with a flat blue background"></td>
<td><img src="docs/public/matexxe-icon-512-recolored.png" width="160" alt="the same icon with the background swapped for orange"></td>
<td><img src="docs/public/matexxe-icon-512-transparent.png" width="160" alt="the same icon with the background removed"></td>
</tr>
</table>

See [examples/basic_recolor/recolor_logo.py](examples/basic_recolor/recolor_logo.py)
for both, run against this exact icon.

For anything bigger than "I know the one colour to change", `matexxe.fit()`
looks at the colours actually used and assigns each one a replacement from
a target palette, no need to know the exact colours up front, and no risk
of guessing a palette that's too big or too small:

```python
import matexxe

# a single image or PDF
painter = matexxe.Painter("logo.png")            # or "figure.pdf"
palette = matexxe.Palette.load("okabe-ito")       # matexxe.available() lists the rest
fitted = matexxe.fit(painter, palette)
painter.restyle(fitted, mode="hue")
painter.save("logo_restyled.png")
```

<table>
<tr><th>before</th><th>okabe-ito</th><th>green-orange</th></tr>
<tr>
<td><img src="docs/public/jolly.png" width="160" alt="a jolly roger flag in its original yellow and red"></td>
<td><img src="docs/public/jolly_okabe-ito.png" width="160" alt="the same flag restyled with the okabe-ito palette"></td>
<td><img src="docs/public/jolly_green-orange.png" width="160" alt="the same flag restyled with the green-orange palette"></td>
</tr>
</table>

Same call both times, only the palette changed, see
[examples/basic_recolor/recolor_logo.py](examples/basic_recolor/recolor_logo.py)
for the full script.

```python
# a whole paper's Overleaf source (a "Source" download, or an already
# extracted project directory), not just the compiled PDF, but every
# figure asset, hyperlink colour and code-listing syntax colour too
project = matexxe.Project("paper.zip")
fitted = matexxe.fit(project, palette)
project.restyle(fitted, mode="hue")
project.save("paper_restyled.zip")   # re-upload to Overleaf and recompile,
                                      # or project.compile(...) locally
```

See [examples/](examples/) for a complete, runnable version, plus a
synthetic "toy paper" restyled through several different palettes.

## How `fit()` decides what to do

1. **Cluster.** Each figure's colours are grouped into independent hues,
   where shades, tints and antialiasing of one series colour count once. A
   figure that turns out to be a continuous colormap (a heatmap, a density
   plot) rather than a handful of series colours is set aside for step 4.
2. **Combine.** Every figure's colours are pooled into one document-wide
   picture, so the same real series colour is recognised consistently
   across figures rather than independently per figure.
3. **Assign.** Each independent colour gets a *distinct* hue from the
   palette whenever the palette offers enough hue families, not just
   whichever palette entry happens to be nearest, which can otherwise pile
   several unrelated colours onto the same replacement even when a clearly
   different, only slightly farther option was sitting right there unused.
4. **Blend.** A figure identified as a continuous colormap in step 1 is
   recoloured separately, by finding its own one or two dominant hues and
   blending *continuously* between their replacements, since snapping a
   smooth gradient onto a handful of discrete colours would band it.

The result is a `PaletteFit`: pass it to `.restyle()` exactly like a plain
`Palette`. `mode` controls how much of the original colour survives:

| mode | keeps | use for |
| --- | --- | --- |
| `"hue"` (default) | original lightness *and* chroma, only the hue changes | the gentlest option; a figure recoloured this way still looks like itself |
| `"tint"` | original lightness, palette's hue and chroma | pale fills stay pale instead of flattening to the target's exact tone |
| `"snap"` | nothing, just the exact palette colour | strict brand compliance, every instance of a colour must match precisely |

Achromatic pixels (axes, rules, body text) are left untouched by default
(`keep_greys=True`) regardless of mode.

## Palettes

Built in (`matexxe.available()`):

| name | notes |
| --- | --- |
| `okabe-ito` | colourblind-safe qualitative, the standard choice for scientific figures |
| `tol-bright`, `tol-muted` | Paul Tol's colourblind-safe qualitative schemes |
| `persian` | yellow/red/blue/lavender; yellow, red and blue are marked `primary` (see below) |
| `grayscale` | luminance-separated greys for black-and-white print; has no hue, so only `mode="snap"` works with it |
| `green-orange`, `violet` | deliberately narrow diagnostic palettes, useful for confirming a restyle actually changed something |

Load one with `matexxe.Palette.load("name")`, or write your own as a small
TOML file (see `src/matexxe/palettes/*.toml` for the format) and load it with
`matexxe.Palette.from_file("mine.toml")`. A palette can optionally mark a
few colours `primary`, its signature colours, which get first claim
whenever a document doesn't need every colour available; the rest of the
palette only joins once a document genuinely has more independent colours
than the primary set covers.

## Logging

`matexxe` stays silent by default. Turn on progress messages, what was
found, what got mapped to what, and clear warnings when something looks
off, with:

```python
matexxe.enable_logging()
```

## Tutorial

A notebook walkthrough of the low-level image API is in
[examples/matexxe_tutorial.ipynb](examples/matexxe_tutorial.ipynb); for the
palette/`fit()`/`Project` workflow, see [examples/](examples/).
