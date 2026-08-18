# Examples

## `basic_recolor/`

The simplest cases: recolouring one image directly, either by exact colour
swap (`replace_colors`) or automatically via a palette (`fit()`/`restyle()`).
Start here if you're new to `matexxe`.

```sh
cd basic_recolor && uv run python recolor_logo.py
```

## `paper_restyling/`

Restyling a whole paper, at two levels:

- **`restyle_pdf.py`**, works on a compiled PDF alone. Reaches every figure
  embedded in it, but not colours LaTeX paints directly (hyperlinks,
  code-listing syntax highlighting), since those never become a discrete
  object in the compiled output.
- **`restyle_project.py`**, works on a paper's full Overleaf source (a
  "Source" .zip download). Reaches the same figures, from their original,
  higher-fidelity source files, plus `\definecolor` and syntax-highlight
  colours in the `.tex` itself.

The example paper to run either script against is **`toy_paper/`**, a
small, entirely synthetic paper (see `make_toy_paper.py`), with eight
figures deliberately plotted with clashing, mismatched colour schemes
(matplotlib's tab10, seaborn's Set2, Dark2 and Accent, three unrelated
continuous colormaps, and a flat PNG logo), exactly the kind of
inconsistency `matexxe.fit()` is meant to clean up, without needing anyone's
real research code or data. `restyle_all_palettes.py` runs the whole project
through several palettes and saves one PDF per palette, so you can flip
between them and compare. Needs matplotlib/seaborn (`uv sync --extra examples`)
only to *regenerate* the plots, `toy_paper.zip` and `main.pdf` are already
built.

```sh
cd paper_restyling && uv run python restyle_pdf.py
cd paper_restyling && uv run python restyle_project.py
cd paper_restyling/toy_paper && uv run python restyle_all_palettes.py
```

## `matexxe_tutorial.ipynb`

A notebook walkthrough of the lower-level `Painter` image API
(`remove_color`, `replace_colors`, resizing, ...).
