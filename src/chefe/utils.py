from __future__ import annotations

import platform

from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion, Version


def current_platform() -> str:
    """This host's pixi platform, e.g. `osx-arm64` / `linux-64` / `linux-aarch64`."""
    osname = {"Darwin": "osx", "Linux": "linux", "Windows": "win"}[platform.system()]
    arm = platform.machine() in ("arm64", "aarch64")
    arch = "aarch64" if arm and osname == "linux" else "arm64" if arm else "64"
    return f"{osname}-{arch}"


def satisfied(spec: str, version: str) -> bool:
    """Whether `version` meets `spec` (display-only; pixi is the real gate)."""
    if spec in ("*", ""):
        return True
    try:
        return Version(version) in SpecifierSet(spec)
    except (InvalidVersion, InvalidSpecifier):
        return True
