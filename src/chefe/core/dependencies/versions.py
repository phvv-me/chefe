from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion, Version


def is_satisfied(spec: str, version: str | None) -> bool:
    """Whether `version` meets `spec` (display-only; pixi is the real gate).

    A `None` version (an editable/path install pixi reports without a pin) has nothing to
    compare, so it counts as satisfied rather than forcing a pointless reinstall.
    """
    if spec in ("*", "") or version is None:
        return True
    try:
        return Version(version) in SpecifierSet(spec)
    except InvalidVersion, InvalidSpecifier:
        return True
