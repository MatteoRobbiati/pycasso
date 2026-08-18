"""
Three ways to recolour a single image, from simplest to most automatic.

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

# --- 2. Remove a background colour ------------------------------------------
# remove_color makes matching pixels transparent instead of replacing them
# with another colour, handy for stripping a flat background. shadow_range
# also catches the antialiased pixels along the icon's rounded corners and
# letterforms, which are a slightly different shade of the same blue, not
# an exact match, and would otherwise leave a faint halo behind.
icon = matexxe.Painter("images/matexxe-icon-512.png")
icon.remove_color(color=(143, 163, 220), shadow_range=30)
icon.save("images/matexxe-icon-512-transparent.png")

# --- 3. Palette-based restyle ------------------------------------------------
# Automatic: matexxe.fit() figures out how many independent colours the
# image uses and assigns each one a replacement from the target palette,
# no need to know the exact colours up front. See matexxe.available() for
# the built-in palettes.
jolly = matexxe.Painter("images/jolly.png")
palette = matexxe.Palette.load("okabe-ito")
fitted = matexxe.fit(jolly, palette)
jolly.restyle(fitted, mode="hue")
jolly.save("images/jolly_okabe-ito.png")

print("wrote images/chalmers_white.png, images/matexxe-icon-512-transparent.png "
      "and images/jolly_okabe-ito.png")
