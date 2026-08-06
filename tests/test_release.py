import tomllib
from pathlib import Path


def test_pyproject_version_matches_changelog_head() -> None:
    """The packaged version and the top changelog entry agree, so neither drifts unseen.

    Releases are cut from `pyproject.toml`, and `chefe --version` plus the upgrade hints in
    error messages read from that same metadata. A changelog that ran ahead of `pyproject`
    (as 0.0.21 once did) is exactly the silent drift this guards against.
    """
    root = Path(__file__).resolve().parents[1]
    packaged = tomllib.loads((root / "pyproject.toml").read_text())["project"]["version"]
    headings = [
        line.removeprefix("## ").strip()
        for line in (root / "CHANGELOG.md").read_text().splitlines()
        if line.startswith("## ")
    ]
    assert headings[0] == packaged
