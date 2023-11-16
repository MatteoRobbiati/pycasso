from PIL import Image
from copy import deepcopy

class Painter:
    def __init__(self, imagepath:str):
        """
        Image processing tool.
        
        Args:
            image: path to the image which has to be processed.
        """
        self.imagepath = imagepath
        image = Image.open(imagepath).convert("RGBA")
        self.set_image(image)
        # make a copy of the original image
        self.original_image = deepcopy(self.image)

    def set_image(self, image:Image):
        """Set new image as default."""
        self.image = image
        self.format = self.image.format
        self.pixels = self.image.load()
        self.width, self.height = self.image.size    

    def resize(self, size:tuple):
        """Resize image."""
        image = self.image.resize(size)
        self.set_image(image)      

    def remove_color(self, color:tuple, shadow_range:int=None):
        """Remove color provided in RGB form."""
        for i in range(self.width):
            for j in range(self.height):
                channels = self.image.getpixel((i,j))
                if shadow_range is not None:
                    inside = 0
                    for k in range(3):
                        if (channels[k] <= color[k] + shadow_range and channels[k] >= color[k] - shadow_range):
                            inside += 1
                    if inside == 3:
                        self.pixels[i,j] = (0, 0, 0, 0)
                else:   
                    if channels[:-1] == color:
                        self.pixels[i,j] = (0, 0, 0, 0)


    def replace_colors(self, old_color:tuple, new_color:tuple, alpha:int = 255):
        """
        Replace ``old_color`` with ``new_color``.
        
        Args:
            old_color: tuple containing RGB code of the color to be replaced;
            new_color: tuple containing RGB code of the new color to be set;
            alpha: opacity of the new color.    
        """
        if (alpha < 0 or alpha > 255):
            raise ValueError(f"Opacity value {alpha} is not allowed. Please set one integer in [0, 255].")
        
        for i in range(self.width):
            for j in range(self.height):
                channels = self.image.getpixel((i,j))
                if channels[:-1] == old_color:
                    self.pixels[i,j] = new_color + (alpha,)

    def save(self, title:str = None, format:str = None):
        """Save processed image."""
        if format is None:
            format = self.format
        if title is None:
            title = f"{self.imagepath}_processed"
        self.image.save(fp=title, format=format)


    def back_to_original(self):
        """Restore initial image."""
        self.set_image(self.original_image)   
