"""
Restyle a paper's full Overleaf source: figure assets AND \\definecolor.

Restyling the compiled PDF (see restyle_paper.py) only reaches colours that
ended up embedded as a discrete drawing object. Colours LaTeX paints
directly -- hyperlink and citation colours defined with \\definecolor and
wired up through hyperref -- never become one, so they're invisible to that
approach. Working from the project's own source reaches both of those, plus
the original figure files themselves (cleaner than reverse-engineering a
flattened, compiled PDF).

Setup: put an Overleaf "Source" download (Menu -> Download -> Source) at
PROJECT_ZIP below -- a paper_data/ folder next to this script is a
reasonable place to keep it out of the way.

A figure `fit()` recognises as a continuous colormap (a heatmap, a
colourbar) is not simply left untouched: `restyle()` recolours it
separately with `pycasso.fit_colormap()`, blending continuously between the
figure's own dominant hues (reusing `fitted`'s own assigned colours as
their replacements) instead of snapping to a handful of discrete ones --
see restyle_paper.py's docstring for why that distinction matters.

IMPORTANT: `project.restyle(...)` only mutates each asset's in-memory
Painter -- nothing is written back to the extracted project's files until
`project.save(...)` runs, which flushes every asset to disk before packing
the new zip. Always call save() (or nothing will actually change).

Run from this directory:

    uv run python restyle_project.py
"""

from pathlib import Path

import pycasso

pycasso.enable_logging()

PROJECT_ZIP = "paper_data/overleaf_file.zip"
ZIP_OUT = "paper_data/overleaf_file_restyled.zip"
PALETTE_NAME = "green-orange"
MODE = "hue"

# Recompiling locally is entirely optional -- restyle() and save() below
# never need a LaTeX toolchain. Set this to False to skip trying, or leave
# it True and let it fail gracefully if latexmk/pdflatex isn't installed.
TRY_LOCAL_COMPILE = True
PDF_OUT = "paper_data/main_restyled.pdf"

project = pycasso.Project(PROJECT_ZIP)
palette = pycasso.Palette.load(PALETTE_NAME)

print(f"\n{project}")
print(f"figure assets: {list(project.assets)}")
print(f"\\definecolor entries: {project.tex_colors}\n")

fitted = pycasso.fit(project, palette)
project.restyle(fitted, mode=MODE)   # recolours every asset (incl. colormaps) + every chromatic \definecolor
project.save(ZIP_OUT)                # flushes every asset to disk, then packs the new zip

print(f"\nsaved -> {Path(ZIP_OUT).resolve()}")
print("re-upload that zip to Overleaf and hit Recompile, or:")

if TRY_LOCAL_COMPILE:
    try:
        pdf = project.compile(PDF_OUT)
        print(f"compiled locally -> {pdf}")
    except RuntimeError as error:
        print(f"local compile skipped: {error}")
