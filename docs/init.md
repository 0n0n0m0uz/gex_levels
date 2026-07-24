## \__init\__.py

The **\__init\__.py__** file in each directory is required for Python to see that directory 
as a package.

In the simplest case, __init__.py can just be an empty file, but it can also execute initialization code for the package or set the __all__ variable, described later.

This prevents directories with a common name, such as string, from unintentionally 
hiding valid modules that occur later on the module search path. 

## Benefits and Drawbacks

By adding import statements into the __init__ file it allows you a shorter import statement 
in your actual codebase since the subdirectory is a separate package you can use 
"from subdir import func"

It makes things easier to update and is better encapsulation and refactoring however it can be heavier
in terms of resources because certain things get imported into memory when they would not otherwise

The __init__.py only contains import statements from objects in the same package and exports
them somthat other packages can import those same objects more doncisely/directlt. 
It flattens the modules namespace and places all objects in all subpackages at the same level

This means that objects / functions in different modules cant have identical names
helper functions that start w underscore should not be placed in init

You can add package level variables that all .py files in that directory will use
an __all__ variable that defines a list of imports that will respond to import *

## Namespace Package
A subdirectory inside a regular package that does not contain an __init__.py file is
treated as an implicit _namespace package_ rooted in that parent.


(See PEP 420 for the underlying specification)

Namespace Packages allow you to join multiple components located at different physical locations into a single package
This virtual package will be held in memory since it doesn't exist in a single location on a drive.

