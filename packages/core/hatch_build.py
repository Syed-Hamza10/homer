import shutil
from pathlib import Path
from typing import Any

from hatchling.builders.hooks.plugin.interface import BuildHookInterface

PACKAGED = Path("achilles_core") / "models" / "manifest.json"
SOURCE = Path("..") / ".." / "models" / "manifest.json"


def copy_manifest(root: Path) -> Path:
    """Copies the repo's models/manifest.json into the package. Inside an sdist the repo source is
    gone but the copy already exists, so it is kept."""
    target = root / PACKAGED
    source = (root / SOURCE).resolve()
    if source.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    elif not target.exists():
        raise FileNotFoundError(f"{source} is missing and {target} does not exist")
    return target


class ManifestHook(BuildHookInterface):
    PLUGIN_NAME = "manifest"

    def initialize(self, version: str, build_data: dict[str, Any]) -> None:
        copy_manifest(Path(self.root))
