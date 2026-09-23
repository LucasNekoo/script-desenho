# autodraw-lineart

Extração de *line art* por IA para o [AutoDraw](https://github.com/LucasNekoo/script-desenho),
rodando em **CPU** e em **processo separado**.

O AutoDraw continua leve e sem PyTorch. Quando esta ferramenta está instalada,
ele a chama uma vez por imagem carregada: ela recebe a ilustração e devolve
uma imagem de linhas limpas, que o AutoDraw transforma em traços.

```
AutoDraw                                   autodraw-lineart
────────                                   ────────────────
carrega imagem ─► autodraw-lineart extract ─► Anime2Sketch (U-Net, CPU)
                  (~1 s, uma vez por imagem)   pesos conferidos por SHA-256
lê o PNG de linhas ◄──────────────────────── grava PNG em tons de cinza
limiar + linha central + traços              processo termina → RAM liberada
```

> **Onde este código vive:** na branch órfã `autodraw-lineart` do repositório
> do AutoDraw. Ela tem histórico próprio, sem nenhum arquivo em comum com
> `main`/`developer`, e **nunca deve ser mesclada nelas**: é, na prática, um
> repositório separado no mesmo endereço.

O modelo é o [Anime2Sketch](https://github.com/Mukosame/Anime2Sketch) (MIT). A
definição da rede foi copiada para [network.py](src/autodraw_lineart/network.py);
veja [Segurança](#segurança) para o porquê de não depender do repositório original.

---

## Contrato com o AutoDraw

Toda chamada imprime **exatamente uma linha JSON** no stdout e termina com um
código de saída. O campo `contract` só muda em alterações incompatíveis.

| Comando | O que faz | Importa PyTorch? |
| --- | --- | --- |
| `autodraw-lineart check [--model M]` | Diz se os pesos estão presentes e íntegros | Não (rápido) |
| `autodraw-lineart extract ENTRADA --out SAIDA.png [--model M] [--size 512] [--threads N]` | Gera a imagem de linhas | Sim |
| `autodraw-lineart download [--model M]` | Baixa e confere os pesos | Não |
| `autodraw-lineart --version` | Versão | Não |

Opções comuns: `--model default|improved`, `--weights-dir PASTA`, `--skip-verify`
(confere só o tamanho, sem SHA-256).

**Saída de `extract`:** PNG em tons de cinza (`L`), **do mesmo tamanho da
entrada**, fundo claro e linhas escuras. Transparência vira fundo branco.

```json
{"contract": 1, "version": "0.1.0", "ok": true, "output": "linhas.png", "model": "default",
 "size": 512, "threads": 4, "width": 512, "height": 512,
 "seconds": {"load": 0.727, "inference": 0.098}}
```

**Erros:** `{"contract": 1, "version": "0.1.0", "ok": false, "error": TIPO, "message": "..."}`

| Código | `error` | Quando |
| --- | --- | --- |
| 0 | — | sucesso |
| 1 | `unexpected` | falha inesperada |
| 2 | `usage` | argumentos inválidos (ex.: `--size` não múltiplo de 256) |
| 3 | `weights` | pesos ausentes ou diferentes dos publicados |
| 4 | `input` | imagem de entrada inválida |

**Do lado do AutoDraw**, a imagem de linhas precisa de limiar antes de virar
esqueleto. Nos testes, **220** funcionou bem; 170 perdeu os olhos.

---

## Instalação

Requer Python 3.10 ou superior. **Instale o PyTorch do índice CPU antes** do
pacote; sem isso, o pip pode trazer a versão com CUDA, muito maior.

Clone só esta branch:

```bash
git clone -b autodraw-lineart --single-branch https://github.com/LucasNekoo/script-desenho.git autodraw-lineart
cd autodraw-lineart
```

Linux (fish):

```fish
python -m venv .venv
source .venv/bin/activate.fish
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -e ".[download]"
autodraw-lineart download            # modelo padrão, 218 MB
```

Windows (PowerShell):

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install torch --index-url https://download.pytorch.org/whl/cpu
.\.venv\Scripts\python.exe -m pip install -e ".[download]"
.\.venv\Scripts\autodraw-lineart.exe download
```

Os pesos ficam em `%LOCALAPPDATA%\autodraw-lineart\weights` (Windows) ou
`~/.local/share/autodraw-lineart/weights` (Linux). A variável
`AUTODRAW_LINEART_WEIGHTS` troca a pasta.

## Uso

```bash
autodraw-lineart check
autodraw-lineart extract ilustracao.png --out linhas.png
autodraw-lineart extract ilustracao.png --out linhas.png --model improved --threads 2
```

---

## Recursos (medidos)

CPU de 12 threads, sem GPU; imagem de 512 px.

| | `default` | `improved` |
| --- | --- | --- |
| Rede, 1 / 2 / 4 núcleos | 0,25 / 0,14 / 0,09 s | 0,82 / 0,48 / 0,36 s |
| Chamada completa (importar PyTorch + pesos + rede) | ~1,1 s | ~1,4 s |
| Pico de RAM | ~680 MB (950 MB a 1024 px) | ~1,8 GB |
| Pesos | 218 MB | 192 MB |
| PyTorch CPU instalado | 772 MB (download de 188 MB) | |

Por padrão a ferramenta usa metade dos núcleos, no máximo 4: o jogo roda na
mesma máquina. A memória volta ao sistema quando o processo termina.

## Limitações conhecidas

* **Fundos escuros com efeitos de luz:** o modelo `default` gera um padrão
  quadriculado; o `improved` troca por manchas. Os dois rendem ruído depois
  do limiar. Funciona bem em ilustrações de fundo claro.
* O lado de processamento é quadrado (a imagem é esticada para 512×512 e
  volta ao tamanho original), como no projeto original.

---

## Segurança

O commit mais recente do Anime2Sketch (`50a6a12`, 08/09/2026, "allow lower
versions") troca o `requirements.txt` por instalações direto de repositórios
git, incluindo `requests` de `github.com/pypll/requests`, que não é o oficial
(`psf/requests`) e já não existe. É o padrão de um ataque à cadeia de
suprimentos. Por isso:

* **não usamos o `requirements.txt` do Anime2Sketch** nem dependemos do
  repositório dele; só a definição da rede, do commit anterior (`1c1a2ed`), foi
  copiada e revisada;
* os pesos (pickles do PyTorch) são conferidos por **SHA-256** antes de
  carregar, e carregados com `weights_only=True`, que não executa código;
* o PyTorch vem do índice oficial `download.pytorch.org`.

| Arquivo | SHA-256 |
| --- | --- |
| `netG.pth` (default) | `ccabdcc3f5cf3c07cf65d58776acb21df7dfda825cdc70c9766a93fd62bfc488` |
| `improved.bin` | `d2913793286bdeb32f340e2f64e54154ab291daf43f5a352f73543cd3a5a3248` |

## Desenvolvimento

```bash
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -e ".[dev,download]"
pytest          # sem pesos: o teste com o modelo real é pulado
ruff check .
```

A maioria dos testes usa a rede com pesos aleatórios, o que basta para validar
formato, contrato e erros. Com `AUTODRAW_LINEART_WEIGHTS` apontando para os
pesos, o teste com o modelo real também roda.

## Licença

A definição da rede e os pesos vêm do Anime2Sketch, sob licença MIT; o texto
está em [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md). A licença do
restante deste repositório ainda não foi definida.
