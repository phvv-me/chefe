from enum import StrEnum


class Change(StrEnum):
    """What a dry-run `chefe install` would do to one dependency, as the mark a plan prints."""

    INSTALL = "[green]+ install[/green]"
    UPDATE = "[yellow]~ update[/yellow]"
    REMOVE = "[red]- remove[/red]"
