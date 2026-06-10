import shlex
from collections.abc import Sequence
from pathlib import Path

from jinja2 import Environment as Jinja
from jinja2 import PackageLoader

# Shell templates ship as package data so they stay diffable and shellcheck-able.
TEMPLATES = Jinja(
    loader=PackageLoader("chefe"),
    keep_trailing_newline=True,
    trim_blocks=True,
    lstrip_blocks=True,
)

# Where Lmod / environment-modules drops its shell init. The first that exists wins; on a host
# without modules (a laptop, gold) none exist and module setup degrades to a harmless no-op.
MODULE_INITS = (
    "/usr/share/lmod/lmod/init/bash",
    "/etc/profile.d/modules.sh",
    "/etc/profile.d/z00_lmod.sh",
    "/etc/profile.d/lmod.sh",
)


def module_init_snippet(inits: Sequence[str] = MODULE_INITS) -> str:
    """A bash snippet that loads `module` into a non-login shell from the first init that exists.

    `module` is a shell function and is undefined in PBS non-login shells, so a job must source
    the Lmod/environment-modules init before any `module load`. The loop stops at the first
    present init and is a clean no-op on a host that ships none.
    """
    candidates = " ".join(shlex.quote(init) for init in inits)
    return (
        f"for _modinit in {candidates}; do "
        '[ -f "$_modinit" ] && . "$_modinit" && break; done; unset _modinit'
    )


class Environment:
    """Generates a per-host `.chefe/activate.sh` that sets up the whole runtime in one `source`.

    The script sources the module init, `module purge`s, `module load`s the pinned modules
    (the `nvidia` HPC SDK bundles a matching CUDA + toolchain, so no CXXABI/libstdc++ fix is
    needed), then applies pixi's own activation (the same env vars, PATH, and activation scripts
    `chefe run` applies). Sourcing it makes `python -m <module>` Just Work from a bare PBS or
    interactive shell. Off-cluster the `module` lines are guarded by `command -v module`, so the
    script degrades to pure pixi activation.
    """

    def __init__(self, path: Path, hook: str) -> None:
        self.path = path
        self.hook = hook

    def write(self, modules: Sequence[str]) -> Path:
        """Write the `activate.sh` loading ``modules`` to :attr:`path` and return it."""
        self.path.write_text(self.render(modules))
        return self.path

    def render(self, modules: Sequence[str]) -> str:
        """The `activate.sh` text: module init + purge + load, then pixi activation.

        With no `[modules]` declared the whole module block is omitted, so the script never
        purges whatever stack the surrounding job had loaded.
        """
        return TEMPLATES.get_template("activate.sh.j2").render(
            module_init=module_init_snippet(),
            modules=shlex.join(modules),
            hook=self.hook.strip(),
        )
