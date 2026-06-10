import platform

from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion, Version


def current_platform() -> str:
    """This host's pixi platform, e.g. `osx-arm64` / `linux-64` / `linux-aarch64`."""
    osname = {"Darwin": "osx", "Linux": "linux", "Windows": "win"}[platform.system()]
    arm = platform.machine() in ("arm64", "aarch64")
    arch = "aarch64" if arm and osname == "linux" else "arm64" if arm else "64"
    return f"{osname}-{arch}"


def platform_scopes(platform: str) -> tuple[str, ...]:
    """The selector keys covering ``platform``, most specific first.

    Pixi targets accept both concrete platforms and families, so `linux-64` is covered by
    `linux-64`, `linux`, and `unix`, while a family key like `linux` is covered by itself
    and `unix`.
    """
    family = platform.split("-")[0]
    scopes = [platform] if family == platform else [platform, family]
    if family in ("linux", "osx"):
        scopes.append("unix")
    return tuple(scopes)


def satisfied(spec: str, version: str) -> bool:
    """Whether `version` meets `spec` (display-only; pixi is the real gate)."""
    if spec in ("*", ""):
        return True
    try:
        return Version(version) in SpecifierSet(spec)
    except InvalidVersion, InvalidSpecifier:
        return True
