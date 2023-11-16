from PIL import Image

img_name = "IFT.png"

img = Image.open(f"images/{img_name}")
img = img.convert("RGBA")

pixels = img.load()

width, height = img.size

for i in range(width):
    for j in range(height):
        channels = img.getpixel((i,j))
        if channels[-1] != 0:
            pixels[i, j] = (255, 255, 255, 255)

img_name = img_name.split(".")[0]
img.save(f"images/{img_name}_but_swapped.png")