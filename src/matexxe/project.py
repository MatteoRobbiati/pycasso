"""
Work with a paper's full source, not just its compiled PDF.

A compiled PDF only exposes colours that ended up embedded as a discrete
drawing object. Colours LaTeX paints directly -- hyperlink and citation
colours defined with ``\\definecolor`` and wired up through ``hyperref`` --
never become one, so restyling a compiled PDF alone can't reach them.
Working from the project's own source (typically an Overleaf "Source"
download) reaches both of those, plus the original figure files themselves,
which are usually cleaner than reverse-engineering a flattened, compiled PDF.

``Project`` never requires a LaTeX toolchain: :meth:`Project.restyle` and
:meth:`Project.save` work purely by editing files inside the extracted
project and repacking them. :meth:`Project.compile` is a separate, optional
convenience for producing a PDF locally instead of re-uploading to Overleaf,
and fails with a clear, actionable message if no toolchain is installed.
"""

import logging
import re
import shutil
import subprocess
import tempfile
import zipfile
from collections import Counter
from pathlib import Path

import numpy as np

from matexxe.cluster import hue_families
from matexxe.color import parse, to_hex, to_lab
from matexxe.workshop import Painter

log = logging.getLogger(__name__)

_INCLUDEGRAPHICS = re.compile(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}")
_DEFINECOLOR = re.compile(r"\\definecolor\{(?P<name>[^}]+)\}\{(?P<model>[^}]+)\}\{(?P<spec>[^}]+)\}")

# extensions LaTeX tries, in order, when \includegraphics omits one
GRAPHICS_EXTENSIONS = (".pdf", ".png", ".jpg", ".jpeg", ".eps")

_JUNK_NAMES = {".ds_store"}


class _WithSkip:
    """
    ``palette``, but with ``.skip`` replaced.

    Used by :meth:`Project.restyle` to hand each asset a version of the
    palette whose ``.skip`` has been translated from globally-qualified
    figure names back to that one asset's own unqualified names -- every
    other attribute (``.map()``, ``.name``, ``.clusters``, ``.assigned``,
    ...) forwards straight through to ``palette``.
    """

    def __init__(self, palette, skip):
        self._palette = palette
        self.skip = frozenset(skip)

    def __getattr__(self, name):
        return getattr(self._palette, name)


#: listings-package style keys that set actual syntax-highlight colour --
#: deliberately excludes backgroundcolor/rulecolor (the code block's
#: background and border, structural chrome that should stay put) and
#: numberstyle (line numbers, conventionally neutral grey).
CODE_STYLE_KEYS = ("commentstyle", "keywordstyle", "stringstyle", "identifierstyle")
_CODE_STYLE_COLOR = re.compile(
    r"(?P<key>" + "|".join(CODE_STYLE_KEYS) + r")\s*=\s*\\color(?:\[(?P<model>[^\]]+)\])?\{(?P<value>[^}]+)\}"
)


class CodeStyleColor:
    """
    One syntax-highlight colour reference found in the source -- typically
    inside an ``\\lstdefinestyle``/``\\lstset`` block for the ``listings``
    package, e.g. ``keywordstyle=\\color{NavyBlue}``.

    Deliberately narrower than ``\\definecolor``: only :data:`CODE_STYLE_KEYS`
    are covered -- never ``backgroundcolor`` or ``rulecolor``, the code
    block's background and border, which should stay whatever neutral
    colour the author chose rather than follow the document's theme.
    """

    def __init__(self, key:str, model, value:str, line:int):
        self.key = key
        self.model = model      # None for a plain \color{Name} reference
        self.value = value      # the colour name, or the raw spec if model is set
        self.line = line
        self.rgb = None         # set once resolved -- stays None if it can't be

    def __repr__(self):
        spec = f"[{self.model}]{{{self.value}}}" if self.model else f"{{{self.value}}}"
        return f"CodeStyleColor({self.key}=\\color{spec})"


class TexColor:
    """One ``\\definecolor`` entry: a name, its current RGB, and its source line."""

    def __init__(self, name:str, model:str, spec:str, line:int):
        self.name = name
        self.model = model.strip()
        self.spec = spec.strip()
        self.line = line
        self.rgb = self._parse(self.model, self.spec)

    @staticmethod
    def _parse(model, spec):
        # xcolor's "rgb" (0-1 floats) and "RGB" (0-255 integers) differ only
        # by case, so the exact-case forms must be checked before anything
        # gets lowercased
        if model == "HTML":
            return parse(spec)
        if model == "RGB":
            return np.array([float(p.strip()) for p in spec.split(",")]) / 255
        if model == "rgb":
            return np.array([float(p.strip()) for p in spec.split(",")])
        if model.lower() in ("gray", "grey"):
            value = float(spec.split(",")[0])
            return np.array([value, value, value])
        raise ValueError(f"unsupported \\definecolor model {model!r}")

    def formatted(self, rgb):
        """Render ``rgb`` back using this entry's original model."""
        if self.model.lower() == "html":
            return to_hex(rgb).lstrip("#")
        if self.model == "RGB":
            return ",".join(str(int(round(v * 255))) for v in rgb)
        if self.model.lower() in ("gray", "grey"):
            return f"{float(np.mean(rgb)):.4f}"
        return ",".join(f"{v:.4f}" for v in rgb)

    def __repr__(self):
        return f"TexColor({self.name!r}, {to_hex(self.rgb)})"


class Project:
    def __init__(self, path, main_tex:str = None):
        """
        A paper's Overleaf source: figure assets plus LaTeX-defined colours.

        Args:
            path: path to the project's ``.zip`` (an Overleaf "Source"
                download) or to an already-extracted project directory;
            main_tex: relative path to the root ``.tex`` file, if it can't
                be found automatically (see :meth:`_find_main_tex`).
        """
        self.path = Path(path)
        if self.path.is_dir():
            self._workdir = self.path
            self._owns_workdir = False
        else:
            self._workdir = Path(tempfile.mkdtemp(prefix="matexxe_project_"))
            self._owns_workdir = True
            with zipfile.ZipFile(self.path) as archive:
                for member in archive.namelist():
                    if member.startswith("__MACOSX/") or Path(member).name.lower() in _JUNK_NAMES:
                        continue
                    archive.extract(member, self._workdir)
        log.info("opened %s -> %s", self.path, self._workdir)

        self.tex_files = sorted(self._workdir.rglob("*.tex"))
        self.main_tex = (self._workdir / main_tex) if main_tex else self._find_main_tex()
        if self.main_tex:
            log.info("main .tex: %s", self.main_tex.relative_to(self._workdir))
        else:
            log.warning("no main .tex file found -- figure assets and \\definecolor entries won't be discovered")

        source = self.main_tex.read_text(encoding="utf-8", errors="replace") if self.main_tex else ""
        self.tex_colors = self._parse_colors(source) if self.main_tex else []
        self.code_styles = self._parse_code_styles(source) if self.main_tex else []
        self.assets = self._load_assets(source) if self.main_tex else {}

        log.info("found %d figure asset(s), %d \\definecolor entr%s, %d code-style colour%s",
                  len(self.assets), len(self.tex_colors), "y" if len(self.tex_colors) == 1 else "ies",
                  len(self.code_styles), "" if len(self.code_styles) == 1 else "s")

    def _find_main_tex(self):
        """The one .tex file with \\documentclass, preferring one literally named main.tex."""
        candidates = [p for p in self.tex_files if "documentclass" in p.read_text(encoding="utf-8", errors="replace")]
        if len(candidates) == 1:
            return candidates[0]
        if len(candidates) > 1:
            named = [p for p in candidates if p.stem == "main"]
            if len(named) == 1:
                return named[0]
            raise ValueError(
                f"found {len(candidates)} .tex files with \\documentclass, can't tell which is "
                f"the main one: {[str(p.relative_to(self._workdir)) for p in candidates]}; "
                "pass main_tex= explicitly"
            )
        return None

    def _load_assets(self, source):
        assets = {}
        for match in _INCLUDEGRAPHICS.finditer(source):
            ref = match.group(1)
            if ref in assets:
                continue
            resolved = self._resolve_graphics_path(self.main_tex.parent, ref)
            if resolved is None:
                log.warning(r"could not resolve \includegraphics{%s}; skipping", ref)
                continue
            try:
                assets[ref] = Painter(str(resolved))
            except ValueError as error:
                log.warning("no Painter backend for %s (%s); skipping", resolved, error)
        return assets

    @staticmethod
    def _resolve_graphics_path(base, ref):
        direct = base / ref
        if direct.is_file():
            return direct
        for extension in GRAPHICS_EXTENSIONS:
            candidate = base / f"{ref}{extension}"
            if candidate.is_file():
                return candidate
        return None

    def _parse_colors(self, source):
        colors = []
        for line_number, line in enumerate(source.splitlines(), start=1):
            match = _DEFINECOLOR.search(line)
            if not match:
                continue
            try:
                colors.append(TexColor(match.group("name"), match.group("model"), match.group("spec"), line_number))
            except ValueError as error:
                log.debug("skipping \\definecolor on line %d (%s)", line_number, error)
        return colors

    def _parse_code_styles(self, source):
        """
        Find syntax-highlight colour references -- see :data:`CODE_STYLE_KEYS`.

        A reference that names one of this document's own ``\\definecolor``
        entries is resolved to that colour's actual RGB (accurate: that
        entry is already recoloured by :meth:`_restyle_tex_colors`, nothing
        further needed here). A reference to an external named colour --
        typically one of xcolor's built-in sets, e.g. dvipsnames'
        ``ForestGreen`` -- has no locally-known RGB, so it's left
        unresolved (``.rgb is None``) rather than guessing; see
        :meth:`_restyle_code_styles` for how those are still handled.
        """
        found = []
        color_by_name = {entry.name: entry for entry in self.tex_colors}
        for line_number, line in enumerate(source.splitlines(), start=1):
            for match in _CODE_STYLE_COLOR.finditer(line):
                key, model, value = match.group("key"), match.group("model"), match.group("value")
                entry = CodeStyleColor(key, model, value, line_number)
                if model is not None:
                    try:
                        entry.rgb = TexColor._parse(model, value)
                    except ValueError as error:
                        log.debug("code style %s on line %d: %s", key, line_number, error)
                elif value in color_by_name:
                    entry.rgb = color_by_name[value].rgb
                found.append(entry)
        return found

    @property
    def figures(self):
        """
        Every figure across every figure asset -- what :func:`~matexxe.fit.fit` sizes the palette from.

        Names are qualified with their owning asset (``"asset::figure"``).
        Two different single-page assets both name their own page figure
        ``"page1"`` -- entirely reasonable on its own, since each asset's
        ``.figures`` is independently unique -- but collecting them across
        assets without qualifying first would silently conflate two
        unrelated figures that happen to share a name, corrupting
        :attr:`~matexxe.fit.PaletteFit.skip`. :meth:`restyle` translates
        the qualified names back before handing each asset its own figures.
        """
        found = []
        for asset, painter in self.assets.items():
            for figure in painter.figures:
                figure.name = f"{asset}::{figure.name}"
                found.append(figure)
        return found

    def colors(self):
        """Count of every colour used across every figure asset, keyed by hex."""
        tally = Counter()
        for figure in self.figures:
            tally.update(figure.colors())
        return tally

    def restyle(self, palette, mode:str = "hue", keep_greys:bool = True,
                grey_tolerance:float = 0.04, recolor_tex:bool = True, recolor_colormaps:bool = True,
                recolor_code_styles:bool = True):
        """
        Restyle every figure asset and, by default, every ``\\definecolor``
        and syntax-highlight colour.

        Args:
            palette: the target palette (a plain
                :class:`~matexxe.palette.Palette` or a
                :class:`~matexxe.fit.PaletteFit`);
            mode, keep_greys, grey_tolerance: forwarded to each asset's
                ``.restyle()`` -- see :meth:`Palette.map
                <matexxe.palette.Palette.map>`. ``keep_greys`` also governs
                ``\\definecolor``: a near-grey entry is almost always a
                code-listing background or border, which should stay
                whatever neutral colour the author chose rather than
                follow the theme -- this is exactly why ``keep_greys``
                defaults to ``True``;
            recolor_tex: also rewrite ``\\definecolor`` lines in the main
                ``.tex`` file. Classified against the same palette, so a
                document colour used both in a figure and as, say, the
                hyperlink colour ends up consistent;
            recolor_colormaps: recolour figures flagged as a continuous
                colormap with :func:`~matexxe.cmap.fit_colormap` instead of
                leaving them untouched -- see
                :meth:`~matexxe.paper.PdfPainter.restyle`.
            recolor_code_styles: also rewrite ``keywordstyle``/``commentstyle``/
                ``stringstyle``/``identifierstyle`` colour references --
                see :data:`CODE_STYLE_KEYS`. Never touches
                ``backgroundcolor``/``rulecolor``, regardless of this flag.

        This only mutates each asset's in-memory :class:`~matexxe.workshop.Painter`
        -- call :meth:`save` afterwards to write the changes back to the
        extracted project and pack it into a new zip.
        """
        self.changes = Counter()
        global_skip = set(getattr(palette, "skip", ()))
        for asset, painter in self.assets.items():
            # translate the globally-qualified skip set back to this
            # asset's own unqualified figure names -- see .figures for why
            # the qualification exists in the first place
            prefix = f"{asset}::"
            local_skip = {name[len(prefix):] for name in global_skip if name.startswith(prefix)}
            asset_palette = _WithSkip(palette, local_skip) if local_skip else palette

            painter.restyle(asset_palette, mode=mode, keep_greys=keep_greys, grey_tolerance=grey_tolerance,
                             recolor_colormaps=recolor_colormaps)
            self.changes.update(getattr(painter, "changes", None) or {})

        if recolor_tex and self.tex_colors:
            self._restyle_tex_colors(palette, mode, keep_greys, grey_tolerance)
        if recolor_code_styles and self.code_styles:
            self._restyle_code_styles(palette)
        return self

    def _restyle_tex_colors(self, palette, mode, keep_greys, grey_tolerance):
        lines = self.main_tex.read_text(encoding="utf-8", errors="replace").splitlines()
        touched = False
        for entry in self.tex_colors:
            mapped, changed = palette.map(
                entry.rgb.reshape(1, 3), mode=mode, keep_greys=keep_greys, grey_tolerance=grey_tolerance,
            )
            if not changed[0]:
                log.debug(r"  \definecolor{%s}: unchanged (%s)", entry.name, to_hex(entry.rgb))
                continue
            new_rgb = mapped[0]
            new_spec = entry.formatted(new_rgb)
            lines[entry.line - 1] = _DEFINECOLOR.sub(
                lambda m, e=entry, s=new_spec: (
                    f"\\definecolor{{{e.name}}}{{{e.model}}}{{{s}}}" if m.group("name") == e.name else m.group(0)
                ),
                lines[entry.line - 1],
            )
            log.info(r"  \definecolor{%s}: %s -> %s", entry.name, to_hex(entry.rgb), to_hex(new_rgb))
            touched = True
        if touched:
            self.main_tex.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _restyle_code_styles(self, palette):
        """
        Recolour syntax-highlight references -- see :data:`CODE_STYLE_KEYS`.

        An entry that resolves to one of this document's own
        ``\\definecolor`` entries needs nothing further: that entry was
        already recoloured by :meth:`_restyle_tex_colors`, and this
        reference just names it. An entry naming an external colour (no
        local ``\\definecolor`` -- typically one of xcolor's built-in sets)
        has no RGB we can look up, so rather than guess one, it's assigned
        a fresh colour directly and rewritten in place.
        """
        unresolved = [entry for entry in self.code_styles if entry.rgb is None]
        if not unresolved:
            return

        by_value = {}
        for entry in unresolved:
            by_value.setdefault(entry.value, []).append(entry)
        names = sorted(by_value)

        if hasattr(palette, "clusters") and hasattr(palette, "assigned") and palette.clusters:
            target_rgb_pool = palette.assigned
        else:
            target_rgb_pool = palette.rgb[palette.target_pool(len(names))]
        target_hue = np.arctan2(to_lab(target_rgb_pool)[:, 2], to_lab(target_rgb_pool)[:, 1])
        families = hue_families(target_hue, merge_degrees=30.0)

        lines = self.main_tex.read_text(encoding="utf-8", errors="replace").splitlines()
        touched = False
        for index, name in enumerate(names):
            # cycle through distinct hue families -- comment/keyword/string
            # end up on genuinely different hues whenever the palette
            # offers enough; if it doesn't, later roles start repeating
            _, member_indices = families[index % len(families)]
            # the most saturated member of the family: syntax highlighting
            # reads better bold and vivid than pale, unlike a figure fill
            chroma = np.hypot(to_lab(target_rgb_pool[member_indices])[:, 1],
                               to_lab(target_rgb_pool[member_indices])[:, 2])
            new_rgb = target_rgb_pool[member_indices[int(np.argmax(chroma))]]
            new_hex = to_hex(new_rgb).lstrip("#")

            keys = sorted({entry.key for entry in by_value[name]})
            for entry in by_value[name]:
                old = f"\\color{f'[{entry.model}]' if entry.model else ''}{{{entry.value}}}"
                new = f"\\color[HTML]{{{new_hex}}}"
                line = lines[entry.line - 1]
                if old not in line:
                    log.warning(r"could not find %s on line %d to rewrite; skipping", old, entry.line)
                    continue
                lines[entry.line - 1] = line.replace(old, new, 1)
                touched = True
            log.info(r"  %s (%s): -> %s", name, ", ".join(keys), new_hex)

        if touched:
            self.main_tex.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def save(self, output_path):
        """
        Flush every figure asset to disk, then repack the project into a new zip.

        :meth:`restyle` only mutates each asset's in-memory
        :class:`~matexxe.workshop.Painter` -- nothing reaches the extracted
        project on disk until this writes each one back to its own file
        (``\\definecolor`` changes are the exception: those are written
        straight to ``main.tex`` as they happen, since there's no
        in-memory Painter standing in for the ``.tex`` source itself).
        """
        for asset, painter in self.assets.items():
            painter.save(painter.imagepath)
            log.debug("flushed %s -> %s", asset, painter.imagepath)

        output_path = Path(output_path)
        with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as archive:
            for file in sorted(self._workdir.rglob("*")):
                if file.is_file():
                    archive.write(file, file.relative_to(self._workdir))
        log.info("saved %s", output_path)
        return output_path

    def compile(self, output_pdf=None, engine:str = None):
        """
        Recompile the project locally, if a LaTeX toolchain is available.

        Entirely optional: :meth:`restyle` and :meth:`save` never need this.
        Call it only if you want a compiled PDF back without re-uploading
        the result of :meth:`save` to Overleaf and recompiling there.

        Args:
            output_pdf: where to copy the resulting PDF; left in place next
                to the source if omitted;
            engine: ``"latexmk"`` or ``"pdflatex"``; tries both, in that
                order, if omitted.

        Raises:
            RuntimeError: if there's no main ``.tex`` file, no LaTeX
                toolchain is found on ``PATH``, or compilation fails --
                in each case with a message explaining what to do instead.
        """
        if self.main_tex is None:
            raise RuntimeError("no main .tex file found to compile")

        candidates = [engine] if engine else ["latexmk", "pdflatex"]
        found = next((shutil.which(name) for name in candidates if name and shutil.which(name)), None)
        if found is None:
            raise RuntimeError(
                f"no LaTeX toolchain found on PATH (looked for {', '.join(candidates)}). "
                "Install TeX Live / MacTeX to compile locally, or call .save(...) and "
                "recompile on Overleaf instead -- restyle() and save() never need LaTeX."
            )

        args = (
            [found, "-pdf", "-interaction=nonstopmode", "-halt-on-error", self.main_tex.name]
            if Path(found).name.startswith("latexmk") else
            [found, "-interaction=nonstopmode", "-halt-on-error", self.main_tex.name]
        )
        log.info("compiling with %s", " ".join(args))
        result = subprocess.run(args, cwd=self.main_tex.parent, capture_output=True, text=True)
        if result.returncode != 0:
            tail = "\n".join(result.stdout.splitlines()[-40:])
            raise RuntimeError(f"compilation failed (exit {result.returncode}):\n{tail}")

        produced = self.main_tex.with_suffix(".pdf")
        if output_pdf:
            output_pdf = Path(output_pdf)
            shutil.copy(produced, output_pdf)
            log.info("compiled -> %s", output_pdf)
            return output_pdf
        log.info("compiled -> %s", produced)
        return produced

    def cleanup(self):
        """Remove the temporary extraction directory, if one was created."""
        if self._owns_workdir:
            shutil.rmtree(self._workdir, ignore_errors=True)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.cleanup()

    def __repr__(self):
        return f"Project({self.path!r}, {len(self.assets)} assets, {len(self.tex_colors)} tex colours)"
