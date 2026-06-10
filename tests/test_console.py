from rich.console import Console

from chefe.console import markup


def test_static_markup_passes_through() -> None:
    """Literal t-string parts keep their rich markup tags verbatim."""
    assert markup(t"[green]added[/green] done") == "[green]added[/green] done"


def test_interpolations_are_escaped() -> None:
    """A value carrying markup-like brackets prints literally, not as markup."""
    package = "[red]x[/red]"
    text = markup(t"[green]added[/green] {package}")
    assert text == "[green]added[/green] \\[red]x\\[/red]"
    console = Console(no_color=True)
    with console.capture() as capture:
        console.print(text)
    assert capture.get() == "added [red]x[/red]\n"


def test_non_str_values_are_stringified() -> None:
    """Non-string interpolations render through `str()`."""
    total = 3
    assert markup(t"installed {total} deps") == "installed 3 deps"
