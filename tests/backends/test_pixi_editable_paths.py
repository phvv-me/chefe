from pathlib import Path

from chefe.backends import Pixi


def test_editable_path_dep_is_found_through_nested_tables(tmp_path: Path) -> None:
    (tmp_path / "pixi.toml").write_text(
        '[pypi-dependencies]\natpx = { path = "../packages/atpx", editable = true }\n',
        encoding="utf-8",
    )
    assert Pixi(tmp_path)._has_editable_paths()


def test_editable_search_walks_arrays_of_tables(tmp_path: Path) -> None:
    (tmp_path / "pixi.toml").write_text(
        "[[tool.entries]]\nname = 'plain'\n\n"
        '[[tool.entries]]\ninner = { path = "../packages/patos", editable = true }\n',
        encoding="utf-8",
    )
    assert Pixi(tmp_path)._has_editable_paths()


def test_no_editable_paths_without_a_manifest_or_matches(tmp_path: Path) -> None:
    assert not Pixi(tmp_path)._has_editable_paths()
    (tmp_path / "pixi.toml").write_text(
        '[pypi-dependencies]\nnumpy = ">=2"\nlist = [1, 2]\n', encoding="utf-8"
    )
    assert not Pixi(tmp_path)._has_editable_paths()
