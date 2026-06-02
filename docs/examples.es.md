# Ejemplos

Un `chefe.toml` real es el recorrido más convincente. Este es el manifest detrás de un
monorepo de ML multilingüe, recortado para facilitar la lectura pero con cada característica
en exhibición: conda + PyPI (torch desde un índice personalizado) + npm + cargo, una base
de CUDA del sistema, variables de entorno, superposiciones de plataforma, un entorno
de servicio aislado y tareas.

```toml
[workspace]
name      = "life"
platforms = ["osx-arm64", "linux-64", "linux-aarch64"]
channels  = ["conda-forge", "nvidia"]
dotenv    = true                          # cargar automáticamente .env

[system]                                  # la base de paquetes virtuales de conda
cuda = "13.0"

[env]                                     # variables de compilación; los secretos permanecen en .env
CUDA_DEVICE_ORDER    = "PCI_BUS_ID"
CUDA_VISIBLE_DEVICES = "0"

[deps]                                    # la tabla vacía es conda, la fuente predeterminada
python      = ">=3.14"
nodejs      = ">=25"
ripgrep-all = ">=0.10"
pandoc      = ">=3.9"
# … los runtimes, bibliotecas y CLIs viven aquí

[pypi]                                    # configuraciones → pixi [pypi-options]
index-strategy   = "unsafe-best-match"
extra-index-urls = ["https://pypi.nvidia.com"]

[pypi.indexes]                            # índices con nombre a los que una dependencia puede anclarse
pytorch = "https://download.pytorch.org/whl/cu132"

[pypi.deps]
pydantic = ">=2.13"
polars   = ">=1.40"
torch    = { version = ">=2.11", index = "pytorch" }   # anclado al índice con nombre
# … el resto del stack de Python

[npm.deps]
"@tobilu/qmd" = ">=0.1"
prettier      = ">=3"

[cargo.deps]
bookokrat = { version = ">=0.1", locked = true }

[on.linux.deps]                           # superposición de plataforma → pixi [target.linux]
cuda-nvcc = ">=13.3"
cupy      = ">=14"

[envs.serving]                            # un entorno con nombre y aislado
no-default = true

[envs.serving.pypi.deps]
sglang        = ">=0.5"
sglang-kernel = { url = "https://github.com/sgl-project/whl/releases/download/v0.4.2/sglang_kernel-0.4.2+cu130-cp310-abi3-manylinux2014_aarch64.whl" }

[envs.serving.on.linux-64.deps]           # superposición anidada dentro de un entorno
vllm = { version = ">=0.19", build = "cuda129*" }

[tasks]                                   # ejecutar dentro del entorno activado
test = "python -m pytest"
lint = "pre-commit run --all-files"
```

## Configuración

```sh
chefe sync                 # compilar chefe.toml → .chefe/{pixi.toml, package.json}
chefe install              # aprovisionar cada ecosistema a la vez (conda, PyPI, npm, cargo)
chefe shell                # una shell activada con todos los binarios en PATH
chefe run test             # ejecutar una tarea dentro del entorno
chefe tree                 # declarado vs instalado, cada uno verificado en su propio ecosistema
```

El entorno `serving` aislado se aprovisiona e inspecciona de la misma manera:

```sh
chefe install serving      # resolver + aprovisionar solo el entorno serving (sglang, vllm, …)
chefe tree serving
```

Y para herramientas de uso único, no se necesita un manifest:

```sh
chefe x ruff check .       # ejecutar una herramienta en un entorno desechable, como uvx
```