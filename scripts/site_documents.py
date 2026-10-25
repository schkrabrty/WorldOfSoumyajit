"""Page source locations are independent of the public permalink and manager ID."""
from pathlib import Path


def page_sources(root):
    root = Path(root)
    return sorted([*root.glob("*.html"), *(root / "pages").glob("*.html")])


def content_path(root, name):
    root = Path(root)
    # Bare HTML names are stable manager IDs, also used by older undo entries.
    if Path(name).name == name and name.endswith(".html"):
        if (root / "pages").is_dir() and not (root / name).exists():
            return root / "pages" / name
    return root / name
