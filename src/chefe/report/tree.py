from collections import Counter
from collections.abc import Mapping, Sequence

from packaging.utils import canonicalize_name
from rich.console import Console
from rich.table import Table

from ..core import Declared, Installed, Project, is_satisfied
from .changes import Change
from .markup import markup


class TreeReport:
    """Renders the declared-vs-installed reconciliation for one env, as a table or a dry-run plan.

    Bound once to a console, it takes the already-gathered declared deps, the installed-by-source
    view, and pixi's provisioned map, and owns every bit of presentation: the status table, the
    per-row marks, and the `--plan` change list.
    """

    def __init__(self, console: Console) -> None:
        self.console = console

    @staticmethod
    def grid(env: str, rows: Sequence[tuple[str, Declared, str, str, str]]) -> Table:
        """The declared-vs-installed table for ``env``, one row per reconciled dependency."""
        report = Table(
            title=f"{Project.name} · {env} · declared vs installed", header_style="bold cyan"
        )
        for column in ("package", "language", "declared", "installed", ""):
            report.add_column(column)
        for name, dep, mark, shown, _ in rows:
            report.add_row(name, dep.source, dep.spec, shown, mark)
        return report

    @staticmethod
    def reconciled(
        declared: Mapping[str, Declared], by_source: Mapping[str, Mapping[str, str]]
    ) -> list[tuple[str, Declared, str | None]]:
        """Every declared dep in name order, beside the version its own ecosystem reports."""
        return [
            (
                name,
                dep,
                by_source.get(dep.source, {}).get(
                    canonicalize_name(name) if dep.source == "python" else name
                ),
            )
            for name, dep in sorted(declared.items())
        ]

    @staticmethod
    def row_status(spec: str, version: str | None) -> tuple[str, str, str]:
        """The (mark, shown version, tally bucket) for a declared dep vs what's installed."""
        if version is None:
            return "[red]✗ missing[/red]", "[dim]·[/dim]", "missing"
        if is_satisfied(spec, version):
            return "[green]✓[/green]", version, "ok"
        return "[yellow]≠ drift[/yellow]", f"[yellow]{version}[/yellow]", "drift"

    @staticmethod
    def summary(rows: Sequence[tuple[str, Declared, str, str, str]], transitive: int) -> str:
        """The counted line printed under the table, one figure per status bucket."""
        tally = Counter(bucket for *_, bucket in rows)
        return (
            f"[green]{tally['ok']} ok[/green] · [yellow]{tally['drift']} drift[/yellow] · "
            f"[red]{tally['missing']} missing[/red] · [dim]{transitive} transitive installed[/dim]"
        )

    @classmethod
    def changes(
        cls,
        declared: Mapping[str, Declared],
        by_source: Mapping[str, Mapping[str, str]],
        provisioned: Mapping[str, Installed],
    ) -> list[tuple[Change, str]]:
        """What a `chefe install` would do, as (change, subject) pairs in the order shown.

        A missing dep is an install, a drifted one an update, and an *explicit* installed dep
        absent from the manifest a removal. Transitive installs are left out, since the solver
        owns those.
        """
        actions = [
            (Change.INSTALL, f"{name} {dep.spec}".rstrip())
            if installed is None
            else (Change.UPDATE, f"{name} {installed} → {dep.spec}")
            for name, dep, installed in cls.reconciled(declared, by_source)
            if installed is None or not is_satisfied(dep.spec, installed)
        ]
        explicit = {
            name for name, inst in provisioned.items() if inst.explicit and inst.source == "conda"
        }
        return actions + [(Change.REMOVE, name) for name in sorted(explicit - declared.keys())]

    def plan(
        self,
        env: str,
        declared: Mapping[str, Declared],
        by_source: Mapping[str, Mapping[str, str]],
        provisioned: Mapping[str, Installed],
    ) -> None:
        """Print the changes a `chefe install` would make for ``env``, installing nothing."""
        changes = self.changes(declared, by_source, provisioned)
        if not changes:
            self.console.print(f"[green]up to date[/green] · {env} matches the manifest")
            return
        self.console.print(f"[bold cyan]{Project.name} · {env} · install would change[/bold cyan]")
        for change, subject in changes:
            self.console.print(change, markup(t"{subject}"))

    def table(
        self,
        env: str,
        declared: Mapping[str, Declared],
        by_source: Mapping[str, Mapping[str, str]],
        provisioned: Mapping[str, Installed],
    ) -> None:
        """Show declared vs installed deps for ``env``, each checked in its own ecosystem."""
        rows = [
            (name, dep, *self.row_status(dep.spec, installed))
            for name, dep, installed in self.reconciled(declared, by_source)
        ]
        transitive = sum(1 for inst in provisioned.values() if not inst.explicit)
        self.console.print(self.grid(env, rows))
        self.console.print(self.summary(rows, transitive))
