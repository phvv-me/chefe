# Exemplos

Um `chefe.toml` real é o tour mais convincente. Este é o manifest por trás de um
monorepo de ML multilíngue, simplificado para facilitar a leitura, mas com todos os recursos
em exibição: conda + PyPI (torch de um índice personalizado) + npm + cargo, uma base
de sistema CUDA, variáveis de ambiente, sobreposições de plataforma, um ambiente
de serviço isolado e tarefas.

```toml
[workspace]
name      = "life"
platforms = ["osx-arm64", "linux-64", "linux-aarch64"]
channels  = ["conda-forge", "nvidia"]
dotenv    = true                          # carrega automaticamente o .env

[system]                                  # a base de pacotes virtuais do conda
cuda = "13.0"

[env]                                     # variáveis de build; segredos permanecem no .env
CUDA_DEVICE_ORDER    = "PCI_BUS_ID"
CUDA_VISIBLE_DEVICES = "0"

[deps]                                    # tabela simples é conda, a fonte padrão
python      = ">=3.14"
nodejs      = ">=25"
ripgrep-all = ">=0.10"
pandoc      = ">=3.9"
# … runtimes, libs e CLIs vivem todos aqui

[pypi]                                    # configurações → pixi [pypi-options]
index-strategy   = "unsafe-best-match"
extra-index-urls = ["https://pypi.nvidia.com"]

[pypi.indexes]                            # índices nomeados aos quais uma dep pode se fixar
pytorch = "https://download.pytorch.org/whl/cu132"

[pypi.deps]
pydantic = ">=2.13"
polars   = ">=1.40"
torch    = { version = ">=2.11", index = "pytorch" }   # fixado ao índice nomeado
# … o restante da stack Python

[npm.deps]
"@tobilu/qmd" = ">=0.1"
prettier      = ">=3"

[cargo.deps]
bookokrat = { version = ">=0.1", locked = true }

[on.linux.deps]                           # sobreposição de plataforma → pixi [target.linux]
cuda-nvcc = ">=13.3"
cupy      = ">=14"

[envs.serving]                            # um ambiente nomeado e isolado
no-default = true

[envs.serving.pypi.deps]
sglang        = ">=0.5"
sglang-kernel = { url = "https://github.com/sgl-project/whl/releases/download/v0.4.2/sglang_kernel-0.4.2+cu130-cp310-abi3-manylinux2014_aarch64.whl" }

[envs.serving.on.linux-64.deps]           # sobreposição aninhada dentro de um ambiente
vllm = { version = ">=0.19", build = "cuda129*" }

[tasks]                                   # executado dentro do ambiente ativado
test = "python -m pytest"
lint = "pre-commit run --all-files"
```

## Configuração

```sh
chefe sync                 # compila chefe.toml → .chefe/{pixi.toml, package.json}
chefe install              # provisiona todos os ecossistemas de uma vez (conda, PyPI, npm, cargo)
chefe shell                # um shell ativado com todos os binários no PATH
chefe run test             # executa uma tarefa dentro do ambiente
chefe tree                 # declarado vs instalado, cada um verificado em seu próprio ecossistema
```

O ambiente `serving` isolado é provisionado e inspecionado da mesma forma:

```sh
chefe install serving      # resolve + provisiona apenas o ambiente de serviço (sglang, vllm, …)
chefe tree serving
```

E para ferramentas de uso único, não é necessário manifest:

```sh
chefe x ruff check .       # executa uma ferramenta em um ambiente descartável, como o uvx
```