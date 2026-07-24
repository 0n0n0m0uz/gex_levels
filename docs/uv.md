# uv

uv is a tool that combines, pip, virtualenv in a ground up rewrite written in rust

virtualenv creates isolated python environmemts for each project to avoid dependency 
conflicts inherent in a global configuration where everything is shared

virtualenv is stricty python packages using pip, no other i frastructure or ecosystem packages 
but uv fixes that and is more similar to a mamba improvement on conda but conda has a wider 
array of packages. its becoming obsolete because its just the empty env the packages is installed 
by separate process

the main benefit to uv vs mamba is its even faster due to parallelization of rust and its 
more local centric where the environment is inside a single package only wheras conda is like
a sandbox w more sprawl for a category of projects

uv doesnt require activation of env before running script either andis locked down to exact
same packages for anyone that runs it

## uv tool
used to install globally scoped tools to manage and build locally scoped projects 


you should think about your intended audience before younbegin the project becauae there are
different approaches to packagind depending on who and how it will be used.

simple scripts that only use the standard internal python librariew can be emailed s a single .py
file but multiple scripts and external libraries require more.

A python library is a building block not a complete application

a source distribution package or sdist is a built in tool in the .tar.bz format for pure python packages where you know the 
distro env is compatible

wheels contain non python artifacts and are precompiled binaries. you can even use wheels for pure
python packages and thats what pip does.

source allows user to compile build it whereas wheel is already compiled

## pip

pip is the package installer for Python. You can use pip to install packages 
from the Python Package Index and other indexes.

## pipx

used for installing python scripts executed from the command line (not just a dependency)
