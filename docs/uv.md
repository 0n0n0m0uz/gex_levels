# uv

uv is a tool that combines, pip, virtualenv in a ground up rewrite written in rust

virtualenv creates isolated python environmemts for each project to avoid dependency 
conflicts inherent in a global configuration where everything is shared

virtualenv is stricty python packages using pip, no other i frastructure or ecosystem packages 
but uv fixes that and is more similar to a mamba improvement on conda but conda has a wider 
array of packages

the main benefit to uv vs mamba is its even faster due to parallelization of rust and its 
more local centric where the environment is inside a single package only wheras conda is like
a sandbox w more sprawl for a category of projects

uv doesnt require activation of env before running script either andis locked down to exact
same packages for anyone that runs it



