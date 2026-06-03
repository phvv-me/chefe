# Roadmap

Where chefe is headed. chefe compiles one `chefe.toml` into native manifests and lets the real
tools (pixi, npm, cargo) do the solving. This document tracks what works today and what each
milestone needs. It is a direction, not a contract, so order and scope can shift.

## Today (0.0.x)

The core loop works end to end.

- [x] One `chefe.toml` compiles into `.chefe/pixi.toml` and `.chefe/package.json`.
- [x] Installs across four ecosystems. conda and PyPI through pixi (PyPI via `uv`), npm through
  npm, and cargo crates into the pixi env prefix via `pixi run cargo`.
- [x] Language runtimes are auto-ensured from conda-forge when an ecosystem needs one.
- [x] Platform overlays, named environments, tasks, system requirements, and env vars.
- [x] A full CLI. `init`, `add`, `remove`, `upgrade`, `sync`, `install`, `update`, `clean`,
  `tree`, `run`, `x`, `shell`, and a global install.
- [x] Tests at full coverage, published to PyPI, with a one-line installer and i18n docs.

## v0.1.0

Make chefe complete and trustworthy across every ecosystem it advertises.

- [ ] **Finish the gem backend** so `[gem.deps]` installs the way cargo does, through
  `pixi run gem` into the env prefix. Today gem is in the schema and CLI but never installs, so
  this closes the gap between the docs and reality.
- [x] **Swappable JavaScript backends.** `[npm] manager` names any package-manager binary
  (npm by default, or pnpm, bun, aube, yarn, …) and chefe runs it in the env dir, so a new tool
  needs no code, only its name. Generalizing the same choice to other ecosystems is still ahead.
- [ ] **Lockfiles and reproducibility.** An application (`[npm] app`) already gets its manager's
  lockfile at the project root, committable as is. Still ahead: surface `pixi.lock` and the
  tooling lockfile under `.chefe/`, decide what belongs in version control, and guarantee an
  install reproduces from a lock.
- [ ] **Cross-platform CI.** Test the compile and install paths on Linux, macOS, and Windows, not
  only where they were written.
- [ ] **Friendlier failures.** Clear messages when a tool, runtime, or index is missing, plus a
  `chefe doctor` that checks the toolchain and reports what is off.
- [ ] **Richer `chefe tree`.** Show the source per package, drift between declared and installed,
  and what an install would change.
- [ ] **CLI ergonomics.** Shell completions, and an `exec` alias for `x` so `chefe exec` works
  for people who reach for the longer verb.
- [ ] **LLM-friendly docs.** Polish the generated `llms.txt` and `llms-full.txt` so assistants
  get clean, sectioned context, keep them building in CI, and link them from the README.
- [ ] **Further i18n.** Grow beyond the current four locales (pt-BR, es, ja, zh) and keep every
  page in sync through the Gemini translation workflow.
- [ ] **Close the honesty gaps** where the docs promise more than the code delivers, the gem
  backend being the first.

## v1.0.0

Freeze the surface and make chefe safe to depend on.

- [ ] **Stable manifest schema.** Publish a versioned JSON Schema for editor autocomplete and
  validation, with a written migration and deprecation policy.
- [ ] **Full tested parity** across conda, PyPI, npm with the package-manager choice, cargo, and
  gem, on every supported platform.
- [ ] **A backend plugin API** so new ecosystems can be added without touching core. The
  hard-coded backends become a registry others can extend.
- [ ] **Reproducible by default.** A single lock that pins every ecosystem and a `chefe install`
  that honors it.
- [ ] **Parallel installs** across ecosystems, since they are independent once compiled.
- [ ] **Robust self-management.** A `chefe self update`, a hardened installer, and signed
  releases.
- [ ] **Compatibility guarantees.** Semantic versioning, a deprecation policy, and a 1.x promise
  for the manifest and CLI.
- [ ] **Complete reference docs** in every supported language.

## Later

Ideas worth doing once the milestones above land.

- [ ] More ecosystems such as Go modules, Composer, and system package managers.
- [ ] Recipe includes so projects can share a common base `chefe.toml`.
- [ ] Monorepo support with several member recipes under one workspace.
- [ ] Build and download caching for faster, offline-friendly installs.
- [ ] An editor extension on top of the published JSON Schema.
- [ ] A `chefe export` that ejects to raw native manifests.
