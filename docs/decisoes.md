# Decisões

Registro das decisões de desenho, com o contexto de quando foram tomadas.
Formato: contexto → decisão → consequências → alternativas descartadas.

## D1. Processo separado, não plugin

**Contexto.** A extração por IA precisa do PyTorch (772 MB instalado) e usa
680 MB a 1,8 GB de RAM. O AutoDraw tem orçamento de < 400 MB instalado e
< 500 MB de RAM, e roda ao lado do jogo.

**Decisão.** A ferramenta é um executável que o AutoDraw chama por
`subprocess`: imagem entra, imagem de linhas sai (escolha do mantenedor em
23/09/2026).

**Consequências.**
* O AutoDraw não depende do PyTorch; sem a ferramenta, a opção de IA só não aparece.
* A memória volta ao sistema ao fim de cada chamada.
* Cada lado tem seu próprio Python (o PyTorch costuma demorar a suportar
  versões novas; isso não trava o AutoDraw).
* Custo: ~1 s por chamada, sendo ~0,57 s só para importar o PyTorch. Aceitável
  porque acontece uma vez por imagem.

**Descartado.** Pacote Python instalado no mesmo ambiente e descoberto como
plugin: mais rápido por chamada, mas colocaria o PyTorch e a memória da rede
dentro do processo do AutoDraw durante toda a sessão.

## D2. Branch órfã no repositório do AutoDraw

**Contexto.** O mantenedor preferiu um repositório separado, mas depois pediu
que o código ficasse no repositório já existente, numa branch à parte.

**Decisão.** Branch **órfã** `autodraw-lineart` em `LucasNekoo/script-desenho`:
histórico próprio, sem nenhum commit em comum com `main`/`developer`.

**Consequências.**
* Um só endereço para os dois projetos, mas históricos e dependências separados.
* **Nunca mesclar** em `main`/`developer`. O GitHub sugere abrir um PR ao
  receber o push; ignore, porque os históricos não têm relação.
* Clonar só esta branch: `git clone -b autodraw-lineart --single-branch ...`.
* A CI desta branch dispara em push para `autodraw-lineart` (o workflow vive
  dentro dela, não na `main`).

**Descartado.** Pasta dentro do AutoDraw (misturaria as dependências);
repositório novo no GitHub (possível no futuro: basta `git push` desta branch
como `main` de outro repositório, porque o histórico já é independente).

## D3. Copiar a definição da rede em vez de depender do Anime2Sketch

**Contexto.** O repositório original recebeu um commit suspeito que injeta um
`requests` não oficial no `requirements.txt` (veja [Segurança](seguranca.md)).

**Decisão.** Copiar só `UnetGenerator`, `UnetSkipConnectionBlock`, `Smooth`
e `Upsample` do commit `1c1a2ed`, sem mudar a arquitetura nem os nomes, com
atribuição e licença MIT.

**Consequências.** Nenhuma dependência do repositório original; a cópia é
pequena (~130 linhas) e coberta por testes que conferem os nomes dos
parâmetros contra os arquivos de pesos reais (32 e 62).

**Descartado.** Submódulo git ou `pip install git+...` do original: traria de
volta a exposição a commits futuros de lá.

## D4. Pesos fora do git, conferidos por SHA-256 e carregados com `weights_only`

**Contexto.** Os pesos têm 218 MB e 192 MB e são pickles do PyTorch, capazes
de executar código ao carregar.

**Decisão.** Registrar tamanho e SHA-256 de cada arquivo no código; conferir
antes de carregar; carregar com `weights_only=True`; baixar sob demanda
(`autodraw-lineart download`) para a pasta de dados do usuário.

**Consequências.** O repositório fica leve (menos de 1 MB); um arquivo
adulterado é recusado; a instalação tem um passo a mais (o download).

**Descartado.** Git LFS (custo e cota no GitHub, sem ganho de segurança);
embutir os pesos no pacote (tamanho).

## D5. Contrato JSON versionado com códigos de saída

**Decisão.** Uma linha JSON no stdout em toda chamada, inclusive erros de
argumento; `contract` versionado; códigos de saída distintos por tipo de erro;
mensagens em português prontas para a interface. Especificação em
[contrato.md](contrato.md).

**Consequências.** O AutoDraw trata erros sem interpretar texto livre; o
contrato pode ganhar campos sem quebrar clientes.

**Descartado.** Ler o texto do stderr (frágil) ou só o código de saída (sem
mensagem para o usuário).

## D6. A saída é uma imagem de linhas, não traços

**Decisão.** A ferramenta devolve um PNG de linhas; a conversão em traços
(limiar + linha central) fica no AutoDraw.

**Consequências.**
* O contrato não depende do modelo: dá para trocar o Anime2Sketch por outro
  extrator de line art sem mexer no AutoDraw.
* O traçado por linha central também serve para imagens que já têm line art,
  **sem IA**, e por isso pertence ao AutoDraw.
* No AutoDraw isso virou `autodraw/centerline.py` (modo `linhas`), que
  percorre o esqueleto como grafo, por caminhos de Euler. O exemplo
  [`linhas_para_tracos.py`](../examples/linhas_para_tracos.py) é a primeira
  versão, gulosa, mantida como referência simples.

**Descartado.** Devolver polilinhas em JSON: acoplaria a ferramenta às regras
de traçado do AutoDraw (tamanho mínimo, simplificação), que mudam com os sliders.

## D7. Metade dos núcleos, no máximo 4, por padrão

**Contexto.** O jogo roda na mesma máquina. De 4 para 6 threads a rede só cai
de 0,09 s para 0,07 s.

**Decisão.** `--threads` padrão = `max(1, min(4, núcleos // 2))`.

## D8. Python ≥ 3.10

**Contexto.** O projeto é novo e não precisa carregar o 3.9 como o AutoDraw
carrega. A CI passa com Python 3.10 e 3.13 (o pip escolhe a versão do PyTorch
compatível com cada um), e o desenvolvimento foi feito em 3.14.

**Decisão.** `requires-python >= 3.10`, sintaxe moderna de tipos (`X | None`).
O cliente de referência foi escrito para rodar também no Python 3.9 que o
AutoDraw ainda aceita (usa `from __future__ import annotations` e nada além da
biblioteca padrão), mas não foi testado nessa versão.

## D9. `default` como modelo padrão

**Decisão.** O modelo `default` é o padrão; o `improved` fica opcional.

**Motivo.** O `improved` custa 3–4× o tempo e 2,6× a memória e só melhora
fundos escuros, onde mesmo ele ficou pior que o Canny nos testes.
