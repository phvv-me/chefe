# Ejemplos

Un `chefe.toml` real es el recorrido más convincente. Este es el manifest detrás de un
monorepo de ML multilenguaje, recortado para mayor legibilidad pero con cada función a
la vista: conda + PyPI (torch desde un índice personalizado) + npm + cargo, un mínimo de CUDA
del sistema, variables de entorno, superposiciones por plataforma, un entorno de serving
aislado y tareas.

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

[deps]                                    # bare table is conda, the default source
python      = ">=3.14"
nodejs      = ">=25"
ripgrep-all = ">=0.10"
pandoc      = ">=3.9"
# … runtimes, libs, and CLIs all live here

[pypi]                                    # settings → pixi [pypi-options]
index-strategy   = "unsafe-best-match"
extra-index-urls = ["https://pypi.nvidia.com"]

[pypi.indexes]                            # named indexes a dep can pin
pytorch = "https://download.pytorch.org/whl/cu132"

[pypi.deps]
pydantic = ">=2.13"
polars   = ">=1.40"
torch    = { version = ">=2.11", index = "pytorch" }   # pinned to the named index
# … the rest of the Python stack

[npm.deps]
"@tobilu/qmd" = ">=0.1"
prettier      = ">=3"

[cargo.deps]
bookokrat = { version = ">=0.1", locked = true }

[on.linux.deps]                           # platform overlay → pixi [target.linux]
cuda-nvcc = ">=13.3"
cupy      = ">=14"

[envs.serving]                            # a named, isolated environment
no-default = true

[envs.serving.pypi.deps]
sglang        = ">=0.5"
sglang-kernel = { url = "https://github.com/sgl-project/whl/releases/download/v0.4.2/sglang_kernel-0.4.2+cu130-cp310-abi3-manylinux2014_aarch64.whl" }

[envs.serving.on.linux-64.deps]           # overlay nested inside an env
vllm = { version = ">=0.19", build = "cuda129*" }

[tasks]                                   # run inside the activated env
test = "python -m pytest"
lint = "pre-commit run --all-files"
```

## Cómo configurarlo

```sh
chefe sync                 # compile chefe.toml → .chefe/{pixi.toml, package.json}
chefe install              # provision every ecosystem at once (conda, PyPI, npm, cargo)
chefe shell                # an activated shell with all the binaries on PATH
chefe run test             # run a task inside the environment
chefe tree                 # declared vs installed, each checked in its own ecosystem
```

El entorno `serving` aislado se aprovisiona e inspecciona de la misma manera:

```sh
chefe install serving      # solve + provision just the serving env (sglang, vllm, …)
chefe tree serving
```

Y para herramientas de un solo uso, sin necesidad de manifest:

```sh
chefe x ruff check .       # run a tool in a throwaway env, like uvx
```
