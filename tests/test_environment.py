from pathlib import Path

import pytest
from plumbum import local

from chefe.environment import Environment, module_init_snippet

MODULES = ("nvidia/26.3", "gcc/15.2.0")


def render(tmp_path: Path, modules: tuple[str, ...], hook: str = "export FOO=bar") -> str:
    """The `activate.sh` text an :class:`Environment` writes for ``modules``."""
    return Environment(tmp_path / "activate.sh", hook).render(modules)


def test_module_script_contents(tmp_path: Path) -> None:
    """With modules pinned the script sources module init, guards every module command behind
    `command -v module`, purges, loads exactly the pinned list, and carries no libstdc++ hack."""
    script = render(tmp_path, MODULES)
    present = (
        "module purge",
        "module load nvidia/26.3 gcc/15.2.0",
        "/usr/share/lmod/lmod/init/bash",
        "if command -v module >/dev/null 2>&1; then",
    )
    assert all(line in script for line in present)
    assert "LD_PRELOAD" not in script and "libstdc++" not in script  # no CXXABI fix needed


def test_empty_modules_emit_no_module_block(tmp_path: Path) -> None:
    """With no modules configured the whole module block is omitted, so sourcing the script
    never purges whatever stack the surrounding job had loaded."""
    script = render(tmp_path, ())
    assert "module purge" not in script
    assert "module load" not in script
    assert "export FOO=bar" in script


def test_hook_is_embedded_verbatim(tmp_path: Path) -> None:
    """The pixi shell-hook text is reproduced as-is, so PATH and env vars match `chefe run`."""
    hook = 'export PATH="/env/bin:$PATH"\nexport PYTHONPATH="research"'
    script = render(tmp_path, MODULES, hook)
    assert 'export PATH="/env/bin:$PATH"' in script
    assert 'export PYTHONPATH="research"' in script


@pytest.mark.parametrize("modules", [(), MODULES])
def test_generated_script_is_valid_bash(tmp_path: Path, modules: tuple[str, ...]) -> None:
    """Both the module and module-less scripts parse and source cleanly under bash."""
    path = tmp_path / "activate.sh"
    path.write_text(render(tmp_path, modules))
    syntax = local["bash"]["-n", str(path)].run(retcode=None)[0]
    sourced = local["bash"]["-c", f"source {path} && echo ok"].run(retcode=None)
    assert syntax == 0
    assert sourced[0] == 0 and "ok" in sourced[1]


def test_write_persists_the_script(tmp_path: Path) -> None:
    """`write` renders to disk and returns the path it wrote."""
    path = Environment(tmp_path / "activate.sh", "export FOO=bar").write(MODULES)
    assert path == tmp_path / "activate.sh"
    assert "module load nvidia/26.3 gcc/15.2.0" in path.read_text()


def test_module_init_snippet_sources_first_existing(tmp_path: Path) -> None:
    """The init snippet sources the first present init and is a no-op when none exist."""
    present = tmp_path / "present.sh"
    present.write_text("export MOD_INIT_RAN=1\n")
    snippet = module_init_snippet([str(tmp_path / "missing.sh"), str(present)])
    out = local["bash"]["-c", f"{snippet}; echo ${{MOD_INIT_RAN:-no}}"]()
    assert out.strip() == "1"
    nothing = module_init_snippet([str(tmp_path / "absent.sh")])
    assert local["bash"]["-c", f"{nothing}; echo done"]().strip() == "done"


def test_activation_relaxes_nounset_around_sourcing(tmp_path: Path) -> None:
    """Sourcing under `set -eu` survives nounset-unsafe activation hooks and restores `set -u`."""
    script = render(tmp_path, MODULES, hook='echo "hook ran: ${UNDEFINED_VAR:-}"')
    assert "set +u" in script and "set -u" in script
    path = tmp_path / "activate.sh"
    path.write_text(script)
    probe = tmp_path / "probe.sh"
    probe.write_text(
        f'set -eu\nsource "{path}"\n'
        "case $- in *u*) echo NOUNSET_RESTORED;; *) echo NOUNSET_LOST;; esac\n"
    )
    result = local["bash"][str(probe)]()
    assert "hook ran" in result
    assert "NOUNSET_RESTORED" in result
