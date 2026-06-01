"""``saci`` — one manifest (`saci.toml`) compiled into the native package
managers' files under `.saci/`, then installed and inspected as one env.

Commands mirror pixi's verbs on the unified manifest; `saci tree` shows
declared-vs-installed state. Structure is validated by the :mod:`models` schema;
package specs are pixi's job. tomlkit does all TOML I/O (it keeps comments on
edits); the env itself lives in `.saci/.pixi/`, so saci is self-contained.
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

import tomlkit
from cyclopts import App
from loguru import logger
from plumbum import FG, ProcessExecutionError, local
from rich.console import Console
from rich.table import Table

from .models import Manifest, PackageJson, PixiManifest, satisfied

# Paths are relative to the working directory, so saci operates on the project you
# run it in — the monorepo root here, any project once it's a standalone tool.
MANIFEST = Path("saci.toml")
OUT = Path(".saci")
PIXI = OUT / "pixi.toml"
ECOSYSTEMS = ("pypi", "cargo", "npm", "gem")

pixi = local["pixi"]
console = Console()
app = App(name="saci", help="One manifest, many package managers.")
glob = App(name="global", help="Install the conda deps into the shared global pixi env.")
app.command(glob)


def load() -> Manifest:
    """Parse + validate `saci.toml` into a typed :class:`Manifest`."""
    return Manifest.model_validate(tomlkit.parse(MANIFEST.read_text()).unwrap())


def installed_deps(env: str) -> dict[str, dict[str, Any]]:
    """Installed packages in the active pixi ``env``: name -> {version, kind, explicit}.

    Reads whichever env is provisioned (the repo's own until ``saci install`` owns
    ``.saci/.pixi``), so ``tree`` works as a declared-vs-reality check today.
    """
    records = json.loads(pixi["list", "-e", env, "--json"]())
    return {
        rec["name"]: {"version": rec["version"], "kind": rec["kind"], "explicit": rec["is_explicit"]}
        for rec in records
    }


def cargo_installed() -> dict[str, str]:
    """Crates installed via `cargo install` (name -> version), or empty if cargo is absent."""
    if not shutil.which("cargo"):
        return {}
    listing = local["cargo"]("install", "--list")
    return dict(re.findall(r"^(\S+) v([\d.]+):", listing, re.MULTILINE))


def npm_installed() -> dict[str, str]:
    """npm packages under `.saci/node_modules` (name -> version), scoped names included."""
    manifests = (*OUT.glob("node_modules/*/package.json"), *OUT.glob("node_modules/@*/*/package.json"))
    return {(data := json.loads(m.read_text()))["name"]: data["version"] for m in manifests}


# ── commands ────────────────────────────────────────────────────────────────
@app.command
def sync() -> None:
    """Compile `saci.toml` into `.saci/{pixi.toml, package.json}`."""
    manifest = load()
    OUT.mkdir(exist_ok=True)
    pixi_doc = PixiManifest.from_manifest(manifest).model_dump(by_alias=True, exclude_defaults=True)
    PIXI.write_text(tomlkit.dumps(pixi_doc))
    if (package := PackageJson.from_manifest(manifest)) is not None:
        (OUT / "package.json").write_text(json.dumps(package.model_dump(), indent=2) + "\n")
    logger.info("synced {} -> {}/", MANIFEST.name, OUT.name)


@app.command
def install(env: str = "default") -> None:
    """Sync, then install every ecosystem for ``env`` (pixi + npm)."""
    sync()
    pixi["install", "--manifest-path", str(PIXI), "-e", env] & FG
    if (OUT / "package.json").exists():
        local["npm"]["install", "--prefix", str(OUT), "--no-audit", "--no-fund"] & FG
    logger.info("installed env {}", env)


@glob.command(name="install")
def global_install(name: str = "") -> None:
    """Install the conda `[deps]` into a shared global pixi env (`pixi global`)."""
    manifest = load()
    name = name or manifest.saci.name
    specs = [pkg if spec in ("*", "") else f"{pkg}{spec}" for pkg, spec in manifest.deps.items()]
    pixi["global", "install", "--environment", name, *specs] & FG
    logger.info("installed {} conda deps into global env '{}'", len(specs), name)


@app.command
def run(task: str, *args: str) -> None:
    """Run a task inside the env (`pixi run`)."""
    pixi["run", "--manifest-path", str(PIXI), task, *args] & FG


@app.command
def shell(env: str = "default") -> None:
    """Open an activated shell in ``env`` (`pixi shell`)."""
    pixi["shell", "--manifest-path", str(PIXI), "-e", env] & FG


@app.command
def tree(env: str = "default") -> None:
    """Show declared (`saci.toml`) vs installed deps — each checked in its own ecosystem."""
    declared = load().declared(env)
    pixi_env = installed_deps(env)
    by_source = {
        "conda": {name: rec["version"] for name, rec in pixi_env.items()},
        "pypi": {name: rec["version"] for name, rec in pixi_env.items()},
        "cargo": cargo_installed(),
        "npm": npm_installed(),
    }
    table = Table(title=f"saci · {env} — declared vs installed", header_style="bold cyan")
    for column in ("package", "source", "declared", "installed", ""):
        table.add_column(column)
    counts = {"ok": 0, "drift": 0, "missing": 0}
    for name in sorted(declared):
        spec, source = declared[name]["spec"], declared[name]["source"]
        version = by_source.get(source, {}).get(name)
        if version is None:
            status, shown, counts["missing"] = "[red]✗ missing[/red]", "[dim]—[/dim]", counts["missing"] + 1
        elif satisfied(spec, version):
            status, shown, counts["ok"] = "[green]✓[/green]", version, counts["ok"] + 1
        else:
            status, shown = "[yellow]≠ drift[/yellow]", f"[yellow]{version}[/yellow]"
            counts["drift"] += 1
        table.add_row(name, source, spec, shown, status)
    console.print(table)
    transitive = sum(1 for rec in pixi_env.values() if not rec["explicit"])
    console.print(
        f"[green]{counts['ok']} ok[/green] · [yellow]{counts['drift']} drift[/yellow] · "
        f"[red]{counts['missing']} missing[/red] · [dim]{transitive} transitive installed[/dim]"
    )


# ── editing saci.toml (tomlkit keeps comments + formatting) ─────────────────
def dep_path(source: str, env: str) -> list[str]:
    """The `[…]deps` table path for ``source`` (conda = bare `[deps]`), under ``env`` if given."""
    base = ["deps"] if source == "conda" else [source, "deps"]
    return ["envs", env, *base] if env else base


def ensure_table(doc: Any, path: list[str]) -> Any:
    """Walk ``path`` in a tomlkit document, creating tables as needed; return the leaf."""
    node = doc
    for key in path:
        if key not in node:
            node[key] = tomlkit.table()
        node = node[key]
    return node


def dep_tables(doc: Any) -> list[Any]:
    """Every dep table in the manifest (base + per-ecosystem + per-env), for lookup/removal."""
    tables: list[Any] = []
    for scope in (doc, *doc.get("envs", {}).values()):
        if "deps" in scope:
            tables.append(scope["deps"])
        tables += [scope[eco]["deps"] for eco in ECOSYSTEMS if eco in scope and "deps" in scope[eco]]
    return tables


@app.command
def add(
    *packages: str,
    pypi: bool = False,
    cargo: bool = False,
    npm: bool = False,
    gem: bool = False,
    env: str = "",
    spec: str = "*",
) -> None:
    """Add packages to `saci.toml` then re-sync — conda by default; `--pypi`/`--cargo`/`--npm`/`--gem` pick the source."""
    source = next((s for s, on in zip(ECOSYSTEMS, (pypi, cargo, npm, gem)) if on), "conda")
    doc = tomlkit.parse(MANIFEST.read_text())
    table = ensure_table(doc, dep_path(source, env))
    for package in packages:
        table[package] = spec
    MANIFEST.write_text(tomlkit.dumps(doc))
    logger.info("added {} -> [{}]", ", ".join(packages), ".".join(dep_path(source, env)))
    sync()


@app.command
def remove(*packages: str) -> None:
    """Remove packages from `saci.toml` wherever they're declared, then re-sync."""
    doc = tomlkit.parse(MANIFEST.read_text())
    removed = [p for table in dep_tables(doc) for p in packages if table.pop(p, None) is not None]
    MANIFEST.write_text(tomlkit.dumps(doc))
    logger.info("removed {}", ", ".join(dict.fromkeys(removed)) or "(nothing found)")
    sync()


if __name__ == "__main__":
    app()
