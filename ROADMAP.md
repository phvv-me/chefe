# Roadmap

Where chefe is headed. chefe compiles one `chefe.toml` into native manifests and lets the real
tools (pixi, npm, cargo, and runtime-keyed managers) do the solving. This document tracks what works today and what each
milestone needs. It is a direction, not a contract, so order and scope can shift.

## Today (0.0.x)

The core loop works end to end.

- [x] One `chefe.toml` compiles into `.chefe/pixi.toml` and `.chefe/package.json`.
- [x] Installs across the built-in adapters. conda and Python packages go through pixi (Python packages via `uv`),
  Node.js packages go through the selected manager, and Rust crates install into the pixi env
  prefix via `pixi run cargo`.
- [x] Runtime-keyed toolchains. A package declared in `[deps]` can have a matching `[<name>]`
  table, so new toolchain tables do not need a schema edit.
- [x] Platform overlays, named environments, tasks, system requirements, and env vars.
- [x] A full CLI. `init`, `add`, `remove`, `upgrade`, `sync`, `install`, `update`, `clean`,
  `tree`, `run`, `x`, `shell`, and a global install.
- [x] Tests at full coverage, published to PyPI, with a one-line installer and i18n docs.

## v0.1.0

Make chefe complete and trustworthy across the adapters and generic toolchain tables it advertises.

- [x] **Swappable JavaScript backends.** `[nodejs] manager` names any compatible package-manager
  binary (npm by default, or pnpm, yarn, …) and chefe runs it in the env dir, so a new compatible
  tool needs no code, only its name.
- [x] **Generic toolchain discovery.** A runtime/toolchain name under `[deps]` unlocks a matching
  table such as `[zig]`, `[c-compiler]`, or `[cxx-compiler]`; chefe validates and reports those
  deps without carrying a language catalog.
- [x] **Dev dependencies for Node.js and Pixi-backed languages.** `[nodejs.dev.deps]` compiles to
  `devDependencies`, and `[dev.deps]`/`[dev.python.deps]` compile to a pixi `dev` feature in the
  default env. Still ahead: a `chefe install --prod` to exclude them.
- [ ] **Lockfiles and reproducibility.** An application (`[nodejs] app`) already gets its manager's
  lockfile at the project root, committable as is. Still ahead: surface `pixi.lock` and the
  tooling lockfile under `.chefe/`, decide what belongs in version control, and guarantee an
  install reproduces from a lock.
- [ ] **Cross-platform CI.** Test the compile and install paths on Linux, macOS, and Windows, not
  only where they were written.
- [ ] **Friendlier failures.** Clear messages when a tool, runtime, or index is missing, plus a
  `chefe doctor` that checks declared toolchains and reports what is off.
- [ ] **Richer `chefe tree`.** Shows the language/toolchain per package and the drift between
  declared and installed, and `chefe tree --plan` is a dry run of what an install would change
  (install the missing, update the drifted, remove the explicit-but-undeclared). Still ahead: a
  per-package transitive breakdown.
- [ ] **CLI ergonomics.** `chefe completions [shell]` emits a bash/zsh/fish completion script
  (following `$SHELL` by default), and the `exec` alias for `x` ships so `chefe exec` works for
  people who reach for the longer verb. Still ahead: an installer that drops the script straight
  into the shell's completion dir.
- [ ] **LLM-friendly docs.** Polish the generated `llms.txt` and `llms-full.txt` so assistants
  get clean, sectioned context, keep them building in CI, and link them from the README.
- [ ] **Further i18n.** Grow beyond the current four locales (pt-BR, es, ja, zh) and keep every
  page in sync through the Gemini translation workflow.
- [ ] **Close honesty gaps** where docs, examples, and adapters drift from the runtime-keyed
  contract.

## v1.0.0

Freeze the surface and make chefe safe to depend on.

- [ ] **Stable manifest schema.** Publish a versioned JSON Schema for editor autocomplete and
  validation, with a written migration and deprecation policy.
- [ ] **Full tested parity** across conda, Python, Node.js with the package-manager choice, Rust,
  and generic toolchain tables, on every supported platform.
- [ ] **A backend plugin API** so new languages/toolchains can be added without touching core. The
  hard-coded backends become a registry others can extend.
- [ ] **Reproducible by default.** A single lock that pins every language/toolchain and a `chefe install`
  that honors it.
- [ ] **Parallel installs** across languages/toolchains, since they are independent once compiled.
- [ ] **Robust self-management.** A `chefe self update`, a hardened installer, and signed
  releases.
- [ ] **Compatibility guarantees.** Semantic versioning, a deprecation policy, and a 1.x promise
  for the manifest and CLI.
- [ ] **Complete reference docs** in every supported language.

## Later

Ideas worth doing once the milestones above land.

- [ ] More languages/toolchains such as Go modules, Composer, and system package managers.
- [ ] Recipe includes so projects can share a common base `chefe.toml`.
- [ ] Monorepo support with several member recipes under one workspace.
- [ ] Build and download caching for faster, offline-friendly installs.
- [ ] An editor extension on top of the published JSON Schema.
- [ ] A `chefe export` that ejects to raw native manifests.
