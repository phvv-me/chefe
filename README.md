<div align="center">

<img src="assets/logo.svg" width="110" alt="saci logo — a whirlwind bottled in a jar" />

# saci

**One manifest for every package manager.**
Conda, PyPI, npm, cargo & more — bottled into a single file.

[![CI](https://github.com/phvv-me/saci/actions/workflows/ci.yml/badge.svg)](https://github.com/phvv-me/saci/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/saci.svg)](https://pypi.org/project/saci/)
[![Python](https://img.shields.io/pypi/pyversions/saci.svg)](https://pypi.org/project/saci/)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![CodeRabbit](https://img.shields.io/coderabbit/prs/github/phvv-me/saci?labelColor=171717&color=FF570A&label=CodeRabbit+Reviews)](https://coderabbit.ai)

</div>

---

Every language ships its own manager — `pixi`, `uv`, `npm`, `cargo`, `bundler`, `go`. Real projects need several at once, scattered across `pixi.toml`, `package.json`, `Cargo.toml`… **saci bottles them into one `saci.toml`**, compiles each native manifest, runs the real tools, and activates everything as one environment. It never re-implements a solver — it delegates, and unifies.

## Quickstart

```sh
pip install saci          # or: pixi global install saci
saci sync                 # compile saci.toml → native manifests
saci install              # provision every ecosystem at once
saci tree                 # what's declared vs what's installed, per ecosystem
```

## The manifest

```toml
[saci]
name      = "my-project"
channels  = ["conda-forge"]

[deps]                      # bare table = conda (the default source)
python = ">=3.11"
ripgrep = "*"

[pypi.deps]                 # resolved by pixi-via-uv, in the same env
torch = { version = ">=2.6", index = "pytorch" }

[pypi.indexes]
pytorch = "https://download.pytorch.org/whl/cu124"

[cargo.deps]                # other ecosystems are explicit: [<eco>.deps]
bookokrat = "*"

[npm.deps]
prettier = ">=3"

[on.linux.deps]             # platform overlays → native targets
cupy = ">=13"

[envs.serving]              # named environments compose, like pixi features
no-default = true
[envs.serving.pypi.deps]
vllm = ">=0.6"
```

## Commands

| command | what it does |
|---|---|
| `saci sync` | compile `saci.toml` → `.saci/{pixi.toml, package.json, …}` |
| `saci install [env]` | provision every ecosystem for `env` |
| `saci add <pkg> [--pypi/--cargo/--npm]` | add to the manifest (keeps your comments) |
| `saci remove <pkg>` | drop it wherever it's declared |
| `saci tree [env]` | declared-vs-installed, each dep checked in **its own** ecosystem |
| `saci run <task>` · `saci shell` | run a task / open a shell inside the env |
| `saci global install` | put the deps in the shared global env |

## How it works

`saci.toml` → **structure** validated by `pydantic` → compiled into each tool's native manifest under `.saci/` → installed by the real tools (specs validated by them) → activated as one. Editing keeps your comments via `tomlkit`; the environment lives in `.saci/`, so saci is self-contained.

## The name

In Brazilian folklore the **Saci** is a whirlwind of mischief you tame by **trapping it in a glass jar**. Scattered package managers are that mischief — saci bottles them into one. 🌀

## License

MIT
