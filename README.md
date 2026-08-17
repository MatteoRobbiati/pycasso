![pycasso](https://github.com/MatteoRobbiati/pycasso/assets/62071516/5e0a7459-692f-4e2d-9a9b-fcf881e3399a)

Automatic image processing tool based on the [pillow](https://github.com/python-pillow/Pillow) package.

I was tired to use graphical apps to remove backgrounds and replace colors, and 
now I am happy to have `pycasso` helping me.

## Install it

`pycasso` is managed with [uv](https://docs.astral.sh/uv/). Clone this repo and let
`uv` set up the environment for you:

```sh
uv sync
```

This creates a `.venv` with `pycasso` installed in editable mode. Run anything
inside it with `uv run`, for example:

```sh
cd examples && uv run python chalmers_white.py
```

To add `pycasso` to an environment of your own instead:

```sh
uv pip install .
```
You can know use it as you wish.

## Tutorial
A fast tutorial to the usage can be found [here](https://github.com/MatteoRobbiati/pycasso/blob/main/examples/pycasso_tutorial.ipynb).
