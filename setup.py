#!/usr/bin/env python

from setuptools import setup, find_packages

setup(
    name="pycasso",
    version="0.0.1",
    package_dir={"": "src"},
    packages=find_packages("src"),
    install_requires=[
        'pillow>=10.0.0',
    ],
    zip_safe=False,
)
