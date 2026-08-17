.PHONY: all clean distclean clean-all view help watch

# Main LaTeX file
MAIN = main
TEX_FILES = $(MAIN).tex
BIBTEX_FILE = references.bib
PDF_OUTPUT = $(MAIN).pdf

# LaTeX compiler
LATEX = pdflatex
LATEX_FLAGS = -interaction=nonstopmode -halt-on-error
BIBTEX = bibtex

# Temporary files to clean
TEMP_EXTENSIONS = aux log out toc blg bbl fls fdb_latexmk synctex.gz

# Default target
all: $(PDF_OUTPUT)

# Main PDF compilation
$(PDF_OUTPUT): $(TEX_FILES) $(BIBTEX_FILE)
	@echo "Compiling LaTeX document..."
	$(LATEX) $(LATEX_FLAGS) $(MAIN) > /dev/null
	@echo "Running BibTeX..."
	$(BIBTEX) $(MAIN)
	@echo "Re-compiling LaTeX (first pass)..."
	$(LATEX) $(LATEX_FLAGS) $(MAIN) > /dev/null
	@echo "Re-compiling LaTeX (second pass)..."
	$(LATEX) $(LATEX_FLAGS) $(MAIN) > /dev/null
	@echo "✓ PDF compiled successfully: $(PDF_OUTPUT)"

# Watch mode - continuously recompile on file changes
watch:
	@command -v fswatch >/dev/null 2>&1 || { echo "fswatch not installed. Install with: brew install fswatch"; exit 1; }
	@echo "Watching for changes... (Press Ctrl+C to stop)"
	fswatch -e '\.swp' $(TEX_FILES) $(BIBTEX_FILE) figures/ | while read; do $(MAKE) all; done

# Clean temporary files
clean:
	@echo "Cleaning temporary files..."
	@for ext in $(TEMP_EXTENSIONS); do rm -f $(MAIN).$$ext; done
	@rm -f .DS_Store
	@echo "✓ Cleaned"

# Clean everything including PDF
distclean: clean
	@echo "Removing PDF..."
	@rm -f $(PDF_OUTPUT)
	@echo "✓ Full clean complete"

# Alias for distclean
clean-all: distclean

# View the PDF
view: $(PDF_OUTPUT)
	@command -v open >/dev/null 2>&1 && open $(PDF_OUTPUT) || xdg-open $(PDF_OUTPUT)
	@echo "Opening $(PDF_OUTPUT)..."

# Alias for view
open: view

# Show help
help:
	@echo "LaTeX Paper Build System"
	@echo ""
	@echo "Available targets:"
	@echo "  make              - Compile the paper (main.tex)"
	@echo "  make all          - Same as 'make'"
	@echo "  make clean        - Remove temporary LaTeX files"
	@echo "  make clean-all    - Remove everything including PDF"
	@echo "  make distclean    - Same as clean-all"
	@echo "  make view/open    - Compile and open PDF viewer"
	@echo "  make watch        - Watch for changes and auto-compile (requires fswatch)"
	@echo "  make help         - Show this help message"
	@echo ""
	@echo "Temporary files cleaned: $(TEMP_EXTENSIONS)"
