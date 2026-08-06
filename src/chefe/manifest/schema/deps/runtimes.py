from typing import ClassVar


class Runtimes:
    """How a language name maps onto the conda packages that provide it.

    A manifest declares `python = ">=3.11"` under `[deps]` and writes that runtime's packages
    under `[python]`, so the table name and the conda package usually match. Where they do not,
    `packages` records every conda package whose presence counts as declaring the runtime, and
    `provisionable` names the standalone managers chefe installs itself rather than expecting
    on PATH.
    """

    packages: ClassVar[dict[str, set[str]]] = {"python": {"python", "python-freethreading"}}
    provisionable: ClassVar[set[str]] = {"pnpm", "yarn", "bun", "uv"}

    @classmethod
    def providers(cls, language: str) -> set[str]:
        """Every conda package whose presence declares ``language``."""
        return cls.packages.get(language, {language})

    @classmethod
    def provisions(cls, manager: str | None) -> bool:
        """Whether chefe installs ``manager`` into the env itself."""
        return manager in cls.provisionable

    @classmethod
    def source(cls, language: str) -> str:
        """The manifest dependency table ``language`` writes into.

        `python-freethreading` is still the `[python]` toolchain, so a package added with
        `-l python-freethreading` lands beside every other Python dep instead of fabricating a
        table no compiler reads.
        """
        return next(
            (name for name, runtimes in cls.packages.items() if language in runtimes), language
        )
