import functools
from pathlib import Path

import pytest

from chefe.cli import build
from chefe.manager import PackageManager

from .conftest import write_manifest

# Each CLI argv and the manager method it must delegate to (cli.py is pure wiring).
COMMANDS = [
    (["init", "proj"], "init"),
    (["sync"], "sync"),
    (["install", "serving"], "install"),
    (["activate"], "activate"),
    (["update"], "update"),
    (["clean"], "clean"),
    (["run", "build", "--", "-x"], "run"),
    (["x", "ruff", "check", "."], "x"),
    (["shell"], "shell"),
    (["tree"], "tree"),
    (["add", "numpy", "-l", "python"], "add"),
    (["upgrade", "numpy"], "upgrade"),
    (["remove", "numpy"], "remove"),
    (["global", "install", "shared"], "global_install"),
]


def recording_manager(seen: list[str]) -> PackageManager:
    """A manager whose every command records its name instead of doing work.

    Each override keeps the real method's signature (via ``functools.wraps``) so cyclopts
    still parses each command exactly as in production.
    """

    class Spy(PackageManager):
        pass

    def spy(name: str):  # noqa: ANN202  (returns a wrapped no-op)
        @functools.wraps(getattr(PackageManager, name))
        def record(self: PackageManager, *args: object, **kwargs: object) -> None:
            seen.append(name)

        return record

    for _, method in COMMANDS:
        setattr(Spy, method, spy(method))
    return Spy()


@pytest.mark.parametrize(("argv", "method"), COMMANDS, ids=[f"{c[0][0]}/{c[1]}" for c in COMMANDS])
def test_cli_delegates_to_manager(argv: list[str], method: str) -> None:
    """Every command parses and forwards exactly once to its manager method."""
    seen: list[str] = []
    app = build(recording_manager(seen))
    with pytest.raises(SystemExit) as exit_info:  # cyclopts exits 0 on success
        app(argv)
    assert exit_info.value.code in (0, None)
    assert seen == [method]


def test_cli_prints_chefe_errors(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """User mistakes are shown as concise CLI errors, not Python tracebacks."""
    write_manifest(
        tmp_path,
        """
        [deps]
        python = "*"
        """,
    )
    app = build(PackageManager(tmp_path))
    with pytest.raises(SystemExit) as exit_info:
        app(["add", "ripgrep", "-l", "rust"])
    assert exit_info.value.code == 1
    assert "Language `rust` is not declared in [deps]" in capsys.readouterr().out
