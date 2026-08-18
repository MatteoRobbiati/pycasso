"""
The two ways to recolour a single image, from simplest to most automatic.

Run from this directory:

    uv run python recolor_logo.py
"""

import pycasso

# --- 1. Direct colour replacement -----------------------------------------
# Precise, manual control: swap one exact colour for another. Good when you
# already know exactly which colour needs to go.
logo = pycasso.Painter("images/chalmers_logo.png")
logo.replace_colors(old_color=(0, 0, 0), new_color=(255, 255, 255), alpha=None)
logo.save("images/chalmers_white.png")

# --- 2. Palette-based restyle ----------------------------------------------
# Automatic: pycasso.fit() figures out how many independent colours the
# image uses and assigns each one a replacement from the target palette --
# no need to know the exact colours up front. See pycasso.available() for
# the built-in palettes.
jolly = pycasso.Painter("images/jolly.png")
palette = pycasso.Palette.load("okabe-ito")
fitted = pycasso.fit(jolly, palette)
jolly.restyle(fitted, mode="hue")
jolly.save("images/jolly_okabe-ito.png")

print("wrote images/chalmers_white.png and images/jolly_okabe-ito.png")
