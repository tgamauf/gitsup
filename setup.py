from setuptools import setup

setup(
    name="gitsup",
    maintainer="Thomas Gamauf",
    version="",#TODO
    description="Git submodule updater",
    long_description="file: README.md",
    classifiers = """ Programming Language :: Python :: 3
                      Programming Language :: Python :: 3.7
                      Programming Language :: Python :: 3.8
                  """,
    url="https://github.com/tgamauf/gitsup",
    zip_safe=True,
    packages=["gitsup"],
    python_requires=">3.6",
    install_requires=[
        "PyYAML",
        "requests"
    ],
    entry_points={"console_scripts": ["gitsup = gitsup.main:main"]},
)
