# Contrato v1

A especificação da conversa entre o AutoDraw e o `autodraw-lineart`. Tudo aqui
é garantido enquanto o campo `contract` valer `1`; o
[cliente de referência](../examples/cliente_autodraw.py) implementa este
documento e está coberto por testes.

## Regras gerais

1. A ferramenta é um **executável**: `autodraw-lineart` (ou
   `python -m autodraw_lineart`). O AutoDraw nunca a importa como biblioteca.
2. Toda chamada escreve **exatamente uma linha JSON** (UTF-8) no **stdout** e
   termina com um **código de saída**. Isso vale também para erros de argumento.
3. O **stderr** é livre (progresso de download, avisos) e pode ser ignorado.
   Leia sempre a **última linha** do stdout.
4. Exceções, só para uso humano: `--help` e `--version` escrevem texto.
5. Toda resposta tem `contract` (inteiro), `version` (versão do pacote) e `ok`
   (booleano). Quando `ok` é `false`, também tem `error` (tipo) e `message`
   (texto em português, pronto para mostrar ao usuário).

## Códigos de saída

| Código | `error` | Significado | O que o AutoDraw deve fazer |
| --- | --- | --- | --- |
| 0 | — | Sucesso | Usar o resultado |
| 1 | `unexpected` | Falha não prevista (bug, falta de memória...) | Voltar ao modo sem IA e registrar `message` |
| 2 | `usage` | Argumentos inválidos | Bug no chamador: corrigir a chamada |
| 3 | `weights` | Pesos ausentes, de tamanho errado ou com SHA-256 diferente | Esconder a opção de IA e orientar a rodar `autodraw-lineart download` |
| 4 | `input` | Imagem de entrada ilegível ou inexistente | Avisar o usuário |

## Comandos

### Opções comuns

| Opção | Padrão | Efeito |
| --- | --- | --- |
| `--model {default,improved}` | `default` | Qual modelo usar ou conferir |
| `--weights-dir PASTA` | `$AUTODRAW_LINEART_WEIGHTS` ou a pasta de dados do usuário | Onde procurar os pesos |
| `--skip-verify` | desligado | Confere só o tamanho, sem SHA-256 |

### `check`: os pesos estão prontos?

Não importa o PyTorch: ~30 ms com `--skip-verify`, ~0,2 s conferindo o SHA-256
dos dois arquivos (410 MB). `ok` reflete o modelo pedido em `--model`; `models`
traz o estado de todos.

```console
$ autodraw-lineart check --skip-verify
```
```json
{"contract": 1, "version": "0.1.1", "ok": true,
 "weights_dir": "/home/usuario/.local/share/autodraw-lineart/weights",
 "models": {"default":  {"ok": true, "path": "/home/usuario/.local/share/autodraw-lineart/weights/netG.pth"},
            "improved": {"ok": true, "path": "/home/usuario/.local/share/autodraw-lineart/weights/improved.bin"}}}
```
Código 0. Sem pesos:
```json
{"contract": 1, "version": "0.1.1", "ok": false, "weights_dir": "/tmp/vazia",
 "models": {"default":  {"ok": false, "message": "Pesos 'netG.pth' não encontrados em /tmp/vazia. Rode: autodraw-lineart download --model default"},
            "improved": {"ok": false, "message": "Pesos 'improved.bin' não encontrados em /tmp/vazia. Rode: autodraw-lineart download --model improved"}},
 "error": "weights",
 "message": "Pesos 'netG.pth' não encontrados em /tmp/vazia. Rode: autodraw-lineart download --model default"}
```
Código 3.

### `extract`: gerar a imagem de linhas

```console
$ autodraw-lineart extract ENTRADA --out SAIDA.png [--size 512] [--threads N] [--model M]
```

| Argumento | Padrão | Regra |
| --- | --- | --- |
| `ENTRADA` | obrigatório | Qualquer imagem que o Pillow abra (PNG, JPEG...) |
| `--out` | obrigatório | Caminho do PNG de saída; pastas são criadas se faltarem |
| `--size` | 512 | Lado do quadrado de processamento; **múltiplo de 256**, no mínimo 256 |
| `--threads` | metade dos núcleos, máx. 4 | Threads do PyTorch |

**Saída:** PNG em tons de cinza (modo `L`), **do mesmo tamanho da entrada**,
fundo claro (perto de 255) e linhas escuras. Transparência na entrada vira
fundo branco. Um arquivo `--out` já existente é sobrescrito.

```json
{"contract": 1, "version": "0.1.1", "ok": true, "output": "linhas.png", "model": "default",
 "size": 512, "threads": 4, "width": 700, "height": 900,
 "seconds": {"load": 0.678, "inference": 0.101}}
```

| Campo | Tipo | Conteúdo |
| --- | --- | --- |
| `output` | texto | O caminho de `--out`, como recebido |
| `model`, `size`, `threads` | texto, inteiro, inteiro | O que foi usado de fato |
| `width`, `height` | inteiros | Tamanho da imagem gravada (igual ao da entrada) |
| `seconds.load` | número | Importar o PyTorch + conferir e carregar os pesos |
| `seconds.inference` | número | Pré-processamento + rede + pós-processamento |

Erros possíveis, com as mensagens reais:

```json
{"contract": 1, "version": "0.1.1", "ok": false, "error": "input",
 "message": "Não foi possível abrir nao-existe.png: [Errno 2] No such file or directory: 'nao-existe.png'"}
```
```json
{"contract": 1, "version": "0.1.1", "ok": false, "error": "usage",
 "message": "autodraw-lineart extract: the following arguments are required: --out"}
```
```json
{"contract": 1, "version": "0.1.1", "ok": false, "error": "usage", "message": "--size precisa ser múltiplo de 256."}
```

### `download`: baixar e conferir os pesos

Requer o extra `[download]` (`gdown`). Baixa do Google Drive para um arquivo
`.part`, confere o SHA-256 e só então renomeia; um arquivo que não confere é
apagado. O progresso vai para o stderr.

```json
{"contract": 1, "version": "0.1.1", "ok": true, "model": "default",
 "path": "/home/usuario/.local/share/autodraw-lineart/weights/netG.pth"}
```

## Versionamento

* `contract` sobe **só** quando uma mudança quebraria um cliente existente:
  remover ou renomear campos, mudar tipos, mudar o significado de um código de
  saída, mudar o formato da imagem de saída.
* **Não** sobem o contrato: novos campos, novos comandos, novos modelos, novos
  valores de `error` (o cliente deve tratar tipos desconhecidos como
  `unexpected`).
* O cliente deve **recusar** um `contract` que não conhece (o de referência
  levanta `LineartError("contract", ...)`).
* `version` é a versão do pacote (semver) e serve só para diagnóstico.

## Tempo limite recomendado

Uma chamada fria leva ~1–1,5 s numa máquina moderna. Num notebook fraco, com o
jogo aberto, pode passar de alguns segundos. O cliente de referência usa 120 s
para `extract` e 15 s para `check`, valores folgados para não abortar à toa.
