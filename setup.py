#!/usr/bin/env python
# _*_ coding: utf-8 _*_
import os
import sys
import shutil
from setuptools import setup, find_packages

data_files = ()
setup(
    name='pircy',
    version="pircy-22",
    description='A pure-python IRCD',
    author='tbd',
    author_email='tbd',
    url='',
    download_url = '',
    data_files = data_files,
    packages=['pircy'],
    package_dir = {'':'src'},
    entry_points = { 'console_scripts': ['pircy=pircy.cli:cli'] },
    include_package_data=True,
    install_requires=[
        'click',
        'pyhcl',
        'uvloop',
    ],
    keywords=["irc", "ircd"]
)


