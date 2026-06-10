import tomllib
from pathlib import Path

from ..manifest import Spec
from ..state import Installed
from ..utils import satisfied
from .pixi import Pixi
from .tool import Tool


class Cargo(Tool):
    """The cargo backend: crates install into the pixi env prefix, so they share its PATH.

    cargo lives inside the pixi env, so every command runs through `pixi run cargo`,
    pinned to the env being synced so an env-scoped rust toolchain resolves correctly.
    """

    def __init__(self, out: Path, pixi: Pixi) -> None:
        self.out = out
        self.pixi = pixi

    def __call__(self, verb: str, *args: str, **flags: bool | str | None) -> None:
        self.pixi("run", "cargo", verb, *args, **flags)

    def root(self, env: str) -> Path:
        """The pixi env prefix; crates install here so they share the env's activated PATH."""
        return self.pixi.env_prefix(env)

    def installed(self, env: str) -> dict[str, Installed]:
        crates = self.root(env) / ".crates.toml"
        try:
            entries = tomllib.loads(crates.read_text()).get("v1", {})
        except FileNotFoundError:
            return {}
        return {
            parts[0]: Installed(version=parts[1], kind="cargo")
            for key in entries
            if (parts := key.split())
        }

    def sync(self, env: str, declared: dict[str, Spec]) -> None:
        """Make ``env``'s crates match ``declared``: install missing or drifted, drop removed."""
        at = str(self.root(env))
        have = self.installed(env)
        for name in have.keys() - declared.keys():
            self("uninstall", "--root", at, name, environment=env)
        for name, spec in declared.items():
            current = have.get(name)
            if current is not None and satisfied(spec.version or "*", current.version):
                continue
            force = ("--force",) if current is not None else ()
            self("install", "--root", at, *self.install_args(spec), *force, name, environment=env)

    @staticmethod
    def install_args(spec: Spec) -> tuple[str, ...]:
        """The `cargo install` args expressing ``spec``: a version pin plus source extras.

        `git`/`path`/`branch`/`tag`/`rev` and `locked` ride through as their cargo flags, so a
        spec like `{ version = ">=0.1", locked = true }` installs exactly as declared.
        """
        extra = spec.model_extra or {}
        args: list[str] = []
        if spec.version not in (None, "*"):
            args += ["--version", str(spec.version)]
        for key in ("git", "path", "branch", "tag", "rev"):
            if value := extra.get(key):
                args += [f"--{key}", str(value)]
        if extra.get("locked"):
            args.append("--locked")
        return tuple(args)
