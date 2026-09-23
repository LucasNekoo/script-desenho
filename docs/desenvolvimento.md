# Desenvolvimento

## Ambiente

```bash
git clone -b autodraw-lineart --single-branch https://github.com/LucasNekoo/script-desenho.git autodraw-lineart
cd autodraw-lineart
python -m venv .venv
source .venv/bin/activate          # fish: source .venv/bin/activate.fish · Windows: .venv\Scripts\activate
pip install torch --index-url https://download.pytorch.org/whl/cpu   # sempre antes, e do índice CPU
pip install -e ".[dev,download]"
autodraw-lineart download          # 218 MB; opcional para a maioria dos testes
```

| Extra | Traz | Para quê |
| --- | --- | --- |
| (nenhum) | `torch`, `numpy`, `Pillow` | Usar a ferramenta |
| `[download]` | `gdown` | Comando `download` |
| `[examples]` | OpenCV (headless), scikit-image | Rodar [`examples/linhas_para_tracos.py`](../examples/linhas_para_tracos.py) |
| `[dev]` | pytest, ruff + os do `[examples]` | Testes e lint |

## Estrutura

```
autodraw-lineart/
├── src/autodraw_lineart/
│   ├── cli.py              contrato: comandos, JSON, códigos de saída
│   ├── weights.py          registro dos modelos, pasta de dados, SHA-256, download
│   ├── extract.py          carga dos pesos e inferência
│   ├── network.py          U-Net copiada do Anime2Sketch (não reformatar nomes)
│   └── __main__.py         python -m autodraw_lineart
├── examples/
│   ├── cliente_autodraw.py     cliente de referência (só biblioteca padrão)
│   └── linhas_para_tracos.py   limiar + linha central (referência do AutoDraw)
├── tests/                  35 testes (veja abaixo)
├── docs/                   esta documentação (+ docs/img)
├── .github/workflows/ci.yml
├── THIRD_PARTY_LICENSES.md
└── pyproject.toml
```

## Testes

```bash
pytest               # tudo; o que precisa dos pesos reais é pulado se eles faltarem
pytest -m weights    # só os que usam os pesos reais
pytest -m "not weights"
ruff check .
```

A maior parte da suíte roda **sem os pesos**: os testes de contrato trocam
`load_model` por uma rede de pesos aleatórios, o que basta para validar formato,
tamanho, códigos de saída e JSON. Os testes com pesos reais procuram os pesos
na pasta padrão ou em `AUTODRAW_LINEART_WEIGHTS`.

| Arquivo | Cobre |
| --- | --- |
| `test_network.py` | Saída de 1 canal em [-1, 1]; troca das 6 camadas no `improved`; **nomes e contagem de parâmetros** (32/62) iguais aos dos pesos publicados |
| `test_weights.py` | Pasta padrão e variável de ambiente; recusa de arquivo ausente, de tamanho errado e **adulterado com o mesmo tamanho**; erro claro sem `gdown` |
| `test_cli.py` | Uma linha JSON por chamada; códigos 0/2/3/4; **erros de argumento em JSON**; saída em tons de cinza do tamanho da entrada; transparência → branco; `check` sem importar o PyTorch; **stdout limpo no `download`**; teste com o modelo real |
| `test_examples.py` | **Linha grossa → 1 traço percorrido uma vez**; cruz e círculo sem repetição; limiar 220 × 170; sujeira descartada; cliente: ferramenta ausente, sem pesos, imagem inválida, ponta a ponta com o modelo real |

## CI

[`.github/workflows/ci.yml`](../.github/workflows/ci.yml): Linux e Windows ×
Python 3.10 e 3.13; instala o PyTorch do índice CPU, roda `ruff` e `pytest`.
Não baixa pesos (os testes que precisam deles são pulados). Dispara em push
para `autodraw-lineart` (e `main`, para o caso de a branch virar repositório
próprio) e em pull requests. Leva ~40 s no Linux e ~1,5 min no Windows.

## Trabalhando com a branch órfã

* A branch `autodraw-lineart` **não tem histórico em comum** com `main` e
  `developer`. Nunca mescle entre elas; o GitHub oferece um PR a cada push,
  ignore.
* Para mudanças maiores, crie branches **a partir de `autodraw-lineart`** e abra
  PR **para `autodraw-lineart`**. Isso funciona normalmente, porque elas
  compartilham histórico.
* Tags desta ferramenta devem ter prefixo, para não se confundir com as do
  AutoDraw: `lineart-v0.1.0`.
* Se um dia virar repositório próprio: crie o repositório vazio e rode
  `git push <novo-remoto> autodraw-lineart:main`.

## Adicionar um modelo

1. Consiga o arquivo de pesos de fonte confiável e confira que carrega com
   `torch.load(..., weights_only=True)` (veja [Segurança](seguranca.md#se-for-preciso-atualizar-os-pesos-ou-o-modelo)).
2. Se a arquitetura for outra, implemente-a num módulo novo; se for uma
   variação da U-Net, estenda `build_generator`.
3. Registre em `MODELS` ([`weights.py`](../src/autodraw_lineart/weights.py)):
   nome, arquivo, tamanho, SHA-256, ID do Drive e o que distingue a arquitetura.
4. Ajuste `load_model` em [`extract.py`](../src/autodraw_lineart/extract.py) se
   o pré-processamento for diferente.
5. Acrescente o caso ao teste de nomes e contagem de parâmetros.
6. Atualize [Arquitetura](arquitetura.md#os-dois-modelos),
   [Segurança](seguranca.md#hashes-publicados) e [Desempenho](desempenho.md).

Um modelo novo **não** muda o contrato: `--model` apenas ganha uma opção.

## Mudar o contrato

Só quando a mudança quebraria clientes (veja [Contrato § Versionamento](contrato.md#versionamento)):

1. Suba `CONTRACT` em [`cli.py`](../src/autodraw_lineart/cli.py).
2. Atualize `SUPPORTED_CONTRACT` e o código do
   [cliente de referência](../examples/cliente_autodraw.py).
3. Atualize [contrato.md](contrato.md) e os testes de `test_cli.py`.
4. Registre no [CHANGELOG](../CHANGELOG.md) e avise quem integra (o AutoDraw
   precisa atualizar o cliente dele).

## Publicar uma versão

1. `__version__` em [`__init__.py`](../src/autodraw_lineart/__init__.py) (semver).
2. [CHANGELOG](../CHANGELOG.md).
3. `ruff check . && pytest` com os pesos presentes (para rodar também os testes reais).
4. Commit, tag `lineart-vX.Y.Z`, push da branch e da tag.

## Problemas comuns

| Sintoma | Causa provável | Solução |
| --- | --- | --- |
| A instalação baixa gigabytes de pacotes `nvidia-*` | O `torch` veio do PyPI com CUDA | `pip uninstall torch` e reinstale com `--index-url https://download.pytorch.org/whl/cpu` |
| `error: weights` com "não confere com o SHA-256" | Download incompleto ou arquivo trocado | Apague o arquivo e rode `autodraw-lineart download` de novo |
| O `download` falha com erro do Google Drive | O Drive às vezes limita arquivos muito baixados | Tente mais tarde, ou baixe pelo navegador (links no README do Anime2Sketch), coloque na pasta de pesos e rode `check` para conferir |
| No Windows, uma janela preta pisca a cada imagem | O AutoDraw chamou o processo sem `CREATE_NO_WINDOW` | Use o cliente de referência, que já passa esse flag |
| Testes com pesos reais aparecem como `skipped` | Pesos não encontrados | `autodraw-lineart download` ou `AUTODRAW_LINEART_WEIGHTS=...` |
