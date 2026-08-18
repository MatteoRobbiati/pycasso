"""
Restyle the same project through several palettes, one PDF per palette.

The point of the toy paper (see make_toy_paper.py) is that its five figures
were plotted with five unrelated, clashing colour schemes -- matplotlib's
tab10, seaborn's Set2, Dark2, a diverging coolwarm heatmap, and Pastel1. This
script runs the whole pipeline once per target palette and compiles a
separate, consistently-themed PDF each time, so you can flip between the
outputs and see how differently each palette reads on the exact same figures.

Needs matplotlib/seaborn to have already produced toy_paper.zip once:

    uv sync --extra examples
    uv run python make_toy_paper.py       # only if toy_paper.zip isn't there yet
    uv run python restyle_all_palettes.py

Run from this directory.
"""

from pathlib import Path

import matexxe

matexxe.enable_logging()

PROJECT_ZIP = "toy_paper.zip"
OUTPUT_DIR = Path("restyled")
PALETTES = ["okabe-ito", "tol-bright", "persian", "violet", "green-orange"]
MODE = "hue"

if not Path(PROJECT_ZIP).is_file():
    raise SystemExit(f"{PROJECT_ZIP} not found -- run make_toy_paper.py first")

OUTPUT_DIR.mkdir(exist_ok=True)

for name in PALETTES:
    print(f"\n=== {name} ===")
    palette = matexxe.Palette.load(name)

    # a fresh Project each time: restyle() mutates in place, so reopening
    # keeps each palette's run independent of the last
    project = matexxe.Project(PROJECT_ZIP)
    fitted = matexxe.fit(project, palette)
    project.restyle(fitted, mode=MODE)
    project.save(OUTPUT_DIR / f"toy_paper_{name}_source.zip")

    try:
        pdf = project.compile(OUTPUT_DIR / f"toy_paper_{name}.pdf")
        print(f"-> {pdf}")
    except RuntimeError as error:
        print(f"local compile skipped ({error}); the restyled source zip is still in {OUTPUT_DIR}")

print(f"\ndone -- compare the PDFs in {OUTPUT_DIR.resolve()}")
