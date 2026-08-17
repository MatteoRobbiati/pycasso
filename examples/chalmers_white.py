from pycasso import workshop

picture = workshop.Painter("images/chalmers_logo.png")
picture.replace_colors(
    old_color=(0, 0, 0),
    new_color=(255, 255, 255),
    alpha=255
)
picture.save("images/chalmers_white.png")