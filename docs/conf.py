from importlib.metadata import version as pkg_version

project = "tether"
author = "tether contributors"
release = pkg_version("tether")

extensions = ["myst_parser", "sphinx_click"]
source_suffix = {".rst": "restructuredtext", ".md": "markdown"}

root_doc = "index"
exclude_patterns = ["_build"]
html_theme = "furo"

man_pages = [
    (
        "cli",
        "tether",
        "Run AI coding harnesses in a disposable Docker container",
        ["tether contributors"],
        1,
    ),
]
