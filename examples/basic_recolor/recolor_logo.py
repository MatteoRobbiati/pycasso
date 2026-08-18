"""
Several ways to recolour a single image, from simplest to most automatic.

Run from this directory:

    uv run python recolor_logo.py
"""

import matexxe

# --- 1. Direct colour replacement -------------------------------------------
# Precise, manual control: swap one exact colour for another. Good when you
# already know exactly which colour needs to go.
logo = matexxe.Painter("images/chalmers_logo.png")
logo.replace_colors(old_color=(0, 0, 0), new_color=(255, 255, 255), alpha=None)
logo.save("images/chalmers_white.png")

# --- 2. Swap one flat colour for another ------------------------------------
# Same replace_colors call, this time on the icon: swap its background
# blue for a flat orange. An exact, deterministic colour swap, no palette
# or clustering involved, good when there is exactly one colour to change
# and you already know what it should become.
icon = matexxe.Painter("images/matexxe-icon-512.png")
icon.replace_colors(old_color=(143, 163, 220), new_color=(230, 81, 0), alpha=None)
icon.save("images/matexxe-icon-512-recolored.png")

# --- 3. Remove a background colour ------------------------------------------
# remove_color makes matching pixels transparent instead of replacing them
# with another colour, handy for stripping a flat background. shadow_range
# also catches the antialiased pixels along the icon's rounded corners and
# letterforms, which are a slightly different shade of the same blue, not
# an exact match, and would otherwise leave a faint halo behind.
icon = matexxe.Painter("images/matexxe-icon-512.png")
icon.remove_color(color=(143, 163, 220), shadow_range=30)
icon.save("images/matexxe-icon-512-transparent.png")

# --- 4. Palette-based restyle ------------------------------------------------
# Automatic: matexxe.fit() looks at how many independent colours the image
# actually uses and assigns each one a replacement from the target palette,
# no need to know the exact colours up front. See matexxe.available() for
# the built-in palettes.
jolly = matexxe.Painter("images/jolly.png")
palette = matexxe.Palette.load("violet")
fitted = matexxe.fit(jolly, palette)
jolly.restyle(fitted, mode="hue")
jolly.save("images/jolly_violet.png")

# --- 5. Same image, a different palette -------------------------------------
# Nothing about the call changes, only the palette. green-orange is a
# deliberately narrow diagnostic palette, useful for confirming a restyle
# actually changed something, since the result can't be mistaken for the
# original by accident.
jolly = matexxe.Painter("images/jolly.png")
palette = matexxe.Palette.load("green-orange")
fitted = matexxe.fit(jolly, palette)
jolly.restyle(fitted, mode="hue")
jolly.save("images/jolly_green-orange.png")

print("wrote images/chalmers_white.png, images/matexxe-icon-512-recolored.png, "
      "images/matexxe-icon-512-transparent.png, "
      "images/jolly_violet.png and images/jolly_green-orange.png")
