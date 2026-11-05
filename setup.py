import io
import os

from setuptools import find_packages, setup

here = os.path.abspath(os.path.dirname(__file__))


def read(name):
    with io.open(os.path.join(here, name), encoding="utf-8") as fh:
        return fh.read()


about = {}
for line in read(os.path.join("subnetcalc", "__init__.py")).splitlines():
    if line.startswith("__version__"):
        about["version"] = line.split("=")[1].strip().strip('"').strip("'")
        break

setup(
    name="subnetcalc",
    version=about.get("version", "0.2.0"),
    description="A small CIDR/subnet toolkit CLI for network admins",
    long_description=read("README.md") if os.path.exists(os.path.join(here, "README.md")) else "",
    long_description_content_type="text/markdown",
    author="Michael Tarassov",
    author_email="michael@tarassov.me",
    license="MIT",
    url="https://github.com/moveeeax/subnetcalc",
    packages=find_packages(exclude=("tests", "tests.*")),
    # The code itself only needs 3.7 (``IPv4Network.subnet_of``); the floor
    # follows the oldest CPython release that still receives security fixes.
    python_requires=">=3.11",
    classifiers=[
        "Development Status :: 4 - Beta",
        "Environment :: Console",
        "Intended Audience :: System Administrators",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
        "Programming Language :: Python :: 3.14",
        "Programming Language :: Python :: 3.15",
        "Topic :: System :: Networking",
    ],
    entry_points={
        "console_scripts": [
            "subnetcalc=subnetcalc.cli:main",
        ],
    },
)
