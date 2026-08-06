from string.templatelib import Interpolation, Template

from rich.markup import escape


def markup(template: Template) -> str:
    """Render a t-string for rich: literal parts keep their markup, values are escaped.

    template: a t-string whose static parts carry intended rich markup tags, so an
    interpolated value such as a package named `[red]x[/red]` prints literally
    instead of being parsed as markup.
    """
    return "".join(
        escape(str(part.value)) if isinstance(part, Interpolation) else part for part in template
    )
