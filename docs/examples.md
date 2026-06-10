# Examples

A real `chefe.toml` is the most convincing tour. This is the manifest behind a
multi-language ML monorepo, trimmed for readability but with every feature on
display: conda + Python (torch from a custom index) + Node.js + Rust, a system CUDA
floor, environment variables, platform overlays, an isolated serving
environment, and tasks.

```toml
[workspace]
name      = "life"
platforms = ["osx-arm64", "linux-64", "linux-aarch64"]
channels  = ["conda-forge", "nvidia"]
dotenv    = true                          # auto-load .env

[system]                                  # the conda virtual-package floor
cuda = "13.0"

[env]                                     # build vars; secrets stay in .env
CUDA_DEVICE_ORDER    = "PCI_BUS_ID"
CUDA_VISIBLE_DEVICES = "0"

[deps]                                    # bare table is conda, the default resolver
python      = ">=3.14"
nodejs      = ">=25"
rust        = "*"
ripgrep-all = ">=0.10"
pandoc      = ">=3.9"
# … runtimes, libs, and CLIs all live here

[python]                                  # settings for Python packages
index-strategy   = "unsafe-best-match"
extra-index-urls = ["https://pypi.nvidia.com"]

[python.indexes]                            # named indexes a dep can pin
pytorch = "https://download.pytorch.org/whl/cu132"

[python.deps]
pydantic = ">=2.13"
polars   = ">=1.40"
torch    = { version = ">=2.11", index = "pytorch" }   # pinned to the named index
# … the rest of the Python stack

[nodejs.dev.deps]
"@tobilu/qmd" = ">=0.1"
prettier      = ">=3"

[rust.deps]
bookokrat = { version = ">=0.1", locked = true }

[modules]                                 # HPC modules baked into .chefe/activate.sh
cuda = "13.2"
gcc  = "15.2.0"

[on.linux.deps]                           # platform overlay → pixi [target.linux]
cuda-nvcc = ">=13.3"
cupy      = ">=14"

[envs.serving]                            # a named, isolated environment
no-default = true

[envs.serving.deps]
python = "*"

[envs.serving.python.deps]
sglang        = ">=0.5"
sglang-kernel = { url = "https://github.com/sgl-project/whl/releases/download/v0.4.2/sglang_kernel-0.4.2+cu130-cp310-abi3-manylinux2014_aarch64.whl" }

[envs.serving.on.linux-64.deps]           # overlay nested inside an env
vllm = { version = ">=0.19", build = "cuda129*" }

[tasks]                                   # run inside the activated env
test = "python -m pytest"
lint = "pre-commit run --all-files"
```

## Setting it up

```sh
chefe sync                 # compile chefe.toml → .chefe/{pixi.toml, package.json}
chefe install              # provision every language/toolchain at once
chefe shell                # an activated shell with all the binaries on PATH
chefe run test             # run a task inside the environment
chefe tree                 # declared vs installed, each checked in its own language/toolchain
```

The isolated `serving` environment is provisioned and inspected the same way:

```sh
chefe install serving      # solve + provision just the serving env (sglang, vllm, …)
chefe tree serving
```

And for one-off tools, no manifest needed:

```sh
chefe x ruff check .       # run a tool in a throwaway env, like pipx run
```
