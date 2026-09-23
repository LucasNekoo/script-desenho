# Segurança

## O incidente no projeto original

Ao montar o experimento, em 23/09/2026, o repositório
[Mukosame/Anime2Sketch](https://github.com/Mukosame/Anime2Sketch) tinha como
commit mais recente:

| | |
| --- | --- |
| Commit | `50a6a12` |
| Data | 08/09/2026 10:38 (-0700) |
| Mensagem | "allow lower versions" |
| Arquivos alterados | só `requirements.txt` |

A mensagem diz uma coisa e o diff faz outra. Em vez de relaxar versões, ele
troca as dependências comuns por instalações direto de repositórios git e
**acrescenta uma que não existia**:

```diff
-torch
-torchvision
-Pillow
...
+requests @ git+https://github.com/pypll/requests.git
+torch @ git+https://github.com/pytorch/pytorch.git
+torchvision @ git+https://github.com/pytorch/vision.git
+Pillow @ git+https://github.com/python-pillow/Pillow.git
...
```

* O `requests` oficial fica em `psf/requests`, não em `pypll/requests`. E
  nenhum arquivo `.py` do Anime2Sketch importa `requests`.
* Em 23/09/2026, tanto `github.com/pypll/requests` quanto `github.com/pypll`
  respondiam **HTTP 404**, ou seja, tinham sido apagados.
* Enquanto esse repositório existiu, quem rodasse `pip install -r requirements.txt`
  teria baixado e executado o código de instalação dele. Não sabemos o que o
  pacote fazia.

É o padrão de um **ataque à cadeia de suprimentos**: um pacote com nome
conhecido vindo de um lugar desconhecido, colocado por um commit com mensagem
enganosa. Não sabemos se a conta do mantenedor foi comprometida. O README e os
arquivos `.py` do projeto não mudam desde 2023.

> Não abrimos issue no projeto original. É uma ação pública e fica a critério
> dos mantenedores do AutoDraw.

## O que fizemos a respeito

| Risco | Proteção |
| --- | --- |
| Instalar o pacote malicioso | **Nunca** usamos o `requirements.txt` do Anime2Sketch. As dependências daqui são só `torch`, `numpy` e `Pillow`, declaradas no nosso `pyproject.toml` |
| Código do projeto original alterado depois | Não dependemos do repositório. A definição da rede foi **copiada** do commit `1c1a2ed` (o anterior ao suspeito), revisada, e mantida com os mesmos nomes (necessário para os pesos) |
| PyTorch adulterado | Instalado só do índice oficial `https://download.pytorch.org/whl/cpu` |
| Pesos adulterados (arquivos pickle podem executar código ao carregar) | (1) **tamanho e SHA-256 fixos** conferidos antes de carregar; (2) `torch.load(..., weights_only=True)`, que carrega só tensores e não executa código mesmo se o arquivo for malicioso |
| Download corrompido ou trocado | O `download` grava num `.part`, confere o SHA-256 e só então renomeia; se não conferir, apaga |
| Pesos no repositório | Nunca vão para o git (`.gitignore`) |

## Hashes publicados

| Arquivo | Tamanho (bytes) | SHA-256 | Origem |
| --- | --- | --- | --- |
| `netG.pth` | 217.631.959 | `ccabdcc3f5cf3c07cf65d58776acb21df7dfda825cdc70c9766a93fd62bfc488` | Google Drive, pasta do README original (arquivo de 11/04/2021) |
| `improved.bin` | 191.927.595 | `d2913793286bdeb32f340e2f64e54154ab291daf43f5a352f73543cd3a5a3248` | Google Drive, link do README original (arquivo de 03/08/2023) |

Os dois arquivos são anteriores ao commit suspeito. Para conferir à mão:

```bash
sha256sum ~/.local/share/autodraw-lineart/weights/*          # Linux
Get-FileHash $env:LOCALAPPDATA\autodraw-lineart\weights\*    # Windows (PowerShell)
```

`autodraw-lineart check` faz a mesma conferência.

## `--skip-verify`

Confere só a existência e o tamanho, não o SHA-256. Existe para o `check`
rápido que o AutoDraw faz na inicialização (~30 ms em vez de ~0,2 s). O
`extract` do cliente de referência **não** usa essa opção, então os pesos são
conferidos a cada imagem processada. Não recomendamos usá-la no `extract`.

## Se for preciso atualizar os pesos ou o modelo

1. Obtenha o arquivo novo de uma fonte confiável e registre de onde veio.
2. Confira que ele carrega com `weights_only=True`. Se exigir
   `weights_only=False`, **não use**: significa que o arquivo traz objetos
   Python, não só tensores.
3. Atualize `MODELS` em [`weights.py`](../src/autodraw_lineart/weights.py)
   (nome, tamanho, SHA-256, ID do Drive) e a tabela acima.
4. Se a arquitetura mudar, atualize [`network.py`](../src/autodraw_lineart/network.py)
   e o teste de contagem de parâmetros.

Veja também [Desenvolvimento § Adicionar um modelo](desenvolvimento.md#adicionar-um-modelo).
