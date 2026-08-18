"""
Generate a small, entirely synthetic "paper" about pycasso itself, used to
demo the Project workflow end to end -- no real research code or data.

Eight figures, each plotted with a different, clashing colour scheme on
purpose: matplotlib's tab10, seaborn's Set2, Dark2, Accent, a diverging
coolwarm heatmap, a sequential viridis contour plot, a plasma noise field,
and a plain PNG logo -- plus a couple of `pycasso` code snippets in the
text itself. Every figure's caption names its original colour source with a
link, so it's easy to look up what a palette or colormap is actually called
before and after a restyle.

Needs matplotlib/seaborn, which plain pycasso does not depend on:

    uv sync --extra examples
    uv run python make_toy_paper.py

Regenerates:
    toy_paper_source/figures/*.pdf, *.png   -- the plots (+ a copied logo)
    toy_paper_source/main.tex               -- a minimal LaTeX paper around them
    toy_paper.zip                           -- an Overleaf-style "Source" export
    main.pdf                                -- compiled, if a LaTeX toolchain is found
"""

import shutil
import subprocess
import zipfile
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns

matplotlib.use("Agg")
rng = np.random.default_rng(7)

HERE = Path(__file__).parent
SOURCE = HERE / "toy_paper_source"
FIGURES = SOURCE / "figures"
FIGURES.mkdir(parents=True, exist_ok=True)
JOLLY_LOGO = HERE.parent.parent / "basic_recolor" / "images" / "jolly.png"

FIGSIZE = (6.5, 4.6)   # a good deal larger than a typical inline plot,
                        # so each colour choice is easy to see at a glance


def savefig(fig, name):
    fig.savefig(FIGURES / name, bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------------------------------
# 1. Bar chart -- matplotlib's default "tab10" colours. Illustrative numbers
#    only (see the caption); a roughly even spread, not an exponential one,
#    so every one of the eight bars -- including the blue first one -- is
#    clearly visible rather than dwarfed by its neighbours.
methods = [f"v{i}" for i in range(1, 9)]
runtime = rng.uniform(0.35, 1.0, size=len(methods))
fig, ax = plt.subplots(figsize=FIGSIZE)
ax.bar(methods, runtime, color=plt.get_cmap("tab10").colors[:len(methods)])
ax.set_xlabel("pycasso version (illustrative)")
ax.set_ylabel("relative restyle time")
ax.set_title("Restyle runtime across releases")
savefig(fig, "benchmark_runtime.pdf")

# ---------------------------------------------------------------------------
# 2. Scatter -- seaborn's pastel "Set2", categorical clusters
n_per_cluster = 50
clusters = [rng.normal(center, 0.6, size=(n_per_cluster, 2))
            for center in [(-2, -1), (2, 2), (0, 3), (-3, 2.5)]]
x = np.concatenate([c[:, 0] for c in clusters])
y = np.concatenate([c[:, 1] for c in clusters])
label = np.repeat(["cluster 1", "cluster 2", "cluster 3", "cluster 4"], n_per_cluster)
fig, ax = plt.subplots(figsize=FIGSIZE)
sns.scatterplot(x=x, y=y, hue=label, palette="Set2", ax=ax, legend="brief", s=55)
ax.set_title("Cluster assignment")
ax.set_xlabel("feature 1")
ax.set_ylabel("feature 2")
savefig(fig, "cluster_scatter.pdf")

# ---------------------------------------------------------------------------
# 3. Multi-line convergence curves -- matplotlib's "Dark2" colormap
fig, ax = plt.subplots(figsize=FIGSIZE)
t = np.linspace(0, 10, 200)
dark2 = plt.get_cmap("Dark2").colors
for index, rate in enumerate([0.25, 0.45, 0.7, 1.0, 1.4]):
    noise = rng.normal(0, 0.015, size=t.size)
    ax.plot(t, np.exp(-rate * t) + noise, color=dark2[index], label=f"run {index + 1}", linewidth=2)
ax.set_yscale("log")
ax.set_xlabel("iteration")
ax.set_ylabel("residual")
ax.set_title("Convergence curves")
ax.legend(fontsize=9)
savefig(fig, "convergence_curves.pdf")

# ---------------------------------------------------------------------------
# 4. Donut chart -- seaborn's muted "Accent", a categorical share breakdown
shares = np.array([28, 22, 19, 16, 15])
accent = plt.get_cmap("Accent").colors[:len(shares)]
fig, ax = plt.subplots(figsize=FIGSIZE)
wedges, _ = ax.pie(shares, colors=accent, startangle=90, wedgeprops={"width": 0.4})
ax.legend(wedges, [f"category {i + 1}" for i in range(len(shares))],
          loc="center left", bbox_to_anchor=(1.0, 0.5), fontsize=9)
ax.set_title("Share breakdown (synthetic)")
savefig(fig, "share_donut.pdf")

# ---------------------------------------------------------------------------
# 5. Heatmap -- a genuinely continuous *diverging* colormap (coolwarm)
size = 12
base = rng.normal(0, 1, size=(size, size))
correlation = np.corrcoef(base)
fig, ax = plt.subplots(figsize=FIGSIZE)
sns.heatmap(correlation, cmap="coolwarm", center=0, ax=ax, cbar_kws={"label": "correlation"})
ax.set_title("Synthetic correlation matrix")
savefig(fig, "correlation_heatmap.pdf")

# ---------------------------------------------------------------------------
# 6. Contour plot -- a genuinely continuous *sequential* colormap (viridis)
xx, yy = np.meshgrid(np.linspace(-3, 3, 200), np.linspace(-3, 3, 200))
field = np.exp(-(xx**2 + yy**2) / 4) + 0.5 * np.exp(-((xx - 1.5)**2 + (yy - 1.5)**2) / 2)
fig, ax = plt.subplots(figsize=FIGSIZE)
contour = ax.contourf(xx, yy, field, levels=15, cmap="viridis")
fig.colorbar(contour, ax=ax, label="density")
ax.set_title("Synthetic density field")
ax.set_xlabel("x")
ax.set_ylabel("y")
savefig(fig, "density_contour.pdf")

# ---------------------------------------------------------------------------
# 7. Random noise field -- a third, unrelated continuous colormap (plasma)
noise = rng.normal(size=(60, 60))
smoothed = np.zeros_like(noise)
kernel = np.ones((5, 5)) / 25
pad = np.pad(noise, 2, mode="wrap")
for i in range(smoothed.shape[0]):
    for j in range(smoothed.shape[1]):
        smoothed[i, j] = (pad[i:i + 5, j:j + 5] * kernel).sum()
fig, ax = plt.subplots(figsize=FIGSIZE)
image = ax.imshow(smoothed, cmap="plasma")
fig.colorbar(image, ax=ax, label="amplitude")
ax.set_title("Smoothed noise field")
ax.set_xticks([])
ax.set_yticks([])
savefig(fig, "noise_field.pdf")

# ---------------------------------------------------------------------------
# 8. A plain PNG logo, reused from examples/images -- exercises the raster
#    path (and is a fun thing to watch pycasso recolour in the paper itself)
shutil.copy(JOLLY_LOGO, FIGURES / "jolly.png")

print(f"wrote {len(list(FIGURES.iterdir()))} figure files -> {FIGURES}")

# ---------------------------------------------------------------------------
# main.tex -- a paper *about* pycasso, including two pycasso code snippets,
# a table of contents, and a "colour source" note (with a link) under every
# figure. \definecolor entries and the listings style mirror a real paper's
# setup (hyperlink colours, syntax-highlighted code using xcolor named
# colours), so restyling this project exercises the same code paths.
MAIN_TEX = r"""\documentclass[11pt]{article}
\usepackage[margin=1in]{geometry}
\usepackage{graphicx}
\usepackage[dvipsnames]{xcolor}
\usepackage{listings}

\definecolor{persianred}{rgb}{0.8, 0.2, 0.2}
\definecolor{mediumpersianblue}{rgb}{0.0, 0.4, 0.65}
\definecolor{darklavender}{rgb}{0.45, 0.31, 0.59}
\definecolor{lightcodegray}{rgb}{0.97, 0.97, 0.97}
\definecolor{softborder}{gray}{0.8}

\usepackage[colorlinks=true,citecolor=mediumpersianblue,linkcolor=persianred,urlcolor=darklavender]{hyperref}

\lstdefinestyle{pythonstyle}{
    language=Python,
    backgroundcolor=\color{lightcodegray},
    commentstyle=\color{ForestGreen}\itshape,
    keywordstyle=\color{NavyBlue}\bfseries,
    stringstyle=\color{BrickRed},
    basicstyle=\ttfamily\small,
    breaklines=true,
    frame=single,
    framerule=0.3pt,
    rulecolor=\color{softborder},
    numbers=left,
    numbersep=5pt,
}
\lstset{style=pythonstyle}

\title{A Toy Paper for \texttt{pycasso}}
\author{An Example Author}
\date{}

\begin{document}
\maketitle
\tableofcontents
\vspace{1em}

\begin{abstract}
This is a synthetic paper, generated only to demonstrate \texttt{pycasso}'s
project-wide restyling on a document with several figures, each plotted
with a different, mismatched colour scheme -- the kind of inconsistency
that accumulates naturally across a real paper's revision history, as
different co-authors add figures with whatever colour scheme their own
plotting habits default to. None of the numbers below mean anything; only
the colours, and how \texttt{pycasso} reassigns them, do. Every figure's
caption names exactly which colour source it used, linked, so you can look
it up and compare it against whatever \texttt{pycasso} decided to do with
it.
\end{abstract}

\section{Introduction}
\texttt{pycasso} recolours the figures of a paper -- and, when given the
project's own \LaTeX{} source rather than just the compiled PDF, its
hyperlink colours and code-listing syntax highlighting too -- onto a
consistent palette (see \url{https://github.com/MatteoRobbiati/pycasso}).
It decides how many independent colours a document really uses by
clustering hues, then assigns each one a distinct replacement from the
target palette whenever the palette has enough hue families to offer one.
Sections~\ref{sec:categorical} and~\ref{sec:continuous} below run through
the two kinds of figure it treats differently: a handful of discrete
series colours, versus a genuinely continuous colormap encoding a
continuous quantity.

\section{Discrete, categorical figures}
\label{sec:categorical}
The four figures in this section each use a small number of distinct,
named colours -- exactly the case \texttt{pycasso.fit()} is built around.
Figure~\ref{fig:runtime} uses matplotlib's default qualitative cycle,
\href{https://matplotlib.org/stable/users/prev_whats_new/dflt_style_changes.html#colors-in-default-property-cycle}{tab10}.
Figure~\ref{fig:scatter} uses seaborn's
\href{https://seaborn.pydata.org/tutorial/color_palettes.html}{Set2}.
Figure~\ref{fig:convergence} uses matplotlib's
\href{https://matplotlib.org/stable/users/explain/colors/colormaps.html\#qualitative}{Dark2}.
Figure~\ref{fig:donut} uses matplotlib's
\href{https://matplotlib.org/stable/users/explain/colors/colormaps.html\#qualitative}{Accent}.
None of these four sources were designed with one another in mind, which
is exactly the point: a real paper accretes exactly this kind of mismatch
one figure at a time.

\begin{figure}[h]
    \centering
    \includegraphics[width=0.85\linewidth]{figures/benchmark_runtime.pdf}
    \caption{Restyle runtime across releases (illustrative numbers). Colour source: matplotlib \href{https://matplotlib.org/stable/users/prev_whats_new/dflt_style_changes.html\#colors-in-default-property-cycle}{tab10}.}
    \label{fig:runtime}
\end{figure}

\begin{figure}[h]
    \centering
    \includegraphics[width=0.85\linewidth]{figures/cluster_scatter.pdf}
    \caption{Cluster assignment in a toy feature space. Colour source: seaborn \href{https://seaborn.pydata.org/tutorial/color_palettes.html}{Set2}.}
    \label{fig:scatter}
\end{figure}

\begin{figure}[h]
    \centering
    \includegraphics[width=0.85\linewidth]{figures/convergence_curves.pdf}
    \caption{Convergence curves for five synthetic runs. Colour source: matplotlib \href{https://matplotlib.org/stable/users/explain/colors/colormaps.html\#qualitative}{Dark2}.}
    \label{fig:convergence}
\end{figure}

\begin{figure}[h]
    \centering
    \includegraphics[width=0.7\linewidth]{figures/share_donut.pdf}
    \caption{A synthetic share breakdown. Colour source: matplotlib \href{https://matplotlib.org/stable/users/explain/colors/colormaps.html\#qualitative}{Accent}.}
    \label{fig:donut}
\end{figure}

\clearpage
\section{Continuous colormaps}
\label{sec:continuous}
Not every figure uses a handful of discrete colours. The three figures
below use unrelated \emph{continuous} colormaps: a diverging one, and two
sequential ones with entirely different hues. \texttt{pycasso} recognises
this (see \texttt{pycasso.cluster.looks\_continuous}) and switches to
\texttt{pycasso.fit\_colormap}, which finds each figure's own one or two
dominant hues and blends continuously between their replacements, instead
of snapping a smooth gradient onto a handful of discrete colours and
introducing visible banding.

\begin{figure}[h]
    \centering
    \includegraphics[width=0.75\linewidth]{figures/correlation_heatmap.pdf}
    \caption{A synthetic correlation matrix. Colour source: matplotlib/seaborn \href{https://matplotlib.org/stable/users/explain/colors/colormaps.html\#diverging}{coolwarm} (diverging).}
    \label{fig:heatmap}
\end{figure}

\begin{figure}[h]
    \centering
    \includegraphics[width=0.75\linewidth]{figures/density_contour.pdf}
    \caption{A synthetic density field. Colour source: matplotlib \href{https://matplotlib.org/stable/users/explain/colors/colormaps.html\#sequential}{viridis} (sequential).}
    \label{fig:contour}
\end{figure}

\begin{figure}[h]
    \centering
    \includegraphics[width=0.75\linewidth]{figures/noise_field.pdf}
    \caption{A smoothed noise field. Colour source: matplotlib \href{https://matplotlib.org/stable/users/explain/colors/colormaps.html\#sequential}{plasma} (sequential, unrelated hue to viridis).}
    \label{fig:noise}
\end{figure}

\clearpage
\section{A raster logo}
\texttt{pycasso} works on plain images too, not just figures inside a
paper. Figure~\ref{fig:jolly} is a flat PNG, included here to exercise that
same path from inside a full project restyle. Its own colours (a
particular yellow and red) happen to already sit close to some palettes'
own yellow and red, so a restyle onto one of those can look almost
unchanged at a glance -- that is \texttt{mode="hue"} correctly doing very
little when there is very little to do, not a sign that nothing happened;
a palette with unrelated hues (e.g. \texttt{violet}) changes it clearly.

\begin{figure}[h]
    \centering
    \includegraphics[width=0.35\linewidth]{figures/jolly.png}
    \caption{A raster logo, recoloured alongside everything else. Original colours: flat yellow and red, no particular named source.}
    \label{fig:jolly}
\end{figure}

\clearpage
\section{Using pycasso}
Restyling the compiled PDF alone reaches only what ended up embedded as a
drawing object:

\begin{lstlisting}
import pycasso

palette = pycasso.Palette.load("okabe-ito")
paper = pycasso.Painter("main.pdf")
fitted = pycasso.fit(paper, palette)
paper.restyle(fitted, mode="hue")
paper.save("main_restyled.pdf")
\end{lstlisting}

Working from the project's own source, as this paper does, also reaches
hyperlink colours and code-listing syntax highlighting:

\begin{lstlisting}
import pycasso

palette = pycasso.Palette.load("persian")
project = pycasso.Project("toy_paper.zip")
fitted = pycasso.fit(project, palette)
project.restyle(fitted, mode="hue")
project.save("toy_paper_restyled.zip")
\end{lstlisting}

See \url{https://github.com/MatteoRobbiati/pycasso} for the full API.

\section{Conclusion}
This document exists only to be recoloured.

\end{document}
"""
(SOURCE / "main.tex").write_text(MAIN_TEX, encoding="utf-8")
print(f"wrote {SOURCE / 'main.tex'}")

# ---------------------------------------------------------------------------
# pack into an Overleaf-style zip, exactly what pycasso.Project expects
zip_path = HERE / "toy_paper.zip"
with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
    for file in sorted(SOURCE.rglob("*")):
        if file.is_file():
            archive.write(file, Path("toy_paper") / file.relative_to(SOURCE))
print(f"zipped -> {zip_path}")

# ---------------------------------------------------------------------------
# compile twice (a table of contents needs a second pass to settle page
# numbers), if a LaTeX toolchain happens to be available -- entirely optional
engine = shutil.which("latexmk") or shutil.which("pdflatex")
if engine:
    args = (
        [engine, "-pdf", "-interaction=nonstopmode", "-halt-on-error", "main.tex"]
        if "latexmk" in engine else
        [engine, "-interaction=nonstopmode", "-halt-on-error", "main.tex"]
    )
    passes = 1 if "latexmk" in engine else 2   # latexmk already reruns as needed
    for _ in range(passes):
        result = subprocess.run(args, cwd=SOURCE, capture_output=True, text=True)
        if result.returncode != 0:
            print("compilation failed:\n" + "\n".join(result.stdout.splitlines()[-20:]))
            break
    else:
        shutil.copy(SOURCE / "main.pdf", HERE / "main.pdf")
        print(f"compiled -> {HERE / 'main.pdf'}")
else:
    print("no LaTeX toolchain found -- skipped compiling main.pdf (toy_paper.zip is still complete)")
