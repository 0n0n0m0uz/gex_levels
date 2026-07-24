# The __init__.py files are required to make Python treat directories containing 
# the file as packages (unless using a namespace package, a relatively advanced feature). 
# This prevents directories with a common name, such as string, from unintentionally 
# hiding valid modules that occur later on the module search path. 

# In the simplest case, __init__.py can just be an empty file, but it can also execute 
# initialization code for the package or set the __all__ variable, described later.

# Namespace Packages
# A subdirectory inside a regular package that does not contain an __init__.py file is 
# treated as an implicit namespace package (a “namespace subpackage”) rooted in that parent. 
# See PEP 420 for the underlying specification.

# Basically you can join a bunch of random components located all across wherever and gice the, 
# the same namespace nd the full package will be held in memory and not actually physically
# exist in one single location

# By adding import statements into the __init__ file it allows you a shorter import statement 
# in your actual codebase since the subdirectory is a separate package you can use 
# "from subdir import func"

# It makes things easier to update and is better encapsulation ans refactoring

# The __init__.py only contains import statements from objects in the same package and exports
# them somthat other packages can import those same objects more doncisely/directlt. 
# It flattens the modules namespace and places all objects in all subpackages at the same level

# This means that objects / functions in different modules cant have identical names
# helper functions that start w underscore should not be placed in init

# You can add package level variables that all .py files in that directory will use