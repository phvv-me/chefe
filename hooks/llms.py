import re
from collections.abc import Sequence
from pathlib import Path

from mkdocs.config.defaults import MkDocsConfig

_SECTIONS: dict[str, list[str]] = {
    "Usage": ["index.md", "how-it-works.md", "commands.md", "examples.md"],
    "Reference": ["manifest.md"],
}

_FRONT_MATTER = re.compile(r"\A---\n.*?\n---\n", re.DOTALL)
_FENCED_CODE = re.compile(r"^```.*?^```", re.DOTALL | re.MULTILINE)
_H1 = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)


def _title_for(markdown: str, *, doc_path: str) -> str:
    """Pick a link title: the page's first `# ` heading, else the file stem.

    Headings inside fenced code blocks (like `# paste ...` comments) do not
    count, so a hero-only page with no real heading falls back to the stem.

    markdown: full source text of the page.
    doc_path: path of the page relative to `docs/`, used for the fallback.
    """
    match = _H1.search(_FENCED_CODE.sub("", markdown))
    if match:
        return match.group(1)
    stem = Path(doc_path).stem
    return "Home" if stem == "index" else stem


def _page_url(site_url: str, *, doc_path: str) -> str:
    """Build the english page URL the way `mkdocs-llmstxt` does.

    With directory URLs, `foo/bar.md` is served at `foo/bar/` and the
    markdown twin lives at `foo/bar/index.md`. `index.md` maps to the
    section root, so its twin is `index.md` at the site root.

    site_url: the configured `site_url`, with a trailing slash.
    doc_path: path of the page relative to `docs/`.
    """
    base = site_url if site_url.endswith("/") else f"{site_url}/"
    stem = doc_path[: -len(".md")]
    twin = "index.md" if stem == "index" else f"{stem}/index.md"
    return f"{base}{twin}"


def _read_page(docs_dir: Path, doc_path: str) -> str:
    """Read a source page and strip any YAML front-matter.

    docs_dir: the `docs/` directory.
    doc_path: path of the page relative to `docs/`.
    """
    text = (docs_dir / doc_path).read_text(encoding="utf-8")
    return _FRONT_MATTER.sub("", text).strip()


def _locale_suffixes(config: MkDocsConfig) -> list[str]:
    """The `.<locale>` page suffixes `mkdocs-static-i18n` builds twins under, from its own config.

    The default language keeps the untouched page, so only the other locales get a twin beside
    it, and those twins are the ones `llms.txt` skips. Reading the plugin means adding a language
    to `mkdocs.yml` needs no edit here.

    config: the MkDocs config this hook was handed.
    """
    i18n = config.plugins.get("i18n")
    if i18n is None:
        return []
    return [f".{language.locale}" for language in i18n.config.languages if not language.default]


def _section_entries(
    docs_dir: Path, site_url: str, doc_paths: Sequence[str], *, locales: Sequence[str]
) -> tuple[list[str], list[str]]:
    """One section's index links and full-text bodies, with localized page twins skipped.

    docs_dir: the `docs/` directory.
    site_url: the configured `site_url`.
    doc_paths: the section's pages, relative to `docs/`.
    locales: the `.<locale>` suffixes marking a translated twin.
    """
    index: list[str] = []
    full: list[str] = []
    for doc_path in doc_paths:
        if any(Path(doc_path).stem.endswith(suffix) for suffix in locales):
            continue
        markdown = _read_page(docs_dir, doc_path)
        title = _title_for(markdown, doc_path=doc_path)
        index.append(f"- [{title}]({_page_url(site_url, doc_path=doc_path)})")
        full.append(f"\n# {title}\n\n{markdown}\n")
    return index, full


def on_post_build(config: MkDocsConfig) -> None:
    """Write english `llms.txt` and `llms-full.txt` into the built `site/`."""
    docs_dir = Path(config.docs_dir)
    site_url = config.site_url or ""
    header = f"# {config.site_name}\n\n> {config.site_description or ''}\n"
    index_lines = [header]
    full_lines = [header]
    locales = _locale_suffixes(config)
    for section, doc_paths in _SECTIONS.items():
        index_lines.append(f"\n## {section}\n")
        index, full = _section_entries(docs_dir, site_url, doc_paths, locales=locales)
        index_lines.extend(index)
        full_lines.extend(full)
    site_dir = Path(config.site_dir)
    (site_dir / "llms.txt").write_text("\n".join(index_lines) + "\n", encoding="utf-8")
    (site_dir / "llms-full.txt").write_text("\n".join(full_lines) + "\n", encoding="utf-8")
