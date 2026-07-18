from collections import Counter

from packaging.utils import canonicalize_name
from rich.console import Console
from rich.table import Table

from . import NAME
from .console import markup
from .state import Declared, Installed
from .utils import satisfied

# pixi reports Python packages as `pypi`; the manifest declares them under `[python]`.
KIND_SOURCES = {"pypi": "python"}


class TreeReport:
    """Renders the declared-vs-installed reconciliation for one env, as a table or a dry-run plan.

    Bound once to a console, it takes the already-gathered declared deps, the installed-by-source
    view, and pixi's provisioned map, and owns every bit of presentation: the status table, the
    per-row marks, and the `--plan` change list.
    """

    def __init__(self, console: Console) -> None:
        self.console = console

    def table(
        self,
        env: str,
        declared: dict[str, Declared],
        by_source: dict[str, dict[str, str]],
        provisioned: dict[str, Installed],
    ) -> None:
        """Show declared vs installed deps for ``env``, each checked in its own ecosystem."""
        report = Table(title=f"{NAME} · {env} · declared vs installed", header_style="bold cyan")
        for column in ("package", "language", "declared", "installed", ""):
            report.add_column(column)
        tally: Counter[str] = Counter()
        for name, dep in sorted(declared.items()):
            installed_name = canonicalize_name(name) if dep.source == "python" else name
            installed = by_source.get(dep.source, {}).get(installed_name)
            mark, shown, bucket = self.row_status(dep.spec, installed)
            tally[bucket] += 1
            report.add_row(name, dep.source, dep.spec, shown, mark)
        self.console.print(report)
        transitive = sum(1 for inst in provisioned.values() if not inst.explicit)
        self.console.print(
            f"[green]{tally['ok']} ok[/green] · [yellow]{tally['drift']} drift[/yellow] · "
            f"[red]{tally['missing']} missing[/red] · [dim]{transitive} transitive installed[/dim]"
        )

    @staticmethod
    def row_status(spec: str, version: str | None) -> tuple[str, str, str]:
        """The (mark, shown version, tally bucket) for a declared dep vs what's installed."""
        if version is None:
            return "[red]✗ missing[/red]", "[dim]·[/dim]", "missing"
        if satisfied(spec, version):
            return "[green]✓[/green]", version, "ok"
        return "[yellow]≠ drift[/yellow]", f"[yellow]{version}[/yellow]", "drift"

    def plan(
        self,
        env: str,
        declared: dict[str, Declared],
        by_source: dict[str, dict[str, str]],
        provisioned: dict[str, Installed],
    ) -> None:
        """Print the changes a `chefe install` would make for ``env``, installing nothing.

        Compares each declared dep against what its ecosystem holds: a missing dep is an install,
        a drifted one an update, and an *explicit* installed dep absent from the manifest a
        removal. Transitive installs are left out, since the solver owns those.
        """
        explicit = {
            name
            for name, inst in provisioned.items()
            if inst.explicit and KIND_SOURCES.get(inst.kind, inst.kind) == "conda"
        }
        actions: list[tuple[str, str]] = []
        for name, dep in sorted(declared.items()):
            installed_name = canonicalize_name(name) if dep.source == "python" else name
            installed = by_source.get(dep.source, {}).get(installed_name)
            if installed is None:
                actions.append(("[green]+ install[/green]", f"{name} {dep.spec}".rstrip()))
            elif not satisfied(dep.spec, installed):
                actions.append(("[yellow]~ update[/yellow]", f"{name} {installed} → {dep.spec}"))
        for name in sorted(explicit - declared.keys()):
            actions.append(("[red]- remove[/red]", name))
        if not actions:
            self.console.print(f"[green]up to date[/green] · {env} matches the manifest")
            return
        self.console.print(f"[bold cyan]{NAME} · {env} · install would change[/bold cyan]")
        for mark, detail in actions:
            self.console.print(mark, markup(t"{detail}"))
