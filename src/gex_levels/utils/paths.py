from pathlib import Path


def get_project_root() -> Path:
    """Finds the project root by searching for pyproject.toml or .git"""
    current_path = Path(__file__).resolve()

    # Check the current directory and all parent directories
    for parent in [current_path] + list(current_path.parents):
        if (parent / "pyproject.toml").exists() or (parent / ".git").exists():
            return parent  # Correctly returning the 'parent' object found in the loop

    return current_path.parent